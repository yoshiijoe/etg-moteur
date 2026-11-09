#!/usr/bin/env python3
"""Envoie data/prix_hebdo.csv au site (repli si Yahoo bloque les serveurs Vercel).

  ETG_SITE_URL=https://mon-site.vercel.app .venv/bin/python scripts/envoyer_prix.py [fichier.csv]

Le mot de passe du site est demandé au clavier (ou lu dans ETG_SITE_PASSWORD). Il n'est jamais enregistré.
"""
import getpass, http.cookiejar, json, os, pathlib, sys, urllib.error, urllib.request

RACINE = pathlib.Path(__file__).resolve().parents[1]
site = os.environ.get("ETG_SITE_URL", "").rstrip("/")
if not site.startswith("https://"):
    sys.exit("Indiquer l'adresse du site dans ETG_SITE_URL (https://...).")
fichier = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "data" / "prix_hebdo.csv"
if not fichier.exists():
    sys.exit(f"Fichier introuvable : {fichier}")
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
etat = appeler("/api/importer", fichier.read_bytes(), "text/csv")
print(f"Prix envoyés : dernier vendredi {etat['dernier_vendredi']}, {etat['semaines']} semaines.")
