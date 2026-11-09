"""Stockage des prix du site : Vercel Blob privé en production, dossier local en développement.

Le navigateur ne reçoit jamais l'adresse du fichier : seule l'API lit et écrit le stockage.
Variables d'environnement : ETG_STOCKAGE_LOCAL (dossier, développement et tests) ou
BLOB_READ_WRITE_TOKEN (posée par Vercel quand le Blob est relié au projet).

Chaque mise à jour écrit un nouveau fichier `prix/<date UTC>_<source>.csv` : le Blob met les lectures
en cache, un nom unique évite de relire une ancienne version. La dernière version est la plus récente
dans la liste (jamais mise en cache) ; les plus anciennes sont supprimées.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import re

PREFIXE = "prix/"
CONSERVER = 3
MODELE = re.compile(r"^prix/(\d{8}T\d{6}Z)_(yahoo|import)\.csv$")
SOURCES = {"yahoo": "Yahoo Finance", "import": "Import CSV", "saisie": "Saisie"}


class ErreurStockage(RuntimeError):
    pass


class StockageLocal:
    def __init__(self, dossier: str):
        self.dossier = pathlib.Path(dossier)
        (self.dossier / "prix").mkdir(parents=True, exist_ok=True)

    def lister(self, prefixe: str) -> list[str]:
        dossier = self.dossier / prefixe
        return sorted(p.relative_to(self.dossier).as_posix() for p in dossier.glob("*") if p.is_file()) if dossier.is_dir() else []

    def lire(self, nom: str) -> bytes | None:
        chemin = self.dossier / nom
        return chemin.read_bytes() if chemin.exists() else None

    def ecrire(self, nom: str, contenu: bytes, type_contenu: str) -> None:
        chemin = self.dossier / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)

    def supprimer(self, nom: str) -> None:
        (self.dossier / nom).unlink(missing_ok=True)


class StockageBlob:
    """Vercel Blob en accès privé (SDK Python `vercel`)."""

    def __init__(self):
        try:
            from vercel.blob import sync as blob
        except ImportError as e:  # pragma: no cover
            raise ErreurStockage("Le paquet « vercel » n'est pas installé.") from e
        self.blob = blob

    def _appel(self, f, *args, **kw):
        try:
            return f(*args, **kw)
        except self.blob.BlobNotFoundError:
            return None
        except self.blob.BlobError as e:
            raise ErreurStockage(f"Stockage indisponible : {e}") from e

    def lister(self, prefixe: str) -> list[str]:
        return sorted(b.pathname for b in (self._appel(lambda: list(self.blob.query_blobs(prefix=prefixe))) or []))

    def lire(self, nom: str) -> bytes | None:
        r = self._appel(self.blob.get_blob, nom, access="private")
        return None if r is None else r.body

    def ecrire(self, nom: str, contenu: bytes, type_contenu: str) -> None:
        self._appel(self.blob.put_blob, nom, contenu, access="private", content_type=type_contenu,
                    allow_overwrite=True)

    def supprimer(self, nom: str) -> None:
        self._appel(self.blob.delete_blob, nom)


def ouvrir():
    dossier = os.environ.get("ETG_STOCKAGE_LOCAL")
    if dossier:
        return StockageLocal(dossier)
    if os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("VERCEL"):
        return StockageBlob()
    raise ErreurStockage("Aucun stockage configuré (ETG_STOCKAGE_LOCAL ou Vercel Blob).")


def _etat(nom: str) -> dict:
    horodatage, source = MODELE.match(nom).groups()
    quand = dt.datetime.strptime(horodatage, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
    return dict(mise_a_jour=quand.isoformat(timespec="seconds"), source=SOURCES[source])


def lire_prix(stockage) -> tuple[str, dict] | None:
    """(texte du CSV, état) de la version la plus récente, ou None s'il n'y en a pas."""
    noms = [n for n in stockage.lister(PREFIXE) if MODELE.match(n)]
    for nom in reversed(noms):  # la plus récente d'abord ; si un fichier a disparu, on essaie la précédente
        contenu = stockage.lire(nom)
        if contenu is not None:
            return contenu.decode("utf-8"), _etat(nom)
    return None


def ecrire_prix(stockage, texte_csv: str, source: str, maintenant: dt.datetime | None = None) -> dict:
    """Range une nouvelle version ('yahoo' ou 'import'), supprime les plus anciennes. Renvoie l'état."""
    maintenant = (maintenant or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    nom = f"{PREFIXE}{maintenant:%Y%m%dT%H%M%SZ}_{source}.csv"
    stockage.ecrire(nom, texte_csv.encode("utf-8"), "text/csv")
    anciens = [n for n in stockage.lister(PREFIXE) if MODELE.match(n) and n != nom]
    for n in sorted(anciens)[:-(CONSERVER - 1)]:
        stockage.supprimer(n)
    return _etat(nom)


# --- Autres familles de fichiers versionnés (prix du portefeuille, positions) -------------------------------

PREFIXE_PRIX_PORTEFEUILLE = "prix_portefeuille/"
PREFIXE_POSITIONS = "positions/"
CONSERVER_POSITIONS = 10  # historique des 10 dernières versions


def _modele(prefixe: str, extension: str):
    return re.compile(rf"^{re.escape(prefixe)}(\d{{8}}T\d{{6}}Z)_(yahoo|import|saisie)\.{extension}$")


def lire_version(stockage, prefixe: str, extension: str) -> tuple[bytes, dict] | None:
    """(contenu, état) de la version la plus récente d'une famille de fichiers, ou None."""
    modele = _modele(prefixe, extension)
    for nom in reversed([n for n in stockage.lister(prefixe) if modele.match(n)]):
        contenu = stockage.lire(nom)
        if contenu is not None:
            return contenu, _etat_famille(nom, modele)
    return None


def _etat_famille(nom: str, modele) -> dict:
    horodatage, source = modele.match(nom).groups()
    quand = dt.datetime.strptime(horodatage, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
    return dict(mise_a_jour=quand.isoformat(timespec="seconds"), source=SOURCES[source])


def ecrire_version(stockage, prefixe: str, extension: str, contenu: bytes, type_contenu: str, source: str,
                   conserver: int, maintenant: dt.datetime | None = None) -> dict:
    """Range une nouvelle version, supprime les plus anciennes (on en garde `conserver`). Renvoie l'état."""
    maintenant = (maintenant or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    nom = f"{prefixe}{maintenant:%Y%m%dT%H%M%SZ}_{source}.{extension}"
    stockage.ecrire(nom, contenu, type_contenu)
    modele = _modele(prefixe, extension)
    anciens = sorted(n for n in stockage.lister(prefixe) if modele.match(n) and n != nom)
    for n in anciens[:-(conserver - 1)] if conserver > 1 else anciens:
        stockage.supprimer(n)
    return _etat_famille(nom, modele)


def lister_versions(stockage, prefixe: str, extension: str) -> list[dict]:
    """Versions disponibles, de la plus récente à la plus ancienne : nom et état."""
    modele = _modele(prefixe, extension)
    return [dict(nom=n, **_etat_famille(n, modele)) for n in sorted(stockage.lister(prefixe), reverse=True) if modele.match(n)]
