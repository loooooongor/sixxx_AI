"""六爻 AI 後端：純標準庫 HTTP 伺服器（零外部依賴）。

端點：
    GET  /                    前端單頁應用
    GET  /api/health          健康檢查與設定狀態
    GET  /api/providers       可用 LLM 供應商
    GET  /api/settings        讀取目前 LLM 設定（不含明文 key）
    POST /api/settings        儲存 LLM 設定
    POST /api/cast            排盤（不呼叫 LLM），回傳完整卦盤
    POST /api/preview         組 prompt 並回傳（除錯／透明化用）
    POST /api/read            串流解卦（SSE）
    POST /api/followup        串流追問（SSE）
    GET  /api/glossary        術語表

**一卦只起一次**：只要請求帶了 ``board``（前端已排好的卦盤），
``/api/preview`` 與 ``/api/read`` 一律沿用該卦盤、不再擲錢起卦 ——
保證「畫面上顯示的卦」與「LLM 解讀的卦」永遠是同一個卦。

為什麼不用 FastAPI：本機環境缺少可編譯的 pydantic-core，
改以標準庫 http.server 實作，零編譯依賴、開箱即跑。
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from liuyao_ai import divination, knowledge, llm, prompt  # noqa: E402

WEB_DIR = HERE / "web"
HOST = os.environ.get("LIUYAO_HOST", "127.0.0.1")
PORT = int(os.environ.get("LIUYAO_PORT", "8848"))


# ────────────────────────────── 工具 ──────────────────────────────

def _json_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def parse_when(when: dict | None) -> datetime | None:
    """把前端傳來的時間物件轉成 datetime；未給則 None（代表現在）。"""
    if not when:
        return None
    try:
        if when.get("iso"):
            return datetime.fromisoformat(when["iso"])
        y = int(when.get("year"))
        mo = int(when.get("month"))
        d = int(when.get("day"))
        h = int(when.get("hour", 12))
        mi = int(when.get("minute", 0))
        tz = timezone.utc  # 由 calendar 轉成 +8
        return datetime(y, mo, d, h, mi, tzinfo=tz)
    except (TypeError, ValueError) as e:
        raise ValueError(f"時間格式錯誤：{e}") from e


# ───────────────────── 一卦只起一次：沿用前端帶回的卦盤 ─────────────────────

#: 前端帶回的卦盤必須具備的欄位（＝ divination.board_to_dict 的輸出）。
_BOARD_KEYS = (
    "cast_time", "hexagram", "changed_hexagram", "palace", "palace_wx",
    "world_pos", "response_pos", "month_zhi", "month_wx", "day_gz", "day_wx",
    "xunkong", "yongshen_qin", "yongshen_lines", "moving_positions",
    "moving_text", "lines", "gua_ci", "yao_ci", "changed_gua_ci",
    "gua_bian", "fu_yin", "fan_yin", "sanhe",
    "is_liuhe_gua", "is_liuchong_gua", "changed_is_liuhe", "changed_is_liuchong",
)
_CAST_TIME_KEYS = (
    "moment", "moment_display", "year_gz", "month_gz", "month_zhi",
    "day_gz", "day_gan", "day_zhi", "xunkong", "shichen", "jie", "lunar_text",
)
_LINE_KEYS = (
    "pos", "pos_name", "yao_name", "yin_yang", "gan", "zhi", "wx",
    "qin", "shen", "is_moving", "state", "stage", "tags",
)


def board_from_body(body: dict) -> tuple[dict, str] | None:
    """取出前端帶回的卦盤；未帶則回 ``None``（代表需由後端重新排盤）。

    這是「一卦只起一次」的唯一保證點：只要請求帶了 board，呼叫端就必須
    直接沿用這份卦盤，**絕不可再擲一次銅錢**——否則畫面顯示的卦與
    LLM 解讀的卦會是兩個不同的卦。

    Raises:
        ValueError: 卦盤缺欄位、爻數不對、卦名與六爻不符、動爻標記矛盾等。
    """
    raw = body.get("board")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("卦盤資料格式錯誤：board 必須是物件")

    missing = [k for k in _BOARD_KEYS if k not in raw]
    if missing:
        raise ValueError("卦盤資料不完整，缺少欄位：" + "、".join(missing[:6]))

    ct = raw["cast_time"]
    if not isinstance(ct, dict):
        raise ValueError("卦盤資料格式錯誤：cast_time 必須是物件")
    missing = [k for k in _CAST_TIME_KEYS if k not in ct]
    if missing:
        raise ValueError("占卦時間資料不完整，缺少欄位：" + "、".join(missing[:6]))
    if not isinstance(ct["xunkong"], list) or len(ct["xunkong"]) != 2:
        raise ValueError("占卦時間資料錯誤：旬空必須是兩個地支")

    lines = raw["lines"]
    if not isinstance(lines, list) or len(lines) != 6:
        raise ValueError("卦盤資料錯誤：必須剛好六爻")
    for ln in lines:
        if not isinstance(ln, dict) or any(k not in ln for k in _LINE_KEYS):
            raise ValueError("卦盤資料錯誤：每一爻的欄位不完整")
    if sorted(ln["pos"] for ln in lines) != [1, 2, 3, 4, 5, 6]:
        raise ValueError("卦盤資料錯誤：爻位必須是 1–6 各一")

    hexagram = str(raw.get("hexagram") or "").strip()
    if not hexagram:
        raise ValueError("卦盤資料錯誤：缺少卦名")
    bottom_up = [1 if ln["yin_yang"] == "陽" else 0
                 for ln in sorted(lines, key=lambda l: l["pos"])]
    try:
        derived = divination.lines_to_hexagram(bottom_up)
    except ValueError:
        derived = ""
    if derived and derived != hexagram:
        raise ValueError(f"卦盤資料不一致：卦名「{hexagram}」與六爻（{derived}）不符")

    moving = raw["moving_positions"]
    if not isinstance(moving, list) or any(
            not isinstance(p, int) or isinstance(p, bool) or p < 1 or p > 6
            for p in moving):
        raise ValueError("卦盤資料錯誤：動爻必須是 1–6 的整數清單")
    if sorted(moving) != sorted(ln["pos"] for ln in lines if ln["is_moving"]):
        raise ValueError("卦盤資料不一致：動爻位置與六爻的動爻標記不符")

    if not isinstance(raw["yongshen_lines"], list):
        raise ValueError("卦盤資料錯誤：yongshen_lines 必須是清單")
    if not isinstance(raw["yao_ci"], dict):
        raise ValueError("卦盤資料錯誤：yao_ci 必須是物件")

    question = str(body.get("question") or raw.get("question") or "").strip()
    if not question:
        raise ValueError("請先輸入占問的問題")

    board = dict(raw)
    board["cast_time"] = dict(ct)
    board["question"] = question
    return board, question


# ────────────────────────────── 請求處理 ──────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "LiuyaoAI/1.0"
    protocol_version = "HTTP/1.1"

    # —— 基礎回應 ——

    def _send(self, status: int, body: bytes, ctype: str,
              extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, _json_bytes(obj), "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": message}, status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(f"請求內容不是合法 JSON：{e}") from e

    # —— SSE ——

    def _sse_start(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

    def _sse(self, event: str, data) -> None:
        """送出一個 SSE 事件。

        delta 的文字一律再做一層 JSON 字串轉義：確保整個事件只佔「一行 data」，
        內容中的換行永遠不會被誤認為事件分隔，任何代理／防火牆都不會拆壞。
        前端以 JSON.parse 還原（失敗則當純文字）。
        """
        payload = json.dumps(data, ensure_ascii=False)
        try:
            self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise

    # —— 路由 ——

    def do_GET(self) -> None:                     # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._serve_static("index.html")
            if path.startswith("/assets/"):
                return self._serve_static(path.lstrip("/"))
            if path == "/api/health":
                cfg = llm.LLMConfig.load()
                kb = knowledge.get_kb()
                return self._json({
                    "ok": True,
                    "server": self.server_version,
                    "sections_indexed": len(kb.sections),
                    "docs_indexed": len(kb.doc_texts),
                    "llm": cfg.public(),
                })
            if path == "/api/providers":
                return self._json({"ok": True, "providers": llm.provider_catalog()})
            if path == "/api/settings":
                cfg = llm.LLMConfig.load()
                return self._json({"ok": True, "settings": cfg.public()})
            if path == "/api/glossary":
                return self._json({"ok": True, "glossary": knowledge.get_glossary()})
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            return self._error("找不到此路徑", 404)
        except Exception as e:                     # noqa: BLE001
            self._log_exc(e)
            return self._error(f"伺服器錯誤：{e}", 500)

    def do_POST(self) -> None:                    # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/settings":
                return self._handle_settings()
            if path == "/api/cast":
                return self._handle_cast()
            if path == "/api/preview":
                return self._handle_preview()
            if path == "/api/read":
                return self._handle_read()
            if path == "/api/followup":
                return self._handle_followup()
            return self._error("找不到此路徑", 404)
        except ValueError as e:
            return self._error(str(e), 400)
        except llm.LLMError as e:
            return self._error(str(e), 502)
        except Exception as e:                     # noqa: BLE001
            self._log_exc(e)
            return self._error(f"伺服器錯誤：{type(e).__name__} {e}", 500)

    # —— 各端點實作 ——

    def _handle_settings(self) -> None:
        body = self._read_json()
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

        cfg.save()
        return self._json({"ok": True, "settings": cfg.public()})

    def _build_cast(self, body: dict) -> dict:
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

    def _resolve_board(self, body: dict) -> tuple[dict, str, str]:
        """取得本次要解讀的卦盤，回傳 ``(board, question, source)``。

        * 請求帶了 board（前端已排好的卦盤）→ 直接沿用，``source="client"``。
          **不重擲銅錢**，確保畫面與解讀是同一個卦。
        * 未帶 board → 才由後端排盤／擲錢，``source="server"``。
        """
        provided = board_from_body(body)
        if provided is not None:
            board, question = provided
            return board, question, "client"
        result = self._build_cast(body)
        return result["board"], result["meta"]["question"], "server"

    def _handle_cast(self) -> None:
        result = self._build_cast(self._read_json())
        return self._json({"ok": True, **result})

    def _handle_preview(self) -> None:
        body = self._read_json()
        board, question, source = self._resolve_board(body)
        bundle = prompt.build_prompt(board, question)
        return self._json({
            "ok": True,
            "board": board,
            "board_source": source,
            "question": question,
            "system_chars": len(bundle.system),
            "user_chars": len(bundle.user),
            "system": bundle.system,
            "user": bundle.user,
        })

    def _handle_read(self) -> None:
        body = self._read_json()
        board, question, source = self._resolve_board(body)

        cfg = llm.LLMConfig.load()
        if not cfg.configured():
            return self._json({
                "ok": False,
                "error": "尚未設定 LLM API key。請點右上角「設定」填入，"
                         "或設定環境變數 " + cfg.spec["env_key"],
                "board": board,
                "need_settings": True,
            }, 428)

        bundle = prompt.build_prompt(board, question)
        self._sse_start()
        self._sse("board", board)
        self._sse("meta", {
            "provider": cfg.spec["label"],
            "model": cfg.model,
            "prompt_chars": len(bundle.system) + len(bundle.user),
            "board_source": source,
            "hexagram": board["hexagram"],
            "changed_hexagram": board.get("changed_hexagram"),
            "moving_positions": board["moving_positions"],
        })
        try:
            for chunk in llm.stream_chat(cfg, bundle.system, bundle.messages()):
                self._sse("delta", chunk)
            self._sse("done", {"ok": True})
        except llm.LLMError as e:
            self._sse("error", {"message": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_followup(self) -> None:
        body = self._read_json()
        board = body.get("board")
        if not isinstance(board, dict) or not board.get("hexagram"):
            raise ValueError("缺少卦盤資料")
        question = str(body.get("question") or "").strip()
        prior = str(body.get("prior_answer") or "").strip()
        followup = str(body.get("followup") or "").strip()
        if not followup:
            raise ValueError("請輸入追問內容")

        cfg = llm.LLMConfig.load()
        if not cfg.configured():
            return self._json({
                "ok": False,
                "error": "尚未設定 LLM API key，無法追問。",
                "need_settings": True,
            }, 428)

        bundle = prompt.build_followup(board, question, prior, followup)
        self._sse_start()
        try:
            for chunk in llm.stream_chat(cfg, bundle.system, bundle.messages()):
                self._sse("delta", chunk)
            self._sse("done", {"ok": True})
        except llm.LLMError as e:
            self._sse("error", {"message": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass

    # —— 靜態檔 ——

    def _serve_static(self, rel: str) -> None:
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            return self._error("找不到檔案", 404)
        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype,
                   {"Cache-Control": "no-cache"})

    # —— 日誌 ——

    def _log_exc(self, e: Exception) -> None:
        traceback.print_exc()

    def log_message(self, fmt: str, *args) -> None:
        # 只記重要請求，避免噪音
        msg = fmt % args
        if "/api/" in msg or " 500 " in msg or " 502 " in msg:
            sys.stderr.write(f"[{self.log_date_time_string()}] {msg}\n")


def main() -> int:
    if not (ROOT / "src" / "liuyao").exists():
        print("錯誤：找不到排盤引擎（src/liuyao）", file=sys.stderr)
        return 1
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    url = f"http://{HOST}:{PORT}/"
    print("=" * 62)
    print("  六爻 AI · 繁體版")
    print("=" * 62)
    cfg = llm.LLMConfig.load()
    print(f"  網址    : {url}")
    print(f"  知識庫  : {len(knowledge.get_kb().sections)} 個小節 / "
          f"{len(knowledge.get_kb().doc_texts)} 冊")
    print(f"  LLM     : {cfg.spec['label']} · {cfg.model or '（未設定）'}"
          f"{'' if cfg.configured() else '  ← 尚未設定 API key'}")
    print("  停止    : 按 Ctrl+C")
    print("=" * 62)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
