#!/usr/bin/env python3
"""Envoie data/prix_msci_hebdo.csv au site, pour les tranches de 6 mois depuis 2001.

  ETG_SITE_URL=https://etg-moteur.vercel.app .venv/bin/python scripts/envoyer_msci.py

Construire d'abord le fichier avec scripts/construire_prix_msci.py. Le mot de passe du site est demandé au
clavier (ou lu dans ETG_SITE_PASSWORD) et n'est jamais enregistré.
"""
import getpass, http.cookiejar, json, os, pathlib, sys, urllib.error, urllib.request

RACINE = pathlib.Path(__file__).resolve().parents[1]
site = os.environ.get("ETG_SITE_URL", "").rstrip("/")
if not site.startswith("https://"):
    sys.exit("Indiquer l'adresse du site dans ETG_SITE_URL (https://...).")
fichier = RACINE / "data" / "prix_msci_hebdo.csv"
if not fichier.exists():
    sys.exit("Fichier introuvable : lancer d'abord scripts/construire_prix_msci.py.")
mot_de_passe = os.environ.get("ETG_SITE_PASSWORD") or getpass.getpass("Mot de passe du site : ")
ouvreur = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def appeler(chemin, corps, type_contenu):
    req = urllib.request.Request(site + chemin, data=corps, method="POST", headers={"Content-Type": type_contenu})
    try:
        return json.load(ouvreur.open(req, timeout=120))
    except urllib.error.HTTPError as e:
        try:
            message = json.load(e).get("erreur", "")
        except ValueError:
            message = ""
        sys.exit(f"Erreur {e.code} sur {chemin} : {message}")


appeler("/api/connexion", json.dumps({"motdepasse": mot_de_passe}).encode(), "application/json")
etat = appeler("/api/importer-msci", fichier.read_bytes(), "text/csv")
print(f"Indices MSCI envoyés : {etat['premier_vendredi']} → {etat['dernier_vendredi']}, {etat['semaines']} semaines.")
