# RUNBOOK — Outreach engine v2

Operational guide for `outreach_engine/`. Read this before running any
command. Nothing in this runbook sends anything on its own.

Companion: `docs/adr/002-outreach-engine-architecture.md` (why it is built
this way), `DECISION_GRAPH.md` R55-R60 (the rules it implements).

---

## 0. The one rule that matters

**The engine never sends anything by itself.** A message goes out only when
(a) it passed every hard gate, (b) it is in the approval bundle, (c) a human
approved it in a decision file, and (d) the operator passed `--send`.

---

## 1. The daily loop

```bash
cd /Users/Subho/job_pipeline

# 1. INGRESS — read every source node into one candidate pool
python3 -m outreach_engine ingest

# 2. ELIGIBLE — apply the hard gates, get reason codes
python3 -m outreach_engine eligible

# 3. RANK — deterministic score + P0-P7 tier + 2-per-company cap
python3 -m outreach_engine rank

# 4. PANEL — optional multi-model second opinion (demotes only)
python3 -m outreach_engine panel

# 5. DRAFT — house-format messages, claim whitelist enforced
python3 -m outreach_engine draft

# 6. APPROVAL — export the human bundle
python3 -m outreach_engine approval
#    -> runs/outreach/engine_state/APPROVAL_bundle.md

# 7. HUMAN REVIEW — read the bundle, edit, and write a decision file
#    (format below)

# 8. DISPATCH — dry run first, then send
python3 -m outreach_engine dispatch --approved runs/outreach/engine_state/approved.json
python3 -m outreach_engine dispatch --approved runs/outreach/engine_state/approved.json --send

# 9. OUTCOMES — record replies / rejections, see follow-ups due
python3 -m outreach_engine outcomes
python3 -m outreach_engine outcomes --set "Liquiloans|Head, Growth Strategy|replied" --note "recruiter replied"

# 10. STATUS — where the pipeline stands
python3 -m outreach_engine status
```

Every command prints a JSON summary and writes an artifact under
`runs/outreach/engine_state/`:

| Artifact | Written by |
|---|---|
| `candidates.json` | `ingest` |
| `eligible.json` | `eligible` |
| `ranked.json` | `rank` |
| `panel.json` | `panel` |
| `drafts.json` | `draft` |
| `APPROVAL_bundle.md` / `.json` | `approval` |
| `outcomes.jsonl` | `outcomes` (append-only) |
| `li_dm_log.jsonl` | `dispatch` (append-only) |
| `status.json` | `status` |

---

## 2. What needs human approval

Everything in `APPROVAL_bundle.md` needs a human decision. Each numbered item
carries the channel, the recipient, their designation, the application it
refers to, the LinkedIn URL, the resume filename, and the **exact** message
that would be sent in a fenced block.

Write a decision file naming what you approve. Both formats work:

```json
{"approved": ["Pankaj Juneja", "Manish Pathania"], "rejected": ["Girish Gupta"]}
```

```json
{"approved": [{"name": "Pankaj Juneja", "rank": 1}, {"rank": 3}]}
```

```markdown
1. Pankaj Juneja — approved
2. Girish Gupta — rejected
3. Manish Pathania — approved
```

Then:

```bash
python3 -m outreach_engine dispatch --approved runs/outreach/engine_state/approved.json
```

---

## 3. Rules the engine enforces (and you cannot override)

| Rule | Source | Effect |
|---|---|---|
| 15-day eligibility window | `config.dm_eligibility_days` | older applications are `window_expired` |
| banned companies | canonical `companies_banned` ∪ `claims_banned_written` keys | `banned_company` |
| do-not-approach names | canonical `do_not_approach` | `do_not_approach` |
| R39 — no managers | `eligibility._MANAGER_RE` | `r39_manager` |
| R40 — no analysts | `eligibility._ANALYST_RE` | `r40_analyst` |
| no repeat contact | `li_dm_log.jsonl`, `multi_channel_log.jsonl`, prior `APPROVAL*.json` | `already_contacted` |
| Apollo free tier is not contactable | obfuscated last name | `apollo_obfuscated_unresolved` |
| must be reachable | LinkedIn URL or verified email | `no_url_no_email` |
| seniority ladder | canonical `seniority.leadership_keywords` | `not_senior` |
| function fit | growth / marketing / GTM / TA | `off_function` |
| TA + business dual role | recruiter AND strong business function | `ta_or_business_dual` |
| max 2 contacts per company | `config.max_per_company` | dropped from the ranked list |
| max 5 DMs per run | `config.max_dms_per_day` | dispatch stops at 5 |
| claim whitelist | canonical `claims_approved` | draft is dropped |
| banned written strings | canonical `claims_banned_written` | draft is dropped |

---

## 4. Budgets and cadences

| Knob | Default | Env override |
|---|---|---|
| Monid outreach bucket | **$0.30 / day** | `OE_MONID_OUTREACH_BUDGET_USD` |
| Monid balance (reported) | $3.19 | `OE_MONID_BALANCE_USD` |
| Max DMs per run | 5 | `OE_MAX_DMS_PER_DAY` |
| Pause between DMs | 20-40s | `OE_DM_PAUSE_MIN`, `OE_DM_PAUSE_MAX` |
| Max contacts per company | 2 | `OE_MAX_PER_COMPANY` |
| Follow-up offsets | +3 / +7 / +14 days | `OE_FOLLOWUP_OFFSETS` |
| Message body cap | 600 chars | `OE_MAX_BODY_CHARS` |
| DM eligibility window | 15 days | `OE_DM_WINDOW_DAYS` |

Spend is tracked in `runs/outreach/engine_state/monid_spend.json`. The Apollo
adapter refuses to run live when the day's outreach spend has reached the
bucket ceiling.

---

## 5. Channel toggles

| Channel | Default | Env | Notes |
|---|---|---|---|
| LinkedIn DM | ON | `OE_CHANNEL_LINKEDIN=0/1` | CDP on `http://127.0.0.1:9335` |
| Email | **OFF** | `OE_CHANNEL_EMAIL=1` | SMTP; verified email only; gates E1-E4 |
| WhatsApp | **OFF** | `OE_CHANNEL_WHATSAPP=1` | GoWA wrapper at `127.0.0.1:8090` |

Live source lanes (opt-in, each may spend money or take minutes):

| Lane | Env | Default |
|---|---|---|
| Apollo live search | `OE_APOLLO_LIVE=1` | off (free tier obfuscates names anyway) |
| LinkedIn live harvest | `OE_LINKEDIN_LIVE=1` | off (offline pools are used) |
| Gmail reply mining | `OE_GMAIL=0` disables | on, read-only |

---

## 6. Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `NO_MESSAGE_BUTTON` | only Connect/Follow on the profile | expected — the engine never sends a connection request |
| `typed_needs_manual_send` | the Send control did not render; Enter does not send | open the browser, press Send by hand; a screenshot is saved under `/tmp/dm_screenshots` |
| `SEND_CLICKED_BUT_COMPOSER_NOT_CLEARED` | send may not have gone through | check the screenshot before assuming anything |
| `TEXT_MISMATCH` | the composer did not accept the exact message | check the composer, do not resend blindly |
| `ATTACH_FAILED` | no file input rendered | attach the resume by hand before sending |
| `apollo_obfuscated_unresolved` | Apollo free tier returns `Last*` names | resolve the real name + URL first; the candidate is not contactable until then |
| `window_expired` for everything | the tracker dates are old, or `--today` is wrong | check `python3 -m outreach_engine status` |
| `claim violation` in the draft warnings | the message contained an unapproved number | fix the source of the number; the engine dropped the draft deliberately |
| panel falls back to rules only | no panel CLI reachable, or it timed out | informational; set `OE_PANEL_BACKEND=cli_panel` and ensure a CLI is on PATH |
| `playwright not installed` | CDP dispatch needs playwright | it is already available in this environment; otherwise install it |

**Screenshots**: `/tmp/dm_screenshots/` (override with `OE_SCREENSHOT_DIR`).

---

## 7. Artifacts of record

| File | Owner | Purpose |
|---|---|---|
| `runs/outreach/engine_state/candidates.json` | engine | the unified candidate pool |
| `runs/outreach/engine_state/APPROVAL_bundle.md` | engine | what a human reads |
| `runs/outreach/engine_state/outcomes.jsonl` | engine | append-only outcome log |
| `runs/outreach/engine_state/li_dm_log.jsonl` | engine | append-only DM attempt log |
| `attachments/outreach/li_dm_log.jsonl` | prior lane | read as suppression input |
| `applied_companies_tracker.json` | tracker | what we applied for, and when |

---

## 8. Tests

```bash
python3 -m unittest tests.test_outreach_engine -v
```

Stdlib `unittest` only. No network access, no sending.


---

## 11. Clean pipeline (v1, 2026-11-20) — batch-of-10 approval flow

Canonical orchestrator: `runs/outreach/pipeline_clean.py`

```bash
# Audit sources and state
python3 runs/outreach/pipeline_clean.py sources

# Full run (deterministic shortlist; adds dual-LLM judge when providers available)
python3 runs/outreach/pipeline_clean.py run --min-batch 10

# Deterministic only (no LLM calls)
python3 runs/outreach/pipeline_clean.py run --no-llm --min-batch 10

# Check status / pending batches
python3 runs/outreach/pipeline_clean.py status
```

**Flow:** HARVEST → FETCH EMAIL (free: book/SMTP/catch-all) → SHORTLIST (hard gates + deterministic score + optional dual-LLM AND-gate: crouton-alpha/OpenRouter + glm-5.3/z.ai) → BUILD CONTENT (v3 drafts, JD summary, resume) → BATCH APPROVAL.

**Batch approval rule:** when ≥10 complete packages are ready, present via `ask_user_question` in batches of 10 with all required details (Person, Designation, Company, Email, Address evidence, Applied role, Applied date, Job summary, Subject, Resume, Full email body). Record decisions, send approved, log, repeat. If <10 ready, save packages and do not prompt until threshold met.

**Artifacts:** `runs/outreach/clean_state/{harvest,enriched,shortlist,packages_final,report}.json`, `PENDING_BATCH_*.json`.

**Current exclusions (2026-11-20):** TransUnion (cycle skip), smallcase Dir - Business & Partnerships (skip). Max 2 contacts per applied role.
