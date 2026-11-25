"""Stripe Payments + Billing for 知幾筆記。

使用 Stripe-hosted Checkout（單次與訂閱）與 Customer Portal；金鑰只從
環境變數或本機 `.env` 讀取，不寫進程式碼或版控。

本機可用；雲端部署時 SQLite 會因唯讀檔案系統失敗，正式環境請把
``BillingStore`` 換成 Postgres。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import string
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

API_BASE = "https://api.stripe.com/v1"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_DB = ROOT / "ai" / "data" / "billing.sqlite3"


class StripeError(RuntimeError):
    """Stripe API 或設定錯誤；訊息不含金鑰。"""


def _env(name: str, default: str = "") -> str:
    if os.environ.get(name):
        return os.environ[name]
    for path in (ROOT / ".env", ROOT / "ai" / ".env"):
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"').strip("'")
        except OSError:
            continue
    return default


@dataclass(frozen=True)
class BillingConfig:
    secret_key: str
    webhook_secret: str
    price_single: str
    price_monthly: str
    base_url: str
    db_path: Path

    @classmethod
    def load(cls) -> "BillingConfig":
        raw_db = Path(_env("LIUYAO_BILLING_DB", str(DEFAULT_DB)))
        if not raw_db.is_absolute():
            raw_db = ROOT / raw_db
        return cls(
            secret_key=_env("STRIPE_SECRET_KEY"),
            webhook_secret=_env("STRIPE_WEBHOOK_SECRET"),
            price_single=_env("STRIPE_PRICE_SINGLE"),
            price_monthly=_env("STRIPE_PRICE_MONTHLY"),
            base_url=_env("PUBLIC_BASE_URL", "http://127.0.0.1:8848").rstrip("/"),
            db_path=raw_db,
        )

    def configured(self) -> bool:
        return bool(self.secret_key and self.price_single and self.price_monthly)


def _pairs(prefix: str, value):
    if isinstance(value, dict):
        for key, val in value.items():
            yield from _pairs(f"{prefix}[{key}]" if prefix else str(key), val)
    elif isinstance(value, (list, tuple)):
        for i, val in enumerate(value):
            yield from _pairs(f"{prefix}[{i}]", val)
    elif isinstance(value, bool):
        yield prefix, "true" if value else "false"
    elif value is not None:
        yield prefix, str(value)


def _request(cfg: BillingConfig, method: str, path: str,
             params: dict | None = None, query: dict | None = None) -> dict:
    if not cfg.secret_key:
        raise StripeError("尚未設定 STRIPE_SECRET_KEY")
    headers = {
        "Authorization": f"Bearer {cfg.secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    content = urlencode(list(_pairs("", params or {}))).encode("utf-8")
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.request(
                method,
                API_BASE + path,
                content=content if params is not None else None,
                params=query,
                headers=headers,
            )
    except httpx.HTTPError as e:
        raise StripeError(f"連線 Stripe 失敗：{type(e).__name__}") from e
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        message = (data.get("error") or {}).get("message") or f"Stripe API {resp.status_code}"
        raise StripeError(message)
    return data


def create_checkout(cfg: BillingConfig, plan: str, email: str = "",
                    base_url: str | None = None) -> dict:
    if plan not in ("single", "monthly"):
        raise ValueError("方案必須是 single 或 monthly")
    price = cfg.price_single if plan == "single" else cfg.price_monthly
    if not price:
        raise StripeError("尚未設定 Stripe price ID")
    base = (base_url or cfg.base_url).rstrip("/")
    mode = "payment" if plan == "single" else "subscription"
    params = {
        "mode": mode,
        "line_items": [{"price": price, "quantity": 1}],
        "success_url": f"{base}/billing-success.html?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/pricing.html",
        "allow_promotion_codes": True,
        "locale": "auto",
        "metadata": {"plan": plan},
        "managed_payments": {"enabled": False},
        "integration_identifier": "zhiji_" + "".join(
            secrets.choice(string.ascii_lowercase) for _ in range(8)
        ),
    }
    if email:
        params["customer_email"] = email
    if mode == "payment":
        params["customer_creation"] = "always"
    else:
        params["subscription_data"] = {"metadata": {"plan": plan}}
    try:
        session = _request(cfg, "POST", "/checkout/sessions", params)
    except StripeError as e:
        # 舊 API 版本可能還不認得 integration_identifier；不影響 Checkout 本體。
        if "integration_identifier" not in str(e):
            raise
        params.pop("integration_identifier", None)
        session = _request(cfg, "POST", "/checkout/sessions", params)
    return {"id": session.get("id"), "url": session.get("url")}


def retrieve_session(cfg: BillingConfig, session_id: str) -> dict:
    if not session_id:
        raise ValueError("缺少 session_id")
    return _request(
        cfg, "GET", f"/checkout/sessions/{quote(session_id, safe='')}",
        query={"expand[]": ["subscription", "customer"]},
    )


def session_summary(cfg: BillingConfig, session_id: str) -> dict:
    session = retrieve_session(cfg, session_id)
    customer = session.get("customer")
    customer_id = customer.get("id") if isinstance(customer, dict) else customer
    sub = session.get("subscription")
    sub_id = sub.get("id") if isinstance(sub, dict) else sub
    sub_status = sub.get("status") if isinstance(sub, dict) else None
    details = session.get("customer_details") or {}
    metadata = session.get("metadata") or {}
    return {
        "ok": True,
        "id": session.get("id"),
        "mode": session.get("mode"),
        "status": session.get("status"),
        "payment_status": session.get("payment_status"),
        "customer_id": customer_id,
        "email": details.get("email"),
        "plan": metadata.get("plan"),
        "subscription_id": sub_id,
        "subscription_status": sub_status,
        "amount_total": session.get("amount_total"),
        "currency": session.get("currency"),
    }


def create_portal(cfg: BillingConfig, customer_id: str,
                  base_url: str | None = None) -> dict:
    if not customer_id:
        raise ValueError("缺少 customer_id")
    base = (base_url or cfg.base_url).rstrip("/")
    session = _request(cfg, "POST", "/billing_portal/sessions", {
        "customer": customer_id,
        "return_url": f"{base}/billing-success.html",
    })
    return {"url": session.get("url")}


def verify_webhook(cfg: BillingConfig, payload: bytes, signature: str,
                   tolerance: int = 300) -> dict:
    if not cfg.webhook_secret:
        raise StripeError("尚未設定 STRIPE_WEBHOOK_SECRET")
    if not signature:
        raise StripeError("缺少 Stripe-Signature")
    parts = {}
    for item in signature.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError) as e:
        raise StripeError("Stripe-Signature 格式錯誤") from e
    if abs(time.time() - timestamp) > tolerance:
        raise StripeError("Webhook 時間戳過期")
    signed = str(timestamp).encode() + b"." + payload
    expected = hmac.new(cfg.webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", [])):
        raise StripeError("Webhook 簽章驗證失敗")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StripeError("Webhook payload 不是合法 JSON") from e


class BillingStore:
    """本機 SQLite entitlement store；正式環境請換成 Postgres。"""

    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entitlements (
                customer_id TEXT PRIMARY KEY,
                email TEXT,
                plan TEXT,
                status TEXT,
                subscription_id TEXT,
                current_period_end INTEGER,
                updated_at INTEGER,
                source_event TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                type TEXT,
                created INTEGER,
                customer_id TEXT,
                payload TEXT
            );
            """
        )
        self.conn.commit()

    def record_event(self, event: dict) -> None:
        obj = (event.get("data") or {}).get("object") or {}
        customer = obj.get("customer")
        customer_id = customer.get("id") if isinstance(customer, dict) else customer
        self.conn.execute(
            "INSERT OR IGNORE INTO events (event_id, type, created, customer_id, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (event.get("id"), event.get("type"), event.get("created"),
             customer_id, json.dumps(event, ensure_ascii=False)),
        )
        self.conn.commit()

    def upsert_entitlement(self, customer_id: str, email: str, plan: str,
                           status: str, subscription_id: str = "",
                           current_period_end: int | None = None,
                           source_event: str = "") -> None:
        if not customer_id:
            return
        self.conn.execute(
            """
            INSERT INTO entitlements
              (customer_id, email, plan, status, subscription_id,
               current_period_end, updated_at, source_event)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
              email = COALESCE(NULLIF(excluded.email, ''), entitlements.email),
              plan = COALESCE(NULLIF(excluded.plan, ''), entitlements.plan),
              status = excluded.status,
              subscription_id = COALESCE(NULLIF(excluded.subscription_id, ''), entitlements.subscription_id),
              current_period_end = COALESCE(excluded.current_period_end, entitlements.current_period_end),
              updated_at = excluded.updated_at,
              source_event = excluded.source_event
            """,
            (customer_id, email, plan, status, subscription_id,
             current_period_end, int(time.time()), source_event),
        )
        self.conn.commit()

    def get_entitlement(self, customer_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM entitlements WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self.conn.close()


def _plan_for_price(cfg: BillingConfig, price_id: str) -> str:
    if price_id == cfg.price_monthly:
        return "monthly"
    if price_id == cfg.price_single:
        return "single"
    return ""


def _event_objects(event: dict) -> tuple[dict, str, str]:
    obj = (event.get("data") or {}).get("object") or {}
    customer = obj.get("customer")
    customer_id = customer.get("id") if isinstance(customer, dict) else (customer or "")
    email = ((obj.get("customer_details") or {}).get("email")
             or (customer.get("email") if isinstance(customer, dict) else "")
             or obj.get("receipt_email") or "")
    return obj, customer_id, email


def handle_webhook(cfg: BillingConfig, payload: bytes, signature: str,
                   store: BillingStore | None = None) -> dict:
    event = verify_webhook(cfg, payload, signature)
    own_store = store is None
    store = store or BillingStore(cfg.db_path)
    try:
        store.record_event(event)
        event_type = event.get("type") or ""
        obj, customer_id, email = _event_objects(event)
        plan = (obj.get("metadata") or {}).get("plan") or ""
        subscription = obj.get("subscription")
        subscription_id = subscription.get("id") if isinstance(subscription, dict) else (subscription or "")
        period_end = obj.get("current_period_end")
        status = ""

        if event_type.startswith("checkout.session."):
            plan = (obj.get("metadata") or {}).get("plan") or ("monthly" if obj.get("mode") == "subscription" else "single")
            if event_type == "checkout.session.async_payment_failed":
                status = "payment_failed"
            elif obj.get("payment_status") in ("paid", "no_payment_required"):
                status = "active"
            else:
                status = "pending"
        elif event_type.startswith("customer.subscription."):
            plan = (obj.get("metadata") or {}).get("plan") or plan
            raw_status = obj.get("status") or ""
            status = "active" if raw_status in ("active", "trialing") else raw_status
            period_end = obj.get("current_period_end") or period_end
        elif event_type == "invoice.paid":
            status = "active"
            period_end = ((obj.get("lines") or {}).get("data") or [{}])[0].get("period", {}).get("end") or period_end
        elif event_type == "invoice.payment_failed":
            status = "past_due"
        else:
            return event

        if customer_id and status:
            store.upsert_entitlement(
                customer_id, email, plan, status,
                subscription_id, period_end, event_type,
            )
        return event
    finally:
        if own_store:
            store.close()
