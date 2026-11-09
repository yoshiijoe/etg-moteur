#!/usr/bin/env python3
"""Télécharge les cours quotidiens depuis Yahoo Finance vers data/brut/ (usage personnel, non redistribués)."""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from etg_moteur import prix
from etg_moteur.univers import SYMBOLES

BRUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "brut"
BRUT.mkdir(parents=True, exist_ok=True)
for s in SYMBOLES + ["^STOXX"]:
    try:
        (BRUT / prix.nom_fichier_brut(s)).write_bytes(prix.telecharger_symbole(s))
        print("ok", s)
    except prix.ErreurYahoo as e:
        print("ÉCHEC", s, e.code or e)
    time.sleep(1.2)
