import datetime as dt
import importlib.util
import io
import pathlib
import sys

import openpyxl
import pytest
from fastapi.testclient import TestClient

from etg_moteur import prix, session
from etg_moteur.service import DETENUS_DEFAUT
from outils import bruts_synthetiques, csv_synthetique

RACINE = pathlib.Path(__file__).resolve().parents[1]
MOT_DE_PASSE = "mot-de-passe-de-test"


@pytest.fixture(scope="module")
def csv_texte():
    return csv_synthetique()


@pytest.fixture()
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_PASSWORD", MOT_DE_PASSE)
    monkeypatch.setenv("SESSION_SECRET", "secret-de-session-de-test")
    monkeypatch.setenv("CRON_SECRET", "secret-du-cron")
    monkeypatch.setenv("ETG_STOCKAGE_LOCAL", str(tmp_path / "stock"))
    spec = importlib.util.spec_from_file_location("api_index", RACINE / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    return module


@pytest.fixture()
def client(api):
    return TestClient(api.app, base_url="https://testserver")


@pytest.fixture()
def connecte(client):
    r = client.post("/api/connexion", json={"motdepasse": MOT_DE_PASSE})
    assert r.status_code == 200
    return client


@pytest.fixture()
def avec_prix(connecte, csv_texte):
    r = connecte.post("/api/importer", content=csv_texte.encode(), headers={"content-type": "text/csv"})
    assert r.status_code == 200, r.text
    return connecte


# --- Connexion ------------------------------------------------------------------------------

def test_routes_protegees_sans_cookie(client):
    for methode, route in (("GET", "/api/etat"), ("POST", "/api/prix"), ("POST", "/api/backtest"),
                           ("POST", "/api/decision"), ("POST", "/api/excel"), ("POST", "/api/importer")):
        r = client.request(methode, route)
        assert r.status_code == 401, route
        assert r.json()["erreur"] == "Connexion requise."


def test_mauvais_mot_de_passe(client):
    r = client.post("/api/connexion", json={"motdepasse": "faux"})
    assert r.status_code == 401 and "set-cookie" not in r.headers


def test_connexion_pose_un_cookie_securise(client):
    r = client.post("/api/connexion", json={"motdepasse": MOT_DE_PASSE})
    cookie = r.headers["set-cookie"].lower()
    for attendu in ("httponly", "secure", "samesite=strict", "max-age=604800"):
        assert attendu in cookie
    assert client.get("/api/etat").status_code == 200


def test_cookie_falsifie_ou_expire_refuse(client):
    client.cookies.set("etg_session", "9999999999.signature-bidon")
    assert client.get("/api/etat").status_code == 401
    secret = "secret-de-session-de-test"
    vieux = session.creer_jeton(secret, maintenant=1_000_000)
    assert not session.jeton_valide(vieux, secret)
    assert session.jeton_valide(vieux, secret, maintenant=1_000_100)
    assert not session.jeton_valide(vieux, "autre-secret", maintenant=1_000_100)


def test_connexion_impossible_sans_configuration(monkeypatch, api, client):
    monkeypatch.delenv("SITE_PASSWORD")
    assert client.post("/api/connexion", json={"motdepasse": ""}).status_code == 503


# --- Cron -----------------------------------------------------------------------------------

def test_cron_refuse_sans_secret(client):
    assert client.get("/api/cron").status_code == 401
    assert client.get("/api/cron", headers={"authorization": "Bearer faux"}).status_code == 401


def test_cron_met_a_jour_les_prix(api, client, monkeypatch):
    monkeypatch.setattr(prix, "telecharger", lambda *a, **k: (bruts_synthetiques(), {}))
    r = client.get("/api/cron", headers={"authorization": "Bearer secret-du-cron"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "Yahoo Finance"
    assert r.json()["dernier_vendredi"] <= dt.date.today().isoformat()


# --- Prix -----------------------------------------------------------------------------------

def test_etat_sans_prix(connecte):
    assert connecte.get("/api/etat").json()["disponible"] is False
    r = connecte.post("/api/backtest")
    assert r.status_code == 404 and "Mettre à jour" in r.json()["erreur"]


def test_import_csv_puis_etat(avec_prix, csv_texte):
    e = avec_prix.get("/api/etat").json()
    assert e["disponible"] and e["source"] == "Import CSV"
    assert e["dernier_vendredi"] == "2026-11-06"
    assert e["dernier_vendredi_backtest"] == "2026-10-30"
    assert e["semaines"] == len(csv_texte.splitlines()) - 1
    assert any("Yahoo" in a for a in e["avertissements"]) and any("07/2023" in a for a in e["avertissements"])


def test_import_csv_invalide(connecte):
    r = connecte.post("/api/importer", content=b"a,b\n1,2\n")
    assert r.status_code == 400 and "illisible" in r.json()["erreur"]
    assert connecte.post("/api/importer", content=b"").status_code == 400


def test_mise_a_jour_yahoo_bloque(connecte, monkeypatch):
    erreurs = {s: f"{s} : Yahoo a répondu HTTP 429" for s in ("A", "B")}
    monkeypatch.setattr(prix, "telecharger", lambda *a, **k: ({}, erreurs))
    r = connecte.post("/api/prix")
    assert r.status_code == 502
    assert "429" in r.json()["erreur"] and "Importer un CSV" in r.json()["erreur"]


def test_mise_a_jour_yahoo_ok(connecte, monkeypatch):
    monkeypatch.setattr(prix, "telecharger", lambda *a, **k: (bruts_synthetiques(), {}))
    r = connecte.post("/api/prix")
    assert r.status_code == 200 and r.json()["semaines"] > 900
    assert connecte.get("/api/etat").json()["source"] == "Yahoo Finance"


# --- Backtest -------------------------------------------------------------------------------

def test_backtest_par_defaut(avec_prix):
    r = avec_prix.post("/api/backtest")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["parametres"]["debut"] == "2024-01-05" and j["parametres"]["fin"] == "2026-10-30"
    assert j["periode"]["semaines"] == len(j["series"]["dates"]) - 1
    assert j["series"]["moteur"][0] == 100 and j["series"]["reference"][0] == 100
    assert min(j["series"]["perte_moteur"]) == pytest.approx(j["moteur"]["perte_max"])
    assert [v["nom"] for v in j["variantes"]] == ["Base", "6 mois seuls", "Top 3", "Sans filtre", "Sans zone tampon",
                                                  "STOXX Europe 600"]
    assert j["variantes"][0]["mesures"] == j["moteur"]
    assert len(j["poids"]["colonnes"]) == 12 and len(j["poids"]["valeurs"]) == len(j["poids"]["dates"])
    assert {"ann", "sharpe", "perte_max", "rotation", "hhi", "beta", "vol_ex_ante", "diversification"} <= set(j["moteur"])


def test_backtest_9_etf_sans_defense(avec_prix):
    j = avec_prix.post("/api/backtest", json={"univers": "9", "debut": "2010-01-08"}).json()
    assert len(j["poids"]["colonnes"]) == 11 and "Défense" not in j["poids"]["colonnes"]


def test_backtest_parametres_invalides(avec_prix):
    for corps in ({"court": 30, "long": 26}, {"top": 11}, {"tampon": 2, "top": 4}, {"debut": "2026-01-01", "fin": "2025-01-01"},
                  {"univers": "8"}, {"debut": "pas une date"}, {"debut": "2026-10-23", "fin": "2026-10-30"}):
        r = avec_prix.post("/api/backtest", json=corps)
        assert r.status_code == 400 and r.json()["erreur"], corps


def test_backtest_fin_limitee_a_la_derniere_ouverture(avec_prix):
    j = avec_prix.post("/api/backtest", json={"fin": "2026-11-06"}).json()
    assert j["parametres"]["fin"] == "2026-10-30"


# --- Décision -------------------------------------------------------------------------------

def test_decision_par_defaut(avec_prix):
    j = avec_prix.post("/api/decision").json()
    assert j["date"] == "2026-11-06" and j["date_officielle"] == "2026-11-27" and j["apercu"] is True
    assert j["detenus"] == sorted(DETENUS_DEFAUT)
    assert [l["rang"] for l in j["lignes"]] == sorted(l["rang"] for l in j["lignes"])
    assert {l["action"] for l in j["lignes"]} <= {"acheter", "garder", "vendre", "—"}
    assert (j["libelle_court"], j["libelle_long"]) == ("3 mois", "6 mois")


def test_decision_officielle(avec_prix):
    j = avec_prix.post("/api/decision", json={"vendredi": "2026-10-30",
                                              "detenus": ["Banques", "Technologie"]}).json()
    assert j["apercu"] is False and j["date_officielle"] == "2026-10-30"
    assert [l["detenu"] for l in j["lignes"]].count(True) == 2


def test_decision_erreurs(avec_prix):
    r = avec_prix.post("/api/decision", json={"detenus": ["Licornes"]})
    assert r.status_code == 400 and "Licornes" in r.json()["erreur"]
    r = avec_prix.post("/api/decision", json={"vendredi": "2026-10-29"})
    assert r.status_code == 400 and "Pas de cours" in r.json()["erreur"]


# --- Excel ----------------------------------------------------------------------------------

def test_excel(avec_prix):
    r = avec_prix.post("/api/excel", json={"vendredi": "2026-10-30"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="moteur-etg-2026-10-30.xlsx"'
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Tableau de bord", "Lisez-moi", "Resultats", "Variantes", "Decision", "Serie", "Poids", "Prix_cloture",
                             "Prix_ouverture"]
    lisez = " ".join(str(c.value) for row in wb["Lisez-moi"].iter_rows() for c in row if c.value)
    assert "Yahoo" in lisez and "07/2023" in lisez and "non validés" in lisez
    res = wb["Resultats"]
    assert res["A1"].font.b and res.freeze_panes == "A2"
    assert [res.cell(i, 1).value for i in range(2, 11)] == ["Rendement annualisé", "Volatilité", "Sharpe", "Perte max",
                                                            "Rotation", "HHI", "Bêta", "Volatilité ex-ante",
                                                            "Ratio de diversification"]
    j = avec_prix.post("/api/backtest", json={"vendredi": "2026-10-30"}).json()
    assert res["B2"].value == pytest.approx(j["moteur"]["ann"]) and res["B2"].number_format == "0.00%"
    assert res["C2"].value == pytest.approx(j["reference"]["ann"])
    assert wb["Variantes"].max_row == 7
    dec = wb["Decision"]
    assert [c.value for c in dec[1]] == ["Rang", "ETF", "3 mois", "6 mois", "Signal", "Détenu", "Décision"]
    assert dec.max_row >= 11
    serie = wb["Serie"]
    assert serie["A2"].number_format == "dd/mm/yyyy" and serie["B2"].value == 100
    poids = wb["Poids"]
    assert poids.max_column == 13
    # Aucune formule dans tout le classeur
    for ws in wb:
        assert not any(isinstance(c.value, str) and c.value.startswith("=") for row in ws.iter_rows() for c in row)
    # Prix : même mise en page que le classeur de l'équipe
    for nom in ("Prix_cloture", "Prix_ouverture"):
        ws = wb[nom]
        assert ws.freeze_panes == "B6" and ws.max_column == 14
        assert ws["A3"].value == "Date (vendredi)" and ws["B4"].value == "Banques" and ws["B5"].value == "BNK"
        assert ws["N5"].value == "EXSA"
        assert ws["A6"].number_format == "dd/mm/yyyy" and ws.max_row - 5 <= 520
        assert ws.cell(ws.max_row, 1).value.date() == dt.date(2026, 10, 30)


# --- Stockage -------------------------------------------------------------------------------

def test_stockage_versions_uniques_et_nettoyage(tmp_path):
    from etg_moteur import stockage
    st = stockage.StockageLocal(str(tmp_path))
    assert stockage.lire_prix(st) is None
    t0 = dt.datetime(2026, 11, 9, 12, 0, 0, tzinfo=dt.UTC)
    for i in range(5):
        stockage.ecrire_prix(st, f"version {i}", "import" if i % 2 else "yahoo", t0 + dt.timedelta(minutes=i))
    texte, etat = stockage.lire_prix(st)
    assert texte == "version 4" and etat["source"] == "Yahoo Finance" and etat["mise_a_jour"] == "2026-11-09T12:04:00+00:00"
    assert len(st.lister("prix/")) == stockage.CONSERVER


def test_etat_apres_import_puis_mise_a_jour_reflete_la_derniere_ecriture(avec_prix, monkeypatch):
    assert avec_prix.get("/api/etat").json()["source"] == "Import CSV"
    monkeypatch.setattr(prix, "telecharger", lambda *a, **k: (bruts_synthetiques(), {}))
    assert avec_prix.post("/api/prix").status_code == 200
    assert avec_prix.get("/api/etat").json()["source"] == "Yahoo Finance"


def test_excel_reprend_exactement_le_site(avec_prix):
    """Le tableau de bord de l'Excel affiche les mêmes chiffres que l'API du site, pour des paramètres modifiés."""
    corps = {"vendredi": "2026-10-30", "top": 3, "tampon": 5, "filtre": False, "court": 8, "long": 39,
             "debut": "2024-06-07", "detenus": ["Santé", "Banques"]}
    bt = avec_prix.post("/api/backtest", json=corps).json()
    dec = avec_prix.post("/api/decision", json=corps).json()
    r = avec_prix.post("/api/excel", json=corps)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Tableau de bord"
    ws = wb["Tableau de bord"]
    cellules = {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}
    valeurs = list(cellules.values())
    for cle in ("ann", "sharpe", "perte_max", "rotation"):
        assert any(isinstance(v, float) and v == pytest.approx(bt["moteur"][cle], abs=1e-12) for v in valeurs), cle
    for v in bt["variantes"]:
        assert v["nom"] in valeurs
        assert any(isinstance(x, float) and x == pytest.approx(v["mesures"]["sharpe"], abs=1e-12) for x in valeurs)
    actions = [str(v) for v in valeurs if isinstance(v, str) and v.split(" ")[-1] in ("acheter", "garder", "vendre")]
    assert len(actions) == sum(1 for l in dec["lignes"] if l["action"] != "—")
    assert len(ws._charts) == 2
    serie = wb["Serie"]
    assert serie.max_row - 1 == len(bt["series"]["dates"])
    assert serie.cell(serie.max_row, 2).value == pytest.approx(bt["series"]["moteur"][-1])
    assert "Données réelles" not in " ".join(str(v) for v in valeurs)


def test_changer_les_parametres_ne_donne_jamais_404(avec_prix):
    for corps in ({"top": 3}, {"tampon": 4}, {"filtre": False}, {"utiliser_court": False}, {"univers": "9"},
                  {"debut": "2024-06-07"}, {"court": 8, "long": 39}, {"detenus": []}, {"vendredi": "2026-10-23"}):
        for route in ("/api/backtest", "/api/decision", "/api/excel"):
            r = avec_prix.post(route, json=corps)
            assert r.status_code == 200, (route, corps, r.status_code, r.text[:200])
