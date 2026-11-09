"""Chiffres de référence du cahier des charges (section 9), sur la copie locale de data/prix_hebdo.csv.

Ignoré quand le fichier est absent (les prix ne sont jamais dans git). Si Yahoo révise ses historiques,
comparer avec scripts/lancer_tests.py et scripts/signal_du_mois.py sur le même CSV.
"""
import datetime as dt
import pathlib

import pytest

from etg_moteur.donnees import lire_hebdo
from etg_moteur.moteur import Parametres, backtest
from etg_moteur.service import Requete, lancer_backtest, lancer_decision

CSV = pathlib.Path(__file__).resolve().parents[1] / "data" / "prix_hebdo.csv"
pytestmark = pytest.mark.skipif(not CSV.exists() or "2026-11-06" not in CSV.read_text()[-400:],
                                reason="data/prix_hebdo.csv absent ou arrêté avant le 06/11/2026")


@pytest.fixture(scope="module")
def texte():
    return CSV.read_text(encoding="utf-8")


def test_le_site_donne_les_memes_chiffres_que_les_scripts(texte):
    fin = dt.date(2026, 10, 30)
    ref = backtest(lire_hebdo(str(CSV)), Parametres(), dt.date(2024, 1, 5), fin)
    site = lancer_backtest(texte, Requete(fin=fin))
    for cle in ("ann", "vol", "sharpe", "perte_max", "rotation", "hhi", "beta", "vol_ex_ante", "diversification"):
        assert site["moteur"][cle] == ref[cle]
    assert site["reference"]["ann"] == ref["reference"]["ann"]


def test_chiffres_de_reference_section_9(texte):
    j = lancer_backtest(texte, Requete(fin=dt.date(2026, 10, 30)))
    assert j["moteur"]["ann"] == pytest.approx(0.2162, abs=5e-5)
    assert j["moteur"]["sharpe"] == pytest.approx(1.0209, abs=5e-5)
    assert j["moteur"]["perte_max"] == pytest.approx(-0.1769, abs=5e-5)
    assert j["moteur"]["rotation"] == pytest.approx(1.592, abs=5e-4)
    assert j["reference"]["ann"] == pytest.approx(0.1456, abs=5e-5)
    # Par défaut, le site s'arrête au dernier vendredi avec une ouverture de lundi : 30/10/2026
    assert lancer_backtest(texte, Requete())["moteur"] == j["moteur"]


def test_rotation_si_le_csv_s_arrete_au_30_10(texte):
    lignes = texte.splitlines(keepends=True)
    coupe = "".join(lignes[:-1])
    assert lancer_backtest(coupe, Requete())["moteur"]["rotation"] == pytest.approx(1.415, abs=5e-4)


def test_decision_du_30_10_2026(texte):
    j = lancer_decision(texte, Requete(vendredi=dt.date(2026, 10, 30),
                                       detenus=["Banques", "Pétrole & gaz", "Technologie", "Matières premières"]))
    actions = {l["etf"]: l["action"] for l in j["lignes"] if l["action"] != "—"}
    assert actions == {"Santé": "acheter", "Agroalimentaire": "acheter", "Technologie": "garder",
                       "Pétrole & gaz": "garder", "Banques": "vendre", "Matières premières": "vendre"}
    assert j["apercu"] is False


def test_variantes_identiques_a_lancer_tests(texte):
    d = lire_hebdo(str(CSV))
    fin = dt.date(2026, 10, 30)
    attendu = {"Base": Parametres(), "6 mois seuls": Parametres(utiliser_court=False), "Top 3": Parametres(top=3),
               "Sans filtre": Parametres(filtre=False), "Sans zone tampon": Parametres(tampon=4)}
    site = {v["nom"]: v["mesures"] for v in lancer_backtest(texte, Requete(fin=fin))["variantes"]}
    for nom, p in attendu.items():
        ref = backtest(d, p, dt.date(2024, 1, 5), fin)
        for cle in ("ann", "sharpe", "perte_max", "rotation", "monetaire"):
            assert site[nom][cle] == ref[cle], (nom, cle)
