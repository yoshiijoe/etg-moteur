"""Stockage des prix du site : Vercel Blob privé en production, dossier local en développement.

Le navigateur ne reçoit jamais l'adresse du fichier : seule l'API lit et écrit le stockage.
Variables d'environnement : ETG_STOCKAGE_LOCAL (dossier, développement et tests) ou
BLOB_READ_WRITE_TOKEN (posée par Vercel quand le Blob est relié au projet).
"""
from __future__ import annotations

import json
import os
import pathlib

FICHIER_PRIX = "prix_hebdo.csv"
FICHIER_ETAT = "etat.json"


class ErreurStockage(RuntimeError):
    pass


class StockageLocal:
    def __init__(self, dossier: str):
        self.dossier = pathlib.Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)

    def lire(self, nom: str) -> bytes | None:
        chemin = self.dossier / nom
        return chemin.read_bytes() if chemin.exists() else None

    def ecrire(self, nom: str, contenu: bytes, type_contenu: str) -> None:
        (self.dossier / nom).write_bytes(contenu)


class StockageBlob:
    """Vercel Blob en accès privé (SDK Python `vercel`)."""

    def __init__(self):
        try:
            from vercel.blob import sync as blob
        except ImportError as e:  # pragma: no cover
            raise ErreurStockage("Le paquet « vercel » n'est pas installé.") from e
        self.blob = blob

    def lire(self, nom: str) -> bytes | None:
        try:
            return self.blob.get_blob(nom, access="private").body
        except self.blob.BlobNotFoundError:
            return None
        except self.blob.BlobError as e:
            raise ErreurStockage(f"Lecture du stockage impossible : {e}") from e

    def ecrire(self, nom: str, contenu: bytes, type_contenu: str) -> None:
        try:
            self.blob.put_blob(nom, contenu, access="private", content_type=type_contenu, allow_overwrite=True,
                               cache_control_max_age=60)
        except self.blob.BlobError as e:
            raise ErreurStockage(f"Écriture dans le stockage impossible : {e}") from e


def ouvrir():
    dossier = os.environ.get("ETG_STOCKAGE_LOCAL")
    if dossier:
        return StockageLocal(dossier)
    if os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("VERCEL"):
        return StockageBlob()
    raise ErreurStockage("Aucun stockage configuré (ETG_STOCKAGE_LOCAL ou Vercel Blob).")


def lire_prix(stockage) -> str | None:
    brut = stockage.lire(FICHIER_PRIX)
    return brut.decode("utf-8") if brut is not None else None


def lire_etat(stockage) -> dict:
    brut = stockage.lire(FICHIER_ETAT)
    return json.loads(brut) if brut else {}


def ecrire_prix(stockage, texte_csv: str, etat: dict) -> None:
    stockage.ecrire(FICHIER_PRIX, texte_csv.encode("utf-8"), "text/csv")
    stockage.ecrire(FICHIER_ETAT, json.dumps(etat, ensure_ascii=False).encode("utf-8"), "application/json")
