"""Deuxième référence du backtest : tous les ETF à parts égales, rééquilibrés chaque mois comme le moteur.

Elle répond à la question : « choisir 4 ETF rapporte-t-il plus que de garder les 10 ? »

Mêmes règles de temps que le moteur (voir moteur.py) :
- la décision se prend à la clôture du dernier vendredi du mois (même drapeau que `decider`) ;
- elle est exécutée à l'ouverture du lundi suivant, prix d'exécution de la ligne ;
- la semaine t va de l'ouverture du lundi t-1 à celle du lundi t ;
- entre deux rééquilibrages, les poids dérivent avec les prix.

Quand un ETF n'a pas de prix à la date de décision (la Défense avant 07/2023), on répartit à parts égales entre
les ETF disponibles. Aucune ligne du moteur n'est touchée : ce module ne fait que lire `Donnees`.
"""
from __future__ import annotations

import datetime as dt

from .moteur import Donnees, Parametres, _ex_ante, mesures


def _disponibles(d: Donnees, t: int) -> list[int]:
    """ETF ayant une clôture (décision) et une ouverture du lundi (exécution) à la ligne t."""
    return [i for i in range(len(d.noms)) if d.cloture[i][t] and d.ouverture[i][t]]


def _egaux(n_total: int, dispo: list[int]) -> list[float]:
    w = [0.0] * n_total
    for i in dispo:
        w[i] = 1 / len(dispo)
    return w


def backtest_parts_egales(d: Donnees, p: Parametres, debut: dt.date, fin: dt.date) -> dict:
    """Mesures de la référence « ETF à parts égales » sur la même période que `moteur.backtest`.

    Renvoie les clés des variantes (ann, vol, sharpe, perte_max, rotation, hhi, beta, vol_ex_ante, diversification)
    plus `rendements` et `dates` (une valeur par semaine, comme le moteur).
    """
    A, T = len(d.noms), len(d.dates)
    idx = [t for t in range(T) if debut <= d.dates[t] <= fin]
    if len(idx) < 3:
        raise ValueError("Période trop courte pour la référence à parts égales.")
    dispo = _disponibles(d, idx[0])
    if not dispo:
        raise ValueError("Aucun ETF disponible au début de la période.")
    w = _egaux(A, dispo)           # poids détenus à partir de l'ouverture du lundi de la première ligne
    r, rr, hhi, rotation, nb = [], [], [], 0.0, 0
    poids_fin = w
    for t in idx[1:]:
        hhi.append(sum(x * x for x in w))
        rend_i = [(d.ouverture[i][t] / d.ouverture[i][t - 1] - 1) if w[i] and d.ouverture[i][t] and d.ouverture[i][t - 1] else 0.0
                  for i in range(A)]
        x = sum(w[i] * rend_i[i] for i in range(A))
        r.append(x)
        rr.append(d.reference_ouverture[t] / d.reference_ouverture[t - 1] - 1)
        # dérive des poids jusqu'à l'ouverture du lundi t
        w = [w[i] * (1 + rend_i[i]) / (1 + x) for i in range(A)]
        if t + 1 < T and d.dates[t + 1].month != d.dates[t].month:   # même drapeau que `decider`
            cible = _egaux(A, _disponibles(d, t))
            if sum(cible):
                rotation += sum(abs(a - b) for a, b in zip(cible, w)) / 2
                w = cible
                nb += 1
        poids_fin = w
    n = len(r)
    m = mesures(r, p.taux_sans_risque)
    ma, mb = sum(r) / n, sum(rr) / n
    cov = sum((a - ma) * (b - mb) for a, b in zip(r, rr))
    vb = sum((b - mb) ** 2 for b in rr)
    m.update(rotation=rotation * 52 / n, hhi=sum(hhi) / len(hhi), beta=cov / vb if vb else 0.0, reequilibrages=nb,
             rendements=r, dates=[d.dates[t] for t in idx[1:]])
    # Volatilité ex-ante et diversification : poids de fin de période, même fonction que pour le moteur
    m.update(_ex_ante(d, p, list(poids_fin) + [0.0, 0.0], idx[-1], m["ann"]))
    return m


def libelle(nb_etf: int) -> str:
    return f"{nb_etf} ETF à parts égales"

