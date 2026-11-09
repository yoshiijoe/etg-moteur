#!/usr/bin/env python3
"""Construit data/prix_hebdo.csv : clôture du vendredi et ouverture du lundi, dividendes réinvestis.

Si un cours manque : dernier cours de la semaine (vendredi), premier cours suivant (lundi).
Avant le premier cours d'un ETF, on raccorde le fonds proche indiqué dans univers.py.
La logique est dans src/etg_moteur/prix.py (le site l'utilise aussi).
"""
import datetime as dt, pathlib, sys
RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
from etg_moteur import prix
from etg_moteur.univers import SERIES

DERNIER = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None

brut = RACINE / "data" / "brut"
bruts = {s: (brut / prix.nom_fichier_brut(s)).read_text() for ligne in SERIES for s in ligne[1:3] if s}
texte, semaines = prix.construire_csv(bruts, DERNIER)
sortie = RACINE / "data" / "prix_hebdo.csv"
with open(sortie, "w", newline="", encoding="utf-8") as f:
    f.write(texte)
print(sortie, semaines[0], semaines[-1], len(semaines), "semaines")
