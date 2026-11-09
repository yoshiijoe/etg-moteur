#!/usr/bin/env python3
"""Calcule ce que la règle du moteur demande, à partir des détentions actuelles.

Exemples :
  python scripts/signal_du_mois.py
  python scripts/signal_du_mois.py --date 2026-11-27 --detenus "Santé,Technologie,Pétrole & gaz,Agroalimentaire"
La décision officielle se prend à la clôture du dernier vendredi du mois.
"""
import argparse, datetime as dt, pathlib, sys
RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
from etg_moteur.application import decision, dernier_vendredi
from etg_moteur.donnees import lire_hebdo
from etg_moteur.moteur import Parametres

a = argparse.ArgumentParser()
a.add_argument("--date", help="vendredi à utiliser (AAAA-MM-JJ), par défaut le dernier disponible")
a.add_argument("--detenus", default="Santé,Technologie,Pétrole & gaz,Agroalimentaire",
               help="ETF détenus, séparés par des virgules (par défaut le top 4 déployé le 02/11/2026)")
a.add_argument("--prix", default=str(RACINE / "data" / "prix_hebdo.csv"))
x = a.parse_args()

d = lire_hebdo(x.prix)
p = Parametres()
if x.date:
    cible = dt.date.fromisoformat(x.date)
    if cible not in d.dates:
        sys.exit(f"Pas de cours pour le vendredi {cible}. Dernier disponible : {d.dates[-1]}")
    t = d.dates.index(cible)
else:
    t = max(i for i in range(len(d.dates)) if all(c[i] for c in d.cloture))
res = decision(d, p, t, {s.strip() for s in x.detenus.split(",") if s.strip()})
jour = res["date"]
officiel = dernier_vendredi(jour.year, jour.month)
print(f"Clôture du vendredi {jour:%d/%m/%Y}")
if jour != officiel:
    print(f"APERÇU SEULEMENT : la décision officielle se prend le {officiel:%d/%m/%Y}, avec la clôture de ce jour-là.")
print()
print(f"{'Rang':>4}  {'ETF':20} {'3 mois':>8} {'6 mois':>8} {'Signal':>8}  Détenu  Décision")
for l in res["lignes"]:
    f = lambda v: "   —" if v is None else f"{v:+8.1%}"
    print(f"{l['rang'] or '—':>4}  {l['etf']:20} {f(l['court'])} {f(l['long'])} {f(l['signal'])}  {'oui' if l['detenu'] else '   '}     {l['action']}")
print()
print(f"Chaque ligne retenue pèse {res['poids']:.0%} de la poche moteur (8 % du portefeuille).")
if res["refuges"] or res["cash"]:
    print(f"Places remplacées par le filtre : {res['refuges']} ETF monétaire(s), {res['cash']} en cash.")
print("Prix : data/prix_hebdo.csv, à vérifier sur le cours du jour avant de passer les ordres.")
