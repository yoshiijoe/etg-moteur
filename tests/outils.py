"""Prix synthétiques pour les tests (marches aléatoires reproductibles au format Yahoo)."""
import datetime as dt
import json
import random

from etg_moteur import prix
from etg_moteur.univers import SYMBOLES


def jours_ouvres(debut, fin):
    j, sortie = debut, []
    while j <= fin:
        if j.weekday() < 5:
            sortie.append(j)
        j += dt.timedelta(days=1)
    return sortie


def json_marche(jours, graine, derive=0.0003, devise="EUR", niveau=100.0):
    gen = random.Random(graine)
    cours, v = [], niveau
    for _ in jours:
        v *= 1 + gen.gauss(derive, 0.01)
        cours.append(round(v, 4))
    ouv = [round(c * (1 + gen.gauss(0, 0.002)), 4) for c in cours]
    ts = [int(dt.datetime(j.year, j.month, j.day, 12, tzinfo=dt.UTC).timestamp()) for j in jours]
    return json.dumps({"chart": {"result": [{"meta": {"currency": devise}, "timestamp": ts, "indicators": {
        "quote": [{"close": cours, "open": ouv}], "adjclose": [{"adjclose": cours}]}}]}})


def bruts_synthetiques(fin=dt.date(2026, 11, 6)):
    debut = dt.date(2007, 6, 1)
    bruts = {}
    for i, s in enumerate(SYMBOLES):
        # les ETF récents (.PA) démarrent en 2023, les fonds proches (.DE, CSH) bien avant
        d = dt.date(2023, 7, 3) if s.endswith(".PA") and s not in ("CSH.PA",) else debut
        bruts[s] = json_marche(jours_ouvres(d, fin), graine=i + 1)
    return bruts


def csv_synthetique(fin=dt.date(2026, 11, 6), dernier=None):
    texte, _ = prix.construire_csv(bruts_synthetiques(fin), dernier or fin)
    return texte


def bruts_portefeuille(fin=dt.date(2026, 11, 9)):
    """Yahoo synthétique pour les lignes du portefeuille complet (Mowi en NOK, EURNOK=X) et leurs derniers cours."""
    from etg_moteur.prix_portefeuille import FX_NOK, SYMBOLES_PORTEFEUILLE
    bruts = {}
    for i, s in enumerate(SYMBOLES_PORTEFEUILLE):
        if s == FX_NOK:
            bruts[s] = json_marche(jours_ouvres(dt.date(2007, 6, 1), fin), 500, 0.0, "NOK", 10.5)
        else:
            nok = s.endswith(".OL")
            bruts[s] = json_marche(jours_ouvres(dt.date(2012, 1, 2), fin), 100 + i, 0.0004, "NOK" if nok else "EUR",
                                   2200.0 if nok else 60.0)
    return bruts


def bruts_complets(fin=dt.date(2026, 11, 9)):
    return {**bruts_synthetiques(fin), **bruts_portefeuille(fin)}
