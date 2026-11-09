"""API du simulateur : portefeuille, indicateurs, corrélations, remplacement. Prix synthétiques, aucun accès réseau."""
import datetime as dt
import importlib.util
import pathlib

import pytest
from fastapi.testclient import TestClient

from etg_moteur import prix, prix_portefeuille as pp
from outils import bruts_complets, csv_synthetique, json_marche, jours_ouvres

RACINE = pathlib.Path(__file__).resolve().parents[1]
MOT_DE_PASSE = "mot-de-passe-de-test"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_PASSWORD", MOT_DE_PASSE)
    monkeypatch.setenv("SESSION_SECRET", "secret-de-session-de-test")
    monkeypatch.setenv("CRON_SECRET", "secret-du-cron")
    monkeypatch.setenv("ETG_STOCKAGE_LOCAL", str(tmp_path / "stock"))
    spec = importlib.util.spec_from_file_location("api_index_pf", RACINE / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(prix, "telecharger", lambda s, **k: ({x: v for x, v in bruts_complets().items() if x in set(s)}, {}))
    c = TestClient(module.app, base_url="https://testserver")
    assert c.post("/api/connexion", json={"motdepasse": MOT_DE_PASSE}).status_code == 200
    return c


@pytest.fixture()
def pret(client):
    r = client.post("/api/prix")
    assert r.status_code == 200, r.text
    assert r.json()["portefeuille"]["ok"] is True
    return client


def test_routes_protegees_sans_connexion(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ETG_STOCKAGE_LOCAL", str(tmp_path))
    spec = importlib.util.spec_from_file_location("api_index_pf2", RACINE / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    c = TestClient(module.app, base_url="https://testserver")
    for methode, route in (("GET", "/api/portefeuille"), ("POST", "/api/portefeuille"), ("POST", "/api/portefeuille/restaurer"),
                           ("POST", "/api/portefeuille/moteur"), ("POST", "/api/indicateurs"), ("POST", "/api/correlations"),
                           ("POST", "/api/simulation")):
        assert c.request(methode, route).status_code == 401, route


def test_sans_prix_les_routes_expliquent_quoi_faire(client):
    r = client.get("/api/portefeuille")
    assert r.status_code == 404 and "Mettre à jour" in r.json()["erreur"]


def test_la_mise_a_jour_range_les_prix_du_portefeuille_a_part(pret):
    r = pret.get("/api/portefeuille").json()
    assert r["prix_portefeuille"]["derniere_date"] == "2026-11-06"
    # Le CSV du moteur reste celui du moteur : 13 séries, pas de colonne du portefeuille
    etat = pret.get("/api/etat").json()
    assert etat["semaines"] > 900


def test_portefeuille_par_defaut_est_la_cible(pret):
    j = pret.get("/api/portefeuille").json()
    assert j["mode"] == "cible" and j["libelle_poids"] == "poids cibles" and j["valeur_totale"] is None
    assert len(j["lignes"]) == 19 and sum(l["poids"] for l in j["lignes"]) == pytest.approx(1.0)
    assert [l["code"] for l in j["lignes"][:4]] == ["HLT", "TNO", "ENRG", "FOO"]
    assert j["versions"] == [] and j["positions"] is None
    assert not any(l["sans_prix"] for l in j["lignes"])
    assert next(l for l in j["lignes"] if l["code"] == "MOWI")["cours_eur"] > 0


def test_indicateurs_chiffres_de_controle_via_l_api(pret):
    j = pret.post("/api/indicateurs").json()
    assert round(j["hhi"], 5) == 0.05395
    assert j["exposition_nette"] == pytest.approx(0.815)
    assert j["scenarios"]["A"] == pytest.approx(0.26) and j["scenarios"]["B"] == pytest.approx(0.305)
    assert j["scenarios"]["C"] == pytest.approx(0.435)
    assert j["somme_grosses"] == pytest.approx(0.32) and j["ligne_max"]["poids"] == pytest.approx(0.08)
    assert j["total_poids"] == pytest.approx(1.0)
    assert j["mode"] == "cible" and j["performance"]["disponible"] is False
    r = j["risque"]
    assert r["semaines"] == 180 and r["vol_ex_ante"] > 0 and r["diversification"] > 1 and r["beta"] is not None
    assert sum(x["contribution"] for x in r["contributions_liste"]) == pytest.approx(1.0)
    assert "non publiées" in j["note"] and "approximation" in j["hhi_note"]
    assert j["statut"] in ("conforme", "attention")


def positions(quantite=10.0, cash=1000.0, retire=None):
    base = pp_lignes()
    lignes = [dict(l, quantite=quantite) for l in base if l["type"] != "cash" and l["code"] != retire]
    lignes.append(dict(next(l for l in base if l["type"] == "cash"), quantite=0))
    return dict(lignes=lignes, cash=cash)


def pp_lignes():
    from etg_moteur import service_portefeuille as sp
    return sp.saisie_par_defaut()["lignes"]


def test_enregistrer_des_positions_calcule_les_poids_actuels(pret):
    r = pret.post("/api/portefeuille", json=positions())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "positions" and j["libelle_poids"].startswith("poids actuels")
    assert sum(l["poids"] for l in j["lignes"]) == pytest.approx(1.0)
    assert j["valeur_totale"] > 1000 and len(j["versions"]) == 1 and j["positions"]["source"] == "Saisie"
    ind = pret.post("/api/indicateurs").json()
    assert ind["mode"] == "positions"
    perf = ind["performance"]
    assert perf["disponible"] and perf["depuis"] == "2026-11-02" and "performance_ajustee" in perf
    assert perf["performance_ajustee"] == pytest.approx(perf["performance"] / ind["risque"]["vol_ex_ante"])
    assert "jamais un argument de choix" in perf["note"]


def test_historique_de_dix_versions_et_restauration(pret):
    for i in range(12):
        assert pret.post("/api/portefeuille", json=positions(quantite=5.0 + i)).status_code == 200
    j = pret.get("/api/portefeuille").json()
    assert len(j["versions"]) == 10
    ancienne = j["versions"][-1]["nom"]
    avant = next(l for l in j["lignes"] if l["code"] == "ENX")["quantite"]
    r = pret.post("/api/portefeuille/restaurer", json={"nom": ancienne})
    assert r.status_code == 200
    apres = next(l for l in r.json()["lignes"] if l["code"] == "ENX")["quantite"]
    assert apres != avant and len(r.json()["versions"]) == 10
    assert pret.post("/api/portefeuille/restaurer", json={"nom": "positions/inexistant.json"}).status_code == 404


def test_saisies_invalides(pret):
    base = pp_lignes()
    cas = {
        "code en double": dict(lignes=base + [dict(base[0])]),
        "symbole invalide": dict(lignes=[dict(base[0], symbole="a b;c")] + base[1:]),
        "scénario inconnu": dict(lignes=[dict(base[0], scenario="D")] + base[1:]),
        "type inconnu": dict(lignes=[dict(base[0], type="crypto")] + base[1:]),
        "poids supérieur à 1": dict(lignes=[dict(base[0], poids=1.5)] + base[1:]),
        "quantité négative": dict(lignes=[dict(base[0], quantite=-1)] + base[1:]),
        "isin invalide": dict(lignes=[dict(base[0], isin="XYZ")] + base[1:]),
        "poids cibles ≠ 100 %": dict(lignes=[dict(base[0], poids=0.5)] + base[1:]),
        "aucune ligne": dict(lignes=[]),
    }
    for nom, corps in cas.items():
        r = pret.post("/api/portefeuille", json=corps)
        assert r.status_code == 400 and r.json()["erreur"], nom
    assert pret.get("/api/portefeuille").json()["versions"] == []  # rien d'enregistré


def test_prix_manquant_pour_une_ligne_detenue(pret):
    corps = positions()
    corps["lignes"][5]["symbole"] = "INCONNU.PA"
    r = pret.post("/api/portefeuille", json=corps)
    assert r.status_code == 400 and "Pas de cours" in r.json()["erreur"]


def test_brouillon_non_enregistre_dans_les_indicateurs(pret):
    corps = dict(portefeuille=positions(retire="MOWI", cash=5000.0))
    j = pret.post("/api/indicateurs", json=corps).json()
    assert j["mode"] == "positions" and "MOWI" not in [x["code"] for x in j["lignes_detail"] if x["poids"] > 0]
    assert pret.get("/api/portefeuille").json()["versions"] == []


def test_ligne_sans_historique_dans_les_indicateurs(pret):
    base = pp_lignes()
    base[5]["symbole"] = "ZZZ.PA"
    r = pret.post("/api/indicateurs", json=dict(portefeuille=dict(lignes=base)))
    assert r.status_code == 200 and r.json()["risque"] is None and "Pas d'historique" in r.json()["risque_erreur"]
    assert round(r.json()["hhi"], 5) == 0.05395  # les chiffres qui n'ont pas besoin de prix restent calculés


def test_correlations(pret):
    j = pret.post("/api/correlations", json=dict(fenetre=52)).json()
    assert j["semaines"] == 52 and len(j["codes"]) == 18 and len(j["matrice"]) == 18
    assert all(j["matrice"][i][i] == 1.0 for i in range(18))
    assert pret.post("/api/correlations", json=dict(fenetre=180)).json()["semaines"] == 180
    assert pret.post("/api/correlations", json=dict(fenetre=100)).status_code == 400


def test_aligner_la_poche_moteur_sur_la_decision(pret):
    j = pret.post("/api/portefeuille/moteur").json()
    ch = j["changements_moteur"]
    moteur = [l for l in j["lignes"] if l["poche"] == "Moteur"]
    assert len(moteur) == 4 and sum(l["poids"] for l in moteur) == pytest.approx(0.32)
    assert ch["date_decision"] == "2026-11-06" and ch["apercu"] is True
    assert sum(l["poids"] for l in j["lignes"]) == pytest.approx(1.0)
    assert {l["code"] for l in j["lignes"] if l["poche"] != "Moteur"} == {l["code"] for l in pp_lignes() if l["poche"] != "Moteur"}
    assert pret.get("/api/portefeuille").json()["versions"] == []  # brouillon : rien n'est enregistré


# --- Remplacement -----------------------------------------------------------------------------------------------

@pytest.fixture()
def faux_yahoo(monkeypatch):
    """Candidats synthétiques : un titre normal, un titre allemand, un historique court, un cours sous 1 €, un introuvable."""
    fin = dt.date(2026, 11, 9)
    cas = {
        "SAN.PA": (dt.date(2015, 1, 5), 50.0), "SAP.DE": (dt.date(2015, 1, 5), 120.0),
        "NEUF.PA": (dt.date(2026, 5, 4), 40.0), "PENNY.PA": (dt.date(2015, 1, 5), 0.02),
    }

    def faux(symbole, dernier, pause=0.0):
        if symbole not in cas:
            return {"existe": False}
        debut, niveau = cas[symbole]
        corps = json_marche(jours_ouvres(debut, fin), sum(map(ord, symbole)), 0.0003, "EUR", niveau)
        return dict(existe=True, **pp.resume_symbole(corps, pp.grille(dernier)))
    monkeypatch.setattr(pp, "telecharger_candidat", faux)


def test_simulation_remplacement(pret, faux_yahoo):
    r = pret.post("/api/simulation", json=dict(remplace="UCB", candidats=[dict(symbole="SAN.PA", secteur="Santé")]))
    assert r.status_code == 200, r.text
    j = r.json()["resultats"][0]
    assert r.json()["remplace"] == "UCB" and j["candidat"]["poids"] == pytest.approx(0.045)  # poids de la ligne remplacée
    assert j["candidat"]["scenario"] == "C" and j["candidat_vol"] > 0
    assert {x["code"] for x in j["candidat_correlations"]} == {l["code"] for l in pp_lignes() if l["code"] not in ("UCB", "CASH")}
    assert j["avant"]["risque"] and j["apres"]["risque"] and "vol_ex_ante" in j["ecarts"]
    assert all(x["statut"] == "conforme" for x in j["controles_candidat"])
    corps = repr(j).lower()
    assert "sharpe" not in corps and "performance" not in corps and "ne recommande aucun achat" in corps


def test_simulation_controles_du_candidat(pret, faux_yahoo):
    r = pret.post("/api/simulation", json=dict(remplace="UCB", candidats=[
        dict(symbole="SAP.DE"), dict(symbole="NEUF.PA"), dict(symbole="PENNY.PA"), ][:3]))
    assert r.status_code == 200
    res = {x["symbole"]: x for x in r.json()["resultats"]}
    place = {c["id"]: c["statut"] for c in res["SAP.DE"]["controles_candidat"]}
    assert place["place"] == "hors règle"
    assert any(c["id"] == "places" and c["apres"] == "hors règle" for c in res["SAP.DE"]["changements_de_statut"])
    assert "Historique insuffisant" in res["NEUF.PA"]["erreur"] and "avant" not in res["NEUF.PA"]
    assert {c["id"]: c["statut"] for c in res["NEUF.PA"]["controles_candidat"]}["historique"] == "hors règle"
    penny = {c["id"]: c["statut"] for c in res["PENNY.PA"]["controles_candidat"]}
    assert penny["penny"] == "hors règle"


def test_simulation_symbole_introuvable_et_erreurs_de_saisie(pret, faux_yahoo):
    r = pret.post("/api/simulation", json=dict(remplace="UCB", candidats=[dict(symbole="ZZZ.PA"), dict(symbole="SAN.PA")]))
    res = r.json()["resultats"]
    assert "n'existe pas" in res[0]["erreur"] and "avant" in res[1]  # une erreur n'arrête pas les autres
    assert pret.post("/api/simulation", json=dict(remplace="ZZZ", candidats=[dict(symbole="SAN.PA")])).status_code == 400
    assert pret.post("/api/simulation", json=dict(remplace="CASH", candidats=[dict(symbole="SAN.PA")])).status_code == 400
    assert pret.post("/api/simulation", json=dict(remplace="UCB", candidats=[])).status_code == 400
    assert pret.post("/api/simulation", json=dict(remplace="UCB", candidats=[dict(symbole="SAN.PA")] * 4)).status_code == 400
    r = pret.post("/api/simulation", json=dict(remplace="UCB", candidats=[dict(symbole="SAN.PA", poids=0.2)]))
    assert "Le cash ne suffit pas" in r.json()["resultats"][0]["erreur"]


def test_simulation_trois_candidats_cote_a_cote(pret, faux_yahoo):
    r = pret.post("/api/simulation", json=dict(remplace="LDO", candidats=[dict(symbole="SAN.PA"), dict(symbole="SAP.DE"),
                                                                       dict(symbole="NEUF.PA")]))
    assert r.status_code == 200 and len(r.json()["resultats"]) == 3
