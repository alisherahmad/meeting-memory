"""Settings from environment (and an optional .env file). No secrets are logged."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader: KEY=VALUE lines; never overrides real env vars."""
    path = path or PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    transcripts_dir: Path = field(default_factory=lambda: Path(_env("MM_TRANSCRIPTS_DIR", str(PROJECT_ROOT / "data" / "transcripts"))))
    db_path: Path = field(default_factory=lambda: Path(_env("MM_DB_PATH", str(PROJECT_ROOT / "var" / "memory.db"))))
    agent_model: str = field(default_factory=lambda: _env("MM_AGENT_MODEL", "claude-opus-5-5"))
    extract_model: str = field(default_factory=lambda: _env("MM_EXTRACT_MODEL", "claude-opus-5-5"))
    agent_effort: str = field(default_factory=lambda: _env("MM_AGENT_EFFORT", "medium"))
    extract_effort: str = field(default_factory=lambda: _env("MM_EXTRACT_EFFORT", "medium"))
    use_embeddings: bool = field(default_factory=lambda: _env("MM_EMBEDDINGS", "1") not in ("0", "false", "off"))
    embedding_model: str = field(default_factory=lambda: _env("MM_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    # Agent loop guards
    max_agent_steps: int = field(default_factory=lambda: int(_env("MM_MAX_AGENT_STEPS", "14")))
    max_submit_rejections: int = field(default_factory=lambda: int(_env("MM_MAX_SUBMIT_REJECTIONS", "2")))
    agent_timeout_s: float = field(default_factory=lambda: float(_env("MM_AGENT_TIMEOUT_S", "300")))
    llm_request_timeout_s: float = field(default_factory=lambda: float(_env("MM_LLM_TIMEOUT_S", "240")))
    llm_max_retries: int = field(default_factory=lambda: int(_env("MM_LLM_MAX_RETRIES", "4")))
    ingest_concurrency: int = field(default_factory=lambda: int(_env("MM_INGEST_CONCURRENCY", "6")))
    use_refusal_fallback: bool = field(default_factory=lambda: _env("MM_REFUSAL_FALLBACK", "1") not in ("0", "false", "off"))

    def has_llm_credentials(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def get_settings() -> Settings:
    load_dotenv()
    return Settings()


# USD per million tokens (Anthropic first-party list prices, cached 2026-11-03).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.00, 40.00),
}
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
    pin, pout = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (
        input_tokens * pin + output_tokens * pout + cache_read * pin * CACHE_READ_MULT + cache_write * pin * CACHE_WRITE_MULT
    ) / 1_000_000
