"""Téléchargement des cours Yahoo Finance et construction du CSV hebdomadaire.

Ce module reprend à l'identique la logique de scripts/telecharger_prix.py et de
scripts/construire_prix.py : les deux scripts et le site l'utilisent. Il ne dépend que de la
bibliothèque standard.

Si un cours manque : dernier cours de la semaine (vendredi), premier cours suivant (lundi).
Avant le premier cours d'un ETF, on raccorde le fonds proche indiqué dans univers.py.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from zoneinfo import ZoneInfo

from .univers import SERIES, SYMBOLES

JOUR = dt.timedelta(days=1)
PREMIER_VENDREDI = dt.date(2008, 1, 4)
USER_AGENT = "etg-moteur/1.0"


class ErreurYahoo(RuntimeError):
    """Yahoo n'a pas répondu comme prévu (blocage, limite de débit, réponse inattendue)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def url_yahoo(symbole: str, maintenant: int | None = None) -> str:
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbole)}?period1=0"
            f"&period2={int(time.time()) if maintenant is None else maintenant}"
            f"&interval=1d&events=div%2Csplit&includeAdjustedClose=true")


def nom_fichier_brut(symbole: str) -> str:
    return symbole.replace("^", "_") + ".json"


def telecharger_symbole(symbole: str, essais: int = 3, attente_429: float = 20, delai: float = 30) -> bytes:
    """JSON brut de Yahoo pour un symbole. Réessaie après un 429 ; lève ErreurYahoo sinon."""
    url = url_yahoo(symbole)
    derniere = None
    for essai in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            corps = urllib.request.urlopen(req, timeout=delai).read()
            json.loads(corps)["chart"]["result"][0]
            return corps
        except urllib.error.HTTPError as e:
            derniere = ErreurYahoo(f"{symbole} : Yahoo a répondu HTTP {e.code}", e.code)
            if e.code == 429 and essai < essais - 1:
                time.sleep(attente_429)
                continue
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            derniere = ErreurYahoo(f"{symbole} : connexion à Yahoo impossible ({e})")
            break
        except (ValueError, KeyError, IndexError, TypeError):
            derniere = ErreurYahoo(f"{symbole} : réponse de Yahoo illisible")
            break
    raise derniere


def telecharger(symboles: Iterable[str] = SYMBOLES, pause: float = 1.2,
                rapport: Callable[[str, str], None] | None = None) -> tuple[dict[str, bytes], dict[str, str]]:
    """Télécharge tous les symboles. Renvoie (JSON bruts, erreurs par symbole)."""
    bruts: dict[str, bytes] = {}
    erreurs: dict[str, str] = {}
    for s in symboles:
        try:
            bruts[s] = telecharger_symbole(s)
            if rapport:
                rapport(s, "ok")
        except ErreurYahoo as e:
            erreurs[s] = str(e)
            if rapport:
                rapport(s, f"ÉCHEC {e.code or ''}".strip())
        time.sleep(pause)
    return bruts, erreurs


def lire_brut(corps: bytes | str) -> dict[dt.date, tuple[float, float]]:
    """Jour -> (ouverture ajustée des dividendes, clôture ajustée) pour un JSON Yahoo."""
    r = json.loads(corps)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    aj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    sortie = {}
    for i, x in enumerate(r["timestamp"]):
        if q["close"][i] is None or q["open"][i] is None:
            continue
        d = dt.datetime.fromtimestamp(x, dt.UTC).date()
        facteur = aj[i] / q["close"][i] if aj[i] else 1
        ouv = q["open"][i] or q["close"][i]  # Yahoo donne parfois une ouverture à 0
        sortie[d] = (ouv * facteur, aj[i])
    return sortie


def vendredi(D: dict, F: dt.date):
    return next((F - k * JOUR for k in range(5) if F - k * JOUR in D), None)


def lundi(D: dict, F: dt.date):
    return next((F + k * JOUR for k in range(3, 7) if F + k * JOUR in D), None)


def lire_tous(bruts: dict[str, bytes | str]) -> dict[str, dict]:
    """Cours de tous les symboles utilisés par univers.SERIES."""
    manquants = [s for ligne in SERIES for s in ligne[1:3] if s and s not in bruts]
    if manquants:
        raise ErreurYahoo("Cours manquants : " + ", ".join(sorted(set(manquants))))
    return {s: lire_brut(bruts[s]) for ligne in SERIES for s in ligne[1:3] if s}


def derniere_semaine(cours: dict[str, dict], dernier: dt.date | None = None) -> dt.date:
    """Dernier vendredi retenu : celui demandé, ou le dernier avec un lundi suivant pour le 1er ETF."""
    if dernier is not None:
        return dernier
    derniere = max(max(c) for c in cours.values())
    fin = derniere - dt.timedelta(days=(derniere.weekday() - 4) % 7)
    if lundi(cours[SERIES[0][1]], fin) is None:
        fin -= dt.timedelta(days=7)
    return fin


def dernier_vendredi_disponible(cours: dict[str, dict], maintenant: dt.datetime | None = None) -> dt.date:
    """Dernier vendredi dont la clôture est connue, même si l'ouverture du lundi suivant manque.

    Le jour même, avant 18 h à Paris, la dernière ligne de Yahoo peut être un cours en cours de
    séance : on l'écarte.
    """
    derniere = max(max(c) for c in cours.values())
    if maintenant is not None:
        paris = maintenant.astimezone(ZoneInfo("Europe/Paris"))
        if derniere >= paris.date() and paris.hour < 18:
            derniere -= JOUR
    return derniere - dt.timedelta(days=(derniere.weekday() - 4) % 7)


def construire(cours: dict[str, dict], dernier: dt.date | None = None) -> tuple[list[dt.date], dict]:
    """Table hebdomadaire : {série: {vendredi: (clôture, ouverture du lundi, origine)}}."""
    fin = derniere_semaine(cours, dernier)
    semaines, F = [], PREMIER_VENDREDI
    while F <= fin:
        semaines.append(F)
        F += dt.timedelta(days=7)
    table = {}
    for nom, etf, proche, _ in SERIES:
        E, P = cours.get(etf, {}), cours[proche]
        k = 1.0
        if E:
            d0 = min(E)
            while d0 not in P:
                d0 += JOUR
            k = E[d0][1] / P[d0][1]
        col = {}
        for F in semaines:
            c = o = oc = oo = None
            if E and F >= min(E):
                a, b = vendredi(E, F), lundi(E, F)
                if a: c, oc = E[a][1], "etf"
                if b: o, oo = E[b][0], "etf"
            a, b = vendredi(P, F), lundi(P, F)
            if c is None and a: c, oc = P[a][1] * k, "pxy"
            if o is None and b: o, oo = P[b][0] * k, "pxy"
            col[F] = (c, o, oc if oc == oo else f"{oc}/{oo}")
        table[nom] = col
    return semaines, table


def table_en_csv(semaines: list[dt.date], table: dict) -> str:
    """Texte du CSV hebdomadaire (fins de ligne \\r\\n, comme le script d'origine)."""
    sortie = io.StringIO(newline="")
    w = csv.writer(sortie)
    w.writerow(["vendredi"] + [f"{n[0]} {x}" for n in SERIES for x in ("cloture", "ouverture_lundi", "origine")])
    for F in semaines:
        ligne = [F.isoformat()]
        for n in SERIES:
            c, o, g = table[n[0]][F]
            ligne += [round(c, 4) if c else "", round(o, 4) if o else "", g]
        w.writerow(ligne)
    return sortie.getvalue()


def construire_csv(bruts: dict[str, bytes | str], dernier: dt.date | None = None) -> tuple[str, list[dt.date]]:
    """Du JSON brut de Yahoo au texte du CSV hebdomadaire, en mémoire."""
    semaines, table = construire(lire_tous(bruts), dernier)
    return table_en_csv(semaines, table), semaines
