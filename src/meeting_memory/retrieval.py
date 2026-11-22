"""Hybrid retrieval over transcript chunks and memory items. Plain code.

BM25 (SQLite FTS5) catches exact terms ("titanium", "twelve fifty"); MiniLM
embeddings catch paraphrase ("stop it getting lost" ~ "locator", "beeper").
Ranks are fused with Reciprocal Rank Fusion, which needs no score calibration.

Scale note: lexical search is index-backed and team-scoped. The dense side is a
brute-force cosine over the *filtered* candidate set (one team, or one meeting),
which stays small at any corpus size because questions are scoped. Unscoped dense
search over 10k+ meetings would need an ANN index (sqlite-vec / pgvector / FAISS).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from . import embeddings
from .store import Store, fts_query

RRF_K = 60


@dataclass
class ChunkHit:
    chunk_id: int
    meeting_id: str
    team: str
    start_idx: int
    end_idx: int
    text: str
    score: float
    sources: list[str] = field(default_factory=list)


def _rrf(rankings: dict[str, list], k: int = RRF_K) -> dict:
    fused: dict = {}
    for _, ranked in rankings.items():
        for rank, key in enumerate(ranked):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank + 1)
    return fused


class Retriever:
    def __init__(self, store: Store, embedding_model: str | None = None):
        self.store = store
        self.embedding_model = embedding_model  # None disables the dense side

    @property
    def dense_enabled(self) -> bool:
        return bool(self.embedding_model) and embeddings.available(self.embedding_model)

    # -- transcript chunks -------------------------------------------------------
    def _bm25_chunks(self, query: str, team: str | None, meeting_ids: list[str] | None, limit: int) -> list[int]:
        q = fts_query(query)
        if not q:
            return []
        match = f"text:({q})"
        if team:
            match = f'team:"{team.lower()}" AND {match}'
        sql = "SELECT chunk_id, meeting_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?"
        rows = self.store.query(sql, (match, limit * 4 if meeting_ids else limit))
        ids = [r["chunk_id"] for r in rows if not meeting_ids or r["meeting_id"] in meeting_ids]
        return ids[:limit]

    def _dense_chunks(self, query: str, team: str | None, meeting_ids: list[str] | None, limit: int) -> list[int]:
        if not self.dense_enabled:
            return []
        sql, params = "SELECT chunk_id, embedding FROM chunks WHERE embedding IS NOT NULL", []
        if team:
            sql += " AND team=?"
            params.append(team)
        if meeting_ids:
            sql += f" AND meeting_id IN ({','.join('?' * len(meeting_ids))})"
            params.extend(meeting_ids)
        rows = self.store.query(sql, params)
        if not rows:
            return []
        qv = embeddings.encode([query], self.embedding_model)
        if qv is None:
            return []
        mat = np.vstack([embeddings.from_blob(r["embedding"]) for r in rows])
        sims = mat @ qv[0]
        order = np.argsort(-sims)[:limit]
        return [rows[i]["chunk_id"] for i in order]

    def search_chunks(
        self, query: str, team: str | None = None, meeting_ids: list[str] | None = None, limit: int = 6, mode: str = "hybrid"
    ) -> list[ChunkHit]:
        pool = max(limit * 4, 20)
        rankings: dict[str, list[int]] = {}
        if mode in ("hybrid", "bm25"):
            rankings["bm25"] = self._bm25_chunks(query, team, meeting_ids, pool)
        if mode in ("hybrid", "dense"):
            rankings["dense"] = self._dense_chunks(query, team, meeting_ids, pool)
        fused = _rrf(rankings)
        top = sorted(fused, key=lambda cid: -fused[cid])[:limit]
        if not top:
            return []
        rows = {
            r["chunk_id"]: r
            for r in self.store.query(
                f"SELECT chunk_id, meeting_id, team, start_idx, end_idx, text FROM chunks WHERE chunk_id IN ({','.join('?' * len(top))})",
                top,
            )
        }
        return [
            ChunkHit(
                chunk_id=cid, meeting_id=rows[cid]["meeting_id"], team=rows[cid]["team"], start_idx=rows[cid]["start_idx"],
                end_idx=rows[cid]["end_idx"], text=rows[cid]["text"], score=round(fused[cid], 5),
                sources=[name for name, ranked in rankings.items() if cid in ranked],
            )
            for cid in top
        ]

    # -- memory items --------------------------------------------------------------
    def search_items(self, query: str, team: str | None = None, kinds: list[str] | None = None, limit: int = 12) -> list[str]:
        pool = max(limit * 4, 30)
        rankings: dict[str, list[str]] = {}
        q = fts_query(query)
        if q:
            match = f"{{topic statement}}:({q})"
            if team:
                match = f'team:"{team.lower()}" AND {match}'
            rows = self.store.query(
                "SELECT item_id FROM items_fts WHERE items_fts MATCH ? ORDER BY bm25(items_fts, 2.0, 1.0, 0.0) LIMIT ?",
                (match, pool),
            )
            rankings["bm25"] = [r["item_id"] for r in rows]
        if self.dense_enabled:
            sql, params = "SELECT item_id, embedding FROM items WHERE embedding IS NOT NULL", []
            if team:
                sql += " AND team=?"
                params.append(team)
            rows = self.store.query(sql, params)
            qv = embeddings.encode([query], self.embedding_model) if rows else None
            if rows and qv is not None:
                mat = np.vstack([embeddings.from_blob(r["embedding"]) for r in rows])
                order = np.argsort(-(mat @ qv[0]))[:pool]
                rankings["dense"] = [rows[i]["item_id"] for i in order]
        fused = _rrf(rankings)
        ranked = sorted(fused, key=lambda i: -fused[i])
        if kinds:
            kind_of = {
                r["item_id"]: r["kind"]
                for r in self.store.query(
                    f"SELECT item_id, kind FROM items WHERE item_id IN ({','.join('?' * len(ranked))})", ranked
                )
            } if ranked else {}
            ranked = [i for i in ranked if kind_of.get(i) in kinds]
        return ranked[:limit]


_TEAM_RE = re.compile(r"\b([A-Z]{2}\d{4})\b")


def team_from_text(text: str) -> str | None:
    """Deterministic scope hint: a team id named in the question."""
    m = _TEAM_RE.search(text)
    return m.group(1) if m else None
