"""Sensibilité aux paramètres, hors échantillon, sélection glissante et bootstrap."""
from __future__ import annotations

import datetime as dt
import random
from itertools import product

from .moteur import Donnees, Parametres, backtest, mesures


def grille(nb_etf: int) -> list[Parametres]:
    configs = []
    for court, long, top, ecart, filtre in product((None, 4, 8, 13, 17), (26, 39, 52), (3, 4, 5), (0, 1, 2, 3), (True, False)):
        tampon = min(top + ecart, nb_etf)
        if court is None:
            configs.append(Parametres(court=long, long=long, utiliser_court=False, top=top, tampon=tampon, filtre=filtre))
        else:
            configs.append(Parametres(court=court, long=long, top=top, tampon=tampon, filtre=filtre))
    return list(dict.fromkeys(configs))


def libelle(p: Parametres) -> str:
    lb = f"{p.court}+{p.long} sem" if p.utiliser_court else f"{p.long} sem seul"
    return f"{lb}, top {p.top}, tampon {p.tampon}, {'filtre' if p.filtre else 'sans filtre'}"


def calculer_grille(d: Donnees, debut: dt.date, fin: dt.date) -> dict:
    return {p: backtest(d, p, debut, fin) for p in grille(len(d.noms))}


def sous_periode(res: dict, debut: dt.date, fin: dt.date) -> list:
    return [r for x, r in zip(res["dates"], res["rendements"]) if debut <= x <= fin]


def meilleur(resultats: dict, debut: dt.date, fin: dt.date) -> Parametres:
    return max(resultats, key=lambda p: mesures(sous_periode(resultats[p], debut, fin))["sharpe"])


def glissant(resultats: dict, premiere: int, derniere: int, annees_retro: int = 5) -> tuple[list, list]:
    """Chaque 1er janvier, on prend la meilleure configuration des années passées pour l'année suivante."""
    chaine, choix = [], []
    for an in range(premiere, derniere + 1):
        p = meilleur(resultats, dt.date(an - annees_retro, 1, 1), dt.date(an - 1, 12, 31))
        choix.append((an, p))
        chaine += sous_periode(resultats[p], dt.date(an, 1, 1), dt.date(an, 12, 31))
    return chaine, choix


def bootstrap_sharpe(a: list, b: list, tirages: int = 2000, bloc: int = 13, graine: int = 2026) -> dict:
    """Intervalle à 90 % du Sharpe de a et de l'écart de Sharpe a − b, par blocs de semaines."""
    alea = random.Random(graine)
    n = len(a)
    sa, sd = [], []
    for _ in range(tirages):
        i, ra, rb = 0, [], []
        while i < n:
            s = alea.randrange(n)
            for k in range(bloc):
                j = (s + k) % n
                ra.append(a[j])
                rb.append(b[j])
            i += bloc
        ra, rb = ra[:n], rb[:n]
        x, y = mesures(ra)["sharpe"], mesures(rb)["sharpe"]
        sa.append(x)
        sd.append(x - y)
    sa.sort()
    sd.sort()
    q = lambda l, f: l[int(f * (len(l) - 1))]
    return dict(sharpe_5=q(sa, .05), sharpe_95=q(sa, .95), ecart_5=q(sd, .05), ecart_95=q(sd, .95),
                proba_ecart_positif=sum(x > 0 for x in sd) / len(sd))
