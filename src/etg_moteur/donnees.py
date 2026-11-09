"""Lecture des prix hebdomadaires (CSV produit par scripts/construire_prix.py)."""
from __future__ import annotations

import csv
import datetime as dt
import io

from .moteur import Donnees
from .univers import ETF, MONETAIRES, REFERENCE


def lire_hebdo(chemin: str, sans=()) -> Donnees:
    with open(chemin, encoding="utf-8", newline="") as f:
        return lire_hebdo_texte(f, sans)


def lire_hebdo_texte(source, sans=()) -> Donnees:
    """Comme lire_hebdo, à partir d'un texte ou d'un fichier ouvert (le site lit le CSV en mémoire)."""
    if isinstance(source, str):
        source = io.StringIO(source, newline="")
    lignes = list(csv.DictReader(source))

    def serie(nom: str, champ: str) -> list:
        return [float(l[f"{nom} {champ}"]) if l[f"{nom} {champ}"] else None for l in lignes]

    noms = [n for n in ETF if n not in sans]
    return Donnees(
        dates=[dt.date.fromisoformat(l["vendredi"]) for l in lignes],
        noms=noms,
        cloture=[serie(n, "cloture") for n in noms],
        ouverture=[serie(n, "ouverture_lundi") for n in noms],
        monetaire_cloture=[serie(n, "cloture") for n in MONETAIRES],
        monetaire_ouverture=[serie(n, "ouverture_lundi") for n in MONETAIRES],
        reference_cloture=serie(REFERENCE, "cloture"),
        reference_ouverture=serie(REFERENCE, "ouverture_lundi"),
    )
