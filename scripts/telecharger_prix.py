#!/usr/bin/env python3
"""Télécharge les cours quotidiens depuis Yahoo Finance vers data/brut/ (usage personnel, non redistribués)."""
import json, pathlib, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from etg_moteur.univers import SYMBOLES

BRUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "brut"
BRUT.mkdir(parents=True, exist_ok=True)
for s in SYMBOLES + ["^STOXX"]:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(s)}?period1=0"
           f"&period2={int(time.time())}&interval=1d&events=div%2Csplit&includeAdjustedClose=true")
    for essai in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "etg-moteur/1.0"})
            corps = urllib.request.urlopen(req, timeout=30).read()
            json.loads(corps)["chart"]["result"][0]
            (BRUT / (s.replace("^", "_") + ".json")).write_bytes(corps)
            print("ok", s)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and essai < 2:
                time.sleep(20)
                continue
            print("ÉCHEC", s, e.code)
            break
    time.sleep(1.2)
