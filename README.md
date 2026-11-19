# Outreach — clean, maintainable pipeline repo

Dedicated repo for the outreach pipeline (harvest → fetch email → shortlist → build content → batch approval → send).

**Repo:** https://github.com/Das-rebel/outreach  
**Scope:** outreach logic, decision model hooks, docs, and approval/send tooling.  
**Data/state:** lives in the job-pipeline workspace (tracker, canonical profile, email book, logs) and is referenced via config/env paths.

## Clean pipeline flow (v1)

Canonical orchestrator: `pipeline/pipeline_clean.py`

1. **HARVEST** — tracker panel contacts, `EMAIL_BOOK`, LinkedIn people sweep caches, fresh applied roles (≤14d) from tracker
2. **FETCH EMAIL** — free-first evidence: book-published, SMTP-verified 250, catch-all MX; paid Monid/Hunter only within cap/balance
3. **SHORTLIST** — hard gates (DNC/banned/declined/sent/decided, max 2 per applied role, seniority, function fit, freshness) + deterministic scoring + optional **dual-LLM AND-gate** (crouton-alpha/OpenRouter + glm-5.3/z.ai)
4. **BUILD CONTENT** — complete send-ready package: verified email, Person/Designation/Company, Address evidence, Applied role/date, Job summary, Subject, Full email body (v3, claim-whitelist), Resume
5. **BATCH APPROVAL** — when ≥10 complete packages ready, present via `ask_user_question` in batches of 10 with all required details; record decisions, send approved, log, repeat

## Quick start

```bash
# from repo root
export OUTREACH_DATA_ROOT=~/job_pipeline   # or your job-pipeline path

# audit sources
python3 pipeline/pipeline_clean.py sources

# run (deterministic; add LLM judge when providers available)
python3 pipeline/pipeline_clean.py run --no-llm --min-batch 10

# status / pending batches
python3 pipeline/pipeline_clean.py status
```

### Key env/config

| Variable | Purpose | Default |
|---|---|---|
| `OUTREACH_DATA_ROOT` / `JOB_PIPELINE_ROOT` | external data root | `~/job_pipeline` |
| `OUTREACH_TRACKER_PATH` | applied companies tracker | `$DATA_ROOT/applied_companies_tracker.json` |
| `OUTREACH_PROFILE_PATH` | canonical profile (claims/DNC/bans) | `$DATA_ROOT/pipeline_v2/canonical_profile.json` |
| `OUTREACH_DM_LOG_PATH` | outreach send log (JSONL) | `$DATA_ROOT/attachments/outreach/li_dm_log.jsonl` |
| `OUTREACH_BOOK_PATH` | email book | `$DATA_ROOT/runs/outreach/EMAIL_BOOK.json` |
| `OUTREACH_RUNS_DIR` | runs/outreach state dir | `$DATA_ROOT/runs/outreach` |
| `OUTREACH_STATE_DIR` | pipeline clean state output | `pipeline/clean_state` |
| `OE_GMAIL_USER` / `OE_GMAIL_APP_PW` | Gmail SMTP for sending | — |

## Structure

- `pipeline/` — clean pipeline orchestrator + harvest/email/draft/sweep/send helpers
- `outreach_engine/` — modular engine (sources, eligibility, scoring, panel, messaging, approval, dispatch, tracking)
- `xiryn_kit/` — decision helpers (role priority, dual-LLM decide, relevance)
- `docs/` — runbook, decision tree, ADR
- `archive/` — legacy snapshots (messages/scripts)

## Rules (high level)

- **Human-gated:** nothing sent without explicit approval. Batch approval in 10s when ≥10 complete packages ready.
- **Evidence required:** no guessed/fabricated emails; every package needs verified/book/SMTP/catch-all evidence.
- **Caps/limits:** max 2 contacts per applied role; $0.30/day outreach spend cap; Monid paid enrich only when balance allows.
- **Claims:** v3 Minto/house format, fail-closed claim whitelist (canonical profile).
- **Current cycle exclusions:** TransUnion skipped; smallcase (Dir - Business & Partnerships) skipped (2026-11-20).

## Docs

- `docs/RUNBOOK_OUTREACH.md`
- `docs/OUTREACH_DECISION_TREE.md`
- `docs/002-outreach-engine-architecture.md`

## Legacy

Older DM message batches and sender scripts preserved under `archive/` for reference.
