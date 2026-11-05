#!/usr/bin/env python3
"""Lance variantes, simulation réaliste, sensibilité, hors échantillon et bootstrap.

Résultats dans resultats/rapport.json. Tout chiffre dépend des prix de data/prix_hebdo.csv.
"""
import datetime as dt, json, pathlib, statistics as st, sys
RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
from etg_moteur.donnees import lire_hebdo
from etg_moteur.moteur import Parametres, backtest, mesures
from etg_moteur.portefeuille import simuler
from etg_moteur import robustesse as rb

D = dt.date
FICHIER = RACINE / "data" / "prix_hebdo.csv"
BASE = Parametres()
FIN = D(2026, 10, 30)
d10 = lire_hebdo(FICHIER)
d9 = lire_hebdo(FICHIER, sans=("Défense",))
VARIANTES = {"Base": BASE, "6 mois seuls": Parametres(utiliser_court=False), "Top 3": Parametres(top=3),
             "Sans filtre": Parametres(filtre=False), "Sans zone tampon": Parametres(tampon=4)}
rapport = {}


def court(m):
    return {k: m[k] for k in ("n", "perf", "ann", "vol", "sharpe", "perte_max") if k in m}


# 1. Variantes
for nom, d, debut in (("10 ETF 2024-2026", d10, D(2024, 1, 5)), ("9 secteurs 2008-2026", d9, D(2008, 7, 4))):
    bloc = {}
    for v, p in VARIANTES.items():
        r = backtest(d, p, debut, FIN)
        bloc[v] = {**court(r), "rotation": r["rotation"], "monetaire": r["monetaire"]}
    bloc["STOXX Europe 600"] = court(backtest(d, BASE, debut, FIN)["reference"])
    rapport["variantes " + nom] = bloc

# 2. Simulation réaliste
for nom, d, debut in (("10 ETF 2024-2026", d10, D(2024, 1, 5)), ("9 secteurs 2008-2026", d9, D(2008, 7, 4))):
    bloc = {"poche, poids remis à égalité chaque semaine (Excel)": court(backtest(d, BASE, debut, FIN))}
    for lib, mm in (("poche avec dérive, sans mi-mois", False), ("poche avec dérive et mi-mois", True)):
        r = simuler(d, BASE, debut, FIN, mi_mois=mm)
        bloc[lib] = {**court(r), **{k: r[k] for k in ("coupes_mi_mois", "poids_max_ligne", "semaines_au_dessus_9", "semaines_au_dessus_10", "grosses_lignes_max", "semaines_au_dessus_40", "semaines")},
                     "portefeuille_approché": court(r["portefeuille"])}
    rapport["réaliste " + nom] = bloc

# 3. Sensibilité
fen = D(2009, 1, 2)
g9 = rb.calculer_grille(d9, fen, FIN)
reference9 = g9[BASE]["reference"]


def resume_grille(g, ref):
    sh = sorted(m["sharpe"] for m in g.values())
    an = sorted(m["ann"] for m in g.values())
    pm = sorted(m["perte_max"] for m in g.values())
    def marge(cle):
        groupes = {}
        for p, m in g.items():
            groupes.setdefault(cle(p), []).append(m["sharpe"])
        return {str(k): round(st.mean(v), 3) for k, v in sorted(groupes.items(), key=lambda x: str(x[0]))}
    b = g[BASE]
    return dict(configurations=len(g), sharpe_min=sh[0], sharpe_mediane=st.median(sh), sharpe_max=sh[-1], ann_min=an[0], ann_mediane=st.median(an), ann_max=an[-1],
                perte_max_pire=pm[0], perte_max_mediane=st.median(pm), perte_max_meilleure=pm[-1],
                base={**court(b)}, rang_base=1 + sum(m["sharpe"] > b["sharpe"] for m in g.values()),
                part_sharpe_sup_reference=sum(m["sharpe"] > ref["sharpe"] for m in g.values()) / len(g),
                part_ann_sup_reference=sum(m["ann"] > ref["ann"] for m in g.values()) / len(g),
                reference=court(ref),
                par_signal=marge(lambda p: f"{p.court}+{p.long}" if p.utiliser_court else f"{p.long} seul"),
                par_long=marge(lambda p: p.long), par_top=marge(lambda p: p.top), par_ecart_tampon=marge(lambda p: p.tampon - p.top),
                par_filtre=marge(lambda p: p.filtre))


rapport["sensibilité 9 secteurs 2009-2026"] = resume_grille(g9, reference9)
g10 = rb.calculer_grille(d10, D(2024, 1, 5), FIN)
rapport["sensibilité 10 ETF 2024-2026"] = resume_grille(g10, g10[BASE]["reference"])

# 4. Hors échantillon (9 secteurs)
a0, a1, b0, b1 = D(2009, 1, 1), D(2017, 12, 31), D(2018, 1, 1), FIN
choisi = rb.meilleur(g9, a0, a1)
ref_r = dict(zip(g9[BASE]["dates"], g9[BASE]["rendements_reference"]))
ref_b = [ref_r[x] for x in g9[BASE]["dates"] if b0 <= x <= b1]
ref_a = [ref_r[x] for x in g9[BASE]["dates"] if a0 <= x <= a1]
test_sh = sorted(mesures(rb.sous_periode(m, b0, b1))["sharpe"] for m in g9.values())
hs = {"entraînement 2009-2017": {"meilleure": rb.libelle(choisi), "meilleure_sur_entrainement": court(mesures(rb.sous_periode(g9[choisi], a0, a1))),
                                 "base": court(mesures(rb.sous_periode(g9[BASE], a0, a1))), "STOXX": court(mesures(ref_a))},
      "test 2018-2026": {"meilleure_d_entrainement": court(mesures(rb.sous_periode(g9[choisi], b0, b1))), "base": court(mesures(rb.sous_periode(g9[BASE], b0, b1))),
                         "STOXX": court(mesures(ref_b)), "sharpe_mediane_toutes_configs": st.median(test_sh),
                         "rang_base_sur_test": 1 + sum(s > mesures(rb.sous_periode(g9[BASE], b0, b1))["sharpe"] for s in test_sh), "configurations": len(test_sh)}}
chaine, choix = rb.glissant(g9, 2014, 2026)
b_ch = [x for x, y in zip(g9[BASE]["rendements"], g9[BASE]["dates"]) if y >= D(2014, 1, 1)]
r_ch = [x for x, y in zip(g9[BASE]["rendements_reference"], g9[BASE]["dates"]) if y >= D(2014, 1, 1)]
hs["sélection glissante 2014-2026"] = {"glissante": court(mesures(chaine)), "base": court(mesures(b_ch)), "STOXX": court(mesures(r_ch)),
                                       "choix": [(a, rb.libelle(p)) for a, p in choix]}
rapport["hors échantillon"] = hs

# 5. Incertitude
for nom, d, debut in (("9 secteurs 2008-2026", d9, D(2008, 7, 4)), ("10 ETF 2024-2026", d10, D(2024, 1, 5))):
    r = backtest(d, BASE, debut, FIN)
    rapport["bootstrap " + nom] = rb.bootstrap_sharpe(r["rendements"], r["rendements_reference"])

# 6. Par sous-période et par choc (9 secteurs)
r = backtest(d9, BASE, D(2008, 7, 4), FIN)
per = {}
for lib, a, b in (("2008-2012", D(2008, 7, 4), D(2012, 12, 31)), ("2013-2017", D(2013, 1, 1), D(2017, 12, 31)), ("2018-2023", D(2018, 1, 1), D(2023, 12, 31)), ("2024-2026", D(2024, 1, 1), FIN)):
    x = [v for v, t in zip(r["rendements"], r["dates"]) if a <= t <= b]
    y = [v for v, t in zip(r["rendements_reference"], r["dates"]) if a <= t <= b]
    per[lib] = {"moteur": court(mesures(x)), "STOXX": court(mesures(y))}
rapport["sous-périodes 9 secteurs"] = per

sortie = RACINE / "resultats"
sortie.mkdir(exist_ok=True)
(sortie / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1, default=str))
print(json.dumps(rapport, ensure_ascii=False, indent=0, default=lambda o: str(o))[:100])
print("écrit", sortie / "rapport.json")
