# OUTREACH DECISION TREE — Subhajit Das (v2 clean pipeline, 2026-11-20)

## GOLDEN RULE
**For every single outreach: Research the person → Decide → Build complete package → Human approves → Then send. Never batch-template without review. Never present for approval without a verified email and all required details.**

---

## CLEAN PIPELINE FLOW (canonical: `runs/outreach/pipeline_clean.py`)

```
HARVEST → FETCH EMAIL → SHORTLIST → BUILD CONTENT → BATCH APPROVAL (×10) → SEND → LOG → REPEAT
```

1. **HARVEST** (all free/local sources)
   - `applied_companies_tracker.json` fresh apps (≤14 days), priority P0→P7
   - `OUTREACH_TRACKER.json` panel contacts (people matched to applied companies)
   - `EMAIL_BOOK.json` published/verified addresses
   - `LINKEDIN_PEOPLE*.json` sweep caches (logged-in CDP people search)
   - Map each candidate to a fresh applied role/company

2. **FETCH EMAIL** (evidence required, free-first)
   - Book-published address (with verification status)
   - SMTP-verified (250 = deliverable) pattern probe
   - Catch-all MX (server accepts mailbox) — marked as evidence
   - Paid (Hunter/Monid/Apollo enrich) only if balance/cap allows and necessary; Monid $0.30/day cap
   - **No guessed/fabricated emails. No contactable package without evidenced address.**

3. **SHORTLIST** (hard gates + decision model)
   - **Hard gates:** DNC/do-not-approach, banned/declined companies, already sent/contacted/decided, freshness ≤14d, **max 2 contacts per applied role** (company+role), seniority (Head/Director/VP/AVP/Chief/GM), function fit to applied role, no TransUnion/smallcase (current cycle), no generic aliases
   - **Deterministic score:** priority tier (P0 best), recency, seniority, function fit, email evidence quality, slot availability
   - **Dual-LLM decision model (AND-gate, when available):** primary `crouton-alpha` (OpenRouter) + verifier `glm-5.3` (z.ai) via `xiryn_kit/llm_decide.py` pattern — semantic relevance/fit judgment; may demote/re-rank, never bypass hard gates. Fallback: deterministic-only.

4. **BUILD CONTENT** (send-ready, complete package)
   - Subject + full email body (v3 Minto/house format, claim-whitelist enforced, R21/R58)
   - **Job summary** (applied role, date, priority, fit rationale, decision-model note)
   - Resume variant routed by role (`resume_for`: AI_GTM / Digital_Business / MarTech)
   - Required fields in every package: **Person, Designation, Company, Email, Address evidence, Applied role, Applied date, Job summary, Subject, Resume, Full email body**

5. **BATCH APPROVAL** (ask-user CLI, human-gated)
   - Present for approval **only when a complete package exists** (verified/evidenced email + all details)
   - When **≥10 packages ready**: present in **batches of 10** via `ask_user_question` with all required details shown
   - Decisions: Approve & send / Reject / Skip for later
   - Send only approved (Gmail SMTP + resume attached), log to `li_dm_log.jsonl`, update trackers
   - **Repeat** batch-by-batch until queue exhausted or stopped
   - If <10 ready: save and continue discovery; do not prompt until threshold met

---

## DECISION MODEL

- **Deterministic (always):** role priority (P0 fintech → P7 other), recency (≤14d), seniority ladder, function-fit, email evidence, per-role cap
- **Dual-LLM AND-gate (optional, preferred):** crouton-alpha (OpenRouter) + glm-5.3 (z.ai) — both must approve for LLM-approved status; semantic check that contact is relevant, senior, and worth outreach for the specific applied role. Graceful degradation to deterministic-only if providers unavailable.
- **Human (final):** explicit approval per candidate in ask-user CLI; nothing sent without approval

---

## HARD RULES / NEGATIVES (STOP)

| Check | Rule | Action |
|-------|------|--------|
| No evidenced email | No verified/book/SMTP/catch-all evidence | **STOP** — do not package or present |
| Already contacted | in `li_dm_log.jsonl` or prior approvals/sends | **STOP** |
| DNC / do-not-approach | `canonical_profile.do_not_approach` / declined | **STOP** |
| Banned/declined company | canonical/declined list | **STOP** |
| Per-role cap | ≥2 contacts already sent for same applied role | **STOP** |
| Not senior | no Head/Director/VP/AVP/Chief/GM (business) | **STOP** |
| Off-function | title doesn't fit applied role function | **STOP** |
| Generic alias | careers@/hr@/info@/jobs@/hello@ etc. | **STOP** |
| TransUnion | skipped this cycle (2026-11-20) | **STOP** |
| smallcase | skipped for Dir - Business & Partnerships (2026-11-20) | **STOP** |

---

## APPROVAL PACKAGE (required fields, every candidate)

- Person, Designation, Company (+ priority label)
- Email + Address evidence
- Applied role, Applied date
- Job summary (fit/priority/decision rationale)
- Subject, Resume version
- **Full email body**

---

## STATE / ARTIFACTS

- `runs/outreach/clean_state/` — harvest, enriched, shortlist, packages_final, report, PENDING_BATCH_*.json
- `runs/outreach/DECISIONS_*.json`, `approved_names*.json` — human decisions
- `attachments/outreach/li_dm_log.jsonl` — send log (append-only)
- `runs/outreach/OUTREACH_TRACKER.json` — tracker updates
