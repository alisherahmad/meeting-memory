"""SQLite memory store: raw turns, retrieval chunks, extracted memory items,
decision threads, speaker roles, and an LLM call ledger.

One file, no server. FTS5 gives BM25 lexical search; optional embeddings are
stored as float32 blobs. `team` is an *indexed* FTS column so team-scoped
search uses the index rather than post-filtering a corpus-wide match.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .transcripts import Meeting, Turn

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meetings(
  meeting_id TEXT PRIMARY KEY, team TEXT NOT NULL, letter TEXT NOT NULL, ordinal INTEGER NOT NULL,
  n_turns INTEGER NOT NULL, n_words INTEGER NOT NULL, content_hash TEXT NOT NULL, parsed_at TEXT NOT NULL,
  extracted_hash TEXT, extracted_at TEXT, extract_model TEXT, summary TEXT
);
CREATE INDEX IF NOT EXISTS ix_meetings_team ON meetings(team, ordinal);
CREATE TABLE IF NOT EXISTS turns(
  meeting_id TEXT NOT NULL, idx INTEGER NOT NULL, start_time TEXT NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY(meeting_id, idx)
);
CREATE TABLE IF NOT EXISTS chunks(
  chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT NOT NULL, team TEXT NOT NULL,
  start_idx INTEGER NOT NULL, end_idx INTEGER NOT NULL, text TEXT NOT NULL, embedding BLOB
);
CREATE INDEX IF NOT EXISTS ix_chunks_meeting ON chunks(meeting_id);
CREATE INDEX IF NOT EXISTS ix_chunks_team ON chunks(team);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, team, chunk_id UNINDEXED, meeting_id UNINDEXED, tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS roles(
  team TEXT NOT NULL, meeting_id TEXT NOT NULL, speaker TEXT NOT NULL, role TEXT NOT NULL,
  source TEXT NOT NULL, turn_idx INTEGER, quote TEXT, name TEXT,
  PRIMARY KEY(team, meeting_id, speaker, source)
);
CREATE TABLE IF NOT EXISTS threads(
  thread_id TEXT PRIMARY KEY, team TEXT NOT NULL, topic TEXT NOT NULL,
  created_in TEXT NOT NULL, updated_in TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_threads_team ON threads(team);
CREATE TABLE IF NOT EXISTS items(
  item_id TEXT PRIMARY KEY, team TEXT NOT NULL, meeting_id TEXT NOT NULL, ordinal INTEGER NOT NULL, seq INTEGER NOT NULL,
  kind TEXT NOT NULL, thread_id TEXT NOT NULL, relation TEXT NOT NULL, related TEXT NOT NULL,
  topic TEXT NOT NULL, statement TEXT NOT NULL, speakers TEXT NOT NULL, owner TEXT NOT NULL, value TEXT NOT NULL,
  evidence TEXT NOT NULL, verified INTEGER NOT NULL, embedding BLOB
);
CREATE INDEX IF NOT EXISTS ix_items_team ON items(team, ordinal, seq);
CREATE INDEX IF NOT EXISTS ix_items_thread ON items(thread_id);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
  topic, statement, team, item_id UNINDEXED, tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS llm_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, purpose TEXT NOT NULL, ref TEXT, model TEXT NOT NULL,
  input_tokens INTEGER, output_tokens INTEGER, cache_read INTEGER, cache_write INTEGER,
  latency_ms INTEGER, ok INTEGER NOT NULL, error TEXT, cost_usd REAL
);
"""

_STOPWORDS = set(
    """a an and are as at be but by did do does for from had has have he her his how i if in into is it its
    me my no not of on or our she so than that the their them then there these they this to too us was we were
    what when where which who whom why will with would you your team teams remote control meeting meetings
    first later end final what which also any one two""".split()
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fts_query(text: str, max_terms: int = 24) -> str:
    """Turn free text into a safe FTS5 OR-query of quoted terms (no syntax injection)."""
    terms: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS or len(tok) < 2 or tok in terms:
            continue
        terms.append(tok)
    return " OR ".join(f'"{t}"' for t in terms[:max_terms])


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._shared: sqlite3.Connection | None = None
        if str(path) == ":memory:":
            # A single shared connection; :memory: databases are per-connection.
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared.row_factory = sqlite3.Row
        with self.tx() as c:
            c.executescript(SCHEMA)

    # -- connection management -------------------------------------------------
    def conn(self) -> sqlite3.Connection:
        if self._shared is not None:
            return self._shared
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            c = self.conn()
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, tuple(params)).fetchall()

    # -- meetings & turns ------------------------------------------------------
    def meeting_row(self, meeting_id: str) -> sqlite3.Row | None:
        rows = self.query("SELECT * FROM meetings WHERE meeting_id=?", (meeting_id,))
        return rows[0] if rows else None

    def upsert_meeting(self, m: Meeting, chunks: list[tuple[int, int, str]]) -> bool:
        """Store a parsed meeting. Returns False if unchanged (idempotent re-ingest)."""
        existing = self.meeting_row(m.meeting_id)
        if existing and existing["content_hash"] == m.content_hash:
            return False
        with self.tx() as c:
            self._delete_meeting(c, m.meeting_id)
            c.execute(
                "INSERT INTO meetings(meeting_id, team, letter, ordinal, n_turns, n_words, content_hash, parsed_at) VALUES(?,?,?,?,?,?,?,?)",
                (m.meeting_id, m.team, m.letter, m.ordinal, len(m.turns), m.n_words, m.content_hash, now_iso()),
            )
            c.executemany(
                "INSERT INTO turns(meeting_id, idx, start_time, speaker, text) VALUES(?,?,?,?,?)",
                [(m.meeting_id, t.idx, t.start_time, t.speaker, t.text) for t in m.turns],
            )
            for start, end, text in chunks:
                cur = c.execute(
                    "INSERT INTO chunks(meeting_id, team, start_idx, end_idx, text) VALUES(?,?,?,?,?)",
                    (m.meeting_id, m.team, start, end, text),
                )
                c.execute(
                    "INSERT INTO chunks_fts(text, team, chunk_id, meeting_id) VALUES(?,?,?,?)",
                    (text, m.team, cur.lastrowid, m.meeting_id),
                )
        return True

    @staticmethod
    def _delete_meeting(c: sqlite3.Connection, meeting_id: str) -> None:
        c.execute("DELETE FROM chunks_fts WHERE meeting_id=?", (meeting_id,))
        c.execute("DELETE FROM chunks WHERE meeting_id=?", (meeting_id,))
        c.execute("DELETE FROM turns WHERE meeting_id=?", (meeting_id,))
        c.execute("DELETE FROM meetings WHERE meeting_id=?", (meeting_id,))

    def turns(self, meeting_id: str, start: int = 0, end: int | None = None) -> list[Turn]:
        end = 10**9 if end is None else end
        rows = self.query(
            "SELECT idx, start_time, speaker, text FROM turns WHERE meeting_id=? AND idx BETWEEN ? AND ? ORDER BY idx",
            (meeting_id, start, end),
        )
        return [Turn(r["idx"], r["start_time"], r["speaker"], r["text"]) for r in rows]

    def meetings(self, team: str | None = None) -> list[sqlite3.Row]:
        if team:
            return self.query("SELECT * FROM meetings WHERE team=? ORDER BY ordinal", (team,))
        return self.query("SELECT * FROM meetings ORDER BY team, ordinal")

    def teams(self) -> list[str]:
        return [r["team"] for r in self.query("SELECT DISTINCT team FROM meetings ORDER BY team")]

    # -- chunks / embeddings ---------------------------------------------------
    def chunks_missing_embeddings(self) -> list[sqlite3.Row]:
        return self.query("SELECT chunk_id, text FROM chunks WHERE embedding IS NULL")

    def set_chunk_embeddings(self, pairs: list[tuple[int, bytes]]) -> None:
        with self.tx() as c:
            c.executemany("UPDATE chunks SET embedding=? WHERE chunk_id=?", [(e, i) for i, e in pairs])

    def items_missing_embeddings(self) -> list[sqlite3.Row]:
        return self.query("SELECT item_id, topic, statement FROM items WHERE embedding IS NULL")

    def set_item_embeddings(self, pairs: list[tuple[str, bytes]]) -> None:
        with self.tx() as c:
            c.executemany("UPDATE items SET embedding=? WHERE item_id=?", [(e, i) for i, e in pairs])

    # -- roles -----------------------------------------------------------------
    def set_roles(self, team: str, meeting_id: str, source: str, roles: list[dict]) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM roles WHERE meeting_id=? AND source=?", (meeting_id, source))
            c.executemany(
                "INSERT OR REPLACE INTO roles(team, meeting_id, speaker, role, source, turn_idx, quote, name) VALUES(?,?,?,?,?,?,?,?)",
                [(team, meeting_id, r["speaker"], r["role"], source, r.get("turn_idx"), r.get("quote"), r.get("name") or "")
                 for r in roles],
            )

    def roles(self, team: str) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM roles WHERE team=? ORDER BY meeting_id, speaker", (team,))

    # -- memory items & threads --------------------------------------------------
    def replace_meeting_memory(
        self, meeting_id: str, summary: str, items: list[dict], new_threads: list[dict], touched_threads: list[str],
        extracted_hash: str, model: str,
    ) -> None:
        """Atomically replace one meeting's extracted memory."""
        with self.tx() as c:
            old = [r["item_id"] for r in c.execute("SELECT item_id FROM items WHERE meeting_id=?", (meeting_id,))]
            c.executemany("DELETE FROM items_fts WHERE item_id=?", [(i,) for i in old])
            c.execute("DELETE FROM items WHERE meeting_id=?", (meeting_id,))
            c.execute("DELETE FROM threads WHERE created_in=?", (meeting_id,))
            for t in new_threads:
                c.execute(
                    "INSERT INTO threads(thread_id, team, topic, created_in, updated_in) VALUES(?,?,?,?,?)",
                    (t["thread_id"], t["team"], t["topic"], meeting_id, meeting_id),
                )
            for tid in touched_threads:
                c.execute("UPDATE threads SET updated_in=? WHERE thread_id=?", (meeting_id, tid))
            for it in items:
                c.execute(
                    """INSERT INTO items(item_id, team, meeting_id, ordinal, seq, kind, thread_id, relation, related, topic,
                       statement, speakers, owner, value, evidence, verified) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        it["item_id"], it["team"], meeting_id, it["ordinal"], it["seq"], it["kind"], it["thread_id"],
                        it["relation"], json.dumps(it["related"]), it["topic"], it["statement"], json.dumps(it["speakers"]),
                        it["owner"], it["value"], json.dumps(it["evidence"]), int(it["verified"]),
                    ),
                )
                c.execute(
                    "INSERT INTO items_fts(topic, statement, team, item_id) VALUES(?,?,?,?)",
                    (it["topic"], it["statement"], it["team"], it["item_id"]),
                )
            c.execute(
                "UPDATE meetings SET summary=?, extracted_hash=?, extracted_at=?, extract_model=? WHERE meeting_id=?",
                (summary, extracted_hash, now_iso(), model, meeting_id),
            )

    def clear_team_memory_from(self, team: str, ordinal: int) -> None:
        """Drop extracted memory for meetings >= ordinal (they depend on earlier state)."""
        with self.tx() as c:
            mids = [r["meeting_id"] for r in c.execute(
                "SELECT meeting_id FROM meetings WHERE team=? AND ordinal>=?", (team, ordinal))]
            for mid in mids:
                ids = [r["item_id"] for r in c.execute("SELECT item_id FROM items WHERE meeting_id=?", (mid,))]
                c.executemany("DELETE FROM items_fts WHERE item_id=?", [(i,) for i in ids])
                c.execute("DELETE FROM items WHERE meeting_id=?", (mid,))
                c.execute("DELETE FROM threads WHERE created_in=?", (mid,))
                c.execute("DELETE FROM roles WHERE meeting_id=? AND source='llm'", (mid,))
                c.execute("UPDATE meetings SET extracted_hash=NULL, extracted_at=NULL, summary=NULL WHERE meeting_id=?", (mid,))

    def items(self, team: str, before_ordinal: int | None = None) -> list[dict]:
        sql, params = "SELECT * FROM items WHERE team=?", [team]
        if before_ordinal is not None:
            sql += " AND ordinal < ?"
            params.append(before_ordinal)
        return [item_row_to_dict(r) for r in self.query(sql + " ORDER BY ordinal, seq", params)]

    def item(self, item_id: str) -> dict | None:
        rows = self.query("SELECT * FROM items WHERE item_id=?", (item_id,))
        return item_row_to_dict(rows[0]) if rows else None

    def threads(self, team: str) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM threads WHERE team=? ORDER BY thread_id", (team,))

    # -- LLM ledger --------------------------------------------------------------
    def log_llm_call(self, **row: Any) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO llm_calls(ts, purpose, ref, model, input_tokens, output_tokens, cache_read, cache_write,
                   latency_ms, ok, error, cost_usd) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now_iso(), row.get("purpose"), row.get("ref"), row.get("model"), row.get("input_tokens", 0),
                    row.get("output_tokens", 0), row.get("cache_read", 0), row.get("cache_write", 0),
                    row.get("latency_ms", 0), int(row.get("ok", True)), row.get("error"), row.get("cost_usd", 0.0),
                ),
            )


def item_row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d.pop("embedding", None)
    for k in ("related", "speakers", "evidence"):
        d[k] = json.loads(d[k])
    d["verified"] = bool(d["verified"])
    return d
