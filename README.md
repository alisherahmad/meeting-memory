# Meeting Memory

An agent that turns meeting transcripts into **time-aware memory** you can question, and that writes a **pre-meeting brief**. Every quote it cites is checked by code to appear word for word in one speaker turn.

Built for the Catalist Agentic AI Intern build test (138 AMI meetings, 676,745 words, 25 questions, TS3012 brief).

- **How it works:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · **one-page write-up:** [docs/WRITEUP.md](docs/WRITEUP.md)
- **Model vs code, and why:** [docs/DECISION_LOG.md](docs/DECISION_LOG.md)
- **Results and failures:** [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md) · **status:** [docs/EXECUTION_STATUS.md](docs/EXECUTION_STATUS.md)

## Quick start

Requires Python 3.10+ (built on 3.11.9, Windows 11). Run all commands from the project root.

```powershell
pip install -r requirements.txt
```

Put the Catalist data in `data/` (the zip is not committed):

```powershell
Expand-Archive Catalist_AI_Intern_Build_Test_Data.zip -DestinationPath data
```

Add your key: copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Then make the package importable for this shell:

```powershell
$env:PYTHONPATH = "src"
```

| Step | Command | Needs key | Time / cost (measured) |
|---|---|---|---|
| Tests (no network) | `python -m pytest -q` | no | ~12 s |
| Parse + index only | `python -m meeting_memory ingest --no-extract` | no | ~9 s (+ embeddings, see below) |
| Full ingest (memory extraction) | `python -m meeting_memory ingest --report evaluation/results/ingest_report.json` | yes | see EVALUATION_REPORT |
| Ask one question | `python -m meeting_memory ask "Team ES2002: what power source did they first agree on?"` | yes | |
| The submission | `python -m meeting_memory answer-all` → `answers.json` (+ TS3012 brief) | yes | |
| Brief only | `python -m meeting_memory brief --team TS3012` (`--no-llm` for the deterministic version) | optional | |
| Web UI | `python -m meeting_memory serve` → http://127.0.0.1:8765 | for Ask | |
| Check answers.json like the grader | `python -m meeting_memory.evaluate check-answers -v` | no | |
| Score our 12 gold questions | `python -m meeting_memory.evaluate gold` | yes | |
| Retrieval recall (BM25 / dense / hybrid) | `python -m meeting_memory.evaluate retrieval` | no | |
| Cost ledger | `python -m meeting_memory stats` | no | |

Embeddings are optional (`MM_EMBEDDINGS=0` for BM25 only). They use the local `all-MiniLM-L6-v2` from the Hugging Face cache and never download at runtime.

## What's where
```
src/meeting_memory/
  transcripts.py  chunking.py  store.py      parsing, chunks, SQLite + FTS5 (code only)
  quotes.py       roles.py     retrieval.py  citation verification, per-meeting roles, hybrid search (code only)
  memory.py                                  what is current / superseded / open (code only)
  extraction.py                              per-meeting memory extraction (the model)
  agent.py        tools.py                   bounded tool-use agent + read-only tools
  brief.py                                   pre-meeting brief (code picks facts, model writes prose)
  llm.py  ingest.py  cli.py  server.py  static/  evaluate.py
tests/            43 tests, no network (fake model backend)
evaluation/       gold_set.json (12 checked questions), results/
docs/             specification, architecture, decisions, evaluation, walkthrough
```

## Known limitations
See [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md) and [docs/FINAL_REVIEW.md](docs/FINAL_REVIEW.md). In short: memory quality depends on one extraction pass per meeting; the agent can still choose the wrong passage when several meetings discuss the same topic; the UI has no authentication (local use only).

## Data
AMI Meeting Corpus, University of Edinburgh and partners, CC BY 4.0, as reformatted by Catalist. Transcripts, questions and the brief are not committed to this repository.
