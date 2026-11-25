"""檢查 Stripe Billing 的設定、簽章與 entitlement（不呼叫網路）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
ROOT = AI_DIR.parent
for p in (str(ROOT), str(AI_DIR), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from liuyao_ai import billing  # noqa: E402

fails = []


def check(name: str, got, want=True) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{name}: got={got!r} want={want!r}")
    print(("OK   " if ok else "FAIL ") + f"{name}: {got}")


cfg = billing.BillingConfig(
    secret_key="sk_test_dummy",
    webhook_secret="whsec_test_dummy",
    price_single="price_single_test",
    price_monthly="price_monthly_test",
    base_url="http://127.0.0.1:8848",
    db_path=Path(":memory:"),
)

check("單次價格設定", cfg.price_single, "price_single_test")
check("月訂價格設定", cfg.price_monthly, "price_monthly_test")
check("config 已設定", cfg.configured(), True)

real = billing.BillingConfig.load()
check("本機有 Stripe secret", bool(real.secret_key), True)
check("本機有兩個 price ID", bool(real.price_single and real.price_monthly), True)
check("本機 base URL", real.base_url.startswith("http"), True)


def signed(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


event = {
    "id": "evt_test_1",
    "type": "checkout.session.completed",
    "created": int(time.time()),
    "data": {"object": {
        "id": "cs_test_1",
        "mode": "subscription",
        "payment_status": "paid",
        "customer": "cus_test_1",
        "customer_details": {"email": "buyer@example.com"},
        "subscription": "sub_test_1",
        "metadata": {"plan": "monthly"},
        "amount_total": 9800,
        "currency": "hkd",
    }},
}
payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
header = signed(payload, cfg.webhook_secret)

check("簽章可驗證", billing.verify_webhook(cfg, payload, header)["type"], "checkout.session.completed")
try:
    billing.verify_webhook(cfg, payload, f"t={int(time.time())},v1=bad")
    check("壞簽章拒絕", False, True)
except billing.StripeError:
    check("壞簽章拒絕", True, True)

store = billing.BillingStore(":memory:")
result = billing.handle_webhook(cfg, payload, header, store=store)
check("webhook 回傳事件", result["type"], "checkout.session.completed")
entitlement = store.get_entitlement("cus_test_1")
check("有 entitlement", bool(entitlement), True)
check("方案 monthly", entitlement["plan"], "monthly")
check("狀態 active", entitlement["status"], "active")
check("訂閱 ID", entitlement["subscription_id"], "sub_test_1")

# 重送同一個 event id 不應產生第二筆 event
billing.handle_webhook(cfg, payload, header, store=store)
count = store.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
check("webhook 冪等", count, 1)

one_time = {
    "id": "evt_test_2",
    "type": "checkout.session.completed",
    "created": int(time.time()),
    "data": {"object": {
        "id": "cs_test_2",
        "mode": "payment",
        "payment_status": "paid",
        "customer": "cus_test_2",
        "customer_details": {"email": "single@example.com"},
        "metadata": {"plan": "single"},
        "amount_total": 2800,
        "currency": "hkd",
    }},
}
payload2 = json.dumps(one_time, ensure_ascii=False).encode("utf-8")
billing.handle_webhook(cfg, payload2, signed(payload2, cfg.webhook_secret), store=store)
single = store.get_entitlement("cus_test_2")
check("單次方案 plan", single["plan"], "single")
check("單次方案 active", single["status"], "active")
store.close()

print()
if fails:
    print(f"❌ {len(fails)} 項失敗")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ Stripe Billing 全部通過")
