"""
Minimal, dependency-free client for a local Ollama server.

Design notes
------------
* Standard library only (``urllib``).  ``requests`` is NOT installed on the
  build machine, and a skill that others must be able to reproduce should not
  drag in dependencies it does not need.
* Speaks BOTH the native Ollama API (``/api/chat``) and the OpenAI-compatible
  API (``/v1/chat/completions``).  The native API is the default because it
  exposes the real timing counters (``eval_count`` / ``eval_duration``) that
  the verification report needs.
* Proxies are explicitly bypassed: on the build machine a system HTTP proxy is
  configured (``127.0.0.1:7890``) and routing loopback traffic through it would
  be both wrong and slow.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# Never send loopback traffic through the system proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaError(RuntimeError):
    """Raised when the local Ollama server returns an error or is unreachable."""


@dataclass
class ChatResult:
    """One assistant turn plus the server-side timing counters."""

    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    done_reason: str = ""
    # Ollama native timing counters (nanoseconds)
    total_duration: int = 0
    load_duration: int = 0
    prompt_eval_count: int = 0
    prompt_eval_duration: int = 0
    eval_count: int = 0
    eval_duration: int = 0
    # Wall-clock measured by this client (seconds)
    wall_time: float = 0.0
    ttft: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def tokens_per_second(self) -> float:
        """Generation speed reported by the server (eval phase only)."""
        if self.eval_duration and self.eval_count:
            return self.eval_count / (self.eval_duration / 1e9)
        if self.wall_time > 0 and self.eval_count:
            return self.eval_count / self.wall_time
        return 0.0

    @property
    def prompt_tokens_per_second(self) -> float:
        if self.prompt_eval_duration and self.prompt_eval_count:
            return self.prompt_eval_count / (self.prompt_eval_duration / 1e9)
        return 0.0

    @property
    def load_seconds(self) -> float:
        return self.load_duration / 1e9

    def to_metrics(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "eval_count": self.eval_count,
            "prompt_eval_count": self.prompt_eval_count,
            "tok_per_s": round(self.tokens_per_second, 2),
            "prompt_tok_per_s": round(self.prompt_tokens_per_second, 2),
            "ttft_s": round(self.ttft, 4) if self.ttft is not None else None,
            "wall_time_s": round(self.wall_time, 3),
            "load_time_s": round(self.load_seconds, 3),
            "total_duration_s": round(self.total_duration / 1e9, 3),
        }


class OllamaClient:
    """Thin client for a local Ollama server."""

    def __init__(self, host: str = DEFAULT_HOST, timeout: float = 600.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP
    def _request(self, path: str, payload: Optional[dict] = None,
                 method: str = "POST", stream: bool = False):
        url = self.host + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            resp = _OPENER.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:  # server answered with an error
            body = exc.read().decode("utf-8", "replace")
            raise OllamaError(f"HTTP {exc.code} from {url}: {body[:500]}") from exc
        except urllib.error.URLError as exc:  # server not running / bad host
            raise OllamaError(
                f"Cannot reach Ollama at {self.host} ({exc.reason}). "
                f"Start it with: OLLAMA_HOST={self.host} ollama serve"
            ) from exc
        if stream:
            return resp
        return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------- discovery
    def version(self) -> str:
        return self._request("/api/version", method="GET").get("version", "unknown")

    def list_models(self) -> List[Dict[str, Any]]:
        return self._request("/api/tags", method="GET").get("models", []) or []

    def running(self) -> List[Dict[str, Any]]:
        return self._request("/api/ps", method="GET").get("models", []) or []

    def show(self, model: str) -> Dict[str, Any]:
        return self._request("/api/show", {"model": model})

    def has_model(self, model: str) -> bool:
        names = {m.get("name", "") for m in self.list_models()}
        names |= {n.split(":")[0] for n in list(names)}
        return model in names

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        fmt: Optional[Any] = None,
        options: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        think: Optional[bool] = None,
    ) -> ChatResult:
        """Run one chat turn.

        ``fmt`` maps to Ollama's structured-output parameter: pass ``"json"``
        for free-form JSON mode, or a JSON Schema dict to constrain decoding.
        ``stream=True`` measures the true first-token latency (TTFT).
        """
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if tools:
            payload["tools"] = tools
        if fmt is not None:
            payload["format"] = fmt
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think

        started = time.time()

        if not stream:
            raw = self._request("/api/chat", payload)
            wall = time.time() - started
            msg = raw.get("message", {}) or {}
            return ChatResult(
                content=msg.get("content", "") or "",
                tool_calls=msg.get("tool_calls", []) or [],
                model=raw.get("model", model),
                done_reason=raw.get("done_reason", "") or "",
                total_duration=raw.get("total_duration", 0) or 0,
                load_duration=raw.get("load_duration", 0) or 0,
                prompt_eval_count=raw.get("prompt_eval_count", 0) or 0,
                prompt_eval_duration=raw.get("prompt_eval_duration", 0) or 0,
                eval_count=raw.get("eval_count", 0) or 0,
                eval_duration=raw.get("eval_duration", 0) or 0,
                wall_time=wall,
                ttft=None,
                raw=raw,
            )

        # ---- streaming: capture TTFT and stream-observed tok/s -------------
        resp = self._request("/api/chat", payload, stream=True)
        chunks: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        last: Dict[str, Any] = {}
        ttft: Optional[float] = None
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            piece = (obj.get("message", {}) or {}).get("content", "") or ""
            if piece and ttft is None:
                ttft = time.time() - started
            if piece:
                chunks.append(piece)
            if (obj.get("message", {}) or {}).get("tool_calls"):
                tool_calls.extend(obj["message"]["tool_calls"])
            last = obj
        wall = time.time() - started
        return ChatResult(
            content="".join(chunks),
            tool_calls=tool_calls,
            model=last.get("model", model),
            done_reason=last.get("done_reason", "") or "",
            total_duration=last.get("total_duration", 0) or 0,
            load_duration=last.get("load_duration", 0) or 0,
            prompt_eval_count=last.get("prompt_eval_count", 0) or 0,
            prompt_eval_duration=last.get("prompt_eval_duration", 0) or 0,
            eval_count=last.get("eval_count", 0) or 0,
            eval_duration=last.get("eval_duration", 0) or 0,
            wall_time=wall,
            ttft=ttft,
            raw=last,
        )

    # ------------------------------------------------- OpenAI-compatible path
    def openai_chat(self, model: str, messages: List[Dict[str, Any]],
                    tools: Optional[List[Dict[str, Any]]] = None,
                    temperature: float = 0.7) -> Dict[str, Any]:
        """Same turn through ``/v1/chat/completions`` (proof of API parity)."""
        payload: Dict[str, Any] = {
            "model": model, "messages": messages, "temperature": temperature, "stream": False
        }
        if tools:
            payload["tools"] = tools
        return self._request("/v1/chat/completions", payload)


def check_server(host: str = DEFAULT_HOST) -> Dict[str, Any]:
    """Health probe used by scripts/tests to fail loudly instead of cryptically."""
    c = OllamaClient(host)
    info = {"host": host, "reachable": False, "version": None, "models": []}
    try:
        info["version"] = c.version()
        info["models"] = [m.get("name") for m in c.list_models()]
        info["reachable"] = True
    except OllamaError as exc:
        info["error"] = str(exc)
    return info


if __name__ == "__main__":  # pragma: no cover - manual probe
    print(json.dumps(check_server(), indent=2, ensure_ascii=False))
