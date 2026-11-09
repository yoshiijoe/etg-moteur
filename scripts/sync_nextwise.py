#!/usr/bin/env python3
"""Synchronise les positions réelles depuis NextWise vers le stockage du site ETG Moteur.

Identifiants lus depuis .env.local ou les variables d'environnement :
NEXTWISE_EMAIL, NEXTWISE_PASSWORD, NEXTWISE_PORTFOLIO_ID.
"""
from __future__ import annotations

import os
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from etg_moteur import nextwise

FICHIER_ENV = RACINE / ".env.local"


def charger_env() -> None:
    if not FICHIER_ENV.exists():
        return
    with open(FICHIER_ENV, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                k, v = ligne.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip("\"'"))


def main() -> None:
    charger_env()
    print("Connexion à NextWise...")
    res = nextwise.synchroniser()
    print(f"Connexion réussie : Club « {res['nom_club']} »")
    print(f"Cash : {res['cash']:,.2f} € | Valeur totale : {res['valeur_totale']:,.2f} € | Perf NextWise : {res['performance_nw']}")
    print(f"Lignes synchronisées : {len(res['quantites'])}")
    for ticker, qte in sorted(res["quantites"].items()):
        print(f"  {ticker:<8} : {int(qte):>6} titres")
    print(f"Positions enregistrées avec succès dans le stockage privé.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Erreur : {e}", file=sys.stderr)
        sys.exit(1)
