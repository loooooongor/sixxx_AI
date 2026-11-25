"""Vercel / WSGI 入口。

本機仍用 ``ai/server.py`` 的標準庫 HTTP 伺服器；部署到 Vercel 時，
由這個 WSGI app 接手同一組路由與前端靜態檔。

環境變數（雲端部署必填）：
    DEEPSEEK_API_KEY
    LIUYAO_LLM_PROVIDER   （預設 deepseek）
    LIUYAO_LLM_MODEL      （預設 deepseek-chat）

雲端檔案系統是唯讀的，設定頁的「儲存」會回傳 403；請用上述環境變數。
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for _p in (ROOT / "src", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402

from liuyao_ai import billing, divination, knowledge, llm, prompt  # noqa: E402
from server import WEB_DIR, board_from_body, parse_when  # noqa: E402

app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False


# ────────────────────────────── 共用 ──────────────────────────────

def _read_body() -> dict:
    raw = request.get_data(cache=True)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"請求內容不是合法 JSON：{e}") from e
    if not isinstance(data, dict):
        raise ValueError("請求內容必須是 JSON 物件")
    return data


def _error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _build_cast(body: dict) -> dict:
    question = str(body.get("question") or "").strip()
    if not question:
        raise ValueError("請先輸入占問的問題")
    hexagram = body.get("hexagram") or None
    moving = body.get("moving") or []
    if isinstance(moving, str):
        moving = [int(x) for x in moving.replace("，", ",").split(",") if x.strip()]
    moving = [int(x) for x in moving]
    req = divination.CastRequest(
        question=question,
        hexagram=hexagram,
        moving=moving,
        yongshen=body.get("yongshen") or None,
        when=parse_when(body.get("when")),
        use_coins=bool(body.get("use_coins")),
    )
    return divination.build_cast(req)


def _resolve_board(body: dict) -> tuple[dict, str, str]:
    provided = board_from_body(body)
    if provided is not None:
        board, question = provided
        return board, question, "client"
    result = _build_cast(body)
    return result["board"], result["meta"]["question"], "server"


def _sse(events) -> Response:
    def generate():
        for event, data in events:
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache, no-transform"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


def _read_events(board: dict, question: str, source: str):
    cfg = llm.LLMConfig.load()
    bundle = prompt.build_prompt(board, question)
    yield "board", board
    yield "meta", {
        "provider": cfg.spec["label"],
        "model": cfg.model,
        "prompt_chars": len(bundle.system) + len(bundle.user),
        "board_source": source,
        "hexagram": board["hexagram"],
        "changed_hexagram": board.get("changed_hexagram"),
        "moving_positions": board["moving_positions"],
    }
    try:
        for chunk in llm.stream_chat(cfg, bundle.system, bundle.messages()):
            yield "delta", chunk
    except llm.LLMError as e:
        yield "error", {"message": str(e)}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        yield "error", {"message": f"伺服器錯誤：{type(e).__name__}"}
    else:
        yield "done", {"ok": True}


# ────────────────────────────── 靜態檔 ──────────────────────────────

@app.get("/")
@app.get("/index.html")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/pricing.html")
def pricing_page():
    return send_from_directory(WEB_DIR, "pricing.html")


@app.get("/billing-success.html")
def billing_success_page():
    return send_from_directory(WEB_DIR, "billing-success.html")


@app.get("/assets/<path:rel>")
def asset(rel: str):
    return send_from_directory(WEB_DIR / "assets", rel)


@app.get("/favicon.ico")
def favicon():
    return "", 204


# ────────────────────────────── API ──────────────────────────────

@app.get("/api/health")
def health():
    cfg = llm.LLMConfig.load()
    kb = knowledge.get_kb()
    return jsonify({
        "ok": True,
        "server": "LiuyaoAI/1.0",
        "cloud": bool(os.environ.get("VERCEL")),
        "sections_indexed": len(kb.sections),
        "docs_indexed": len(kb.doc_texts),
        "llm": cfg.public(),
    })


@app.get("/api/providers")
def providers():
    return jsonify({"ok": True, "providers": llm.provider_catalog()})


@app.get("/api/settings")
def get_settings():
    return jsonify({"ok": True, "settings": llm.LLMConfig.load().public()})


@app.post("/api/settings")
def save_settings():
    body = _read_body()
    cfg = llm.LLMConfig.load()

    if "provider" in body and body["provider"] in llm.PROVIDERS:
        new_provider = body["provider"]
        spec = llm.PROVIDERS[new_provider]
        if new_provider != cfg.provider:
            cfg.provider = new_provider
            cfg.base_url = spec["base_url"]
            cfg.model = spec["default_model"]
    if body.get("model"):
        cfg.model = str(body["model"]).strip()
    if body.get("base_url"):
        cfg.base_url = str(body["base_url"]).strip()
    if "api_key" in body:
        key = str(body["api_key"]).strip()
        if key:
            cfg.api_key = key
    if "clear_key" in body and body["clear_key"]:
        cfg.api_key = ""
    if "temperature" in body:
        cfg.temperature = max(0.0, min(1.5, float(body["temperature"])))
    if "max_tokens" in body:
        cfg.max_tokens = max(256, min(32000, int(body["max_tokens"])))

    try:
        cfg.save()
    except OSError as e:
        return _error(
            "雲端部署無法寫入本機設定檔。請在 Vercel 專案設定環境變數 "
            "DEEPSEEK_API_KEY、LIUYAO_LLM_PROVIDER、LIUYAO_LLM_MODEL。"
            f"（{e}）",
            403,
        )
    return jsonify({"ok": True, "settings": cfg.public()})


@app.get("/api/glossary")
def glossary():
    return jsonify({"ok": True, "glossary": knowledge.get_glossary()})


@app.get("/api/stripe/session")
def stripe_session():
    session_id = request.args.get("session_id", "")
    return jsonify(billing.session_summary(billing.BillingConfig.load(), session_id))


@app.get("/api/stripe/entitlement")
def stripe_entitlement():
    customer_id = request.args.get("customer_id", "")
    store = billing.BillingStore(billing.BillingConfig.load().db_path)
    try:
        return jsonify({"ok": True, "entitlement": store.get_entitlement(customer_id)})
    finally:
        store.close()


@app.post("/api/stripe/checkout")
def stripe_checkout():
    body = _read_body()
    cfg = billing.BillingConfig.load()
    if not cfg.configured():
        raise billing.StripeError("尚未設定 Stripe 金鑰或 price ID")
    result = billing.create_checkout(cfg, str(body.get("plan") or ""), str(body.get("email") or ""))
    return jsonify({"ok": True, **result})


@app.post("/api/stripe/portal")
def stripe_portal():
    body = _read_body()
    result = billing.create_portal(billing.BillingConfig.load(), str(body.get("customer_id") or ""))
    return jsonify({"ok": True, **result})


@app.post("/api/stripe/webhook")
def stripe_webhook():
    payload = request.get_data(cache=True)
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = billing.handle_webhook(billing.BillingConfig.load(), payload, signature)
    except billing.StripeError as e:
        return _error(str(e), 400)
    return jsonify({"ok": True, "type": event.get("type")})


@app.post("/api/cast")
def cast():
    result = _build_cast(_read_body())
    return jsonify({"ok": True, **result})


@app.post("/api/preview")
def preview():
    body = _read_body()
    board, question, source = _resolve_board(body)
    bundle = prompt.build_prompt(board, question)
    return jsonify({
        "ok": True,
        "board": board,
        "board_source": source,
        "question": question,
        "system_chars": len(bundle.system),
        "user_chars": len(bundle.user),
        "system": bundle.system,
        "user": bundle.user,
    })


@app.post("/api/read")
def read():
    body = _read_body()
    board, question, source = _resolve_board(body)
    cfg = llm.LLMConfig.load()
    if not cfg.configured():
        return jsonify({
            "ok": False,
            "error": "尚未設定 LLM API key。雲端版請在平台設定 "
                     + cfg.spec["env_key"] + " 環境變數。",
            "board": board,
            "need_settings": True,
        }), 428
    return _sse(_read_events(board, question, source))


@app.post("/api/followup")
def followup():
    body = _read_body()
    board = body.get("board")
    if not isinstance(board, dict) or not board.get("hexagram"):
        raise ValueError("缺少卦盤資料")
    question = str(body.get("question") or "").strip()
    prior = str(body.get("prior_answer") or "").strip()
    followup_text = str(body.get("followup") or "").strip()
    if not followup_text:
        raise ValueError("請輸入追問內容")

    cfg = llm.LLMConfig.load()
    if not cfg.configured():
        return jsonify({
            "ok": False,
            "error": "尚未設定 LLM API key，無法追問。",
            "need_settings": True,
        }), 428

    bundle = prompt.build_followup(board, question, prior, followup_text)

    def events():
        try:
            for chunk in llm.stream_chat(cfg, bundle.system, bundle.messages()):
                yield "delta", chunk
        except llm.LLMError as e:
            yield "error", {"message": str(e)}
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            yield "error", {"message": f"伺服器錯誤：{type(e).__name__}"}
        else:
            yield "done", {"ok": True}

    return _sse(events())


# ────────────────────────────── 錯誤處理 ──────────────────────────────

@app.errorhandler(ValueError)
def _on_value_error(e):
    return _error(str(e), 400)


@app.errorhandler(llm.LLMError)
def _on_llm_error(e):
    return _error(str(e), 502)


@app.errorhandler(billing.StripeError)
def _on_stripe_error(e):
    return _error(str(e), 502)


@app.errorhandler(404)
def _on_404(e):
    return _error("找不到此路徑", 404)


@app.errorhandler(Exception)
def _on_error(e):
    traceback.print_exc()
    return _error(f"伺服器錯誤：{type(e).__name__} {e}", 500)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("LIUYAO_HOST", "127.0.0.1"),
        port=int(os.environ.get("LIUYAO_PORT", "8849")),
        threaded=True,
        debug=False,
    )
