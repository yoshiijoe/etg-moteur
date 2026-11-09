"""Prix des lignes du portefeuille complet (socle et convictions), sans toucher au CSV du moteur.

Pour chaque symbole : clôtures du vendredi ajustées des dividendes, converties en euros (Mowi en NOK via EURNOK=X),
sur la même grille de vendredis que le CSV du moteur, plus les derniers cours quotidiens. Les ETF du moteur gardent
leurs prix hebdomadaires dans le CSV du moteur : ici on n'ajoute que leurs derniers cours quotidiens.
"""
from __future__ import annotations

import datetime as dt
import json
import time

from . import prix
from .composition import CONVICTIONS, SOCLE
from .univers import ETF, MONETAIRES, SERIES

FX_NOK = "EURNOK=X"
SYMBOLES_PORTEFEUILLE = sorted({s[3] for s in SOCLE} | {s[2] for s in CONVICTIONS}) + [FX_NOK]
# ETF du moteur : derniers cours quotidiens seulement (leur historique est dans le CSV du moteur)
SYMBOLES_MOTEUR_RECENTS = sorted(s[1] for s in SERIES if s[0] in ETF + MONETAIRES and s[1])
SEMAINES_CONSERVEES = 400
DEBUT_RECENT = dt.date(2026, 10, 26)  # derniers cours quotidiens depuis cette date (ordres du 02/11/2026 compris)
DEVISES_GEREES = ("EUR", "NOK")


class ErreurPrixPortefeuille(ValueError):
    """Symbole illisible ou devise non gérée : le message est destiné à l'utilisateur."""


def devise(corps: bytes | str) -> str:
    try:
        return json.loads(corps)["chart"]["result"][0]["meta"]["currency"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ErreurPrixPortefeuille("Réponse de Yahoo illisible (devise introuvable).")


def grille(dernier: dt.date, semaines: int = SEMAINES_CONSERVEES) -> list[dt.date]:
    """Les derniers vendredis, sur la même grille que le CSV du moteur (4 janvier 2008 + 7 jours × k)."""
    sortie, f = [], prix.PREMIER_VENDREDI
    while f <= dernier:
        sortie.append(f)
        f += dt.timedelta(days=7)
    return sortie[-semaines:]


def _taux(fx: dict, jour: dt.date) -> float | None:
    """Cours EURNOK le jour donné, ou le dernier connu dans les 4 jours qui précèdent."""
    for k in range(5):
        d = jour - k * prix.JOUR
        if d in fx:
            return fx[d][1]
    return None


def _hebdo_euros(cours: dict, monnaie: str, fx: dict | None, vendredis: list[dt.date]) -> list:
    sortie = []
    for f in vendredis:
        j = prix.vendredi(cours, f)
        if j is None or f < min(cours):
            sortie.append(None)
            continue
        c = cours[j][1]
        if monnaie == "NOK":
            t = _taux(fx or {}, j)
            c = c / t if t else None
        sortie.append(round(c, 4) if c else None)
    return sortie


def _quotidiens_euros(cours: dict, monnaie: str, fx: dict | None, depuis: dt.date) -> dict:
    sortie = {}
    for jour in sorted(d for d in cours if d >= depuis):
        o, c = cours[jour]
        if monnaie == "NOK":
            t = _taux(fx or {}, jour)
            if not t:
                continue
            o, c = o / t, c / t
        sortie[jour.isoformat()] = [round(o, 4), round(c, 4)]
    return sortie


def resume_symbole(corps: bytes | str, vendredis: list[dt.date], fx: dict | None = None) -> dict:
    """Série hebdomadaire en euros, dernier cours et nombre de semaines d'historique d'un symbole."""
    monnaie = devise(corps)
    if monnaie not in DEVISES_GEREES:
        raise ErreurPrixPortefeuille(f"Devise {monnaie} non gérée (seuls l'euro et la couronne norvégienne le sont).")
    cours = prix.lire_brut(corps)
    if not cours:
        raise ErreurPrixPortefeuille("Aucun cours exploitable.")
    hebdo = _hebdo_euros(cours, monnaie, fx, vendredis)
    dernier_jour = max(cours)
    quotidien = _quotidiens_euros(cours, monnaie, fx, dernier_jour)
    return dict(hebdo=hebdo, devise=monnaie, semaines=sum(1 for v in hebdo if v is not None),
                recent=_quotidiens_euros(cours, monnaie, fx, DEBUT_RECENT),
                dernier=dict(date=dernier_jour.isoformat(), cours_eur=quotidien[dernier_jour.isoformat()][1]
                             if quotidien else None, cours_local=round(cours[dernier_jour][1], 4)))


def construire(bruts: dict, dernier: dt.date, maintenant: dt.datetime | None = None,
               semaines: int = SEMAINES_CONSERVEES, depuis: dt.date = DEBUT_RECENT) -> dict:
    """Document JSON des prix du portefeuille. Lève ErreurPrixPortefeuille si un symbole manque ou est illisible."""
    maintenant = maintenant or dt.datetime.now(dt.UTC)
    manquants = [s for s in SYMBOLES_PORTEFEUILLE + SYMBOLES_MOTEUR_RECENTS if s not in bruts]
    if manquants:
        raise ErreurPrixPortefeuille("Cours manquants pour : " + ", ".join(manquants) + ".")
    vendredis = grille(dernier, semaines)
    fx = prix.lire_brut(bruts[FX_NOK])
    series, derniers, recents = {}, {}, {}
    for s in SYMBOLES_PORTEFEUILLE:
        if s == FX_NOK:
            continue
        r = resume_symbole(bruts[s], vendredis, fx)
        series[s] = r["hebdo"]
        derniers[s] = dict(r["dernier"], devise=r["devise"])
        monnaie = r["devise"]
        recents[s] = _quotidiens_euros(prix.lire_brut(bruts[s]), monnaie, fx, depuis)
    for s in SYMBOLES_MOTEUR_RECENTS:
        cours = prix.lire_brut(bruts[s])
        monnaie = devise(bruts[s])
        if monnaie != "EUR":
            raise ErreurPrixPortefeuille(f"{s} : devise {monnaie} inattendue pour un ETF du moteur.")
        recents[s] = _quotidiens_euros(cours, monnaie, None, depuis)
        jour = max(cours)
        derniers[s] = dict(date=jour.isoformat(), cours_eur=recents[s][jour.isoformat()][1],
                           cours_local=round(cours[jour][1], 4), devise=monnaie)
    return dict(genere=maintenant.astimezone(dt.UTC).isoformat(timespec="seconds"), dates=[d.isoformat() for d in vendredis],
                series=series, dernier=derniers, recent=recents)


def en_texte(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def lire(texte: str | bytes) -> dict:
    try:
        d = json.loads(texte)
        d["dates"], d["series"], d["dernier"], d["recent"]
        return d
    except (ValueError, KeyError, TypeError):
        raise ErreurPrixPortefeuille("Les prix du portefeuille sont illisibles : mettre les prix à jour.")


def symbole_a_telecharger(symbole: str) -> tuple[str, ...]:
    """Symboles à télécharger pour un candidat : lui-même, et EURNOK=X s'il est coté en couronnes (Oslo)."""
    return (symbole, FX_NOK) if symbole.upper().endswith(".OL") else (symbole,)


def telecharger_candidat(symbole: str, dernier: dt.date, pause: float = 0.0) -> dict:
    """Télécharge un symbole candidat sur Yahoo. Renvoie existe, série hebdomadaire en euros, dernier cours en euros.

    `existe` est faux quand Yahoo répond « introuvable » (404) ; les autres erreurs (blocage, réseau) sont propagées.
    """
    try:
        corps = prix.telecharger_symbole(symbole, essais=2, attente_429=5, delai=20)
    except prix.ErreurYahoo as e:
        if e.code in (404, 400):
            return dict(existe=False)
        raise
    fx = None
    if symbole.upper().endswith(".OL"):
        time.sleep(pause)
        fx = prix.lire_brut(prix.telecharger_symbole(FX_NOK, essais=2, attente_429=5, delai=20))
    r = resume_symbole(corps, grille(dernier), fx)
    return dict(existe=True, **r)
