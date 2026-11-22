"""Ingest pipeline.

Stage 1 (code, no LLM, seconds): parse -> turns + retrieval chunks -> FTS index,
          self-introduction roles.
Stage 2 (local model, optional): chunk embeddings.
Stage 3 (LLM, one call per meeting): structured memory, per team in meeting order
          (meeting c is extracted with a/b's memory as context), teams in parallel.
Stage 4 (local model, optional): item embeddings.

Idempotent: unchanged meetings are skipped (content hash). Re-extracting meeting k
of a team invalidates k+1.. (their memory was built on top of it).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import embeddings
from .chunking import chunk_meeting
from .config import Settings
from .extraction import extract_meeting
from .llm import LLM, LLMError, LLMRefusal, Usage
from .roles import detect_self_introductions
from .store import Store
from .transcripts import Meeting, TranscriptParseError, discover_transcripts, load_transcript

log = logging.getLogger(__name__)


@dataclass
class IngestReport:
    meetings_found: int = 0
    meetings_parsed: int = 0
    meetings_unchanged: int = 0
    parse_errors: list[str] = field(default_factory=list)
    turns: int = 0
    words: int = 0
    chunks: int = 0
    embedded_chunks: int = 0
    embedded_items: int = 0
    embeddings_note: str = ""
    extracted: list[str] = field(default_factory=list)
    extraction_skipped: list[str] = field(default_factory=list)
    extraction_failed: dict[str, str] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    extraction_stats: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    usage: Usage = field(default_factory=Usage)
    seconds: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["usage"] = self.usage.as_dict()
        d["extraction_stats"] = dict(self.extraction_stats)
        return d


def stage_parse(settings: Settings, store: Store, report: IngestReport, only_teams: set[str] | None = None) -> list[Meeting]:
    t0 = time.monotonic()
    meetings = []
    for path in discover_transcripts(Path(settings.transcripts_dir)):
        if only_teams and path.stem[:-1] not in only_teams:
            continue
        report.meetings_found += 1
        try:
            m = load_transcript(path)
        except (TranscriptParseError, UnicodeDecodeError) as e:
            report.parse_errors.append(f"{path.name}: {e}")
            continue
        changed = store.upsert_meeting(m, chunk_meeting(m))
        if changed:
            report.meetings_parsed += 1
            store.set_roles(m.team, m.meeting_id, "intro_regex", detect_self_introductions(m))
        else:
            report.meetings_unchanged += 1
        report.turns += len(m.turns)
        report.words += m.n_words
        meetings.append(m)
    report.chunks = store.query("SELECT COUNT(*) n FROM chunks")[0]["n"]
    report.seconds["parse_index"] = round(time.monotonic() - t0, 2)
    return meetings


def stage_embed_chunks(settings: Settings, store: Store, report: IngestReport) -> None:
    if not settings.use_embeddings:
        report.embeddings_note = "disabled (MM_EMBEDDINGS=0)"
        return
    t0 = time.monotonic()
    rows = store.chunks_missing_embeddings()
    if rows:
        vecs = embeddings.encode([r["text"] for r in rows], settings.embedding_model)
        if vecs is None:
            report.embeddings_note = f"unavailable: {embeddings.unavailable_reason()}"
            return
        store.set_chunk_embeddings([(r["chunk_id"], embeddings.to_blob(v)) for r, v in zip(rows, vecs)])
    report.embedded_chunks = len(rows)
    report.seconds["embed_chunks"] = round(time.monotonic() - t0, 2)


def stage_embed_items(settings: Settings, store: Store, report: IngestReport) -> None:
    if not settings.use_embeddings or report.embeddings_note.startswith("unavailable"):
        return
    t0 = time.monotonic()
    rows = store.items_missing_embeddings()
    if rows:
        vecs = embeddings.encode([f"{r['topic']}: {r['statement']}" for r in rows], settings.embedding_model)
        if vecs is not None:
            store.set_item_embeddings([(r["item_id"], embeddings.to_blob(v)) for r, v in zip(rows, vecs)])
    report.embedded_items = len(rows)
    report.seconds["embed_items"] = round(time.monotonic() - t0, 2)


def _team_series(meetings: list[Meeting]) -> dict[str, list[Meeting]]:
    by_team: dict[str, list[Meeting]] = defaultdict(list)
    for m in meetings:
        by_team[m.team].append(m)
    return {t: sorted(ms, key=lambda m: m.ordinal) for t, ms in by_team.items()}


def _extract_team(team: str, series: list[Meeting], settings: Settings, store: Store, llm: LLM, force: bool,
                  on_event: Callable[[str], None]) -> list[tuple[str, str, object]]:
    """Sequential within a team. Returns [(meeting_id, status, payload)]."""
    out = []
    dirty = force
    for m in series:
        row = store.meeting_row(m.meeting_id)
        if not dirty and row and row["extracted_hash"] == m.content_hash:
            out.append((m.meeting_id, "skipped", None))
            continue
        if not dirty:
            store.clear_team_memory_from(team, m.ordinal)
            dirty = True
        elif force and m is series[0]:
            store.clear_team_memory_from(team, m.ordinal)
        try:
            try:
                res = extract_meeting(m, store, llm, settings.extract_model, settings.extract_effort)
            except LLMRefusal:
                if settings.agent_model == settings.extract_model:
                    raise
                # Client-side fallback: retry this one meeting on the agent model.
                on_event(f"{m.meeting_id}: {settings.extract_model} declined; retrying on {settings.agent_model}")
                res = extract_meeting(m, store, llm, settings.agent_model, settings.extract_effort)
                res.stats["refusal_fallbacks"] = 1
            on_event(f"extracted {m.meeting_id}: {res.stats['items_kept']} items")
            out.append((m.meeting_id, "ok", res.stats))
        except LLMError as e:
            on_event(f"FAILED {m.meeting_id}: {e}")
            out.append((m.meeting_id, "failed", str(e)))
            # Later meetings depend on this one's memory: do not build on a gap.
            out.extend((later.meeting_id, "blocked", None) for later in series if later.ordinal > m.ordinal)
            break
    return out


def stage_extract(settings: Settings, store: Store, llm: LLM, meetings: list[Meeting], report: IngestReport,
                  force: bool = False, on_event: Callable[[str], None] = lambda s: None) -> None:
    t0 = time.monotonic()
    series = _team_series(meetings)
    with ThreadPoolExecutor(max_workers=max(1, settings.ingest_concurrency)) as pool:
        futures = {pool.submit(_extract_team, t, ms, settings, store, llm, force, on_event): t for t, ms in series.items()}
        for fut in as_completed(futures):
            for mid, status, payload in fut.result():
                if status == "skipped":
                    report.extraction_skipped.append(mid)
                elif status == "failed":
                    report.extraction_failed[mid] = payload
                elif status == "blocked":
                    report.blocked.append(mid)
                else:
                    report.extracted.append(mid)
                    for k, v in payload.items():
                        if k == "usage":
                            report.usage.add(Usage(**{f: v[f] for f in v}))
                        else:
                            report.extraction_stats[k] += v
    report.seconds["extract"] = round(time.monotonic() - t0, 2)


def run_ingest(settings: Settings, store: Store, llm: LLM, *, extract: bool = True, force: bool = False,
               only_teams: set[str] | None = None, on_event: Callable[[str], None] = print) -> IngestReport:
    report = IngestReport()
    t0 = time.monotonic()
    meetings = stage_parse(settings, store, report, only_teams)
    on_event(f"parsed {report.meetings_found} meetings ({report.meetings_parsed} new/changed), {report.chunks} chunks")
    stage_embed_chunks(settings, store, report)
    on_event(f"chunk embeddings: {report.embedded_chunks} new {report.embeddings_note}".strip())
    if extract:
        if not llm.available:
            report.embeddings_note += " | extraction skipped: no ANTHROPIC_API_KEY"
            on_event("extraction skipped: no ANTHROPIC_API_KEY configured")
        else:
            stage_extract(settings, store, llm, meetings, report, force=force, on_event=on_event)
            stage_embed_items(settings, store, report)
    report.seconds["total"] = round(time.monotonic() - t0, 2)
    return report
