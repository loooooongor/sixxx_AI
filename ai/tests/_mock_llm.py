"""假的 OpenAI 相容 LLM 伺服器：用於端到端測試串流（不需真 API key）。

回傳一段有結構的假解卦，逐段以 SSE 送出，驗證：
1. 後端 stream_chat 解析正確
2. /api/read 的 SSE 格式前端吃得下
3. 錯誤處理（可切換成回 401）
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "_mock_llm_last_request.json"

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
MODE = sys.argv[2] if len(sys.argv) > 2 else "ok"

FAKE_ANSWER = """## 一、總斷

此緣本質相生，能旺你。然當下時機未至，屬「貴而暫弱」之局——人好、緣分重，但能量尚未出來。

## 二、用神

取**妻財**為用神，因所問為女緣。用神妻財亥水臨五爻君位，臨應爻，正指此人。亥水於未月處死地，
受月建未土之剋、日辰卯木之泄，兩頭受壓，故旺不起來。

## 三、世爻與自身

世爻九二官鬼卯木動化庚寅，為**化退神**，主心氣漸退；又入月建未墓，困束施展不開；
更臨玄武，暗自動搖。

## 四、全局分解

上爻子孫酉金旺相逢日辰卯沖，為**暗動**而非日破——暗中生助亥水，是隱性的托底之力。
兄弟丑土兩重月破，克財阻力被削弱。

## 五、應期

亥子月財爻得令最旺，為最佳窗口；丑月沖開未墓但你出困、財已轉弱，須防錯位。

## 六、建議與提醒

宜守不宜急。占卜斷勢象時機，非事實預測，重大決定仍須專業判斷。
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):                       # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}

        if MODE == "auth_fail":
            body = json.dumps({"error": {"message": "Invalid API key"}}).encode()
            self.send_response(401)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 記錄收到的請求，方便驗證 prompt 有送達（寫入失敗不影響串流）
        try:
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "model": payload.get("model"),
                    "stream": payload.get("stream"),
                    "message_count": len(payload.get("messages", [])),
                    "system_chars": len(payload["messages"][0]["content"])
                    if payload.get("messages") else 0,
                    "user_chars": len(payload["messages"][-1]["content"])
                    if payload.get("messages") else 0,
                    "temperature": payload.get("temperature"),
                }, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[mock] 無法寫入請求紀錄：{e}", file=sys.stderr, flush=True)

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "close")
        self.end_headers()

        # 逐段送出（模擬串流）
        try:
            # 逐行、逐段送出（以「行」為單位切塊，避免把換行切斷）
            for line in FAKE_ANSWER.splitlines(keepends=True):
                for i in range(0, max(1, len(line)), 20):
                    piece = line[i:i + 20]
                    data = {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {"content": piece},
                                     "finish_reason": None}],
                    }
                    payload_text = json.dumps(data, ensure_ascii=False)
                    # 同一事件的所有 data 行以 \n 連接（內容中的換行已由 json 轉義為 \n）
                    self.wfile.write(f"data: {payload_text}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.006)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"mock LLM on http://127.0.0.1:{PORT}  mode={MODE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
