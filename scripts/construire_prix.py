#!/usr/bin/env python3
"""Construit data/prix_hebdo.csv : clôture du vendredi et ouverture du lundi, dividendes réinvestis.

Si un cours manque : dernier cours de la semaine (vendredi), premier cours suivant (lundi).
Avant le premier cours d'un ETF, on raccorde le fonds proche indiqué dans univers.py.
"""
import csv, datetime as dt, json, pathlib, sys
RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
from etg_moteur.univers import SERIES

JOUR = dt.timedelta(days=1)
DERNIER = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None


def lire(s):
    r = json.loads((RACINE / "data" / "brut" / (s.replace("^", "_") + ".json")).read_text())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    aj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    sortie = {}
    for i, x in enumerate(r["timestamp"]):
        if q["close"][i] is None or q["open"][i] is None:
            continue
        d = dt.datetime.fromtimestamp(x, dt.UTC).date()
        facteur = aj[i] / q["close"][i] if aj[i] else 1
        ouv = q["open"][i] or q["close"][i]  # Yahoo donne parfois une ouverture à 0
        sortie[d] = (ouv * facteur, aj[i])
    return sortie


def vendredi(D, F):
    return next((F - k * JOUR for k in range(5) if F - k * JOUR in D), None)


def lundi(D, F):
    return next((F + k * JOUR for k in range(3, 7) if F + k * JOUR in D), None)


cours = {s: lire(s) for ligne in SERIES for s in ligne[1:3] if s}
fin = DERNIER
if fin is None:
    derniere = max(max(c) for c in cours.values())
    fin = derniere - dt.timedelta(days=(derniere.weekday() - 4) % 7)
    if lundi(cours[SERIES[0][1]], fin) is None:
        fin -= dt.timedelta(days=7)
semaines, F = [], dt.date(2008, 1, 4)
while F <= fin:
    semaines.append(F)
    F += dt.timedelta(days=7)
table = {}
for nom, etf, proche, _ in SERIES:
    E, P = cours.get(etf, {}), cours[proche]
    k = 1.0
    if E:
        d0 = min(E)
        while d0 not in P:
            d0 += JOUR
        k = E[d0][1] / P[d0][1]
    col = {}
    for F in semaines:
        c = o = oc = oo = None
        if E and F >= min(E):
            a, b = vendredi(E, F), lundi(E, F)
            if a: c, oc = E[a][1], "etf"
            if b: o, oo = E[b][0], "etf"
        a, b = vendredi(P, F), lundi(P, F)
        if c is None and a: c, oc = P[a][1] * k, "pxy"
        if o is None and b: o, oo = P[b][0] * k, "pxy"
        col[F] = (c, o, oc if oc == oo else f"{oc}/{oo}")
    table[nom] = col
sortie = RACINE / "data" / "prix_hebdo.csv"
with open(sortie, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["vendredi"] + [f"{n[0]} {x}" for n in SERIES for x in ("cloture", "ouverture_lundi", "origine")])
    for F in semaines:
        l = [F.isoformat()]
        for n in SERIES:
            c, o, g = table[n[0]][F]
            l += [round(c, 4) if c else "", round(o, 4) if o else "", g]
        w.writerow(l)
print(sortie, semaines[0], semaines[-1], len(semaines), "semaines")
