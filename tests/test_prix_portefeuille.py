import datetime as dt
import json

import pytest

from etg_moteur import prix, prix_portefeuille as pp, stockage
from outils import bruts_complets, bruts_portefeuille, bruts_synthetiques, json_marche, jours_ouvres

FIN = dt.date(2026, 11, 6)


def test_symboles_du_portefeuille_sont_ceux_verifies():
    assert set(pp.SYMBOLES_PORTEFEUILLE) == {"500.PA", "AEEM.PA", "EJAP.PA", "EVOE.PA", "MTA.PA", "SHC.PA", "ENX.PA", "GALP.LS",
                                              "NN.AS", "PRY.MI", "KRX.IR", "LDO.MI", "UCB.BR", "MOWI.OL", "EURNOK=X"}
    assert len(pp.SYMBOLES_PORTEFEUILLE) == 15  # 14 lignes + le taux de change


def test_grille_est_celle_du_csv_du_moteur():
    g = pp.grille(FIN, 400)
    assert len(g) == 400 and g[-1] == FIN and all(d.weekday() == 4 for d in g)
    assert all(b - a == dt.timedelta(days=7) for a, b in zip(g, g[1:]))
    texte, semaines = prix.construire_csv(bruts_synthetiques(), FIN)
    assert pp.grille(FIN, 10_000)[0] == semaines[0] and pp.grille(FIN, 10_000) == semaines


def test_construire_convertit_mowi_en_euros_et_garde_les_derniers_cours():
    bruts = bruts_complets()
    doc = pp.construire(bruts, FIN, dt.datetime(2026, 11, 9, 15, tzinfo=dt.UTC))
    assert set(doc["series"]) == set(pp.SYMBOLES_PORTEFEUILLE) - {pp.FX_NOK}
    assert len(doc["dates"]) == 400 and doc["dates"][-1] == "2026-11-06"
    assert all(len(v) == 400 for v in doc["series"].values())
    # Mowi : cours en NOK ≈ 2200, EURNOK ≈ 10,5 -> environ 200 € (et non 2 200)
    mowi = doc["dernier"]["MOWI.OL"]
    fx = prix.lire_brut(bruts[pp.FX_NOK])
    assert mowi["devise"] == "NOK"
    assert mowi["cours_local"] / mowi["cours_eur"] == pytest.approx(fx[dt.date.fromisoformat(mowi["date"])][1], rel=1e-3)
    assert doc["dernier"]["500.PA"]["devise"] == "EUR" and doc["dernier"]["500.PA"]["cours_eur"] == doc["dernier"]["500.PA"]["cours_local"]
    # Derniers cours quotidiens : lignes du portefeuille et ETF du moteur
    assert "2026-11-02" in doc["recent"]["ENX.PA"] and "2026-11-02" in doc["recent"]["HLT.PA"]
    assert all(len(v) == 2 for v in doc["recent"]["ENX.PA"].values())
    assert pp.lire(pp.en_texte(doc))["dates"] == doc["dates"]


def test_construire_signale_les_symboles_manquants_et_les_devises_non_gerees():
    bruts = bruts_complets()
    del bruts["ENX.PA"]
    with pytest.raises(pp.ErreurPrixPortefeuille, match="ENX.PA"):
        pp.construire(bruts, FIN)
    bruts = bruts_complets()
    bruts["GALP.LS"] = json_marche(jours_ouvres(dt.date(2020, 1, 1), dt.date(2026, 11, 9)), 1, devise="GBp")
    with pytest.raises(pp.ErreurPrixPortefeuille, match="GBp"):
        pp.construire(bruts, FIN)


def test_historique_court_donne_des_none_avant_la_premiere_cotation():
    bruts = bruts_complets()
    bruts["PRY.MI"] = json_marche(jours_ouvres(dt.date(2026, 1, 5), dt.date(2026, 11, 9)), 3)
    doc = pp.construire(bruts, FIN)
    serie = doc["series"]["PRY.MI"]
    assert serie[0] is None and serie[-1] is not None
    assert 40 <= sum(v is not None for v in serie) <= 46


def test_resume_symbole_compte_les_semaines_d_historique():
    corps = json_marche(jours_ouvres(dt.date(2025, 11, 10), dt.date(2026, 11, 9)), 4)
    r = pp.resume_symbole(corps, pp.grille(FIN))
    assert 50 <= r["semaines"] <= 53 and r["devise"] == "EUR"


def test_candidat_introuvable_ou_bloque(monkeypatch):
    def introuvable(*a, **k):
        raise prix.ErreurYahoo("ZZZ : Yahoo a répondu HTTP 404", 404)
    monkeypatch.setattr(prix, "telecharger_symbole", introuvable)
    assert pp.telecharger_candidat("ZZZ.PA", FIN) == {"existe": False}

    def bloque(*a, **k):
        raise prix.ErreurYahoo("ZZZ : Yahoo a répondu HTTP 429", 429)
    monkeypatch.setattr(prix, "telecharger_symbole", bloque)
    with pytest.raises(prix.ErreurYahoo):
        pp.telecharger_candidat("ZZZ.PA", FIN)


def test_candidat_oslo_telecharge_aussi_le_taux(monkeypatch):
    bruts = bruts_portefeuille()
    appels = []

    def faux(symbole, **k):
        appels.append(symbole)
        return bruts[symbole]
    monkeypatch.setattr(prix, "telecharger_symbole", faux)
    r = pp.telecharger_candidat("MOWI.OL", FIN)
    fx = prix.lire_brut(bruts["EURNOK=X"])
    assert appels == ["MOWI.OL", "EURNOK=X"] and r["existe"] and r["devise"] == "NOK"
    assert r["dernier"]["cours_local"] / r["dernier"]["cours_eur"] == pytest.approx(fx[dt.date.fromisoformat(r["dernier"]["date"])][1], rel=1e-3)
    assert pp.symbole_a_telecharger("ENX.PA") == ("ENX.PA",)


# --- Stockage versionné ---------------------------------------------------------------------------------------

def test_versions_du_portefeuille_et_historique_de_10(tmp_path):
    st = stockage.StockageLocal(str(tmp_path))
    assert stockage.lire_version(st, stockage.PREFIXE_POSITIONS, "json") is None
    t0 = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)
    for i in range(14):
        stockage.ecrire_version(st, stockage.PREFIXE_POSITIONS, "json", json.dumps({"v": i}).encode(), "application/json",
                                "saisie", stockage.CONSERVER_POSITIONS, t0 + dt.timedelta(minutes=i))
    contenu, etat = stockage.lire_version(st, stockage.PREFIXE_POSITIONS, "json")
    assert json.loads(contenu) == {"v": 13} and etat["source"] == "Saisie"
    versions = stockage.lister_versions(st, stockage.PREFIXE_POSITIONS, "json")
    assert len(versions) == 10 and versions[0]["mise_a_jour"] > versions[-1]["mise_a_jour"]
    # les prix du moteur ne sont pas touchés
    assert st.lister(stockage.PREFIXE) == []
