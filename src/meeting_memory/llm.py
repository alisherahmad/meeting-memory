"""Thin adapter over the Anthropic Messages API.

Responsibilities: one place for model/effort/timeouts/retries, refusal fallback,
usage + cost accounting into the store's ledger, and a clean error type the
callers can turn into terminal states. Tests replace `MessagesBackend` with a fake.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Settings, cost_usd
from .store import Store

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Provider failure after the SDK's own retries (or a non-retryable error)."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class LLMUnavailable(LLMError):
    """No credentials configured."""


class MessagesBackend(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class AnthropicBackend:
    """Real backend. Uses the beta endpoint only to opt into server-side refusal fallback."""

    def __init__(self, settings: Settings):
        import anthropic  # imported lazily so code paths without the LLM never need it

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=settings.llm_request_timeout_s, max_retries=settings.llm_max_retries)
        self._fallback = settings.use_refusal_fallback

    def create(self, **kwargs: Any) -> Any:
        a = self._anthropic
        try:
            if self._fallback:
                # Streaming avoids HTTP timeouts on long extraction outputs.
                with self._client.beta.messages.stream(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                ) as stream:
                    return stream.get_final_message()
            with self._client.messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        except a.AuthenticationError as e:
            raise LLMUnavailable(f"Authentication failed: {e.message}") from e
        except a.BadRequestError as e:
            raise LLMError(f"Bad request: {e.message}") from e
        except a.NotFoundError as e:
            raise LLMError(f"Model or endpoint not found: {e.message}") from e
        except a.RateLimitError as e:
            raise LLMError("Rate limited after retries", retryable=True) from e
        except a.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}", retryable=e.status_code >= 500) from e
        except a.APITimeoutError as e:
            raise LLMError("Request timed out after retries", retryable=True) from e
        except a.APIConnectionError as e:
            raise LLMError("Network error reaching the API", retryable=True) from e


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    latency_ms: int = 0

    def add(self, other: "Usage") -> None:
        for f in ("input_tokens", "output_tokens", "cache_read", "cache_write", "cost_usd", "calls", "latency_ms"):
            setattr(self, f, getattr(self, f) + getattr(other, f))

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["cost_usd"] = round(d["cost_usd"], 4)
        return d


class LLM:
    def __init__(self, settings: Settings, store: Store | None = None, backend: MessagesBackend | None = None):
        self.settings = settings
        self.store = store
        if backend is None:
            if not settings.has_llm_credentials():
                self.backend = None
            else:
                self.backend = AnthropicBackend(settings)
        else:
            self.backend = backend

    @property
    def available(self) -> bool:
        return self.backend is not None

    def create(self, *, purpose: str, ref: str = "", model: str, effort: str, **kwargs: Any) -> tuple[Any, Usage]:
        if self.backend is None:
            raise LLMUnavailable("No ANTHROPIC_API_KEY configured (set it in .env).")
        kwargs.setdefault("max_tokens", 16000)
        t0 = time.monotonic()
        ok, err, resp = True, None, None
        try:
            resp = self.backend.create(model=model, output_config={**kwargs.pop("output_config", {}), "effort": effort}, **kwargs)
            return resp, self._usage(model, resp, t0)
        except LLMError as e:
            ok, err = False, str(e)
            raise
        finally:
            u = self._usage(model, resp, t0) if resp is not None else Usage(latency_ms=int((time.monotonic() - t0) * 1000))
            if self.store is not None:
                try:
                    self.store.log_llm_call(
                        purpose=purpose, ref=ref, model=model, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                        cache_read=u.cache_read, cache_write=u.cache_write, latency_ms=u.latency_ms, ok=ok, error=err,
                        cost_usd=u.cost_usd,
                    )
                except Exception:  # ledger must never break a request
                    log.exception("failed to log LLM call")

    @staticmethod
    def _usage(model: str, resp: Any, t0: float) -> Usage:
        u = getattr(resp, "usage", None)
        it = getattr(u, "input_tokens", 0) or 0
        ot = getattr(u, "output_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        served = getattr(resp, "model", None) or model
        return Usage(it, ot, cr, cw, cost_usd(served if served in _known() else model, it, ot, cr, cw), 1,
                     int((time.monotonic() - t0) * 1000))

    def json_call(self, *, purpose: str, ref: str, model: str, effort: str, system: str, user: str, schema: dict,
                  max_tokens: int = 32000) -> tuple[dict, Usage]:
        """Single structured-output call; returns parsed JSON (schema-constrained)."""
        resp, usage = self.create(
            purpose=purpose, ref=ref, model=model, effort=effort, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":
            raise LLMError("Model declined the request (refusal)")
        if stop == "max_tokens":
            raise LLMError("Output truncated at max_tokens", retryable=False)
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {e}") from e


def _known() -> set[str]:
    from .config import PRICES_PER_MTOK

    return set(PRICES_PER_MTOK)
