"""
Fintelligence — Subscription & Payment Module (Razorpay)
=========================================================
Mounted into volguard backend. Handles:
  - Creating Razorpay orders
  - Verifying payment webhooks
  - Upgrading user subscription tier in DB
  - Checking subscription status / gating features

Pricing (INR):
  pro  — ₹499/month  (individual trader)
  team — ₹1999/month (up to 5 seats, family / prop desk)
"""

import os
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_utils import decode_token

log = logging.getLogger("fintelligence.subscriptions")

# ── Razorpay client ───────────────────────────────────────────────────────────
RZP_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RZP_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

rzp_client: Optional[razorpay.Client] = None
if RZP_KEY_ID and RZP_KEY_SECRET:
    rzp_client = razorpay.Client(auth=(RZP_KEY_ID, RZP_KEY_SECRET))
    log.info("Razorpay client initialised")
else:
    log.warning("RAZORPAY_KEY_ID / KEY_SECRET not set — payment endpoints disabled")

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

# ── Pricing table ─────────────────────────────────────────────────────────────
PLANS = {
    "pro":  {"amount_paise": 49900,  "months": 1, "label": "Pro — ₹499/month"},
    "team": {"amount_paise": 199900, "months": 1, "label": "Team — ₹1,999/month"},
}

# ── Auth helper ───────────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)

def _require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> int:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return int(payload["sub"])


# ── Models ────────────────────────────────────────────────────────────────────
class CreateOrderRequest(BaseModel):
    tier: str   # "pro" | "team"

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/plans")
def get_plans():
    """Public — return available plans and pricing."""
    return {
        "plans": [
            {
                "tier":          tier,
                "label":         info["label"],
                "amount_paise":  info["amount_paise"],
                "amount_inr":    info["amount_paise"] / 100,
                "months":        info["months"],
            }
            for tier, info in PLANS.items()
        ],
        "razorpay_key_id": RZP_KEY_ID,  # needed by frontend Razorpay.js
    }


@router.get("/status")
def get_subscription_status(
    user_id: int = Depends(_require_user),
    db: Session = Depends(lambda: None),   # injected by volguard app at registration
):
    """Return current user's subscription tier and expiry."""
    # NOTE: db injected via app.dependency_overrides at registration time
    from volguard_v6_final import SessionLocal, User  # late import avoids circular
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        is_active = (
            user.subscription_tier != "free"
            and user.subscription_expires_at is not None
            and user.subscription_expires_at > datetime.utcnow()
        )
        return {
            "tier":       user.subscription_tier,
            "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            "is_active":  is_active,
        }
    finally:
        db.close()


@router.post("/create-order")
def create_order(
    payload: CreateOrderRequest,
    user_id: int = Depends(_require_user),
):
    """Create a Razorpay order. Frontend uses the order_id to open checkout."""
    if not rzp_client:
        raise HTTPException(status_code=503, detail="Payments not configured on this server")

    tier = payload.tier.lower()
    if tier not in PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown tier '{tier}'. Valid: {list(PLANS)}")

    plan = PLANS[tier]
    try:
        order = rzp_client.order.create({
            "amount":   plan["amount_paise"],
            "currency": "INR",
            "receipt":  f"fintelligence_{user_id}_{tier}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "user_id": str(user_id),
                "tier":    tier,
            },
        })
    except Exception as e:
        log.exception("Razorpay order creation failed")
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {e}")

    # Persist pending order to DB
    from volguard_v6_final import SessionLocal, SubscriptionPayment  # late import
    db = SessionLocal()
    try:
        record = SubscriptionPayment(
            user_id           = user_id,
            razorpay_order_id = order["id"],
            amount_paise      = plan["amount_paise"],
            tier              = tier,
            months            = plan["months"],
            status            = "created",
        )
        db.add(record)
        db.commit()
    finally:
        db.close()

    return {
        "order_id":      order["id"],
        "amount_paise":  plan["amount_paise"],
        "currency":      "INR",
        "key_id":        RZP_KEY_ID,
    }


@router.post("/verify-payment")
def verify_payment(
    payload: VerifyPaymentRequest,
    user_id: int = Depends(_require_user),
):
    """
    Verify Razorpay payment signature and upgrade user tier.
    Called by frontend after successful checkout.
    """
    if not rzp_client:
        raise HTTPException(status_code=503, detail="Payments not configured")

    # Verify HMAC signature
    body = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"
    expected = hmac.new(
        RZP_KEY_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, payload.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    from volguard_v6_final import SessionLocal, User, SubscriptionPayment
    db = SessionLocal()
    try:
        record = db.query(SubscriptionPayment).filter(
            SubscriptionPayment.razorpay_order_id == payload.razorpay_order_id,
            SubscriptionPayment.user_id == user_id,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Order not found")
        if record.status == "paid":
            return {"success": True, "message": "Already activated"}

        # Mark payment paid
        record.status              = "paid"
        record.razorpay_payment_id = payload.razorpay_payment_id
        record.paid_at             = datetime.utcnow()

        # Upgrade user
        user = db.query(User).filter(User.id == user_id).first()
        user.subscription_tier = record.tier
        # Extend from now or from current expiry, whichever is later
        base = max(datetime.utcnow(), user.subscription_expires_at or datetime.utcnow())
        user.subscription_expires_at = base + timedelta(days=30 * record.months)

        db.commit()
        log.info(f"User {user_id} upgraded to {record.tier} until {user.subscription_expires_at}")

        return {
            "success":    True,
            "tier":       record.tier,
            "expires_at": user.subscription_expires_at.isoformat(),
            "message":    f"Welcome to Fintelligence {record.tier.capitalize()}!",
        }
    finally:
        db.close()


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature"),
):
    """
    Razorpay webhook for payment events.
    Provides a server-side safety net in case the user closes the browser
    before verify-payment is called.
    """
    if not RZP_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    body = await request.body()
    expected = hmac.new(RZP_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = await request.json()
    if event.get("event") != "payment.captured":
        return {"status": "ignored"}

    payment = event.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = payment.get("order_id")
    payment_id = payment.get("id")
    if not order_id or not payment_id:
        return {"status": "missing_ids"}

    from volguard_v6_final import SessionLocal, User, SubscriptionPayment
    db = SessionLocal()
    try:
        record = db.query(SubscriptionPayment).filter(
            SubscriptionPayment.razorpay_order_id == order_id
        ).first()
        if not record or record.status == "paid":
            return {"status": "already_handled"}

        record.status              = "paid"
        record.razorpay_payment_id = payment_id
        record.paid_at             = datetime.utcnow()

        user = db.query(User).filter(User.id == record.user_id).first()
        if user:
            user.subscription_tier = record.tier
            base = max(datetime.utcnow(), user.subscription_expires_at or datetime.utcnow())
            user.subscription_expires_at = base + timedelta(days=30 * record.months)
            log.info(f"Webhook: user {record.user_id} upgraded to {record.tier}")

        db.commit()
    finally:
        db.close()

    return {"status": "ok"}
