"""Calculs du site : backtest, variantes, décision. Appelle le moteur sans en dupliquer la logique."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .application import decision, dernier_vendredi
from .donnees import lire_hebdo_texte
from .moteur import Donnees, Parametres, backtest
from . import tranches as _tranches
from .reference_egale import backtest_parts_egales, libelle as libelle_parts_egales
from .univers import ETF, MONETAIRES, REFERENCE

AVERTISSEMENTS = [
    "Les prix viennent de Yahoo Finance et n'ont pas été validés par l'équipe.",
    "La Défense n'a pas de données avant 07/2023.",
    "Avant leur lancement, les ETF sont prolongés par un fonds proche. Résultats passés, hors frais et fiscalité.",
]
DETENUS_DEFAUT = ["Santé", "Technologie", "Pétrole & gaz", "Agroalimentaire"]
DEBUT_DEFAUT = dt.date(2024, 1, 5)

# clé du moteur, libellé, format (pct ou num)
COLONNES_MESURES = [
    ("ann", "Rendement annualisé", "pct"),
    ("vol", "Volatilité", "pct"),
    ("sharpe", "Sharpe", "num"),
    ("perte_max", "Perte max", "pct"),
    ("rotation", "Rotation", "num"),
    ("hhi", "HHI", "num"),
    ("beta", "Bêta", "num"),
    ("vol_ex_ante", "Volatilité ex-ante", "pct"),
    ("diversification", "Ratio de diversification", "num"),
]
CLES_MESURES = ["n", "perf", "ann", "vol", "sharpe", "perte_max", "rotation", "hhi", "beta", "correlation", "cash",
                "monetaire", "reequilibrages", "vol_ex_ante", "perf_sur_vol_ex_ante", "diversification",
                "ex_ante_semaines"]


class ErreurRequete(ValueError):
    """Paramètres invalides ou données insuffisantes : le message est destiné à l'utilisateur."""


@dataclass
class Requete:
    debut: dt.date = DEBUT_DEFAUT
    fin: dt.date | None = None
    univers: str = "10"  # "10" ETF, ou "9" sans la Défense
    court: int = 13
    long: int = 26
    utiliser_court: bool = True
    top: int = 4
    tampon: int = 6
    filtre: bool = True
    detenus: list[str] = field(default_factory=lambda: list(DETENUS_DEFAUT))
    vendredi: dt.date | None = None

    def parametres(self) -> Parametres:
        return Parametres(court=self.court, long=self.long, utiliser_court=self.utiliser_court, top=self.top,
                          tampon=self.tampon, filtre=self.filtre)

    def valider(self) -> None:
        if self.univers not in ("9", "10"):
            raise ErreurRequete("Univers inconnu : choisir 10 ETF ou 9 sans la Défense.")
        if not 1 <= self.court <= 104 or not 2 <= self.long <= 104:
            raise ErreurRequete("Les périodes du signal doivent être comprises entre 1 et 104 semaines.")
        if self.utiliser_court and self.court >= self.long:
            raise ErreurRequete("La période courte doit être plus petite que la période longue.")
        maxi = int(self.univers)
        if not 1 <= self.top <= maxi:
            raise ErreurRequete(f"Le nombre de lignes retenues doit être compris entre 1 et {maxi}.")
        if not self.top <= self.tampon <= maxi:
            raise ErreurRequete(f"La zone tampon doit être comprise entre {self.top} et {maxi}.")
        if self.fin and self.debut >= self.fin:
            raise ErreurRequete("La date de début doit précéder la date de fin.")

    def en_dict(self) -> dict:
        return dict(debut=self.debut.isoformat(), fin=self.fin.isoformat() if self.fin else None, univers=self.univers,
                    court=self.court, long=self.long, utiliser_court=self.utiliser_court, top=self.top,
                    tampon=self.tampon, filtre=self.filtre, detenus=self.detenus,
                    vendredi=self.vendredi.isoformat() if self.vendredi else None)


def charger(texte_csv: str, univers: str = "10") -> Donnees:
    try:
        return lire_hebdo_texte(texte_csv, sans=() if univers == "10" else ("Défense",))
    except (KeyError, ValueError) as e:
        raise ErreurRequete(f"Le fichier de prix est illisible ({e}). Mettre les prix à jour ou importer un CSV valide.")


def derniere_ouverture(d: Donnees) -> int:
    """Dernière ligne dont toutes les ouvertures de lundi existent (limite du backtest)."""
    series = d.ouverture + d.monetaire_ouverture + [d.reference_ouverture]
    return max((t for t in range(len(d.dates)) if all(s[t] for s in series)), default=-1)


def derniere_cloture(d: Donnees) -> int:
    """Dernière ligne où tous les ETF ont une clôture (décision du mois)."""
    return max((t for t in range(len(d.dates)) if all(c[t] for c in d.cloture)), default=-1)


def etat_donnees(texte_csv: str) -> dict:
    """Résumé du CSV : dernier vendredi, nombre de semaines, dernier vendredi avec ouverture du lundi."""
    d = charger(texte_csv)
    t = derniere_cloture(d)
    o = derniere_ouverture(d)
    return dict(dernier_vendredi=d.dates[t].isoformat(), premier_vendredi=d.dates[0].isoformat(), semaines=len(d.dates),
                dernier_vendredi_backtest=d.dates[o].isoformat() if o >= 0 else None)


def _mesures(m: dict) -> dict:
    return {k: m[k] for k in CLES_MESURES if k in m}


def _valeurs(rendements: list, base: float = 100.0) -> list:
    v, sortie = base, [base]
    for r in rendements:
        v *= 1 + r
        sortie.append(v)
    return sortie


def _pertes(valeurs: list) -> list:
    sommet, sortie = 0.0, []
    for v in valeurs:
        sommet = max(sommet, v)
        sortie.append(v / sommet - 1)
    return sortie


def _lancer(d: Donnees, p: Parametres, debut: dt.date, fin: dt.date) -> dict:
    try:
        return backtest(d, p, debut, fin)
    except (TypeError, ZeroDivisionError, IndexError):
        raise ErreurRequete("Le backtest n'a pas pu être calculé sur cette période : certains prix manquent. "
                            "Choisir une date de début plus récente ou l'univers à 9 ETF.")


def variantes(req: Requete) -> list[tuple[str, Parametres]]:
    p = req.parametres()
    return [
        ("Base", p),
        ("6 mois seuls", Parametres(**{**p.__dict__, "utiliser_court": False})),
        ("Top 3", Parametres(**{**p.__dict__, "top": 3})),
        ("Sans filtre", Parametres(**{**p.__dict__, "filtre": False})),
        ("Sans zone tampon", Parametres(**{**p.__dict__, "tampon": p.top})),
    ]


def lancer_backtest(texte_csv: str, req: Requete, avec_variantes: bool = True) -> dict:
    req.valider()
    d = charger(texte_csv, req.univers)
    limite = derniere_ouverture(d)
    if limite < 0:
        raise ErreurRequete("Aucun prix d'ouverture disponible : mettre les prix à jour.")
    fin = min(req.fin or d.dates[limite], d.dates[limite])
    dates_periode = [x for x in d.dates if req.debut <= x <= fin]
    if len(dates_periode) < 10:
        raise ErreurRequete("La période choisie contient moins de 10 semaines de prix.")
    p = req.parametres()
    m = _lancer(d, p, req.debut, fin)

    try:
        egal = backtest_parts_egales(d, p, req.debut, fin)
    except (ValueError, TypeError, ZeroDivisionError):
        raise ErreurRequete("La référence à parts égales n'a pas pu être calculée sur cette période : certains prix manquent.")
    valeurs, ref = _valeurs(m["rendements"]), _valeurs(m["rendements_reference"])
    val_egal = _valeurs(egal["rendements"])
    t_debut = d.dates.index(dates_periode[0])
    colonnes = list(d.noms) + MONETAIRES
    resultat = dict(
        parametres=req.en_dict() | {"fin": fin.isoformat()},
        colonnes_mesures=[dict(cle=c, libelle=l, format=f) for c, l, f in COLONNES_MESURES],
        periode=dict(debut=dates_periode[0].isoformat(), fin=fin.isoformat(), semaines=len(m["rendements"])),
        moteur=_mesures(m),
        reference={**m["reference"], "nom": REFERENCE},
        series=dict(dates=[x.isoformat() for x in dates_periode], moteur=valeurs, reference=ref,
                    perte_moteur=_pertes(valeurs), perte_reference=_pertes(ref),
                    parts_egales=val_egal, perte_parts_egales=_pertes(val_egal)),
        parts_egales=dict(nom=libelle_parts_egales(len(d.noms)), **_mesures(egal)),
        poids=dict(colonnes=colonnes, dates=[x.isoformat() for x in dates_periode],
                   valeurs=[m["poids"][t_debut + i] for i in range(len(dates_periode))]),
    )
    if avec_variantes:
        lignes = []
        for nom, pv in variantes(req):
            mv = m if nom == "Base" else _lancer(d, pv, req.debut, fin)
            lignes.append(dict(nom=nom, mesures=_mesures(mv)))
        lignes.append(dict(nom=libelle_parts_egales(len(d.noms)), mesures=_mesures(egal)))
        lignes.append(dict(nom=REFERENCE, mesures=dict(m["reference"])))
        resultat["variantes"] = lignes
    return resultat


def lancer_tranches(texte_csv: str, req: Requete) -> dict:
    """Backtest par semestres (horizon du jeu) sur tout l'historique, avec les paramètres du backtest.

    La période début/fin du backtest ne s'applique pas : on prend toutes les tranches disponibles.
    """
    req.valider()
    d = charger(texte_csv, req.univers)
    try:
        lignes = _tranches.toutes(d, req.parametres())
        synthese = _tranches.synthese(lignes)
        resume_variantes = [dict(nom=nom, synthese=_tranches.synthese(_tranches.toutes(d, pv)))
                            for nom, pv in variantes(req)]
    except (ValueError, TypeError, ZeroDivisionError, IndexError) as e:
        raise ErreurRequete(f"Les tranches de 6 mois n'ont pas pu être calculées : {e}")
    sortie = []
    for l in lignes:
        date_depart, etf_depart, refuge_depart = l["choix"][0]
        sortie.append(dict(tranche=l["tranche"], debut=l["debut"].isoformat(), fin=l["fin"].isoformat(),
                           semaines=l["semaines"], complete=l["semaines"] >= 24, moteur=l["moteur"], stoxx=l["stoxx"],
                           parts_egales=l["parts_egales"], ecart=l["ecart"], perte_max=l["perte_max"],
                           perte_max_stoxx=l["perte_max_stoxx"], depart=etf_depart, refuge_depart=refuge_depart,
                           decisions=len(l["choix"])))
    return dict(parametres=req.en_dict(), lignes=sortie, synthese=synthese, variantes=resume_variantes,
                reference=REFERENCE, univers=list(d.noms),
                note=("Chaque semestre repart d'un portefeuille vide, achète le top dès la première semaine, "
                      "puis suit la règle chaque fin de mois. Sans frais. La Défense n'entre qu'une fois ses prix "
                      "disponibles (2024)."))


def libelle_periode(semaines: int) -> str:
    return {13: "3 mois", 26: "6 mois"}.get(semaines, f"{semaines} sem.")


def lancer_decision(texte_csv: str, req: Requete) -> dict:
    req.valider()
    d = charger(texte_csv, req.univers)
    t_max = derniere_cloture(d)
    if t_max < 0:
        raise ErreurRequete("Aucune clôture complète disponible : mettre les prix à jour.")
    if req.vendredi:
        if req.vendredi not in d.dates:
            raise ErreurRequete(f"Pas de cours pour le vendredi {req.vendredi:%d/%m/%Y}. "
                                f"Dernier disponible : {d.dates[t_max]:%d/%m/%Y}.")
        t = d.dates.index(req.vendredi)
        if not all(c[t] for c in d.cloture):
            raise ErreurRequete(f"Des clôtures manquent au {req.vendredi:%d/%m/%Y}.")
    else:
        t = t_max
    p = req.parametres()
    try:
        res = decision(d, p, t, set(req.detenus))
    except ValueError as e:
        raise ErreurRequete(str(e))
    jour = res["date"]
    officiel = dernier_vendredi(jour.year, jour.month)
    return dict(
        date=jour.isoformat(), date_officielle=officiel.isoformat(), apercu=jour != officiel,
        derniere_date=d.dates[t_max].isoformat(), detenus=sorted(req.detenus), etf=list(d.noms),
        libelle_court=libelle_periode(p.court), libelle_long=libelle_periode(p.long),
        lignes=[dict(rang=l["rang"], etf=l["etf"], court=l["court"], long=l["long"], signal=l["signal"],
                     detenu=l["detenu"], retenu=l["retenu"], action=l["action"]) for l in res["lignes"]],
        refuges=res["refuges"], cash=res["cash"], poids=res["poids"],
    )


__all__ = ["lancer_tranches", "AVERTISSEMENTS", "DETENUS_DEFAUT", "ETF", "ErreurRequete", "Requete", "charger", "etat_donnees",
           "lancer_backtest", "lancer_decision", "variantes"]
