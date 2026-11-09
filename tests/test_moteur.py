import datetime as dt

import pytest

from etg_moteur.moteur import Donnees, Parametres, backtest, decider, rangs, selection, signal
from etg_moteur.portefeuille import simuler


def vendredis(n, debut=dt.date(2020, 1, 3)):
    return [debut + dt.timedelta(days=7 * i) for i in range(n)]


def donnees(tendances, n=80):
    """Prix réguliers : chaque ETF progresse de `tendance` par semaine."""
    prix = [[100 * (1 + g) ** t for t in range(n)] for g in tendances]
    plat = [[100.0] * n, [100.0] * n]
    return Donnees(vendredis(n), [f"E{i}" for i in range(len(tendances))], prix, [list(p) for p in prix],
                   plat, [list(p) for p in plat], [100.0] * n, [100.0] * n)


def test_signal_moyenne_des_deux_periodes():
    prix = [100.0] * 30
    prix[29], prix[29 - 13], prix[29 - 26] = 121.0, 110.0, 100.0
    assert signal(Parametres(), prix, 29) == pytest.approx(((121 / 110 - 1) + (121 / 100 - 1)) / 2)


def test_signal_six_mois_seuls():
    prix = [100.0] * 30
    prix[29] = 121.0
    assert signal(Parametres(utiliser_court=False), prix, 29) == pytest.approx(0.21)


def test_signal_absent_si_historique_court_ou_prix_manquant():
    prix = [100.0] * 30
    assert signal(Parametres(), prix, 25) is None
    prix[3] = None
    assert signal(Parametres(), prix, 29) is None


def test_rangs_ex_aequo_et_absents():
    assert rangs([.1, None, .3, .1]) == [2, None, 1, 2]


def test_top_4_a_egalite():
    d = donnees([.01, .002, .004, .003, .006, .005, .001, .007, .0005, .0001])
    poids, _ = decider(d, Parametres())
    assert sum(poids[-2]) == pytest.approx(1)
    assert [i for i, x in enumerate(poids[-2][:10]) if x] == [0, 4, 5, 7]


def test_zone_tampon_garde_une_ligne_du_top_6():
    sig = [.9, .8, .7, .6, .5, .4, .3, .2, .1, .05]
    detenu = [0, 0, 0, 0, 0, 1, 0, 0, 0, 0]
    retenu, _ = selection(Parametres(), sig, detenu)
    assert retenu[5] == 1 and sum(retenu) == 4 and retenu[:3] == [1, 1, 1] and retenu[3] == 0


def test_zone_tampon_vend_hors_du_top_6():
    sig = [.9, .8, .7, .6, .5, .4, .3, .2, .1, .05]
    retenu, _ = selection(Parametres(), sig, [0, 0, 0, 0, 0, 0, 1, 0, 0, 0])
    assert retenu[6] == 0 and retenu[:4] == [1, 1, 1, 1]


def test_sans_tampon_vend_des_la_sortie_du_top():
    sig = [.9, .8, .7, .6, .5, .4, .3, .2, .1, .05]
    retenu, _ = selection(Parametres(tampon=4), sig, [0, 0, 0, 0, 0, 1, 0, 0, 0, 0])
    assert retenu[5] == 0


def test_filtre_remplace_par_refuges_puis_cash():
    d = donnees([-.01] * 10)
    w = decider(d, Parametres())[0][-2]
    assert sum(w[:10]) == 0 and w[10] == .25 and w[11] == .25 and 1 - sum(w) == pytest.approx(.5)


def test_sans_filtre_garde_les_signaux_negatifs():
    d = donnees([-.01 - i / 1000 for i in range(10)])
    w = decider(d, Parametres(filtre=False))[0][-2]
    assert sum(w[:10]) == pytest.approx(1) and w[:4] == [.25] * 4 and w[10] == 0 and w[11] == 0


def test_reequilibrage_seulement_le_dernier_vendredi_du_mois():
    d = donnees([.01, .002, .004, .003])
    poids, reeq = decider(d, Parametres(top=2, tampon=2))
    for t in range(1, len(d.dates)):
        if not reeq[t]:
            assert poids[t] == poids[t - 1]
    assert all(d.dates[t + 1].month != d.dates[t].month for t in range(len(d.dates) - 1) if reeq[t])


def test_pas_de_regard_vers_le_futur():
    """Changer les prix après t ne change aucune décision jusqu'à t."""
    d = donnees([.01, .002, .004, .003, .006, .005])
    avant, _ = decider(d, Parametres(tampon=4))
    t = 60
    for i in range(6):
        for k in range(t + 1, 80):
            d.cloture[i][k] *= 1 + (k % 7 - 3) / 10
    apres, _ = decider(d, Parametres(tampon=4))
    assert avant[:t + 1] == apres[:t + 1]


def test_rendement_utilise_les_poids_de_la_semaine_precedente():
    d = donnees([.01, .0100001, .0100002, .0100003], n=60)
    p = Parametres(top=4, tampon=4)
    r = backtest(d, p, d.dates[40], d.dates[59])
    assert r["rendements"][0] == pytest.approx(.01, abs=1e-5)


def test_refuges_rapportent_leur_rendement():
    d = donnees([-.01] * 4, n=60)
    d.monetaire_ouverture[0] = [100 * 1.001 ** t for t in range(60)]
    d.monetaire_cloture[0] = list(d.monetaire_ouverture[0])
    r = backtest(d, Parametres(top=4, tampon=4), d.dates[40], d.dates[59])
    assert r["rendements"][-1] == pytest.approx(.25 * .001)


def test_mi_mois_ramene_une_grosse_ligne_a_8_pourcent():
    n = 70
    d = donnees([.004, .0041, .0042, .0043], n=n)
    # Forte hausse d'une seule ligne juste avant une réunion de mi-mois
    t = next(i for i in range(40, n) if 11 <= d.dates[i].day <= 17)
    for k in range(t, n):
        d.cloture[0][k] *= 1.6
        if k > t:
            d.ouverture[0][k] *= 1.6
    r = simuler(d, Parametres(top=4, tampon=4), d.dates[t - 2], d.dates[t + 2])
    assert r["coupes_mi_mois"] == 1 and r["semaines_au_dessus_9"] >= 1


def test_portefeuille_sans_mouvement_ne_bouge_pas():
    d = donnees([0.0] * 4, n=60)
    r = simuler(d, Parametres(top=1, tampon=1, filtre=False), d.dates[40], d.dates[59])
    assert r["portefeuille"]["perf"] == pytest.approx(0) and r["perf"] == pytest.approx(0)


def test_dernier_vendredi_du_mois():
    from etg_moteur.application import dernier_vendredi
    assert dernier_vendredi(2026, 11) == dt.date(2026, 11, 27)
    assert dernier_vendredi(2026, 10) == dt.date(2026, 10, 30)
    assert dernier_vendredi(2027, 1) == dt.date(2027, 1, 29)


def test_decision_garde_une_ligne_dans_la_zone_tampon():
    from etg_moteur.application import decision
    d = donnees([.01, .009, .008, .007, .006, .005, .004, .003, .002, .001])
    res = decision(d, Parametres(), 79, {"E5"})
    actions = {l["etf"]: l["action"] for l in res["lignes"]}
    assert actions["E5"] == "garder" and actions["E0"] == "acheter" and actions["E3"] == "—"
    assert sum(1 for l in res["lignes"] if l["retenu"]) == 4


def test_decision_refuse_un_etf_inconnu():
    from etg_moteur.application import decision
    with pytest.raises(ValueError):
        decision(donnees([.01] * 4), Parametres(), 79, {"Inconnu"})
