#!/usr/bin/env python3
"""Compare un classeur de backtest enregistré par Excel et le moteur Python, semaine par semaine.

Usage : python scripts/verifier_excel.py classeur.xlsx [autre.xlsx ...]
"""
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from openpyxl import load_workbook
from etg_moteur.moteur import Donnees, Parametres, backtest

TOL = 1e-8


def jour(v):
    return v.date() if hasattr(v, "date") else v


def verifier(chemin):
    wb = load_workbook(chemin, data_only=True)
    pc, po, par, poi, bt, res = [wb[n] for n in ("Prix_cloture", "Prix_ouverture", "Parametres", "Poids", "Backtest", "Resultats")]
    L = range(6, 526)
    col = lambda s, j: [s.cell(r, j).value for r in L]
    d = Donnees([jour(pc.cell(r, 1).value) for r in L], [pc.cell(4, j).value for j in range(2, 12)],
                [col(pc, j) for j in range(2, 12)], [col(po, j) for j in range(2, 12)],
                [col(pc, 12), col(pc, 13)], [col(po, 12), col(po, 13)], col(pc, 14), col(po, 14))
    p = Parametres(court=par["B5"].value, long=par["B6"].value, utiliser_court=par["B7"].value == 1, top=par["B8"].value,
                   tampon=par["B9"].value, filtre=par["B10"].value == 1, nb_monetaires=par["B11"].value,
                   taux_sans_risque=par["B12"].value, semaines_ex_ante=par["B18"].value)
    print(os.path.basename(chemin), "|", p)
    if res["B9"].value is None:
        print("  ÉCHEC : pas de valeurs calculées, ouvrir et enregistrer dans Excel")
        return False
    r = backtest(d, p, jour(par["B15"].value), jour(par["B16"].value))
    ecarts = sum(abs((poi.cell(l, j + 2).value or 0) - r["poids"][t][j]) > TOL for t, l in enumerate(L) for j in range(12))
    print(f"  poids : {520 * 12} cases, {ecarts} écarts")
    F = [(bt.cell(l, 6).value, bt.cell(l, 11).value) for l in L if isinstance(bt.cell(l, 6).value, (int, float))]
    e1 = max(abs(a[0] - b) for a, b in zip(F, r["rendements"]))
    e2 = max(abs(a[1] - b) for a, b in zip(F, r["rendements_reference"]))
    print(f"  rendements : {len(F)} semaines, écart max {e1:.1e} (moteur), {e2:.1e} (référence)")
    ok = ecarts == 0 and len(F) == len(r["rendements"]) and e1 < TOL and e2 < TOL
    for nom, c, v in (("Perf cumulée", "B8", r["perf"]), ("Rendement/an", "B9", r["ann"]), ("Volatilité", "B10", r["vol"]),
                      ("Sharpe", "B11", r["sharpe"]), ("Perte max", "B12", r["perte_max"]), ("Rotation", "B13", r["rotation"]),
                      ("HHI", "B14", r["hhi"]), ("Bêta", "B15", r["beta"]), ("Corrélation", "B16", r["correlation"]),
                      ("Cash", "B17", r["cash"]), ("Monétaire", "B18", r["monetaire"]), ("Rééquilibrages", "B19", r["reequilibrages"]),
                      ("Réf. rendement/an", "C9", r["reference"]["ann"]), ("Réf. perte max", "C12", r["reference"]["perte_max"]),
                      ("Vol ex-ante", "B47", r["vol_ex_ante"]), ("Perf/vol ex-ante", "B48", r["perf_sur_vol_ex_ante"]),
                      ("Diversification", "B50", r["diversification"])):
        bon = abs(res[c].value - v) < TOL
        ok = ok and bon
        if not bon:
            print(f"  KO {nom}: Excel {res[c].value} Python {v}")
    print("  RÉSULTAT :", "IDENTIQUE" if ok else "ÉCARTS À EXAMINER")
    return ok


sys.exit(0 if all([verifier(p) for p in sys.argv[1:]]) else 1)
