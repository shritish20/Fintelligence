"""
Fintelligence — Subscription Gate Middleware
=============================================
FastAPI dependency that gates endpoints behind subscription tier.
Mounted read-only into all 4 backend containers via docker-compose.

Usage:
    from subscription_gate import require_pro, require_tier

    @router.get("/advanced-analysis")
    def endpoint(user_id: int = Depends(require_pro)):
        ...
"""
from datetime import datetime
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.orm import Session
from auth_utils import decode_token

_bearer = HTTPBearer(auto_error=False)

TIER_ORDER = {"free": 0, "pro": 1, "team": 2}


def _get_user_tier(user_id: int, db: Session) -> tuple:
    """Return (tier, expires_at). Defaults to free on any error."""
    try:
        row = db.execute(
            text("SELECT subscription_tier, subscription_expires_at FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if not row:
            return "free", None
        tier, expires_at = row
        if tier != "free" and expires_at and expires_at < datetime.utcnow():
            return "free", expires_at
        return tier or "free", expires_at
    except Exception:
        return "free", None


def require_tier(minimum_tier: str = "pro"):
    """
    Returns a FastAPI dependency enforcing a minimum subscription tier.
    Raises HTTP 402 if the user's tier is insufficient.
    """
    def _dep(
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
        db: Session = Depends(lambda: (_ for _ in ()).throw(RuntimeError("db not injected"))),
    ) -> int:
        if not credentials:
            raise HTTPException(status_code=401, detail="Not authenticated")
        payload = decode_token(credentials.credentials)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        user_id = int(payload["sub"])
        tier, _ = _get_user_tier(user_id, db)
        if TIER_ORDER.get(tier, 0) < TIER_ORDER.get(minimum_tier, 1):
            raise HTTPException(
                status_code=402,
                detail={
                    "code":        "SUBSCRIPTION_REQUIRED",
                    "message":     f"This feature requires a {minimum_tier.capitalize()} subscription.",
                    "required":    minimum_tier,
                    "current":     tier,
                    "upgrade_url": "/subscription",
                }
            )
        return user_id
    return _dep


require_pro  = require_tier("pro")
require_team = require_tier("team")
