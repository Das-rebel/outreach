#!/usr/bin/env python3
"""Email drafting v3 — LOCKED rules (user directive, session 2026-11-16/17).

Locked rule set (from the REBUILT COVER LETTER ENGINE + canonical_profile):
  * Barbara Minto Pyramid: answer first -> 3 proofs -> close
  * R21 TRUE-ONLY metrics, writing-safe strings only.  Anything numeric
    outside canonical_profile.claims_approved = STOP.
  * subho.email_voice: "Hi {name}" — NEVER "Dear Hiring Team"
  * Em-dashes (—) and authentic phrases: "hit the ground running from Week 1"
  * Signature: Growth Leader | IIM Trichy | Fintech & D2C
  * Domain proofs: fintech=[groww,niro] lending=[niro,groww] d2c=[abc,niro]
    health=[orange,niro] saas=[groww,niro] ai=[groww,niro]
    consumer=[orange,abc] default=[groww,niro]  and A3M is ALWAYS the 3rd bullet
  * Banned: paytm, ex-paytm, 10m+ users, dear hiring team, dear sir/madam,
    to whom it may concern, i am writing to apply, $5m/$36m/$8m (verbal-only)

v3 differs from v2 by: locked domain-proof pairs + A3M always third, the
Week-1 authentic close, the full banned list, JD-derived scope lines, and the
"answer first" Minto opening.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_email_drafts_v2 as v2

SIG_TAG = "Growth Leader | IIM Trichy | Fintech & D2C"
SIG_NAME = "Subhajit Das"
PHONE = "+91 79771 10915"
EMAIL = "sdas22@gmail.com"
LINKEDIN = "linkedin.com/in/subhajitd"

BANNED = ["$5m", "$36m", "$8m", "paytm", "ex-paytm", "10m+ users",
          "dear hiring team", "dear sir/madam", "to whom it may concern",
          "i am writing to apply", "dear sir", "dear madam"]

WEEK1 = "I can hit the ground running from Week 1"

# writing-safe proof strings (only numbers inside claims_approved)
PROOFS = {
    'groww':  "grew Groww's credit revenue 60% while cutting cost-per-funded-loan 28%",
    'niro':   "scaled ₹70 Cr monthly disbursals in 6 months at Niro via MyGate/Snapdeal/NoBroker partnerships",
    'abfl':   "took Aditya Birla Capital from ₹0 to ₹100 Cr monthly disbursals (₹15 Cr+ annual budget, NPS 32 → 58)",
    'axis':   "grew an ₹1,500 Cr digital revenue AOP at Axis Bank (+120%), incl. +22% activation via 50+ A/B tests",
    'icici':  "ran 3x digital cross-sell for 500K+ salary customers at ICICI Bank",
    'orange': "lifted retention at Orange Health Labs with +60% repeat engagement and 2x retention",
    'a3m':    "shipped an open-source AI router — 10K downloads in its first 14 days, 80+ model providers",
    'omni':   "build in production too — an AI agent platform with 31K+ npm downloads",
}
# LOCKED domain pairs (from the rebuilt cover-letter engine)
DOMAIN_PROOFS = {
    'fintech': ['groww', 'niro'],
    'lending': ['niro', 'groww'],
    'd2c':     ['abfl', 'niro'],
    'health':  ['orange', 'niro'],
    'saas':    ['groww', 'niro'],
    'ai':      ['groww', 'niro'],
    'consumer':['orange', 'abfl'],
    'agency':  ['axis', 'orange'],
    'hr':      ['abfl', 'a3m'],
    'default': ['groww', 'niro'],
}
A3M_THIRD = 'a3m'   # A3M always the 3rd bullet

def domain_of(company, title):
    blob = f"{company} {title}".lower()
    if re.search(r'whizz|recruit|staffing|\bhr\b|talent|manpower', blob): return 'hr'
    if re.search(r'fintech|lending|credit|nbfc|bank|payments|wealth|insurtech|capital|asset management|securities', blob):
        return 'fintech'
    if re.search(r'\b(ai|llm|agentic|data|devtool|developer)\b', blob): return 'ai'
    if re.search(r'd2c|ecommerce|e-commerce|retail|fmcg|consumer|brand|lifestyle|indigo|aviation|ice cream', blob):
        return 'd2c'
    if re.search(r'saas|b2b|software|platform|email|mar ?tech|crm', blob): return 'saas'
    if re.search(r'agency|consult|kingston|stanley', blob): return 'agency'
    return 'default'

def validate(text, allowed_nums, exempt=()):
    low = text.lower()
    for b in BANNED:
        if b in low:
            return False, f'banned:{b}'
    exempt_cores = {v2._suffix_strip(m2.group(0)) for e in exempt
                    for m2 in re.finditer(r'\b\d[\d,.]*', str(e))}
    for m in re.finditer(r'\b\d[\d,.]*\s*(?:%|Cr|K|M)?\b', text):
        raw = m.group(0).strip()
        core = v2._suffix_strip(raw).rstrip('.,')
        if core in allowed_nums or core in exempt_cores:
            continue
        if re.fullmatch(r'(11|90[- ]second|Week 1|1|91|79771|10915|20\d\d|1[0-2]|3[01]|[1-9])', core):
            continue
        ctx = text[max(0, m.start() - 12):m.end() + 8].replace('\n', ' ')
        return False, f'unapproved-number:{raw} @...{ctx}...'
    return True, 'ok'

def _jd_clause(jd_summary):
    """One clean factual clause from the captured JD (scope only, trimmed)."""
    if not jd_summary:
        return None
    scope = (jd_summary.get('scope') or '').strip()
    if not scope:
        return None
    scope = re.sub(r'^(Overview|About the Role|The Role|Job Purpose|About)\b[:\s-]{0,3}', '', scope, flags=re.I)
    scope = scope.lstrip(' .,:;-')
    # a scope that begins mid-word ("us Green Portfolio is ...") -> drop the
    # leading fragment so the sentence starts cleanly
    first = scope.split(' ', 1)[0]
    if first and first[0].islower() and not first.endswith(('.', ',', ':')):
        scope = scope.split(' ', 1)[1] if ' ' in scope else scope
    scope = re.sub(r'(About the Role|The Role|Job Purpose|Overview)\s*', ' ', scope, flags=re.I)
    scope = re.sub(r'\s+', ' ', scope).strip()
    scope = re.sub(r'\s+', ' ', scope)
    # keep only complete sentences, then cap the length on a word boundary
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', scope) if len(p.strip()) > 30]
    clause = ' '.join(parts[:2]) if parts else scope
    words = clause.split()
    if len(words) > 42:
        clause = ' '.join(words[:42])
        # drop a dangling final fragment
        if not clause.endswith(('.', '!', '?')):
            clause = clause.rsplit(' ', 1)[0]
    clause = clause.rstrip(' .,;:')
    if not clause.endswith(('.', '!', '?')):
        clause += '.'
    return clause

def build_email(t, idx, allowed, jd_summary=None, custom=None):
    first = (t.get('first_name') or (t.get('name') or '').split()[0]).strip()
    company = t.get('company') or ''
    role = t.get('applied_role') or ''
    design = re.sub(r'\s*\([^)]*\)', '', (t.get('contact_designation') or '')).strip()
    applied = str(t.get('applied_date') or '')
    domain = domain_of(company, role)
    ask = (custom or {}).get('ask') or t.get('ask_clause') or \
        f"how {company} is approaching growth and demand generation"

    exempt = []
    d_bit = ''
    if applied:
        exempt.append(applied)
        d_bit = f" ({applied})"

    pair = list(DOMAIN_PROOFS.get(domain, DOMAIN_PROOFS['default']))
    # A3M is always the 3rd bullet, but never repeat a bullet already used
    third = A3M_THIRD
    if third in pair:
        for alt in ('omni', 'icici', 'orange', 'groww'):
            if alt not in pair:
                third = alt
                break
        else:
            third = A3M_THIRD
    bullets_txt = [PROOFS[pair[0]], PROOFS[pair[1]], PROOFS[third]]

    ctx = v2.COMPANY_CTX.get(company.lower(), {})
    mandate = ctx.get('mandate') or v2.DEFAULT_MANDATE
    mapping = ctx.get('mapping') or v2.DEFAULT_MAPPING
    if custom:
        mandate = custom.get('company') or mandate
        mapping = custom.get('mapping') or mapping

    # --- Minto: ANSWER FIRST ---
    remit = (custom or {}).get('remit')
    # a LinkedIn headline is not a job title ("Driving Growth Through ...") —
    # don't put it in the "given your seat as ..." slot
    TITLEISH = re.compile(r'(?i)\b(head|director|vp|chief|founder|president|manager|'
                          r'lead|partner|officer|gm|avp|consultant|executive)\b')
    if design and not TITLEISH.search(design):
        design = ''
    answer = (f"I applied for the {role} role at {company}{d_bit} and wanted to reach you "
              f"directly rather than sit in the application queue — growth leadership with "
              f"P&L ownership is the exact intersection I've spent 11 years building.")
    if design and remit:
        answer = (f"I applied for the {role} role at {company}{d_bit}, and given that you "
                  f"run {remit}, I wanted to reach you directly rather than sit in the "
                  f"application queue — growth leadership with P&L ownership is the exact "
                  f"intersection I've spent 11 years building.")
    elif design:
        answer = (f"I applied for the {role} role at {company}{d_bit} and, given your seat "
                  f"as {design}, wanted to reach you directly rather than sit in the "
                  f"application queue — growth leadership with P&L ownership is the exact "
                  f"intersection I've spent 11 years building.")

    intro = ("A bit about me: 11 years of growth leadership across fintech, banking, "
             "healthtech and consumer internet — owning acquisition, retention and P&L "
             "end-to-end — and I still build AI tooling on the side.")

    bullets = ("Three things that map directly to what you're building:\n"
               f"— I {bullets_txt[0]}.\n"
               f"— I {bullets_txt[1]}.\n"
               f"— I {bullets_txt[2]}.")

    jd_clause = _jd_clause(jd_summary)
    if remit:
        mandate_p = (f"Given what {company} is building — {mandate} — the intersection is "
                     f"direct: {mapping}")
    elif design:
        mandate_p = (f"Given your remit as {design} and what {company} is building — "
                     f"{mandate} — the intersection is direct: {mapping}")
    else:
        mandate_p = (f"Given what {company} is building — {mandate} — the intersection is "
                     f"direct: {mapping}")
    if not mandate_p.rstrip().endswith(('.', '!', '?')):
        mandate_p += '.'
    if jd_clause:
        mandate_p += f" What the role calls for is concrete: {jd_clause}"

    if jd_clause:
        # numbers quoted from the JD are the company's own facts, not candidate
        # claims -> exempt them from the R21 claim whitelist
        exempt.append(jd_clause)

    close = (f"{WEEK1} — I'd welcome the chance to discuss {ask}. Available immediately, "
             f"and equally open to a scoped fractional or advisory engagement with real "
             f"ownership.")

    body = (
        f"Hi {first},\n\n"
        f"{answer}\n\n"
        f"{intro}\n\n"
        f"{bullets}\n\n"
        f"{mandate_p}\n\n"
        f"{close}\n\n"
        f"Resume attached — happy to share anything else useful.\n\n"
        f"Regards,\n"
        f"{SIG_NAME} — {SIG_TAG}\n"
        f"{PHONE} | {EMAIL} | {LINKEDIN}"
    )
    subject = f"{role} — {company} — {SIG_NAME}"
    ok, why = validate(subject + ' ' + body, allowed, exempt=tuple(exempt))
    return subject, body, ok, why, domain
