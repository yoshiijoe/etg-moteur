"""Référence « ETF à parts égales » : mêmes dates et mêmes prix d'exécution que le moteur."""
import datetime as dt
import random

import pytest

from etg_moteur.moteur import Donnees, Parametres, backtest, decider, mesures
from etg_moteur.reference_egale import backtest_parts_egales, libelle


def vendredis(n, debut=dt.date(2020, 1, 3)):
    return [debut + dt.timedelta(days=7 * i) for i in range(n)]


def marche(n, graine, derive=0.001, vol=0.02, debut=0):
    g, v, s = random.Random(graine), 100.0, []
    for t in range(n):
        v *= 1 + g.gauss(derive, vol)
        s.append(v if t >= debut else None)
    return s


def donnees(series, n, ouv=None):
    clo = series
    ouvertures = ouv or [[None if x is None else x * (1 + 0.002 * ((t % 3) - 1)) for t, x in enumerate(s)] for s in clo]
    plat = [[100.0] * n, [100.0] * n]
    ref = marche(n, 99)
    return Donnees(vendredis(n), [f"E{i}" for i in range(len(clo))], clo, ouvertures, plat, [list(x) for x in plat], ref,
                   [x * 1.001 for x in ref])


def test_parts_egales_sans_derive_vaut_la_moyenne_des_rendements():
    """Rééquilibrage chaque semaine impossible : on vérifie à la main sur la première semaine (poids encore égaux)."""
    n = 40
    d = donnees([marche(n, i) for i in range(4)], n)
    debut, fin = d.dates[10], d.dates[30]
    res = backtest_parts_egales(d, Parametres(), debut, fin)
    premier = sum(d.ouverture[i][11] / d.ouverture[i][10] - 1 for i in range(4)) / 4
    assert res["rendements"][0] == pytest.approx(premier)
    assert res["n"] == 20 and len(res["dates"]) == 20 and res["dates"][0] == d.dates[11]


def test_rotation_nulle_quand_rien_ne_derive():
    n = 40
    plat = [[100.0 + 0 * t for t in range(n)] for _ in range(5)]
    d = donnees(plat, n, ouv=[list(x) for x in plat])
    res = backtest_parts_egales(d, Parametres(), d.dates[5], d.dates[35])
    assert res["rotation"] == pytest.approx(0, abs=1e-12) and res["ann"] == pytest.approx(0, abs=1e-12)
    assert res["hhi"] == pytest.approx(0.2)


def test_rebalancement_aux_memes_dates_que_le_moteur():
    n = 60
    d = donnees([marche(n, i) for i in range(4)], n)
    debut, fin = d.dates[0], d.dates[-1]
    res = backtest_parts_egales(d, Parametres(), debut, fin)
    _, drapeaux = decider(d, Parametres())
    attendus = sum(drapeaux[t] for t in range(1, len(d.dates)))   # un rééquilibrage par fin de mois, hors première ligne
    assert res["reequilibrages"] == attendus > 10
    ref_moteur = backtest(d, Parametres(), debut, fin)
    assert res["dates"] == ref_moteur["dates"]                     # mêmes dates de rendement que le moteur
    assert res["beta"] == pytest.approx(res["beta"])               # défini
    assert res["correlation"] if "correlation" in res else True


def test_deux_etf_identiques_donnent_le_meme_resultat_qu_un_seul():
    n = 50
    s = marche(n, 7)
    d2 = donnees([s, list(s)], n)
    d1 = donnees([s], n)
    a = backtest_parts_egales(d2, Parametres(), d2.dates[3], d2.dates[-1])
    b = backtest_parts_egales(d1, Parametres(), d1.dates[3], d1.dates[-1])
    assert a["rendements"] == pytest.approx(b["rendements"]) and a["rotation"] == pytest.approx(0, abs=1e-9)


def test_etf_sans_prix_avant_une_date_est_ajoute_au_prochain_rebalancement():
    """La Défense n'a pas de prix avant juillet 2023 : parts égales entre les ETF disponibles."""
    n = 80
    d = donnees([marche(n, 1), marche(n, 2), marche(n, 3, debut=30)], n)
    res = backtest_parts_egales(d, Parametres(), d.dates[5], d.dates[-1])
    # Avant la ligne 30, deux ETF à 50 % : HHI moyen au début ≈ 0,5, puis tend vers 1/3 après l'arrivée du 3e
    assert res["n"] == 74 and res["reequilibrages"] > 5 and 0.33 < res["hhi"] < 0.5
    premiere = (d.ouverture[0][6] / d.ouverture[0][5] - 1 + d.ouverture[1][6] / d.ouverture[1][5] - 1) / 2
    assert res["rendements"][0] == pytest.approx(premiere)


def test_ex_ante_et_mesures_de_base():
    n = 230
    d = donnees([marche(n, i) for i in range(5)], n)
    res = backtest_parts_egales(d, Parametres(), d.dates[30], d.dates[-1])
    assert res["vol_ex_ante"] > 0 and res["diversification"] > 1
    m = mesures(res["rendements"])
    assert res["ann"] == pytest.approx(m["ann"]) and res["sharpe"] == pytest.approx(m["sharpe"])


def test_periode_trop_courte_et_libelle():
    n = 30
    d = donnees([marche(n, 1)], n)
    with pytest.raises(ValueError):
        backtest_parts_egales(d, Parametres(), d.dates[1], d.dates[2])
    assert libelle(10) == "10 ETF à parts égales" and libelle(9) == "9 ETF à parts égales"
