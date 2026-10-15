# Outreach Pipeline — Das-rebel/job_pipeline mirror

**Purpose:** Authentic-voice LinkedIn DMs to high-relevance applied-role contacts.
All content auto-generated from applied roles tracker + Apollo discovery + top-100 target plan.

---

## 📁 File Map

```
messages/
├── outreach_messages_final_2026-10-14.json   ← MAIN: 95 DMs (plan + gaps)
├── top40_dm_plan_2026-10-14.json          ← D1-D8 wave plan (35 active)
├── outreach_targets_final_2026-10-14.json  ← 72 companies with TYPE A/B contacts
├── outreach_gaps_100_2026-10-14.json      ← 114 tiered gap companies
└── outreach_gaps_discovered_2026-10-14.json ← raw Apollo discovery results

scripts/
├── dm_send_with_resume.py       ← HEADLESS LinkedIn DM sender (this is the code)
├── blocklist.py                  ← do-not-approach + companies_banned enforcement
├── canonical_profile.json        ← SSOT blocklist (do_not_approach: 15 names)
└── li_dm_log.jsonl               ← sent DM audit log

docs/
└── README.md                      ← this file
```

---

## 🔧 How to Build / Regenerate Messages

### Prerequisites
```bash
# Apollo discovery (FREE search, $0.05/enrich — balance $0.02 as of Oct 14)
# Install monid: https://monid.ai
monid balance

# Chromium cookies for LinkedIn session
LI_COOKIE_SRC=chromium   # default — reads from ~/Library/Application Support/Chromium/Default/Cookies

# Python deps
pip install playwright jsonlines
playwright install chromium
```

### Message generation pipeline

```bash
# Step 1: Pull applied roles tracker (last 90 days, senior growth/marketing/brand/GTM)
python3 << 'EOF'
# See: ~/job_pipeline/applied_companies_tracker.json
# Filter: senior titles, fintech/bank/GCC/MarTech, no perf-marketing, no junior
# Classify by category: FINTECH/GCC/MARTECH/D2C
# Dedup by company, rank by priority (fintech>bank>GCC>martech>D2C>other)
# Output: outreach_gaps_100_2026-10-14.json
EOF

# Step 2: Apollo people discovery (FREE, no email enrichment needed for DMs)
# Domain-targeted search per company
monid run -p apollo -e /mixed_people/api_search \
  -i '{"person_titles":["marketing","growth","brand","go-to-market","demand generation","talent acquisition","recruiter"],
       "person_seniorities":["head","director","vp","c_suite","manager","senior"],
       "person_locations":["India"],
       "q_organization_domains_list":["stripe.com","tide.co"],"per_page":8}' \
  -w -o /tmp/apollo_disc/stripe.json

# Step 3: Aggregate + classify TYPE A (TA/recruiter) vs TYPE B (growth/marketing)
python3 << 'EOF'
# See: outreach_targets_final_2026-10-14.json structure
# Filter against: do_not_approach (blocklist.py canonical), already-contacted (li_dm_log.jsonl)
# Confidence: HIGH = TYPE A+B + senior title, MED = single type, NONE = no Apollo hit
EOF

# Step 4: Auto-generate messages
python3 gen_messages.py   # → outreach_messages_final_2026-10-14.json
```

### Message JSON schema
```json
{
  "name": "Kanchan B***",
  "title": "Head of Marketing, India",
  "company": "Stripe",
  "message": "Hi Kanchan — I applied for the Marketing Operations Manager role at Stripe recently. My background is 11 years in fintech — Groww $5M→$36M, Axis Bank ₹1500Cr, Niro ₹70Cr/mo. Resume attached. Would love to learn more.",
  "resume": "Subhajit_Das_AI_GTM_Growth_Systems.pdf",
  "type": "B",
  "confidence": "HIGH",
  "applied": "2026-10-14"
}
```

---

## 🚀 How to Send DMs (Headless)

```bash
# Set LinkedIn cookie source
export LI_COOKIE_SRC=chromium   # or: brave, firefox

# Preview what would be sent (dry run)
python3 dm_send_with_resume.py --dry-run

# Send to specific target by name
python3 dm_send_with_resume.py --only-name "Kanchan"

# Send top N
python3 dm_send_with_resume.py --limit 5

# Resume after interruption
python3 dm_send_with_resume.py --resume
```

### DM send flow (dm_send_with_resume.py)
1. Load `messages/outreach_messages_final_2026-10-14.json`
2. Extract LinkedIn URL from name + company (try `linkedin.com/in/{first-last}` pattern)
3. Navigate to LinkedIn, open messaging modal
4. Attach resume PDF via `input[type=file]` → `set_input_files`
5. Type message with human pauses (50-100ms per char group)
6. Send, screenshot to `/tmp/dm_screenshots/`, log to `li_dm_log.jsonl`

### Cookie / session setup
```bash
# Chromium (primary — session expires ~1-2h)
# Cookies at: ~/Library/Application Support/Chromium/Default/Cookies
# Refresh: open linkedin.com in Chromium, log in if needed

# Brave (blocked — DB empty, use Chromium)
# Firefox (backup)
```

---

## 📋 Active Rules

| Rule | Detail |
|------|--------|
| **DM eligibility** | Company where user applied ≤15 days ago |
| **Cadence** | Max 3-5 DMs/day |
| **Blocklist** | 15 names in `canonical_profile.json` do_not_approach |
| **Companies banned** | groww, swiggy, orange health, oolka, upstock, blinkit, kiddo, hummingbird, huntlo, goodspace, battery, oolka |
| **Email pattern-guessing** | STOP — never guess email patterns (Gokuldas failure lesson) |
| **Message tone** | Jitendra-pattern: casual 2-3 lines, metrics, one clear question. No AI tells. |
| **Resume mapping** | GTM/AI → AI_GTM | Lending/Business → Digital_Business | Marketing/Brand → MarTech |

---

## 📊 Current Status (Oct 14 2026)

- **D1-D8 plan**: 35 active targets, D1 drafted and ready
- **Gap discoveries**: 72 companies with TYPE A/B contacts (38 HIGH, 22 MED, 12 NONE)
- **Apollo balance**: $0.02 — enrich impossible, search FREE
- **LinkedIn session**: needs refresh (cookies expire ~1-2h)
- **Sent DMs log**: `scripts/li_dm_log.jsonl`
