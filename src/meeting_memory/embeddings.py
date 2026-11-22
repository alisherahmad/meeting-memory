"""Optional local sentence embeddings (MiniLM-L6, 384-d, CPU).

Loaded lazily and only from the local Hugging Face cache (HF_HUB_OFFLINE=1): the
system never downloads model weights at runtime. If unavailable, retrieval falls
back to BM25 only and says so.
"""

from __future__ import annotations

import logging
import os
import threading

import numpy as np

log = logging.getLogger(__name__)
DIM = 384
_model = None
_failed: str | None = None
_lock = threading.Lock()


def _load(model_name: str):
    global _model, _failed
    with _lock:
        if _model is not None or _failed:
            return _model
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            from sentence_transformers import SentenceTransformer  # heavy import (torch)

            _model = SentenceTransformer(model_name, device="cpu")
        except Exception as e:  # noqa: BLE001 - any failure means "embeddings unavailable"
            _failed = f"{type(e).__name__}: {e}"
            log.warning("Embeddings unavailable, using BM25 only: %s", _failed)
        return _model


def available(model_name: str) -> bool:
    return _load(model_name) is not None


def unavailable_reason() -> str | None:
    return _failed


def encode(texts: list[str], model_name: str, batch_size: int = 64) -> np.ndarray | None:
    model = _load(model_name)
    if model is None:
        return None
    vecs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
