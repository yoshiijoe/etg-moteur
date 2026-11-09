"""Synchronisation des positions depuis NextWise vers le stockage privé du site."""
from __future__ import annotations

import http.cookiejar
import json
import os
import re
import urllib.parse
import urllib.request

from . import composition as comp, service_portefeuille as sp, stockage

URL_BASE = "https://the-challenge.nextwise.fr"
PORTFOLIO_ID_DEFAUT = "EP9kbUTT1dc"


class ErreurNextwise(RuntimeError):
    """Erreur de connexion ou de données NextWise."""


def nettoyer_nombre(texte: str | None) -> float:
    if not texte:
        return 0.0
    brut = re.sub(r"[^\d,\.\-]", "", texte).replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(brut)
    except ValueError:
        return 0.0


def recuperer_donnees(email: str, password: str, pf_id: str) -> dict:
    """Interroge NextWise et renvoie le cash, la valeur totale et la liste des positions."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": f"{URL_BASE}/login"
    }

    try:
        # Initialisation de la session
        req_init = urllib.request.Request(f"{URL_BASE}/login", headers={"User-Agent": headers["User-Agent"]})
        opener.open(req_init)

        # Authentification
        login_payload = json.dumps({"email": email, "passwrd": password}).encode("utf-8")
        req_login = urllib.request.Request(f"{URL_BASE}/rest/_login.php", data=login_payload, headers=headers)
        resp_login = opener.open(req_login)
        res_auth = json.loads(resp_login.read().decode("utf-8"))
        if not res_auth.get("isAuth"):
            erreurs = res_auth.get("errors") or "Identifiants invalides"
            raise ErreurNextwise(f"Échec d'authentification NextWise : {erreurs}")

        # Récupération du portefeuille
        pf_payload = json.dumps({"id": pf_id}).encode("utf-8")
        req_pf = urllib.request.Request(f"{URL_BASE}/rest/pf/pg-portfolio-data.php", data=pf_payload, headers=headers)
        resp_pf = opener.open(req_pf)
        res_pf = json.loads(resp_pf.read().decode("utf-8"))
    except Exception as e:
        if isinstance(e, ErreurNextwise):
            raise
        raise ErreurNextwise(f"Erreur de communication avec NextWise : {e}")

    pf_data = res_pf.get("pfData")
    if not pf_data:
        raise ErreurNextwise(f"Portefeuille NextWise #{pf_id} introuvable.")

    return {
        "nom_club": pf_data.get("name"),
        "cash": nettoyer_nombre(pf_data.get("cash")),
        "valeur_totale": nettoyer_nombre(pf_data.get("totalPfVal")),
        "performance": pf_data.get("performance"),
        "positions": pf_data.get("positions", [])
    }


def synchroniser(st=None, email: str | None = None, password: str | None = None, pf_id: str | None = None) -> dict:
    """Récupère les positions sur NextWise et les enregistre dans le stockage privé."""
    email = email or os.environ.get("NEXTWISE_EMAIL")
    password = password or os.environ.get("NEXTWISE_PASSWORD")
    pf_id = pf_id or os.environ.get("NEXTWISE_PORTFOLIO_ID", PORTFOLIO_ID_DEFAUT)

    if not email or not password:
        raise ErreurNextwise("NEXTWISE_EMAIL et NEXTWISE_PASSWORD non configurés.")

    st = st or stockage.ouvrir()
    donnees = recuperer_donnees(email, password, pf_id)
    cash_net = donnees["cash"]
    positions_nw = donnees["positions"]

    quantites_recues: dict[str, float] = {}
    for pos in positions_nw:
        ticker = pos.get("ticker", "").strip().upper()
        qte = float(pos.get("cntShares") or 0)
        if ticker and qte > 0:
            quantites_recues[ticker] = qte

    actuel = sp.lire_positions(st)
    if actuel:
        saisie_base = actuel[0]
        lignes, _, _ = sp.lignes_depuis_saisie(saisie_base)
    else:
        lignes = comp.portefeuille_cible()

    nouvelle_saisie = sp.saisie_en_dict(lignes, quantites_recues, cash_net)
    etat = sp.ecrire_positions(st, nouvelle_saisie)

    return {
        "ok": True,
        "nom_club": donnees["nom_club"],
        "cash": cash_net,
        "valeur_totale": donnees["valeur_totale"],
        "performance_nw": donnees["performance"],
        "quantites": quantites_recues,
        "etat": etat
    }
