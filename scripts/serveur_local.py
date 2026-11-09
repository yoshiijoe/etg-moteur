#!/usr/bin/env python3
"""Serveur de développement : le site (public/) et l'API sur http://localhost:8765.

Les prix sont rangés dans .dev-stockage/ (ignoré par git). Le mot de passe local vient de
ETG_DEV_PASSWORD (par défaut « local ») : il ne sert qu'à ce serveur de développement.
Pour copier vos prix : cp data/prix_hebdo.csv .dev-stockage/prix_hebdo.csv
"""
import os, pathlib, sys
RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
os.environ.setdefault("ETG_STOCKAGE_LOCAL", str(RACINE / ".dev-stockage"))
os.environ.setdefault("SITE_PASSWORD", os.environ.get("ETG_DEV_PASSWORD", "local"))
os.environ.setdefault("SESSION_SECRET", "secret-de-developpement-local")
os.environ.setdefault("CRON_SECRET", "cron-de-developpement-local")
import importlib.util
import uvicorn
from fastapi.staticfiles import StaticFiles

spec = importlib.util.spec_from_file_location("api_index", RACINE / "api" / "index.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app
app.mount("/", StaticFiles(directory=RACINE / "public", html=True), name="public")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8765")))
