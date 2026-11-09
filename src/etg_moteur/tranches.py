"""Backtest par tranches de 6 mois : l'horizon réel du jeu.

Chaque tranche démarre comme une équipe au début de la compétition :
- portefeuille vide ; la première décision se prend à la clôture du premier vendredi de la tranche
  (top N, filtre ; la zone tampon ne joue pas puisqu'on ne détient rien), exécutée le lundi suivant ;
- ensuite, la règle normale : rééquilibrage le dernier vendredi de chaque mois ;
- la tranche se termine à l'ouverture du lundi qui suit son dernier vendredi.

Tranches calendaires : janvier-juin et juillet-décembre. On compare le moteur, le STOXX Europe 600
(même calendrier) et les ETF à parts égales (mêmes dates de rééquilibrage).
Les règles viennent de `moteur.py` (`signal`, `selection`) : rien n'y est modifié.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics as st

from .moteur import Donnees, Parametres, mesures, selection, signal


def bornes_tranches(dates: list[dt.date]) -> list[tuple[str, int, int]]:
    """(libellé, ligne du 1er vendredi, ligne du dernier vendredi) pour chaque semestre présent dans les dates."""
    groupes: dict[tuple[int, int], list[int]] = {}
    for t, d in enumerate(dates):
        groupes.setdefault((d.year, 1 if d.month <= 6 else 2), []).append(t)
    return [(f"{a} S{s}", lignes[0], lignes[-1]) for (a, s), lignes in sorted(groupes.items())]


def _rendement(d: Donnees, w: list, t: int) -> float:
    A = len(d.noms)
    r = sum(w[i] * (d.ouverture[i][t] / d.ouverture[i][t - 1] - 1) for i in range(A) if w[i])
    r += w[A] * (d.monetaire_ouverture[0][t] / d.monetaire_ouverture[0][t - 1] - 1)
    r += w[A + 1] * (d.monetaire_ouverture[1][t] / d.monetaire_ouverture[1][t - 1] - 1)
    return r


def une_tranche(d: Donnees, p: Parametres, t0: int, t1: int) -> dict | None:
    """Moteur parti de zéro sur [t0, t1]. None si l'historique ou les prix manquent."""
    A, T = len(d.noms), len(d.dates)
    if t0 < p.long or t1 + 1 >= T + 1:
        return None
    detenu, w = [0] * A, None
    r_mot, r_ref, r_eg, poids = [], [], [], []
    w_eg = None
    for t in range(t0, t1 + 1):
        if t > t0:
            if not all(d.ouverture[i][t] and d.ouverture[i][t - 1] for i in range(A) if w[i] or w_eg[i]):
                return None
            r_mot.append(_rendement(d, w, t))
            r_ref.append(d.reference_ouverture[t] / d.reference_ouverture[t - 1] - 1)
            r_eg.append(sum(w_eg[i] * (d.ouverture[i][t] / d.ouverture[i][t - 1] - 1) for i in range(A) if w_eg[i]))
        fin_de_mois = t + 1 < T and d.dates[t + 1].month != d.dates[t].month
        if t == t0 or (fin_de_mois and t < t1):
            sig = [signal(p, d.cloture[i], t) for i in range(A)]
            if all(s is None for s in sig):
                return None
            detenu, libres = selection(p, sig, detenu)
            ref1 = 1 / p.top if libres >= 1 and p.nb_monetaires >= 1 else 0.0
            ref2 = 1 / p.top if libres >= 2 and p.nb_monetaires >= 2 else 0.0
            w = [x / p.top for x in detenu] + [ref1, ref2]
            dispo = [i for i in range(A) if d.cloture[i][t] and d.ouverture[i][t]]
            w_eg = [1 / len(dispo) if i in dispo else 0.0 for i in range(A)]
            poids.append((d.dates[t], [d.noms[i] for i in range(A) if detenu[i]], ref1 + ref2))
    # Dernière semaine : du lundi après t1-1 au lundi après t1 est déjà comptée ; on ajoute la semaine qui
    # se termine à l'ouverture suivant t1 seulement si elle existe (sinon la tranche s'arrête à t1).
    if t1 + 1 < T and all(d.ouverture[i][t1 + 1] for i in range(A) if w[i]) and d.reference_ouverture[t1 + 1]:
        r_mot.append(_rendement(d, w, t1 + 1))
        r_ref.append(d.reference_ouverture[t1 + 1] / d.reference_ouverture[t1] - 1)
        r_eg.append(sum(w_eg[i] * (d.ouverture[i][t1 + 1] / d.ouverture[i][t1] - 1) for i in range(A) if w_eg[i]))
    if len(r_mot) < 20:
        return None
    m, r, e = mesures(r_mot, p.taux_sans_risque), mesures(r_ref, p.taux_sans_risque), mesures(r_eg, p.taux_sans_risque)
    return dict(debut=d.dates[t0], fin=d.dates[t1], semaines=len(r_mot), moteur=m["perf"], stoxx=r["perf"],
                parts_egales=e["perf"], ecart=m["perf"] - r["perf"], perte_max=m["perte_max"],
                perte_max_stoxx=r["perte_max"], vol=m["vol"], choix=poids)


def toutes(d: Donnees, p: Parametres, premiere: dt.date | None = None) -> list[dict]:
    lignes = []
    for libelle, t0, t1 in bornes_tranches(d.dates):
        if premiere and d.dates[t0] < premiere:
            continue
        res = une_tranche(d, p, t0, t1)
        if res:
            lignes.append(dict(tranche=libelle, **res))
    return lignes


def synthese(lignes: list[dict]) -> dict:
    """Moyennes et dispersion sur les tranches complètes (au moins 24 semaines)."""
    pleines = [l for l in lignes if l["semaines"] >= 24]
    n = len(pleines)
    mot = [l["moteur"] for l in pleines]
    ref = [l["stoxx"] for l in pleines]
    eg = [l["parts_egales"] for l in pleines]
    ec = [l["ecart"] for l in pleines]
    sd = st.stdev(ec) if n > 1 else 0.0
    return dict(
        tranches=n,
        moteur_moyenne=st.mean(mot), moteur_mediane=st.median(mot),
        stoxx_moyenne=st.mean(ref), stoxx_mediane=st.median(ref),
        parts_egales_moyenne=st.mean(eg),
        ecart_moyen=st.mean(ec), ecart_median=st.median(ec), ecart_ecart_type=sd,
        t_ecart=st.mean(ec) / (sd / math.sqrt(n)) if sd else 0.0,
        part_bat_stoxx=sum(x > 0 for x in ec) / n,
        part_bat_parts_egales=sum(a > b for a, b in zip(mot, eg)) / n,
        part_positive=sum(x > 0 for x in mot) / n,
        pire=min(mot), meilleure=max(mot),
        pire_ecart=min(ec), meilleur_ecart=max(ec),
        perte_max_moyenne=st.mean(l["perte_max"] for l in pleines),
    )
