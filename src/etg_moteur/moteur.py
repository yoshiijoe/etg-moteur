"""Règles du moteur : signal, top N, zone tampon, filtre absolu, rééquilibrage mensuel.

Convention de temps : la ligne t correspond au vendredi t. La décision prise avec la clôture
du vendredi t est exécutée à l'ouverture du lundi suivant. Le rendement de la semaine va de
l'ouverture du lundi t-1 à celle du lundi t, avec les poids décidés le vendredi t-1.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Parametres:
    court: int = 13
    long: int = 26
    utiliser_court: bool = True
    top: int = 4
    tampon: int = 6
    filtre: bool = True
    nb_monetaires: int = 2
    taux_sans_risque: float = 0.025
    semaines_ex_ante: int = 180


@dataclass
class Donnees:
    """Listes alignées sur `dates`. Un prix absent vaut None."""
    dates: list[dt.date]
    noms: list[str]
    cloture: list[list]
    ouverture: list[list]
    monetaire_cloture: list[list]
    monetaire_ouverture: list[list]
    reference_cloture: list
    reference_ouverture: list


def signal(p: Parametres, prix: list, t: int):
    """Moyenne des performances court et long terme, ou long terme seul. None si prix manquant."""
    if t < p.long or not prix[t] or not prix[t - p.long] or not prix[t - p.court]:
        return None
    perf_long = prix[t] / prix[t - p.long] - 1
    if not p.utiliser_court:
        return perf_long
    return ((prix[t] / prix[t - p.court] - 1) + perf_long) / 2


def rangs(signaux: list) -> list:
    """Rang 1 = meilleur signal ; ex aequo au même rang (comme RANG dans Excel)."""
    valeurs = [s for s in signaux if s is not None]
    return [None if s is None else 1 + sum(v > s for v in valeurs) for s in signaux]


def selection(p: Parametres, signaux: list, detenu: list) -> tuple[list, int]:
    """Lignes retenues et nombre de places à remplacer par les refuges."""
    r = rangs(signaux)
    n = len(signaux)
    garde = [1 if detenu[i] and r[i] is not None and r[i] <= p.tampon else 0 for i in range(n)]
    places = p.top - sum(garde)
    ajout = [0] * n
    for i in range(n):
        if garde[i] or r[i] is None:
            continue
        meilleurs = sum(1 for j in range(n) if r[j] is not None and r[j] < r[i] and not garde[j])
        if meilleurs < places:
            ajout[i] = 1
    retenu = [
        0 if not garde[i] + ajout[i] else (1 if not p.filtre or signaux[i] > 0 else 0)
        for i in range(n)
    ]
    return retenu, max(0, p.top - sum(retenu))


def decider(d: Donnees, p: Parametres) -> tuple[list[list], list[int]]:
    """Poids décidés chaque vendredi (ETF puis 2 refuges) et drapeaux de rééquilibrage."""
    T, A = len(d.dates), len(d.noms)
    poids, reequilibrage = [], []
    detenu, ref1, ref2 = [0] * A, 0.0, 0.0
    for t in range(T):
        drapeau = 1 if t + 1 < T and d.dates[t + 1].month != d.dates[t].month else 0
        if drapeau:
            signaux = [signal(p, d.cloture[i], t) for i in range(A)]
            # Les détentions conservées utilisent les rangs du jour : la zone tampon ne joue qu'ici.
            detenu, libres = selection(p, signaux, detenu)
            ref1 = 1 / p.top if libres >= 1 and p.nb_monetaires >= 1 else 0.0
            ref2 = 1 / p.top if libres >= 2 and p.nb_monetaires >= 2 else 0.0
        poids.append([x / p.top for x in detenu] + [ref1, ref2])
        reequilibrage.append(drapeau)
    return poids, reequilibrage


def _ecart_type(x: list) -> float:
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def perte_max(rendements: list) -> float:
    v = sommet = 1.0
    pire = 0.0
    for r in rendements:
        v *= 1 + r
        sommet = max(sommet, v)
        pire = min(pire, v / sommet - 1)
    return pire


def mesures(rendements: list, rf: float = 0.025) -> dict:
    """Rendement annualisé, volatilité, Sharpe et perte max d'une suite hebdomadaire."""
    n = len(rendements)
    valeur = 1.0
    for r in rendements:
        valeur *= 1 + r
    an = valeur ** (52 / n) - 1
    vol = _ecart_type(rendements) * math.sqrt(52)
    return dict(n=n, perf=valeur - 1, ann=an, vol=vol, sharpe=(an - rf) / vol if vol else 0.0,
                perte_max=perte_max(rendements))


def backtest(d: Donnees, p: Parametres, debut: dt.date, fin: dt.date) -> dict:
    """Backtest de la poche seule, poids remis à égalité chaque semaine (comme le classeur)."""
    A = len(d.noms)
    poids, reeq = decider(d, p)
    idx = [t for t in range(len(d.dates)) if debut <= d.dates[t] <= fin]
    r, rr, hhi, cash, mon, rotation, nb = [], [], [], [], [], 0.0, 0
    for t in idx:
        w, av = poids[t], poids[t - 1]
        hhi.append(sum(x * x for x in w))
        cash.append(1 - sum(w))
        mon.append(w[A] + w[A + 1])
        rotation += sum(abs(a - b) for a, b in zip(w, av)) / 2
        nb += reeq[t]
        if t == idx[0]:
            continue
        x = sum(av[i] * (d.ouverture[i][t] / d.ouverture[i][t - 1] - 1) for i in range(A) if av[i])
        x += av[A] * (d.monetaire_ouverture[0][t] / d.monetaire_ouverture[0][t - 1] - 1)
        x += av[A + 1] * (d.monetaire_ouverture[1][t] / d.monetaire_ouverture[1][t - 1] - 1)
        r.append(x)
        rr.append(d.reference_ouverture[t] / d.reference_ouverture[t - 1] - 1)
    n = len(r)
    m = mesures(r, p.taux_sans_risque)
    ma, mb = sum(r) / n, sum(rr) / n
    cov = sum((a - ma) * (b - mb) for a, b in zip(r, rr))
    va, vb = sum((a - ma) ** 2 for a in r), sum((b - mb) ** 2 for b in rr)
    m.update(rotation=rotation * 52 / n, hhi=sum(hhi) / len(hhi), beta=cov / vb if vb else 0.0,
             correlation=cov / math.sqrt(va * vb) if va and vb else 0.0, cash=sum(cash) / len(cash),
             monetaire=sum(mon) / len(mon), reequilibrages=nb, rendements=r, rendements_reference=rr,
             dates=[d.dates[t] for t in idx[1:]], poids=poids, reference=mesures(rr, p.taux_sans_risque))
    m.update(_ex_ante(d, p, poids[idx[-1]], idx[-1], m["ann"]))
    return m


def _ex_ante(d: Donnees, p: Parametres, w: list, fin: int, an: float) -> dict:
    """Poids de fin de fenêtre appliqués aux dernières semaines où tous les prix existent."""
    series = d.cloture + d.monetaire_cloture
    lignes = []
    for t in range(max(1, fin - p.semaines_ex_ante + 1), fin + 1):
        if all(s[t] and s[t - 1] for s in series):
            lignes.append([s[t] / s[t - 1] - 1 for s in series])
    if len(lignes) < 2:
        return dict(ex_ante_semaines=len(lignes), vol_ex_ante=0.0, perf_sur_vol_ex_ante=0.0, diversification=0.0)
    port = [sum(a * b for a, b in zip(w, l)) for l in lignes]
    v = _ecart_type(port) * math.sqrt(52)
    sig = [_ecart_type([l[j] for l in lignes]) * math.sqrt(52) for j in range(len(series))]
    return dict(ex_ante_semaines=len(lignes), vol_ex_ante=v, perf_sur_vol_ex_ante=an / v if v else 0.0,
                diversification=sum(a * b for a, b in zip(w, sig)) / v if v else 0.0)
