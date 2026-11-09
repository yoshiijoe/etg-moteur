"""Décision du mois : ce que la règle demande à partir des détentions actuelles."""
from __future__ import annotations

import calendar
import datetime as dt

from .moteur import Donnees, Parametres, rangs, selection, signal


def dernier_vendredi(annee: int, mois: int) -> dt.date:
    jour = dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
    return jour - dt.timedelta(days=(jour.weekday() - 4) % 7)


def decision(d: Donnees, p: Parametres, t: int, detenus: set[str]) -> dict:
    """Signal, rang et décision de chaque ETF à la clôture du vendredi t."""
    inconnus = detenus - set(d.noms)
    if inconnus:
        raise ValueError(f"ETF inconnus : {', '.join(sorted(inconnus))}")
    sig = [signal(p, d.cloture[i], t) for i in range(len(d.noms))]
    detenu = [1 if n in detenus else 0 for n in d.noms]
    retenu, libres = selection(p, sig, detenu)
    lignes = []
    for i, n in enumerate(d.noms):
        c = d.cloture[i]
        perf = lambda k: c[t] / c[t - k] - 1 if c[t] and c[t - k] else None
        if retenu[i]:
            action = "garder" if detenu[i] else "acheter"
        else:
            action = "vendre" if detenu[i] else "—"
        lignes.append(dict(etf=n, signal=sig[i], court=perf(p.court), long=perf(p.long), detenu=bool(detenu[i]), retenu=bool(retenu[i]), action=action))
    r = rangs(sig)
    for l, k in zip(lignes, r):
        l["rang"] = k
    refuges = min(libres, p.nb_monetaires)
    return dict(date=d.dates[t], lignes=sorted(lignes, key=lambda l: (l["rang"] is None, l["rang"] or 0)),
                refuges=refuges, cash=libres - refuges, poids=1 / p.top)
