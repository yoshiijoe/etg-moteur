#!/usr/bin/env python3
"""Construit data/prix_msci_hebdo.csv à partir des indices MSCI Europe (dividendes nets réinvestis, en euros).

Sert à remonter les tranches de 6 mois avant 2008. Même format que data/prix_hebdo.csv, pour être lu par
etg_moteur.donnees.lire_hebdo. Les fichiers bruts (data/msci/*.json, data/msci/eonia.csv, data/msci/estr.csv)
viennent du service public de graphiques de msci.com et de l'API de la BCE ; usage personnel, jamais dans git.

- Clôture du vendredi : dernière valeur de la semaine.
- « Ouverture du lundi » : les indices n'ont pas d'ouverture ; on prend la clôture du premier jour de bourse
  suivant le vendredi (exécution un peu plus tardive que sur les ETF, sans regard vers le futur).
- Monétaire : capitalisation quotidienne de l'EONIA (1999-2021) puis de l'€STR, base exact/360.
- Référence : MSCI Europe (dans la colonne « STOXX Europe 600 », pour garder le format du moteur).
"""
import csv, datetime as dt, json, pathlib, sys
RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
from etg_moteur.univers import SERIES

DOSSIER = RACINE / "data" / "msci"
CODES = {"Banques": "106668", "Pétrole & gaz": "106643", "Défense": "763669", "Technologie": "106650",
         "Industrie": "106645", "Matières premières": "106644", "Santé": "106648", "Télécoms": "106651",
         "Services publics": "106652", "Agroalimentaire": "106647", "STOXX Europe 600": "990500"}
NOMS_MSCI = {"106668": "MSCI Europe Banks", "106643": "MSCI Europe Energy", "763669": "MSCI Europe Aerospace & Defense Capped",
             "106650": "MSCI Europe Information Technology", "106645": "MSCI Europe Industrials",
             "106644": "MSCI Europe Materials", "106648": "MSCI Europe Health Care",
             "106651": "MSCI Europe Communication Services", "106652": "MSCI Europe Utilities",
             "106647": "MSCI Europe Consumer Staples", "990500": "MSCI Europe"}
JOUR = dt.timedelta(days=1)


def niveaux(code):
    j = json.loads((DOSSIER / f"{code}.json").read_text())
    return {dt.datetime.strptime(str(x["calc_date"]), "%Y%m%d").date(): x["level_eod"] for x in j["indexes"]["INDEX_LEVELS"]}


def taux_bce():
    taux = {}
    for fichier, fin in (("eonia.csv", dt.date(2021, 12, 31)), ("estr.csv", None)):
        for l in csv.DictReader(open(DOSSIER / fichier, encoding="utf-8")):
            d = dt.date.fromisoformat(l["TIME_PERIOD"])
            if fichier == "estr.csv" and d <= dt.date(2021, 12, 31):
                continue
            if l["OBS_VALUE"]:
                taux[d] = float(l["OBS_VALUE"])
    return taux


def monetaire(debut, fin):
    taux, valeur, d, r, sortie = taux_bce(), 100.0, debut, None, {}
    while d <= fin:
        r = taux.get(d, r)
        if r is not None:
            valeur *= 1 + r / 100 / 360
        if d.weekday() < 5:
            sortie[d] = valeur
        d += JOUR
    return sortie


series = {nom: niveaux(code) for nom, code in CODES.items()}
premier = min(min(s) for s in series.values())
dernier = max(max(s) for s in series.values())
mon = monetaire(premier, dernier)
for nom in ("Monétaire n°1", "Monétaire n°2"):
    series[nom] = mon


def vendredi(D, F):
    return next((D[F - k * JOUR] for k in range(5) if F - k * JOUR in D), None)


def lundi(D, F):
    return next((D[F + k * JOUR] for k in range(3, 7) if F + k * JOUR in D), None)


F = premier + dt.timedelta(days=(4 - premier.weekday()) % 7)
semaines = []
while F <= dernier:
    semaines.append(F)
    F += dt.timedelta(days=7)
sortie = RACINE / "data" / "prix_msci_hebdo.csv"
with open(sortie, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["vendredi"] + [f"{s[0]} {x}" for s in SERIES for x in ("cloture", "ouverture_lundi", "origine")])
    for F in semaines:
        ligne = [F.isoformat()]
        for s in SERIES:
            D = series[s[0]]
            c, o = vendredi(D, F), lundi(D, F)
            if F >= max(D) and o is None:
                o = None
            ligne += [round(c, 6) if c else "", round(o, 6) if o else "", "msci"]
        w.writerow(ligne)
print(sortie, semaines[0], "→", semaines[-1], len(semaines), "semaines")
for nom, code in CODES.items():
    print(f"  {nom:20} {NOMS_MSCI[code]:40} depuis {min(series[nom])}")
