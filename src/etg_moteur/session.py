"""Mot de passe du site et cookie de session signé (HMAC-SHA256), sans dépendance externe."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

NOM_COOKIE = "etg_session"
DUREE = 7 * 24 * 3600


def _signer(secret: str, message: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def mot_de_passe_valide(saisi: str, attendu: str | None) -> bool:
    """Comparaison en temps constant. Faux si aucun mot de passe n'est configuré."""
    if not attendu or not saisi:
        return False
    return hmac.compare_digest(hashlib.sha256(saisi.encode()).digest(), hashlib.sha256(attendu.encode()).digest())


def creer_jeton(secret: str, maintenant: float | None = None) -> str:
    expire = int((time.time() if maintenant is None else maintenant) + DUREE)
    return f"{expire}.{_signer(secret, str(expire))}"


def jeton_valide(jeton: str | None, secret: str | None, maintenant: float | None = None) -> bool:
    if not jeton or not secret or "." not in jeton:
        return False
    expire, signature = jeton.split(".", 1)
    if not expire.isdigit() or not hmac.compare_digest(signature, _signer(secret, expire)):
        return False
    return int(expire) > (time.time() if maintenant is None else maintenant)
