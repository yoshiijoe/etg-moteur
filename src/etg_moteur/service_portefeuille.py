"""Service du simulateur : assemble positions, prix et composition pour l'API. Ne prévoit aucun cours."""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field, replace

from . import composition as comp
from . import prix, prix_portefeuille as pp, service, stockage
from .composition import ErreurComposition, Ligne
from .univers import ETF, MONETAIRES, SERIES

DEPART_PERF = dt.date(2026, 11, 2)  # ordres du 01/11, exécutés le 02/11/2026 à l'ouverture
FORMAT_SYMBOLE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,19}$")
SCENARIOS = ("", "A", "B", "C")
POCHES = ("Moteur", "Socle", "Convictions", "Cash", "Autre")
MAX_LIGNES = 40


class ErreurPortefeuille(ValueError):
    """Saisie invalide ou prix manquants : le message est destiné à l'utilisateur."""


# --- Saisie : validation et lecture / écriture des positions ---------------------------------------------------

def ligne_depuis_dict(d: dict) -> tuple[Ligne, float]:
    """Valide une ligne saisie. Renvoie la ligne (poids = poids cible saisi) et la quantité détenue."""
    code = str(d.get("code", "")).strip().upper()
    if not re.match(r"^[A-Z0-9][A-Z0-9_\-]{0,11}$", code):
        raise ErreurPortefeuille(f"Code invalide : « {d.get('code')} » (12 caractères au plus, lettres et chiffres).")
    type_ = d.get("type", "action")
    if type_ not in comp.TYPES:
        raise ErreurPortefeuille(f"{code} : type inconnu « {type_} ».")
    scenario = str(d.get("scenario", "") or "").strip().upper()
    if scenario not in SCENARIOS:
        raise ErreurPortefeuille(f"{code} : le scénario est A, B ou C (ou vide : à définir).")
    symbole = (d.get("symbole") or "").strip().upper() or None
    if type_ != "cash" and symbole is not None and not FORMAT_SYMBOLE.match(symbole):
        raise ErreurPortefeuille(f"{code} : symbole Yahoo invalide « {symbole} ».")
    isin = (d.get("isin") or "").strip().upper() or None
    if isin and not re.match(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", isin):
        raise ErreurPortefeuille(f"{code} : ISIN invalide « {isin} ».")
    for cle in ("quantite", "poids"):
        v = d.get(cle)
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0 or v != v):
            raise ErreurPortefeuille(f"{code} : {cle} invalide.")
    poids = float(d.get("poids") or 0.0)
    if poids > 1:
        raise ErreurPortefeuille(f"{code} : le poids cible est une fraction entre 0 et 1.")
    nom = str(d.get("nom") or code).strip()[:80]
    ligne = Ligne(code=code, nom=nom, poche=d.get("poche") if d.get("poche") in POCHES else "Autre", type=type_,
                  symbole=None if type_ == "cash" else symbole, isin=isin, secteur=str(d.get("secteur") or "").strip()[:60],
                  scenario=scenario, poids=poids, secteur_verifie=bool(d.get("secteur_verifie", False)),
                  devise=str(d.get("devise") or "EUR")[:3])
    return ligne, float(d.get("quantite") or 0.0)


def lignes_depuis_saisie(saisie: dict) -> tuple[list[Ligne], dict[str, float], float | None]:
    brutes = saisie.get("lignes") or []
    if not brutes or len(brutes) > MAX_LIGNES:
        raise ErreurPortefeuille(f"Le portefeuille doit contenir de 1 à {MAX_LIGNES} lignes.")
    lignes, quantites = [], {}
    for d in brutes:
        l, q = ligne_depuis_dict(d)
        if any(x.code == l.code for x in lignes):
            raise ErreurPortefeuille(f"Code en double : {l.code}.")
        lignes.append(l)
        quantites[l.code] = q
    if sum(1 for l in lignes if l.type == "cash") > 1:
        raise ErreurPortefeuille("Une seule ligne de cash est possible.")
    cash = saisie.get("cash")
    if cash is not None and (not isinstance(cash, (int, float)) or isinstance(cash, bool) or cash < 0 or cash != cash):
        raise ErreurPortefeuille("Le cash doit être un nombre positif ou nul.")
    return lignes, quantites, (float(cash) if cash is not None else None)


def saisie_en_dict(lignes: list[Ligne], quantites: dict[str, float], cash: float | None) -> dict:
    return dict(version=1, cash=cash, lignes=[
        dict(l.en_dict() | dict(poids=l.poids, quantite=quantites.get(l.code, 0.0)) ) for l in lignes])


def saisie_par_defaut() -> dict:
    cible = comp.portefeuille_cible()
    return saisie_en_dict(cible, {}, None)


def lire_positions(st) -> tuple[dict, dict] | None:
    trouve = stockage.lire_version(st, stockage.PREFIXE_POSITIONS, "json")
    if trouve is None:
        return None
    contenu, etat = trouve
    try:
        return json.loads(contenu), etat
    except ValueError:
        return None


def ecrire_positions(st, saisie: dict, maintenant: dt.datetime | None = None) -> dict:
    lignes, quantites, cash = lignes_depuis_saisie(saisie)
    contenu = json.dumps(saisie_en_dict(lignes, quantites, cash), ensure_ascii=False).encode("utf-8")
    return stockage.ecrire_version(st, stockage.PREFIXE_POSITIONS, "json", contenu, "application/json", "saisie",
                                   stockage.CONSERVER_POSITIONS, maintenant)


# --- Contexte : lignes, poids, rendements -----------------------------------------------------------------------

@dataclass
class Contexte:
    lignes: list[Ligne]
    quantites: dict[str, float]
    cash_eur: float | None
    mode: str                                  # "positions" ou "cible"
    dates: list[str]
    rend: dict[str, list]
    ref: list
    cours_eur: dict[str, float]
    recent: dict[str, dict]
    dernier_cours: dict[str, str]
    manquants: list[str] = field(default_factory=list)


def _series_moteur(texte_csv: str, dates: list[str]) -> tuple[dict[str, list], list]:
    """Clôtures hebdomadaires du CSV du moteur, par symbole Yahoo, alignées sur `dates`. Plus la série du STOXX 600."""
    d = service.charger(texte_csv, "10")
    index = {x.isoformat(): i for i, x in enumerate(d.dates)}
    pos = [index.get(x) for x in dates]

    def aligne(serie):
        return [None if i is None else serie[i] for i in pos]

    par_nom = {n: s for n, s, _, _ in SERIES}
    sortie = {}
    for i, n in enumerate(d.noms):
        sortie[par_nom[n]] = aligne(d.cloture[i])
    for k, n in enumerate(MONETAIRES):
        sortie[par_nom[n]] = aligne(d.monetaire_cloture[k])
    return sortie, aligne(d.reference_cloture)


def construire_contexte(texte_csv: str, doc_prix: dict, saisie: dict | None, mode_force: str | None = None) -> Contexte:
    saisie = saisie or saisie_par_defaut()
    lignes, quantites, cash = lignes_depuis_saisie(saisie)
    dates = doc_prix["dates"]
    moteur, ref_cl = _series_moteur(texte_csv, dates)
    cours, dernier_jour, manquants = {}, {}, []
    rend = {}
    for l in lignes:
        if l.type == "cash" or not l.symbole:
            continue
        serie = doc_prix["series"].get(l.symbole) or moteur.get(l.symbole)
        if serie is None:
            manquants.append(l.code)
        else:
            rend[l.code] = comp.rendements_hebdo(serie)
        dernier = doc_prix["dernier"].get(l.symbole)
        if dernier:
            cours[l.code] = dernier["cours_eur"]
            dernier_jour[l.code] = dernier["date"]
    positions = any(q > 0 for q in quantites.values()) or (cash or 0) > 0
    mode = "positions" if positions else "cible"
    if mode_force:
        mode = mode_force
    if mode == "positions":
        lignes = comp.poids_depuis_positions(lignes, quantites, cash or 0.0, cours)
    else:
        total = sum(l.poids for l in lignes)
        if abs(total - 1) > 1e-6:
            raise ErreurPortefeuille(f"Les poids cibles ne totalisent pas 100 % ({total:.1%}).")
    return Contexte(lignes, quantites, cash, mode, dates, rend, comp.rendements_hebdo(ref_cl), cours,
                    doc_prix["recent"], dernier_jour, manquants)


def performance_depuis(ctx: Contexte, depart: dt.date = DEPART_PERF) -> dict:
    """Performance du portefeuille réel depuis le départ (ouverture du jour de départ, dernier cours), titres constants."""
    if ctx.mode != "positions":
        return dict(disponible=False, raison="positions non saisies : poids cibles utilisés")
    jour = depart.isoformat()
    v0 = v1 = 0.0
    for l in ctx.lignes:
        q = ctx.quantites.get(l.code, 0.0)
        if l.type == "cash" or not q:
            continue
        barres = ctx.recent.get(l.symbole or "", {})
        if jour not in barres:
            return dict(disponible=False, raison=f"pas de cours d'ouverture au {depart:%d/%m/%Y} pour {l.code} "
                                                 f"({l.symbole}) : mettre les prix à jour")
        v0 += q * barres[jour][0]
        v1 += q * ctx.cours_eur[l.code]
    cash = ctx.cash_eur or 0.0
    if v0 + cash <= 0:
        return dict(disponible=False, raison="valeur de départ nulle")
    return dict(disponible=True, depuis=jour, performance=(v1 + cash) / (v0 + cash) - 1,
                valeur_depart=v0 + cash, valeur_actuelle=v1 + cash,
                note="performance passée du portefeuille réel, titres constants depuis l'ouverture du jour de départ : "
                     "information pour le classement, jamais un argument de choix")


# --- Réponses de l'API ---------------------------------------------------------------------------------------------

def vue_portefeuille(ctx: Contexte, etat_positions: dict | None, versions: list[dict], etat_prix: dict | None) -> dict:
    total = None
    if ctx.mode == "positions":
        total = sum(ctx.quantites.get(l.code, 0.0) * ctx.cours_eur.get(l.code, 0.0) for l in ctx.lignes if l.type != "cash") \
            + (ctx.cash_eur or 0.0)
    lignes = []
    for l in ctx.lignes:
        lignes.append(l.en_dict() | dict(quantite=ctx.quantites.get(l.code, 0.0), cours_eur=ctx.cours_eur.get(l.code),
                                         date_cours=ctx.dernier_cours.get(l.code), sans_prix=l.code in ctx.manquants))
    return dict(mode=ctx.mode, lignes=lignes, cash=ctx.cash_eur, valeur_totale=total,
                libelle_poids="poids actuels (derniers cours)" if ctx.mode == "positions" else "poids cibles",
                positions=etat_positions, versions=versions, prix_portefeuille=etat_prix,
                secteurs_a_verifier=[l.code for l in ctx.lignes if l.type != "cash" and not l.secteur_verifie and l.secteur],
                scenarios_a_definir=[l.code for l in ctx.lignes if l.type != "cash" and l.scenario == ""])


def _fenetre(f: int | None) -> int:
    f = f or comp.SEMAINES_EX_ANTE
    if not 26 <= f <= 520:
        raise ErreurPortefeuille("La fenêtre doit être comprise entre 26 et 520 semaines.")
    return f


def calculer_indicateurs(ctx: Contexte, fenetre: int | None = None) -> dict:
    ind = comp.indicateurs(ctx.lignes, ctx.rend, ctx.ref, _fenetre(fenetre), cours_eur=ctx.cours_eur)
    ind["mode"] = ctx.mode
    ind["libelle_poids"] = "poids actuels" if ctx.mode == "positions" else "poids cibles"
    perf = performance_depuis(ctx)
    if perf.get("disponible") and ind["risque"]:
        perf["performance_ajustee"] = perf["performance"] / ind["risque"]["vol_ex_ante"]
    ind["performance"] = perf
    ind["lignes_detail"] = [l.en_dict() for l in ctx.lignes]
    ind["sans_prix"] = ctx.manquants
    if ind["risque"]:
        ind["risque"]["contributions_liste"] = sorted(
            ({"code": c, "poids": next(l.poids for l in ctx.lignes if l.code == c), "vol": ind["risque"]["vols"][c],
              "contribution": v} for c, v in ind["risque"]["contributions"].items()), key=lambda x: -x["contribution"])
    return ind


def calculer_correlations(ctx: Contexte, fenetre: int = 52) -> dict:
    codes = [l.code for l in ctx.lignes if l.type != "cash" and l.symbole and l.poids > 0]
    try:
        return comp.correlations(ctx.rend, codes, fenetre)
    except ErreurComposition as e:
        raise ErreurPortefeuille(str(e))


def _code_candidat(symbole: str, pris: set[str]) -> str:
    base = re.sub(r"[^A-Z0-9]", "", symbole.split(".")[0].upper())[:10] or "CAND"
    code, k = base, 2
    while code in pris:
        code, k = f"{base}{k}", k + 1
    return code


def simuler(ctx: Contexte, code_remplace: str, candidats: list[dict], dernier: dt.date, fenetre: int | None = None,
            telecharger=None) -> dict:
    """Pour chaque candidat (3 au plus) : contrôles, puis avant / après. Une erreur sur un candidat n'arrête pas les autres."""
    if not 1 <= len(candidats) <= 3:
        raise ErreurPortefeuille("Comparer de 1 à 3 candidats.")
    ancienne = next((l for l in ctx.lignes if l.code == code_remplace), None)
    if ancienne is None or ancienne.type == "cash":
        raise ErreurPortefeuille(f"Ligne à remplacer introuvable : {code_remplace}.")
    fen = _fenetre(fenetre)
    telecharger = telecharger or pp.telecharger_candidat
    resultats = []
    pris = {l.code for l in ctx.lignes}
    for c in candidats:
        symbole = str(c.get("symbole", "")).strip().upper()
        if not FORMAT_SYMBOLE.match(symbole):
            resultats.append(dict(symbole=symbole, erreur="Symbole invalide."))
            continue
        try:
            tel = telecharger(symbole, dernier)
        except prix.ErreurYahoo as e:
            resultats.append(dict(symbole=symbole, erreur=str(e)))
            continue
        except pp.ErreurPrixPortefeuille as e:
            resultats.append(dict(symbole=symbole, erreur=str(e)))
            continue
        if not tel["existe"]:
            resultats.append(dict(symbole=symbole, controles_candidat=comp.controles_candidat(symbole, False, 0, None),
                                  erreur="Ce symbole n'existe pas sur Yahoo Finance."))
            continue
        controles = comp.controles_candidat(symbole, True, tel["semaines"], tel["dernier"]["cours_eur"])
        if tel["semaines"] < comp.HISTORIQUE_MINIMUM:
            resultats.append(dict(symbole=symbole, controles_candidat=controles,
                                  erreur=f"Historique insuffisant : {tel['semaines']} semaines, "
                                         f"{comp.HISTORIQUE_MINIMUM} semaines au moins sont nécessaires pour mesurer un risque."))
            continue
        type_ = c.get("type") or ancienne.type
        if type_ not in comp.TYPES or type_ == "cash":
            resultats.append(dict(symbole=symbole, erreur="Type de ligne invalide."))
            continue
        poids = c.get("poids")
        cand = Ligne(code=_code_candidat(symbole, pris), nom=str(c.get("nom") or symbole)[:80], poche=ancienne.poche, type=type_,
                     symbole=symbole, isin=None, secteur=str(c.get("secteur") or "").strip()[:60],
                     scenario=(c.get("scenario") if c.get("scenario") in SCENARIOS else ancienne.scenario),
                     poids=float(ancienne.poids if poids is None else poids), devise=tel["devise"])
        try:
            res = comp.simuler_remplacement(ctx.lignes, ctx.rend, ctx.ref, code_remplace, cand,
                                            comp.rendements_hebdo(tel["hebdo"]), controles, fen, ctx.cours_eur | {cand.code: tel["dernier"]["cours_eur"]})
        except ErreurComposition as e:
            resultats.append(dict(symbole=symbole, controles_candidat=controles, erreur=str(e)))
            continue
        res["symbole"] = symbole
        resultats.append(res)
    return dict(remplace=code_remplace, nom_remplace=ancienne.nom, poids_remplace=ancienne.poids, resultats=resultats)


# --- Poche moteur alignée sur la décision du mois -------------------------------------------------------------------

def aligner_moteur(saisie: dict, decision: dict) -> dict:
    """Remplace les lignes du moteur par celles de la décision (ETF retenus, puis refuges). Les autres lignes ne bougent pas.

    Les lignes déjà présentes gardent leurs quantités, secteurs et scénarios ; les nouvelles partent à zéro titre.
    """
    lignes, quantites, cash = lignes_depuis_saisie(saisie)
    top = max(1, sum(1 for l in decision["lignes"] if l["retenu"]) + decision["refuges"] + decision["cash"])
    noms = [l["etf"] for l in decision["lignes"] if l["retenu"]] + MONETAIRES[:decision["refuges"]]
    anciennes = {l.nom: l for l in lignes if l.poche == "Moteur"}
    moteur = []
    for n in noms:
        nouvelle = comp.ligne_moteur(n, comp.POIDS_MOTEUR / top)
        if n in anciennes:
            a = anciennes[n]
            nouvelle = replace(nouvelle, secteur=a.secteur, secteur_verifie=a.secteur_verifie, scenario=a.scenario,
                               isin=a.isin or nouvelle.isin)
        moteur.append(nouvelle)
    sortis = [l.code for l in lignes if l.poche == "Moteur" and l.nom not in noms]
    entres = [l.code for l in moteur if l.nom not in anciennes]
    autres = [l for l in lignes if l.poche != "Moteur"]
    nouvelles = moteur + autres
    cash_ligne = next((l for l in nouvelles if l.type == "cash"), None)
    if cash_ligne is not None:
        reste = 1 - sum(l.poids for l in nouvelles if l.type != "cash")
        nouvelles = [replace(l, poids=max(0.0, reste)) if l.type == "cash" else l for l in nouvelles]
    q = {k: v for k, v in quantites.items() if k in {l.code for l in nouvelles}}
    sortie = saisie_en_dict(nouvelles, q, cash)
    sortie["changements_moteur"] = dict(entres=entres, sortis=sortis, date_decision=decision["date"], apercu=decision["apercu"])
    return sortie


def symboles_supplementaires(saisie: dict | None) -> list[str]:
    """Symboles des positions enregistrées qui ne sont ni dans le portefeuille de référence ni dans le moteur."""
    if not saisie:
        return []
    connus = set(pp.SYMBOLES_PORTEFEUILLE) | set(pp.SYMBOLES_MOTEUR_RECENTS) | {s[1] for s in SERIES if s[1]}
    sortie = []
    for l in saisie.get("lignes", []):
        s = (l.get("symbole") or "").strip().upper()
        if s and s not in connus and FORMAT_SYMBOLE.match(s) and s not in sortie:
            sortie.append(s)
    return sortie[: MAX_LIGNES]
