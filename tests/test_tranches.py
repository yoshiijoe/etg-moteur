import datetime as dt

import pytest

from etg_moteur import tranches as tr
from etg_moteur.moteur import Donnees, Parametres


def vendredis(n, debut=dt.date(2020, 1, 3)):
    return [debut + dt.timedelta(days=7 * i) for i in range(n)]


def donnees(tendances, n=120):
    prix = [[100 * (1 + g) ** t for t in range(n)] for g in tendances]
    plat = [[100.0] * n, [100.0] * n]
    return Donnees(vendredis(n), [f"E{i}" for i in range(len(tendances))], prix, [list(p) for p in prix],
                   plat, [list(p) for p in plat], [100 * 1.001 ** t for t in range(n)], [100 * 1.001 ** t for t in range(n)])


def test_bornes_semestrielles():
    b = tr.bornes_tranches(vendredis(60))
    assert [x[0] for x in b] == ["2020 S1", "2020 S2", "2021 S1"]
    assert all(tr.bornes_tranches(vendredis(60))[i][2] + 1 == b[i + 1][1] for i in range(len(b) - 1))


def test_tranche_part_de_zero_et_achete_le_top_des_le_debut():
    d = donnees([.004, .001, .003, .002, .005, .0005])
    lignes = tr.toutes(d, Parametres(top=2, tampon=4))
    premiere = lignes[0]
    assert premiere["choix"][0][0] == premiere["debut"]
    assert sorted(premiere["choix"][0][1]) == ["E0", "E4"]
    # Une semaine pleine : rendement moyen des deux meilleurs ETF, tranche après tranche
    assert premiere["moteur"] == pytest.approx((1 + (.004 + .005) / 2) ** premiere["semaines"] - 1, rel=1e-3)


def test_tranches_contigues_sans_chevauchement():
    d = donnees([.004, .001, .003, .002])
    lignes = tr.toutes(d, Parametres(top=2, tampon=2))
    total = sum(l["semaines"] for l in lignes)
    premier = d.dates.index(lignes[0]["debut"])
    dernier = d.dates.index(lignes[-1]["fin"])
    assert total in (dernier - premier, dernier - premier + 1)


def test_filtre_en_marche_baissiere_met_en_refuge():
    d = donnees([-.01, -.02, -.015, -.012])
    l = tr.toutes(d, Parametres(top=2, tampon=2))[0]
    assert l["choix"][0][1] == [] and l["choix"][0][2] == pytest.approx(1.0)
    assert l["moteur"] == pytest.approx(0.0)


def test_synthese():
    lignes = [dict(semaines=26, moteur=.1, stoxx=.05, parts_egales=.04, ecart=.05, perte_max=-.05),
              dict(semaines=26, moteur=-.02, stoxx=.03, parts_egales=0., ecart=-.05, perte_max=-.1),
              dict(semaines=10, moteur=.5, stoxx=0., parts_egales=0., ecart=.5, perte_max=0.)]
    s = tr.synthese(lignes)
    assert s["tranches"] == 2 and s["moteur_moyenne"] == pytest.approx(.04) and s["part_bat_stoxx"] == .5
