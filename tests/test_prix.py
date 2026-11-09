import datetime as dt
import json

import pytest

from etg_moteur import prix
from etg_moteur.donnees import lire_hebdo_texte
from etg_moteur.univers import ETF, SERIES, SYMBOLES


def json_yahoo(jours, base=100.0, ajuste=1.0, ouverture=None):
    """JSON de Yahoo minimal : une clôture par jour, ajustée par un facteur constant."""
    ts = [int(dt.datetime(j.year, j.month, j.day, 12, tzinfo=dt.UTC).timestamp()) for j in jours]
    clo = [base + i * 0.1 for i in range(len(jours))]
    ouv = ouverture if ouverture is not None else [c - 0.05 for c in clo]
    return json.dumps({"chart": {"result": [{"timestamp": ts, "indicators": {
        "quote": [{"close": clo, "open": ouv}], "adjclose": [{"adjclose": [c * ajuste for c in clo]}]}}]}})


def jours_ouvres(debut, fin):
    j, sortie = debut, []
    while j <= fin:
        if j.weekday() < 5:
            sortie.append(j)
        j += dt.timedelta(days=1)
    return sortie


def bruts_synthetiques(fin=dt.date(2026, 11, 6)):
    jours = jours_ouvres(dt.date(2007, 6, 1), fin)
    return {s: json_yahoo(jours, base=50 + 3 * i) for i, s in enumerate(SYMBOLES)}


def test_lire_brut_ajuste_la_cloture_et_l_ouverture():
    jours = jours_ouvres(dt.date(2024, 1, 1), dt.date(2024, 1, 12))
    cours = prix.lire_brut(json_yahoo(jours, base=100, ajuste=0.5))
    ouverture, cloture = cours[dt.date(2024, 1, 1)]
    assert cloture == pytest.approx(50.0)
    assert ouverture == pytest.approx(99.95 * 0.5)


def test_lire_brut_ouverture_a_zero_remplacee_par_la_cloture():
    jours = [dt.date(2024, 1, 1), dt.date(2024, 1, 2)]
    cours = prix.lire_brut(json_yahoo(jours, base=100, ouverture=[0, 99.0]))
    assert cours[dt.date(2024, 1, 1)][0] == pytest.approx(100.0)


def test_lire_brut_ignore_les_jours_sans_cours():
    jours = [dt.date(2024, 1, 1), dt.date(2024, 1, 2)]
    brut = json.loads(json_yahoo(jours))
    brut["chart"]["result"][0]["indicators"]["quote"][0]["close"][0] = None
    assert list(prix.lire_brut(json.dumps(brut))) == [dt.date(2024, 1, 2)]


def test_construire_csv_en_memoire_est_lisible_par_le_moteur():
    texte, semaines = prix.construire_csv(bruts_synthetiques(), dt.date(2026, 11, 6))
    assert semaines[0] == dt.date(2008, 1, 4) and semaines[-1] == dt.date(2026, 11, 6)
    assert all(b - a == dt.timedelta(days=7) for a, b in zip(semaines, semaines[1:]))
    assert texte.splitlines()[0].startswith("vendredi,Banques cloture,Banques ouverture_lundi,Banques origine")
    assert "\r\n" in texte  # fins de ligne identiques au script d'origine
    d = lire_hebdo_texte(texte)
    assert d.noms == ETF and len(d.dates) == len(semaines)
    assert d.cloture[0][-1] is not None
    # Dernier vendredi : pas de lundi suivant dans les données
    assert d.ouverture[0][-1] is None


def test_construire_sans_date_s_arrete_au_dernier_vendredi_avec_lundi():
    _, semaines = prix.construire_csv(bruts_synthetiques(), None)
    assert semaines[-1] == dt.date(2026, 10, 30)


def test_construire_signale_les_cours_manquants():
    bruts = bruts_synthetiques()
    del bruts["BNK.PA"]
    with pytest.raises(prix.ErreurYahoo, match="BNK.PA"):
        prix.construire_csv(bruts)


def test_origine_pxy_avant_le_lancement_de_l_etf():
    bruts = bruts_synthetiques()
    bruts["DEFS.PA"] = json_yahoo(jours_ouvres(dt.date(2023, 7, 3), dt.date(2026, 11, 6)))
    texte, semaines = prix.construire_csv(bruts, dt.date(2026, 11, 6))
    d = lire_hebdo_texte(texte)
    i = d.noms.index("Défense")
    assert d.cloture[i][semaines.index(dt.date(2023, 7, 7))] is not None
    lignes = texte.splitlines()
    colonnes = lignes[0].split(",")
    j = colonnes.index("Défense origine")
    assert lignes[1 + semaines.index(dt.date(2023, 1, 6))].split(",")[j] == "pxy"
    assert lignes[1 + semaines.index(dt.date(2024, 1, 5))].split(",")[j] == "etf"


def test_dernier_vendredi_disponible():
    cours = {"X": {dt.date(2026, 11, 6): (1, 1), dt.date(2026, 11, 9): (1, 1)}}
    assert prix.dernier_vendredi_disponible(cours) == dt.date(2026, 11, 6)
    cours = {"X": {dt.date(2026, 11, 6): (1, 1)}}
    assert prix.dernier_vendredi_disponible(cours) == dt.date(2026, 11, 6)


def test_dernier_vendredi_ecarte_la_seance_en_cours():
    cours = {"X": {dt.date(2026, 10, 30): (1, 1), dt.date(2026, 11, 6): (1, 1)}}
    midi = dt.datetime(2026, 11, 6, 11, 0, tzinfo=dt.UTC)  # 12 h à Paris : séance en cours
    soir = dt.datetime(2026, 11, 6, 17, 30, tzinfo=dt.UTC)  # 18 h 30 à Paris
    assert prix.dernier_vendredi_disponible(cours, midi) == dt.date(2026, 10, 30)
    assert prix.dernier_vendredi_disponible(cours, soir) == dt.date(2026, 11, 6)


def test_telecharger_regroupe_succes_et_erreurs(monkeypatch):
    def faux(symbole, **_):
        if symbole == "ENRG.PA":
            raise prix.ErreurYahoo("ENRG.PA : Yahoo a répondu HTTP 429", 429)
        return b"{}"

    monkeypatch.setattr(prix, "telecharger_symbole", faux)
    bruts, erreurs = prix.telecharger(["BNK.PA", "ENRG.PA"], pause=0)
    assert list(bruts) == ["BNK.PA"] and "429" in erreurs["ENRG.PA"]


def test_serie_complete():
    assert len(SERIES) == 13 and "EXSA.DE" in SYMBOLES
