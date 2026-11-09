"""API du site du moteur ETG (FastAPI, une seule fonction Vercel).

Toutes les routes /api sont protégées par le cookie de session, sauf la connexion et le Cron
(protégé par CRON_SECRET). Aucun secret dans le code : variables d'environnement Vercel.
"""
import datetime as dt
import hmac
import os
import pathlib
import sys
import time
from typing import Literal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from etg_moteur import excel, prix, service, session, stockage
from etg_moteur.univers import SYMBOLES

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Erreur(Exception):
    def __init__(self, message: str, statut: int = 400):
        self.message, self.statut = message, statut


@app.exception_handler(Erreur)
async def _erreur(_: Request, e: Erreur):
    return JSONResponse({"erreur": e.message}, status_code=e.statut)


@app.exception_handler(service.ErreurRequete)
async def _erreur_requete(_: Request, e: service.ErreurRequete):
    return JSONResponse({"erreur": str(e)}, status_code=400)


@app.exception_handler(stockage.ErreurStockage)
async def _erreur_stockage(_: Request, e: stockage.ErreurStockage):
    return JSONResponse({"erreur": str(e)}, status_code=503)


@app.exception_handler(RequestValidationError)
async def _erreur_validation(_: Request, e: RequestValidationError):
    champs = ", ".join(".".join(str(x) for x in err["loc"][1:]) or "requête" for err in e.errors())
    return JSONResponse({"erreur": f"Paramètres invalides : {champs}."}, status_code=400)


# --- Authentification ---------------------------------------------------------------------

def _secret_session() -> str | None:
    return os.environ.get("SESSION_SECRET")


def connecte(request: Request) -> None:
    if not session.jeton_valide(request.cookies.get(session.NOM_COOKIE), _secret_session()):
        raise Erreur("Connexion requise.", 401)


class Connexion(BaseModel):
    motdepasse: str = Field(max_length=200)


@app.post("/api/connexion")
def connexion(corps: Connexion):
    if not _secret_session() or not os.environ.get("SITE_PASSWORD"):
        raise Erreur("Le site n'est pas configuré (SITE_PASSWORD et SESSION_SECRET manquent).", 503)
    if not session.mot_de_passe_valide(corps.motdepasse, os.environ.get("SITE_PASSWORD")):
        time.sleep(1)  # ralentit les essais répétés
        raise Erreur("Mot de passe incorrect.", 401)
    reponse = JSONResponse({"ok": True})
    reponse.set_cookie(session.NOM_COOKIE, session.creer_jeton(_secret_session()), max_age=session.DUREE,
                       httponly=True, secure=True, samesite="strict", path="/")
    return reponse


@app.post("/api/deconnexion")
def deconnexion():
    reponse = JSONResponse({"ok": True})
    reponse.delete_cookie(session.NOM_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return reponse


# --- Prix ---------------------------------------------------------------------------------

def _prix_stockes() -> tuple[str, dict]:
    st = stockage.ouvrir()
    texte = stockage.lire_prix(st)
    if texte is None:
        raise Erreur("Aucun prix en mémoire. Cliquer sur « Mettre à jour les prix » ou importer un CSV.", 404)
    return texte, stockage.lire_etat(st)


def _decrire(texte: str, etat: dict) -> dict:
    return dict(disponible=True, mise_a_jour=etat.get("mise_a_jour"), source=etat.get("source", "Yahoo Finance"),
                avertissements=service.AVERTISSEMENTS, **service.etat_donnees(texte))


@app.get("/api/etat", dependencies=[Depends(connecte)])
def etat():
    st = stockage.ouvrir()
    texte = stockage.lire_prix(st)
    if texte is None:
        return dict(disponible=False, avertissements=service.AVERTISSEMENTS)
    return _decrire(texte, stockage.lire_etat(st))


def mettre_a_jour_prix() -> dict:
    """Télécharge Yahoo, reconstruit le CSV hebdomadaire et le range dans le stockage."""
    bruts, erreurs = prix.telecharger(SYMBOLES, pause=0.3, paralleles=4)
    if erreurs:
        blocage = any("403" in m or "429" in m for m in erreurs.values())
        detail = " ; ".join(sorted(erreurs.values())[:3])
        suite = (" Yahoo bloque probablement les serveurs : importer un CSV (bouton « Importer un CSV »)."
                 if blocage else "")
        raise Erreur(f"Téléchargement Yahoo incomplet ({len(erreurs)} symbole(s) en échec) : {detail}.{suite}", 502)
    cours = prix.lire_tous(bruts)
    maintenant = dt.datetime.now(dt.UTC)
    dernier = prix.dernier_vendredi_disponible(cours, maintenant)
    texte, _ = prix.construire_csv(bruts, dernier)
    etat_csv = service.etat_donnees(texte)  # vérifie que le moteur sait lire le fichier
    etat = dict(mise_a_jour=maintenant.isoformat(timespec="seconds"), source="Yahoo Finance")
    stockage.ecrire_prix(stockage.ouvrir(), texte, etat)
    return dict(disponible=True, avertissements=service.AVERTISSEMENTS, **etat, **etat_csv)


@app.post("/api/prix", dependencies=[Depends(connecte)])
def prix_yahoo():
    try:
        return mettre_a_jour_prix()
    except prix.ErreurYahoo as e:
        raise Erreur(str(e), 502)


@app.get("/api/cron")
def cron(request: Request):
    secret = os.environ.get("CRON_SECRET")
    recu = request.headers.get("authorization", "")
    if not secret or not hmac.compare_digest(recu, f"Bearer {secret}"):
        raise Erreur("Non autorisé.", 401)
    try:
        return mettre_a_jour_prix()
    except prix.ErreurYahoo as e:
        raise Erreur(str(e), 502)


@app.post("/api/importer", dependencies=[Depends(connecte)])
async def importer(request: Request):
    """Importe un CSV hebdomadaire (même format que data/prix_hebdo.csv) : repli si Yahoo bloque."""
    corps = await request.body()
    if not corps or len(corps) > 4_000_000:
        raise Erreur("Fichier vide ou trop gros (4 Mo au maximum).")
    try:
        texte = corps.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Erreur("Le fichier doit être encodé en UTF-8.")
    etat_csv = service.etat_donnees(texte)  # lève une erreur lisible si le format est faux
    service.lancer_backtest(texte, service.Requete(), avec_variantes=False)  # le moteur doit pouvoir tourner
    etat = dict(mise_a_jour=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), source="Import CSV")
    stockage.ecrire_prix(stockage.ouvrir(), texte, etat)
    return dict(disponible=True, avertissements=service.AVERTISSEMENTS, **etat, **etat_csv)


# --- Backtest, décision, Excel ------------------------------------------------------------

class Parametres(BaseModel):
    debut: dt.date = service.DEBUT_DEFAUT
    fin: dt.date | None = None
    univers: Literal["9", "10"] = "10"
    court: int = Field(13, ge=1, le=104)
    long: int = Field(26, ge=2, le=104)
    utiliser_court: bool = True
    top: int = Field(4, ge=1, le=10)
    tampon: int = Field(6, ge=1, le=10)
    filtre: bool = True
    detenus: list[str] | None = Field(None, max_length=10)
    vendredi: dt.date | None = None

    def requete(self) -> service.Requete:
        valeurs = self.model_dump()
        if valeurs["detenus"] is None:
            valeurs["detenus"] = list(service.DETENUS_DEFAUT)
        return service.Requete(**valeurs)


@app.post("/api/backtest", dependencies=[Depends(connecte)])
def backtest(corps: Parametres | None = None):
    texte, etat = _prix_stockes()
    return service.lancer_backtest(texte, (corps or Parametres()).requete())


@app.post("/api/decision", dependencies=[Depends(connecte)])
def decision(corps: Parametres | None = None):
    texte, _ = _prix_stockes()
    return service.lancer_decision(texte, (corps or Parametres()).requete())


@app.post("/api/excel", dependencies=[Depends(connecte)])
def telecharger_excel(corps: Parametres | None = None):
    texte, etat = _prix_stockes()
    req = (corps or Parametres()).requete()
    bt = service.lancer_backtest(texte, req)
    dec = service.lancer_decision(texte, req)
    contenu = excel.construire_classeur(texte, bt, dec, {**etat, **service.etat_donnees(texte)})
    return Response(contenu, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{excel.nom_fichier(dec)}"',
                             "Cache-Control": "no-store"})


@app.middleware("http")
async def entetes(request: Request, appel):
    reponse = await appel(request)
    reponse.headers["Cache-Control"] = reponse.headers.get("Cache-Control", "no-store")
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    return reponse
