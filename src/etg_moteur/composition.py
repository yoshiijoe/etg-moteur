"""Portefeuille complet : poids, indicateurs de risque, contrôles de règles, corrélations, remplacement d'une ligne.

Le simulateur MESURE le risque et la diversification. Il ne prévoit aucun cours et ne recommande aucun achat.
Les formules du classement du jeu ne sont pas publiées : tout ce qui est calculé ici est une estimation.

Convention : les rendements sont hebdomadaires (clôture du vendredi ajustée des dividendes), alignés sur les
mêmes semaines pour toutes les lignes. Un rendement absent vaut None. Le poids d'une ligne est sa part du
portefeuille total, cash compris : la somme des poids vaut 1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .univers import SERIES

# --- Règles (section 4 du cahier des charges) ---------------------------------------------------

LIMITE_LIGNE = 0.10
SEUIL_GROSSE_LIGNE = 0.05
LIMITE_GROSSES_LIGNES = 0.40
LIMITE_REFUGE = 0.08
LIMITE_SECTEUR = 0.15
MAX_ACTIONS_PAR_SECTEUR = 1
SCENARIO_MIN, SCENARIO_MAX = 0.25, 0.45
MARGE_SCENARIO = 0.02           # « attention » à moins de 2 points d'une borne
MARGE_RELATIVE = 0.10           # « attention » au-dessus de 90 % d'un plafond
PRIX_MINIMUM = 1.0              # penny stock : seuil indicatif, définition officielle non publiée
SUFFIXES_AUTORISES = (".PA", ".AS", ".BR", ".LS", ".MI", ".OL", ".IR")
SEMAINES_EX_ANTE = 180
HISTORIQUE_MINIMUM = 52
SEUIL_CORRELATION = 0.7
OBSERVATIONS_MINIMUM = 26       # en dessous, une estimation de risque n'a pas de sens

ESTIMATION = "estimation : formules et pondérations du jeu non publiées"
HHI_APPROXIMATION = "approximation : le jeu regarde à l'intérieur des ETF, ici un ETF compte comme une ligne"

# Types de lignes et sens de l'exposition aux actions
TYPES = {"action": 1.0, "etf_actions": 1.0, "etf_inverse": -1.0, "etf_obligations": 0.0, "etf_monetaire": 0.0, "cash": 0.0}
# Secteurs qui ne comptent ni dans le nombre de secteurs ni dans les plafonds par secteur
NON_SECTORIELS = {"", "Multi-secteurs", "Obligations", "Inverse", "Monétaire", "Cash"}

CONFORME, ATTENTION, HORS_REGLE, INFO = "conforme", "attention", "hors règle", "information"


class ErreurComposition(ValueError):
    """Données insuffisantes ou saisie impossible : le message est destiné à l'utilisateur."""


@dataclass
class Ligne:
    code: str
    nom: str
    poche: str                      # Moteur, Socle, Convictions, Cash
    type: str                       # clé de TYPES
    symbole: str | None
    isin: str | None
    secteur: str                    # "" = à définir
    scenario: str                   # "A", "B", "C" ou "" = à définir
    poids: float
    secteur_verifie: bool = False
    devise: str = "EUR"

    def en_dict(self) -> dict:
        return dict(code=self.code, nom=self.nom, poche=self.poche, type=self.type, symbole=self.symbole,
                    isin=self.isin, secteur=self.secteur, secteur_verifie=self.secteur_verifie,
                    scenario=self.scenario, poids=self.poids, devise=self.devise)


# --- Portefeuille de référence (page Stratégie du Notion, lue le 04/11/2026) --------------------

POIDS_MOTEUR = 0.32
POIDS_SOCLE_CONVICTION = 0.045
POIDS_CASH = 0.05

# code, nom, type, symbole Yahoo, ISIN, secteur, scénario (première lettre de la page Stratégie)
SOCLE = [
    ("500", "Amundi S&P 500", "etf_actions", "500.PA", "LU1681048804", "Multi-secteurs", "B"),
    ("AEEM", "Amundi MSCI Emerging Markets", "etf_actions", "AEEM.PA", "LU1681045370", "Multi-secteurs", "B"),
    ("EJAP", "BNP Paribas Easy MSCI Japan", "etf_actions", "EJAP.PA", "LU1291102447", "Multi-secteurs", "B"),
    ("EVOE", "BNP Paribas Easy Low Volatility Europe", "etf_actions", "EVOE.PA", "LU1377381717", "Multi-secteurs", "C"),
    ("MTA", "Amundi Euro Government Bond 1-3Y", "etf_obligations", "MTA.PA", "LU1650487413", "Obligations", "C"),
    ("SHC", "Amundi CAC 40 Daily (-1x) Inverse", "etf_inverse", "SHC.PA", "FR0010591362", "Inverse", "C"),
]
CONVICTIONS = [
    ("ENX", "Euronext", "ENX.PA", "Services financiers", "A"),
    ("GALP", "Galp", "GALP.LS", "Énergie", "A"),
    ("NN", "NN Group", "NN.AS", "Assurance", "A"),
    ("PRY", "Prysmian", "PRY.MI", "Câbles et équipements électriques", "B"),
    ("KRX", "Kingspan", "KRX.IR", "Matériaux de construction", "B"),
    ("LDO", "Leonardo", "LDO.MI", "Aérospatiale et défense", "A"),
    ("UCB", "UCB", "UCB.BR", "Santé", "C"),
    ("MOWI", "Mowi", "MOWI.OL", "Agroalimentaire", "C"),
]
# Secteur par défaut des ETF du moteur (« à vérifier »), ISIN connus, scénarios définis dans le Notion
SECTEUR_ETF_MOTEUR = {
    "Banques": "Banques", "Pétrole & gaz": "Énergie", "Défense": "Aérospatiale et défense", "Technologie": "Technologie",
    "Industrie": "Industrie", "Matières premières": "Matières premières", "Santé": "Santé", "Télécoms": "Télécoms",
    "Services publics": "Services publics", "Agroalimentaire": "Agroalimentaire",
    "Monétaire n°1": "Monétaire", "Monétaire n°2": "Monétaire",
}
ISIN_ETF_MOTEUR = {"Santé": "LU1834986900", "Technologie": "LU1834988518", "Pétrole & gaz": "LU1834988278",
                   "Agroalimentaire": "LU1834985845"}
SCENARIO_ETF_MOTEUR = {"Santé": "C", "Technologie": "B", "Pétrole & gaz": "A", "Agroalimentaire": "C"}
ETF_MOTEUR_PAR_DEFAUT = ["Santé", "Technologie", "Pétrole & gaz", "Agroalimentaire"]


def ligne_moteur(nom: str, poids: float) -> Ligne:
    """Ligne de la poche moteur pour un ETF de l'univers (univers.SERIES)."""
    for n, symbole, _, code in SERIES:
        if n == nom and symbole:
            monetaire = n.startswith("Monétaire")
            return Ligne(code=code, nom=nom, poche="Moteur", type="etf_monetaire" if monetaire else "etf_actions",
                         symbole=symbole, isin=ISIN_ETF_MOTEUR.get(nom), secteur=SECTEUR_ETF_MOTEUR[nom],
                         scenario=SCENARIO_ETF_MOTEUR.get(nom, ""), poids=poids)
    raise ErreurComposition(f"ETF du moteur inconnu : {nom}")


def portefeuille_cible(etf_moteur: list[str] | None = None, top: int = 4) -> list[Ligne]:
    """Poids cibles de la page Stratégie. `etf_moteur` : lignes du moteur (ETF retenus puis refuges), 32 % en tout."""
    noms = list(etf_moteur or ETF_MOTEUR_PAR_DEFAUT)
    lignes = [ligne_moteur(n, POIDS_MOTEUR / top) for n in noms]
    for code, nom, type_, symbole, isin, secteur, scenario in SOCLE:
        lignes.append(Ligne(code, nom, "Socle", type_, symbole, isin, secteur, scenario, POIDS_SOCLE_CONVICTION))
    for code, nom, symbole, secteur, scenario in CONVICTIONS:
        lignes.append(Ligne(code, nom, "Convictions", "action", symbole, None, secteur, scenario, POIDS_SOCLE_CONVICTION,
                            devise="NOK" if symbole.endswith(".OL") else "EUR"))
    cash = 1 - sum(l.poids for l in lignes)
    lignes.append(Ligne("CASH", "Cash", "Cash", "cash", None, None, "Cash", "C", cash))
    return lignes


# --- Poids ---------------------------------------------------------------------------------------

def poids_depuis_positions(lignes: list[Ligne], quantites: dict[str, float], cash: float, cours: dict[str, float]) -> list[Ligne]:
    """Poids actuels à partir du nombre de titres, du cash et des derniers cours (en euros)."""
    valeurs = {}
    for l in lignes:
        if l.type == "cash":
            continue
        q = quantites.get(l.code, 0) or 0
        if q < 0:
            raise ErreurComposition(f"Quantité négative pour {l.code}.")
        if q and l.code not in cours:
            raise ErreurComposition(f"Pas de cours pour {l.code} ({l.symbole}) : mettre les prix du portefeuille à jour.")
        valeurs[l.code] = q * cours.get(l.code, 0.0)
    if cash < 0:
        raise ErreurComposition("Le cash ne peut pas être négatif.")
    total = sum(valeurs.values()) + cash
    if total <= 0:
        raise ErreurComposition("Le portefeuille est vide : saisir au moins une quantité ou le cash.")
    sortie = []
    for l in lignes:
        if l.type == "cash":
            sortie.append(replace(l, poids=cash / total))
        else:
            sortie.append(replace(l, poids=valeurs[l.code] / total))
    return sortie


# --- Concentration, exposition, scénarios ------------------------------------------------------

def hhi(lignes: list[Ligne]) -> float:
    """Somme des carrés des poids (part du portefeuille total), cash exclu. Un ETF compte comme une ligne."""
    return sum(l.poids ** 2 for l in lignes if l.type != "cash")


def exposition_nette(lignes: list[Ligne]) -> float:
    """Actions et ETF actions moins l'ETF inverse (−1x), hors obligations, monétaire et cash."""
    return sum(l.poids * TYPES[l.type] for l in lignes)


def poids_scenarios(lignes: list[Ligne]) -> dict[str, float]:
    sortie = {"A": 0.0, "B": 0.0, "C": 0.0, "": 0.0}
    for l in lignes:
        sortie[l.scenario if l.scenario in ("A", "B", "C") else ""] += l.poids
    return sortie


def ligne_la_plus_lourde(lignes: list[Ligne]) -> Ligne | None:
    hors_cash = [l for l in lignes if l.type != "cash"]
    return max(hors_cash, key=lambda l: l.poids) if hors_cash else None


def somme_grosses_lignes(lignes: list[Ligne]) -> float:
    return sum(l.poids for l in lignes if l.type != "cash" and l.poids > SEUIL_GROSSE_LIGNE + 1e-12)


def poids_par_secteur(lignes: list[Ligne]) -> dict[str, float]:
    sortie: dict[str, float] = {}
    for l in lignes:
        if l.type != "cash" and l.secteur not in NON_SECTORIELS and l.poids > 0:
            sortie[l.secteur] = sortie.get(l.secteur, 0.0) + l.poids
    return sortie


def nombre_secteurs(lignes: list[Ligne]) -> int:
    return len(poids_par_secteur(lignes))


# --- Statistiques ------------------------------------------------------------------------------

def _moyenne(x: list) -> float:
    return sum(x) / len(x)


def _cov(a: list, b: list) -> float:
    ma, mb = _moyenne(a), _moyenne(b)
    return sum((u - ma) * (v - mb) for u, v in zip(a, b)) / (len(a) - 1)


def _ecart_type(x: list) -> float:
    return math.sqrt(_cov(x, x))


def rendements_hebdo(cloture: list) -> list:
    """Rendements d'une série de clôtures ; None si l'un des deux prix manque. Même longueur que la série."""
    return [None] + [c / p - 1 if c and p else None for p, c in zip(cloture, cloture[1:])]


def _semaines_communes(rend: dict[str, list], codes: list[str], fenetre: int, exige: list | None = None) -> list[int]:
    """Indices des semaines de la fenêtre (les `fenetre` dernières) où tous les codes ont un rendement."""
    if not codes:
        return []
    T = len(rend[codes[0]])
    return [t for t in range(max(0, T - fenetre), T)
            if all(rend[c][t] is not None for c in codes) and (exige is None or exige[t] is not None)]


@dataclass
class Risque:
    semaines: int
    vol_ex_ante: float
    diversification: float
    beta: float | None
    vols: dict[str, float]
    contributions: dict[str, float]


def risque(lignes: list[Ligne], rend: dict[str, list], ref: list | None = None, fenetre: int = SEMAINES_EX_ANTE,
           semaines: list[int] | None = None) -> Risque:
    """Volatilité ex-ante, diversification, bêta et contributions, poids actuels sur les rendements passés.

    `semaines` impose les semaines utilisées (pour comparer avant et après sur la même fenêtre).
    """
    investies = [l for l in lignes if l.type != "cash" and l.poids > 0]
    if not investies:
        raise ErreurComposition("Aucune ligne investie : impossible de mesurer le risque.")
    manquantes = [l.code for l in investies if l.code not in rend]
    if manquantes:
        raise ErreurComposition("Pas d'historique de prix pour : " + ", ".join(manquantes) + ".")
    codes = [l.code for l in investies]
    rows = semaines if semaines is not None else _semaines_communes(rend, codes, fenetre)
    if len(rows) < OBSERVATIONS_MINIMUM:
        raise ErreurComposition(f"Seulement {len(rows)} semaines communes à toutes les lignes : "
                                f"il en faut au moins {OBSERVATIONS_MINIMUM} pour estimer le risque.")
    w = {l.code: l.poids for l in investies}
    serie = {c: [rend[c][t] for t in rows] for c in codes}
    port = [sum(w[c] * serie[c][i] for c in codes) for i in range(len(rows))]
    vol = _ecart_type(port) * math.sqrt(52)
    vols = {c: _ecart_type(serie[c]) * math.sqrt(52) for c in codes}
    var_port = _cov(port, port)
    div = sum(w[c] * vols[c] for c in codes) / vol if vol else 0.0
    contributions = {c: (w[c] * _cov(serie[c], port) / var_port if var_port else 0.0) for c in codes}
    beta = None
    if ref is not None:
        r2 = [t for t in rows if ref[t] is not None]
        if len(r2) >= OBSERVATIONS_MINIMUM:
            p2 = [sum(w[c] * rend[c][t] for c in codes) for t in r2]
            x = [ref[t] for t in r2]
            beta = _cov(p2, x) / _cov(x, x)
    return Risque(len(rows), vol, div, beta, vols, contributions)


# --- Contrôles de règles -------------------------------------------------------------------------

def _plafond(valeur: float, limite: float) -> str:
    if valeur > limite + 1e-12:
        return HORS_REGLE
    return ATTENTION if valeur > limite * (1 - MARGE_RELATIVE) + 1e-12 else CONFORME


def _controle(identifiant: str, libelle: str, statut: str, valeur, seuil: str, detail: str = "") -> dict:
    return dict(id=identifiant, libelle=libelle, statut=statut, valeur=valeur, seuil=seuil, detail=detail)


def place_autorisee(symbole: str | None) -> bool | None:
    """True/False selon le suffixe Yahoo ; None si le symbole est inconnu."""
    if not symbole:
        return None
    return symbole.upper().endswith(SUFFIXES_AUTORISES)


def controles(lignes: list[Ligne], cours_eur: dict[str, float] | None = None) -> list[dict]:
    """Tous les contrôles de la section 4. `cours_eur` : dernier cours en euros par code (alerte penny)."""
    sortie = []
    lourde = ligne_la_plus_lourde(lignes)
    if lourde:
        sortie.append(_controle("ligne", "Poids de chaque ligne", _plafond(lourde.poids, LIMITE_LIGNE), lourde.poids,
                                "≤ 10 %", f"ligne la plus lourde : {lourde.code}"))
    grosses = somme_grosses_lignes(lignes)
    n_grosses = sum(1 for l in lignes if l.type != "cash" and l.poids > SEUIL_GROSSE_LIGNE + 1e-12)
    sortie.append(_controle("grosses", "Somme des lignes au-dessus de 5 %", _plafond(grosses, LIMITE_GROSSES_LIGNES),
                            grosses, "≤ 40 %", f"{n_grosses} ligne(s)"))
    refuges = [l for l in lignes if l.type == "etf_monetaire"]
    if refuges:
        pire = max(refuges, key=lambda l: l.poids)
        sortie.append(_controle("refuge", "Un refuge monétaire", _plafond(pire.poids, LIMITE_REFUGE), pire.poids,
                                "≤ 8 %", pire.code))
    else:
        sortie.append(_controle("refuge", "Un refuge monétaire", CONFORME, 0.0, "≤ 8 %", "aucun refuge détenu"))
    par_secteur = poids_par_secteur(lignes)
    if par_secteur:
        s, v = max(par_secteur.items(), key=lambda kv: kv[1])
        sortie.append(_controle("secteur", "Un secteur, ETF et action cumulés", _plafond(v, LIMITE_SECTEUR), v, "≤ 15 %",
                                f"secteur le plus lourd : {s}"))
    actions: dict[str, list[str]] = {}
    for l in lignes:
        if l.type == "action" and l.poids > 0 and l.secteur not in NON_SECTORIELS:
            actions.setdefault(l.secteur, []).append(l.code)
    exces = {s: c for s, c in actions.items() if len(c) > MAX_ACTIONS_PAR_SECTEUR}
    sortie.append(_controle("actions_secteur", "Actions par secteur", HORS_REGLE if exces else CONFORME,
                            max((len(c) for c in actions.values()), default=0), "≤ 1",
                            "; ".join(f"{s} : {', '.join(c)}" for s, c in exces.items())))
    a_definir = [l.code for l in lignes if l.type == "action" and l.poids > 0 and l.secteur in ("",)]
    if a_definir:
        sortie.append(_controle("secteurs_a_definir", "Secteurs à définir", ATTENTION, len(a_definir), "0",
                                "secteur non renseigné : " + ", ".join(a_definir)))
    scen = poids_scenarios(lignes)
    for k in ("A", "B", "C"):
        v = scen[k]
        if v < SCENARIO_MIN - 1e-12 or v > SCENARIO_MAX + 1e-12:
            statut = HORS_REGLE
        elif v < SCENARIO_MIN + MARGE_SCENARIO - 1e-12 or v > SCENARIO_MAX - MARGE_SCENARIO + 1e-12:
            statut = ATTENTION
        else:
            statut = CONFORME
        sortie.append(_controle(f"scenario_{k}", f"Poids du scénario {k}", statut, v, "entre 25 % et 45 %"))
    if scen[""] > 1e-12:
        sortie.append(_controle("scenario_a_definir", "Poids sans scénario défini", ATTENTION, scen[""], "0 %",
                                "lignes « à définir » : elles ne comptent dans aucun scénario"))
    hors_place = [l.code for l in lignes if l.type != "cash" and place_autorisee(l.symbole) is False]
    inconnus = [l.code for l in lignes if l.type != "cash" and place_autorisee(l.symbole) is None]
    sortie.append(_controle("places", "Places autorisées", HORS_REGLE if hors_place else (ATTENTION if inconnus else CONFORME),
                            len(hors_place), "Paris, Amsterdam, Bruxelles, Lisbonne, Milan, Oslo, Dublin",
                            ("hors liste : " + ", ".join(hors_place)) if hors_place else
                            (("symbole à renseigner : " + ", ".join(inconnus)) if inconnus else "")))
    if cours_eur is not None:
        pennies = [f"{l.code} ({cours_eur[l.code]:.2f} €)" for l in lignes
                   if l.type == "action" and l.code in cours_eur and cours_eur[l.code] < PRIX_MINIMUM]
        sortie.append(_controle("penny", "Penny stocks", ATTENTION if pennies else CONFORME, len(pennies),
                                "cours ≥ 1 € (seuil indicatif)", ", ".join(pennies)))
    total = sum(l.poids for l in lignes)
    sortie.append(_controle("total", "Total des poids", CONFORME if abs(total - 1) < 1e-6 else HORS_REGLE, total, "100 %"))
    return sortie


def pire_statut(liste: list[dict]) -> str:
    ordre = {CONFORME: 0, INFO: 0, ATTENTION: 1, HORS_REGLE: 2}
    return max((c["statut"] for c in liste), key=lambda s: ordre[s], default=CONFORME)


# --- Indicateurs -------------------------------------------------------------------------------

def indicateurs(lignes: list[Ligne], rend: dict[str, list], ref: list | None = None, fenetre: int = SEMAINES_EX_ANTE,
                semaines: list[int] | None = None, cours_eur: dict[str, float] | None = None) -> dict:
    """Indicateurs du portefeuille (section 5.2). Le risque est None si l'historique manque (raison dans `risque_erreur`)."""
    lourde = ligne_la_plus_lourde(lignes)
    scen = poids_scenarios(lignes)
    sortie = dict(
        total_poids=sum(l.poids for l in lignes),
        cash=sum(l.poids for l in lignes if l.type == "cash"),
        lignes=sum(1 for l in lignes if l.type != "cash" and l.poids > 0),
        hhi=hhi(lignes), hhi_note=HHI_APPROXIMATION,
        secteurs=nombre_secteurs(lignes), poids_par_secteur=poids_par_secteur(lignes),
        exposition_nette=exposition_nette(lignes),
        ligne_max=dict(code=lourde.code, poids=lourde.poids) if lourde else None,
        somme_grosses=somme_grosses_lignes(lignes),
        scenarios=scen,
        controles=controles(lignes, cours_eur),
        note=ESTIMATION, risque=None, risque_erreur=None,
    )
    sortie["statut"] = pire_statut(sortie["controles"])
    try:
        r = risque(lignes, rend, ref, fenetre, semaines)
        sortie["risque"] = dict(semaines=r.semaines, vol_ex_ante=r.vol_ex_ante, diversification=r.diversification,
                                beta=r.beta, vols=r.vols, contributions=r.contributions)
    except ErreurComposition as e:
        sortie["risque_erreur"] = str(e)
    return sortie


# --- Corrélations ------------------------------------------------------------------------------

def correlations(rend: dict[str, list], codes: list[str], fenetre: int = 52, seuil: float = SEUIL_CORRELATION) -> dict:
    """Matrice de corrélation des rendements hebdomadaires sur les `fenetre` dernières semaines (52 ou 180).

    Les lignes qui ont moins de 26 observations dans la fenêtre sont écartées (listées dans `exclus`).
    """
    if fenetre not in (52, 180):
        raise ErreurComposition("La fenêtre des corrélations est de 52 ou 180 semaines.")
    presentes = [c for c in codes if c in rend]
    exclus = [c for c in codes if c not in rend]
    gardees = []
    for c in presentes:
        T = len(rend[c])
        if sum(1 for t in range(max(0, T - fenetre), T) if rend[c][t] is not None) >= OBSERVATIONS_MINIMUM:
            gardees.append(c)
        else:
            exclus.append(c)
    rows = _semaines_communes(rend, gardees, fenetre)
    if len(gardees) < 2 or len(rows) < OBSERVATIONS_MINIMUM:
        raise ErreurComposition("Pas assez de semaines communes pour calculer des corrélations.")
    ecarts = {c: _ecart_type([rend[c][t] for t in rows]) for c in gardees}
    matrice = []
    for a in gardees:
        ligne = []
        for b in gardees:
            if a == b:
                ligne.append(1.0)
            else:
                d = ecarts[a] * ecarts[b]
                ligne.append(_cov([rend[a][t] for t in rows], [rend[b][t] for t in rows]) / d if d else 0.0)
        matrice.append(ligne)
    alertes = sorted(({"a": a, "b": gardees[j], "correlation": matrice[i][j]}
                      for i, a in enumerate(gardees) for j in range(i + 1, len(gardees)) if matrice[i][j] > seuil),
                     key=lambda p: -p["correlation"])
    return dict(codes=gardees, matrice=matrice, semaines=len(rows), fenetre=fenetre, seuil=seuil, alertes=alertes,
                exclus=exclus)


# --- « Et si je remplace… » -----------------------------------------------------------------------

def controles_candidat(symbole: str, existe: bool, semaines_historique: int, dernier_cours_eur: float | None) -> list[dict]:
    """Contrôles d'un symbole candidat : existence, place autorisée, historique d'au moins 52 semaines, cours d'au moins 1 €."""
    sortie = [_controle("existe", "Le symbole existe", CONFORME if existe else HORS_REGLE, existe, "oui")]
    if not existe:
        return sortie
    place = place_autorisee(symbole)
    suffixe = "." + symbole.upper().rsplit(".", 1)[-1] if "." in symbole else "aucun suffixe"
    sortie.append(_controle("place", "Place autorisée", CONFORME if place else HORS_REGLE, suffixe,
                            "Paris, Amsterdam, Bruxelles, Lisbonne, Milan, Oslo, Dublin"))
    sortie.append(_controle("historique", "Historique d'au moins 52 semaines",
                            CONFORME if semaines_historique >= HISTORIQUE_MINIMUM else HORS_REGLE, semaines_historique,
                            "≥ 52 semaines"))
    if dernier_cours_eur is not None:
        sortie.append(_controle("penny", "Cours d'au moins 1 €", CONFORME if dernier_cours_eur >= PRIX_MINIMUM else HORS_REGLE,
                                dernier_cours_eur, "≥ 1 € (seuil indicatif)"))
    return sortie


COLONNES_ECARTS = ["hhi", "secteurs", "exposition_nette", "vol_ex_ante", "diversification", "beta", "somme_grosses",
                   "ligne_max", "scenario_A", "scenario_B", "scenario_C"]


def _plat(ind: dict) -> dict:
    """Valeurs numériques comparables d'un jeu d'indicateurs."""
    r = ind["risque"] or {}
    return dict(hhi=ind["hhi"], secteurs=ind["secteurs"], exposition_nette=ind["exposition_nette"],
                vol_ex_ante=r.get("vol_ex_ante"), diversification=r.get("diversification"), beta=r.get("beta"),
                somme_grosses=ind["somme_grosses"], ligne_max=ind["ligne_max"]["poids"] if ind["ligne_max"] else None,
                scenario_A=ind["scenarios"]["A"], scenario_B=ind["scenarios"]["B"], scenario_C=ind["scenarios"]["C"])


def remplacer(lignes: list[Ligne], code_remplace: str, candidat: Ligne) -> list[Ligne]:
    """Portefeuille après remplacement : la différence de poids va au cash (ou en vient)."""
    ancienne = next((l for l in lignes if l.code == code_remplace), None)
    if ancienne is None or ancienne.type == "cash":
        raise ErreurComposition(f"Ligne à remplacer introuvable : {code_remplace}.")
    if any(l.code == candidat.code for l in lignes if l.code != code_remplace):
        raise ErreurComposition(f"Le candidat {candidat.code} est déjà dans le portefeuille.")
    if candidat.poids < 0:
        raise ErreurComposition("Le poids du candidat ne peut pas être négatif.")
    ecart = ancienne.poids - candidat.poids
    cash = next((l for l in lignes if l.type == "cash"), None)
    if cash is None or cash.poids + ecart < -1e-9:
        raise ErreurComposition("Le cash ne suffit pas à financer ce poids : réduire le poids du candidat.")
    sortie = []
    for l in lignes:
        if l.code == code_remplace:
            sortie.append(candidat)
        elif l.type == "cash":
            sortie.append(replace(l, poids=max(0.0, l.poids + ecart)))
        else:
            sortie.append(l)
    return sortie


def simuler_remplacement(lignes: list[Ligne], rend: dict[str, list], ref: list | None, code_remplace: str,
                         candidat: Ligne, rend_candidat: list, controles_du_candidat: list[dict],
                         fenetre: int = SEMAINES_EX_ANTE, cours_eur: dict[str, float] | None = None) -> dict:
    """Avant / après sur les mêmes semaines : indicateurs, volatilité du candidat, corrélation avec chaque ligne restante.

    Ne compare ni rendements ni performance : seulement le risque, la diversification et les règles.
    """
    apres = remplacer(lignes, code_remplace, candidat)
    rend2 = {**rend, candidat.code: rend_candidat}
    codes_avant = [l.code for l in lignes if l.type != "cash" and l.poids > 0]
    codes_apres = [l.code for l in apres if l.type != "cash" and l.poids > 0]
    rows = _semaines_communes(rend2, sorted(set(codes_avant) | set(codes_apres)), fenetre)
    if len(rows) < OBSERVATIONS_MINIMUM:
        raise ErreurComposition(f"Seulement {len(rows)} semaines communes entre le candidat et le portefeuille : "
                                f"il en faut au moins {OBSERVATIONS_MINIMUM}.")
    avant_i = indicateurs(lignes, rend2, ref, fenetre, rows, cours_eur)
    apres_i = indicateurs(apres, rend2, ref, fenetre, rows, cours_eur)
    a, b = _plat(avant_i), _plat(apres_i)
    ecarts = {k: (None if a[k] is None or b[k] is None else b[k] - a[k]) for k in COLONNES_ECARTS}
    restantes = [l.code for l in apres if l.type != "cash" and l.code != candidat.code and l.poids > 0]
    serie_c = [rend_candidat[t] for t in rows]
    corr = {}
    for c in restantes:
        s = [rend2[c][t] for t in rows]
        d = _ecart_type(serie_c) * _ecart_type(s)
        corr[c] = _cov(serie_c, s) / d if d else 0.0
    vol_c = _ecart_type(serie_c) * math.sqrt(52)
    statuts_avant = {c["id"]: c["statut"] for c in avant_i["controles"]}
    changements = [dict(id=c["id"], libelle=c["libelle"], avant=statuts_avant.get(c["id"]), apres=c["statut"])
                   for c in apres_i["controles"] if statuts_avant.get(c["id"]) != c["statut"]]
    return dict(
        remplace=code_remplace, candidat=candidat.en_dict(), semaines=len(rows),
        avant=avant_i, apres=apres_i, ecarts=ecarts, changements_de_statut=changements,
        candidat_vol=vol_c,
        candidat_correlations=sorted(({"code": c, "correlation": v} for c, v in corr.items()),
                                     key=lambda x: -x["correlation"]),
        alertes_correlation=[c for c, v in corr.items() if v > SEUIL_CORRELATION],
        controles_candidat=controles_du_candidat,
        note="Le simulateur compare le risque et la diversification. Il n'utilise aucun rendement passé ni prévision "
             "et ne recommande aucun achat. " + ESTIMATION,
    )
