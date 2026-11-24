"""LLM 供應商抽象層：統一 OpenAI 相容 / Anthropic / Gemini 三種協定，支援串流。

設計目標：
* **可切換供應商**：設定檔改了即生效，不必改程式。
* **串流輸出**：逐字回傳，前端即時顯示（SSE）。
* **憑證安全**：API key 只存本機 ``config.json``／環境變數，永不寫入日誌或回傳前端。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / "ai" / "config"

#: 內建供應商預設值。base_url 皆為「不含 /v1」的根路徑或完整路徑，見各項註解。
PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek",
        "protocol": "openai",
        "base_url": "https://api.deepseek.com",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "env_key": "DEEPSEEK_API_KEY",
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "openai": {
        "label": "OpenAI",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"],
        "env_key": "OPENAI_API_KEY",
        "key_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Claude (Anthropic)",
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "chat_path": "/messages",
        "default_model": "claude-sonnet-4-5",
        "models": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
        "env_key": "ANTHROPIC_API_KEY",
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    "gemini": {
        "label": "Google Gemini",
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "chat_path": "/models/{model}:streamGenerateContent?alt=sse",
        "default_model": "gemini-2.5-pro",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
        "env_key": "GEMINI_API_KEY",
        "key_url": "https://aistudio.google.com/apikey",
    },
    "openrouter": {
        "label": "OpenRouter（聚合多家）",
        "protocol": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek/deepseek-chat-v3.1",
        "models": ["deepseek/deepseek-chat-v3.1", "anthropic/claude-sonnet-4.5",
                   "openai/gpt-4o", "google/gemini-2.5-pro"],
        "env_key": "OPENROUTER_API_KEY",
        "key_url": "https://openrouter.ai/keys",
    },
    "moonshot": {
        "label": "Moonshot（Kimi）",
        "protocol": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "moonshot-v1-32k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "env_key": "MOONSHOT_API_KEY",
        "key_url": "https://platform.moonshot.cn/console/api-keys",
    },
    "custom": {
        "label": "自訂（OpenAI 相容端點）",
        "protocol": "openai",
        "base_url": "",
        "chat_path": "/chat/completions",
        "default_model": "",
        "models": [],
        "env_key": "CUSTOM_LLM_API_KEY",
        "key_url": "",
    },
}


class LLMError(RuntimeError):
    """LLM 呼叫失敗（憑證、網路、額度、格式）。"""


@dataclass
class LLMConfig:
    """目前的 LLM 設定。"""

    provider: str = "deepseek"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 4000

    # —— 載入 / 儲存 ——

    @staticmethod
    def config_path() -> Path:
        return CONFIG_DIR / "llm.json"

    @classmethod
    def load(cls) -> "LLMConfig":
        """依序讀：config/llm.json → 環境變數 → 內建預設。"""
        data: dict = {}
        p = cls.config_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}

        provider = data.get("provider") or os.environ.get("LIUYAO_LLM_PROVIDER") or "deepseek"
        if provider not in PROVIDERS:
            provider = "deepseek"
        spec = PROVIDERS[provider]

        cfg = cls(
            provider=provider,
            model=data.get("model") or os.environ.get("LIUYAO_LLM_MODEL")
            or spec["default_model"],
            api_key=data.get("api_key") or os.environ.get(spec["env_key"], ""),
            base_url=data.get("base_url") or os.environ.get("LIUYAO_LLM_BASE_URL")
            or spec["base_url"],
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 4000)),
        )
        return cfg

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "api_key": self.api_key,
        }
        p = self.config_path()
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:                              # 盡量收緊權限（POSIX）
            p.chmod(0o600)
        except OSError:
            pass

    # —— 狀態 ——

    @property
    def spec(self) -> dict:
        return PROVIDERS[self.provider]

    @property
    def protocol(self) -> str:
        return self.spec["protocol"]

    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def public(self) -> dict:
        """可安全回給前端的資訊（不含 api_key 明文）。"""
        return {
            "provider": self.provider,
            "provider_label": self.spec["label"],
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "configured": self.configured(),
            "has_key": bool(self.api_key),
            "key_hint": (self.api_key[:6] + "…" + self.api_key[-4:])
            if len(self.api_key) > 12 else ("已設定" if self.api_key else ""),
            "env_key": self.spec["env_key"],
            "key_url": self.spec.get("key_url", ""),
            "models": self.spec["models"],
        }


def provider_catalog() -> list[dict]:
    """列出所有可選供應商（給前端下拉選單）。"""
    out = []
    for pid, spec in PROVIDERS.items():
        out.append({
            "id": pid,
            "label": spec["label"],
            "models": spec["models"],
            "default_model": spec["default_model"],
            "protocol": spec["protocol"],
        })
    return out


# ────────────────────────────── 串流呼叫 ──────────────────────────────

def _headers(cfg: LLMConfig) -> dict[str, str]:
    if cfg.protocol == "anthropic":
        return {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    if cfg.protocol == "gemini":
        return {"content-type": "application/json", "x-goog-api-key": cfg.api_key}
    return {
        "Authorization": f"Bearer {cfg.api_key}",
        "content-type": "application/json",
    }


def _endpoint(cfg: LLMConfig) -> str:
    base = cfg.base_url.rstrip("/")
    path = cfg.spec["chat_path"]
    if cfg.protocol == "gemini":
        path = path.format(model=cfg.model)
        return base + path
    return base + path


def _payload(cfg: LLMConfig, system: str, messages: list[dict]) -> dict:
    if cfg.protocol == "anthropic":
        return {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "system": system,
            "messages": messages,
            "stream": True,
        }
    if cfg.protocol == "gemini":
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": cfg.temperature,
                "maxOutputTokens": cfg.max_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body
    # OpenAI 相容
    msgs = [{"role": "system", "content": system}] if system else []
    msgs.extend(messages)
    return {
        "model": cfg.model,
        "messages": msgs,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": True,
    }


def _parse_delta(cfg: LLMConfig, raw: str) -> str | None:
    """解析 SSE 的一行，取出增量文字；不是文字增量則回 None。"""
    line = raw.strip()
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:"):].strip()
    if not data or data == "[DONE]":
        return None
    try:
        obj = json.loads(data)
    except ValueError:
        return None

    if cfg.protocol == "anthropic":
        # event: content_block_delta → {"delta": {"type":"text_delta","text":"…"}}
        if obj.get("type") == "content_block_delta":
            return (obj.get("delta") or {}).get("text")
        return None
    if cfg.protocol == "gemini":
        for cand in obj.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                if "text" in part:
                    return part["text"]
        return None
    # OpenAI 相容
    choices = obj.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    return delta.get("content")


def stream_chat(cfg: LLMConfig, system: str, messages: list[dict],
                timeout: float = 180.0) -> Iterator[str]:
    """串流呼叫 LLM，逐段 yield 文字。失敗時丟 LLMError。"""
    if not cfg.configured():
        raise LLMError(
            "尚未設定 LLM。請在「設定」中選擇供應商並填入 API key，"
            "或設定環境變數 " + cfg.spec["env_key"]
        )

    url = _endpoint(cfg)
    payload = _payload(cfg, system, messages)
    headers = _headers(cfg)

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=20.0)) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    detail = resp.read().decode("utf-8", "replace")[:600]
                    raise LLMError(_friendly_error(cfg, resp.status_code, detail))
                for raw in resp.iter_lines():
                    text = _parse_delta(cfg, raw)
                    if text:
                        yield text
    except LLMError:
        raise
    except httpx.HTTPError as e:
        raise LLMError(f"連線 {cfg.spec['label']} 失敗：{type(e).__name__} {e}") from e


def _friendly_error(cfg: LLMConfig, status: int, detail: str) -> str:
    """把 API 錯誤碼轉成看得懂的中文說明。"""
    base = f"{cfg.spec['label']} 回應 HTTP {status}。"
    hints = {
        401: "API key 無效或過期，請到設定重新填入。",
        403: "API key 權限不足，或該模型未開通。",
        404: "找不到模型或端點，請確認模型名稱與 Base URL。",
        429: "請求過於頻繁或額度用盡，請稍後再試或檢查帳戶餘額。",
        500: "供應商伺服器錯誤，請稍後重試。",
        503: "供應商暫時無法服務，請稍後重試。",
    }
    hint = hints.get(status, "")
    return f"{base}{hint}\n原始訊息：{detail}"


def complete(cfg: LLMConfig, system: str, messages: list[dict],
             timeout: float = 180.0) -> str:
    """非串流版本（測試用）。"""
    return "".join(stream_chat(cfg, system, messages, timeout=timeout))
