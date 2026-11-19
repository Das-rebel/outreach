#!/usr/bin/env python3
"""Generate LONG, per-contact outreach email drafts for APPROVAL_v5 targets.

v2 rebuild (user directive 2026-11-17): v1's rigid 4-sentence skeleton produced
short, near-identical drafts (~650 chars). This module folds in every recovered
earlier engine:

  * /tmp/generate_email_drafts.py (recovered from session 2026-10-25)
      - Minto pyramid: "Three things that map directly to what you're building"
      - 3 domain-matched proof bullets + authentic close
  * /tmp/send_authentic_emails.py (recovered, same session)
      - authentic voice: "Quick background:", Type A follow-up / Type B insight
  * unified_outreach.py (outreach_system, Oct 3)
      - 4-paragraph shape: Hook -> Proof -> Mandate match -> CTA
  * send_pending2.py (canonical sent CoinDCX/PhonePe style)
      - "A bit about me:" paragraph, "Given your mandate and the growth
        challenges you face at {company}..." ask
  * ~/Desktop/email_templates/invested.j2 + casual.j2 (Aug 4)
      - INVESTED = full-length cold application (this module), CASUAL = short
  * build_approval_v5.py house phrases (domain_phrase / proof_points / ask_clause)
  * gen_email_drafts.py v1 validator discipline (banned strings +
    claims_approved numeric whitelist) — KEPT UNCHANGED.

Output per row: role_summary + subject + body (long email) + dm_message
(Latin-house DM, unchanged from approved v5) + validation.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))

APPROVAL = os.path.join(HERE, 'APPROVAL_v5.json')
DECISIONS = os.path.join(HERE, 'DECISIONS_v5.json')
TRACKER = os.path.join(HERE, 'OUTREACH_TRACKER.json')
PROFILE = '/Users/Subho/job_pipeline/pipeline_v2/canonical_profile.json'
OUT = os.path.join(HERE, 'EMAIL_DRAFTS_v2.json')

DL = '/Users/Subho/Downloads/'
RESUMES = {
    'digital': (DL + 'Subhajit_Das_Growth_Digital_Business.pdf', 'Growth_Digital_Business.pdf'),
    'martech': (DL + 'Subhajit_Das_Growth_Marketing_MarTech.pdf', 'Growth_Marketing_MarTech.pdf'),
    'ai':      (DL + 'Subhajit_Das_AI_GTM_Growth_Systems.pdf', 'AI_GTM_Growth_Systems.pdf'),
}

AI_KW = re.compile(r'\b(ai|llm|ml|agentic|machine learning|data scien|nlp|genai|generative)\b', re.I)
MKT_KW = re.compile(r'\b(marketing|brand|demand[- ]?gen|growth market|mar ?tech|crm|lifecycle|content|seo|performance market|communications?|acquisition)\b', re.I)
BIZ_KW = re.compile(r'\b(head of growth|vp growth|vice president.*growth|director.*growth|partnership|business development|\bbd\b|gtm|go[- ]to[- ]market|chief growth|p&l|general manager)\b', re.I)

# ---------------------------------------------------------------------------
# Proof pool — WRITING-safe strings only. Every numeric token must exist in
# canonical_profile.claims_approved (validated below).
# ---------------------------------------------------------------------------
PROOFS = {
    'groww':  "grew Groww's credit revenue 60% while cutting cost-per-funded-loan 28%",
    'niro':   "scaled ₹70 Cr monthly disbursals in 6 months at Niro via MyGate/Snapdeal/NoBroker partnerships",
    'abfl':   "took Aditya Birla Capital from ₹0 to ₹100 Cr monthly disbursals (₹15 Cr+ annual budget, NPS 32 → 58)",
    'axis':   "grew an ₹1,500 Cr digital revenue AOP at Axis Bank (+120%), incl. +22% activation via 50+ A/B tests",
    'icici':  "ran 3x digital cross-sell for 500K+ salary customers at ICICI Bank",
    'orange': "lifted retention at Orange Health Labs with +60% repeat engagement and 2x retention",
    'a3m':    "shipped an open-source AI router — 10K downloads in the first 14 days, 80+ model providers",
    'omni':   "build in production too — an AI agent platform with 31K+ npm downloads",
}
DOMAIN_PROOFS = {
    'fintech': ['groww', 'niro'], 'lending': ['niro', 'groww'],
    'd2c': ['orange', 'abfl'], 'consumer': ['orange', 'axis'],
    'saas': ['groww', 'a3m'], 'ai': ['a3m', 'groww'],
    'agency': ['axis', 'orange'], 'hr': ['abfl', 'a3m'],
    'default': ['groww', 'orange'],
}
# Third bullet rotates so no two emails in a wave read identically.
THIRD_ROTATE = ['a3m', 'icici', 'omni', 'axis']

AI_LINE = ("I build in the AI tooling space myself — an open-source AI router with "
           "10K downloads in its first 14 days — so AI-era GTM is how I operate.")
FRACTIONAL_LINE = "Equally open to a scoped fractional or advisory engagement with real ownership."
SIG_TAG = "Growth Leader | IIM Trichy | Fintech & D2C"
SIG_NAME = "Subhajit Das"
PHONE = "+91 79771 10915"
EMAIL = "sdas22@gmail.com"
BANNED = ["$5m", "$36m", "$8m", "paytm", "dear hiring team", "dear sir/madam",
          "to whom it may concern", "i am writing to apply"]

# ---------------------------------------------------------------------------
# Per-company mandate context (verified-safe facts only; no invented claims)
# ---------------------------------------------------------------------------
COMPANY_CTX = {
    'lifestyle': {
        'mandate': "Lifestyle is one of India's largest fashion retail chains, where "
                   "e-commerce growth economics — CAC, retention, repeat purchase — are the game",
        'mapping': "the retention and performance-marketing levers I've run at Orange Health "
                   "and Groww transfer directly to that playbook",
    },
    'titan email': {
        'mandate': "Titan Email sits in the email/CRM marketing-tech layer, where product-led "
                   "growth and demand generation have to reinforce each other",
        'mapping': "I've driven exactly that pairing — demand-gen efficiency at Groww and "
                   "full-funnel brand work at Axis — on both sides of the funnel",
    },
    'kingston stanley': {
        'mandate': "Kingston Stanley's portfolio spans marketing leadership mandates across "
                   "sectors, so the ability to map growth playbooks to very different businesses matters",
        'mapping': "11 years across fintech, banking, healthtech and consumer gives me that "
                   "cross-sector range first-hand",
    },
    'interglobe aviation (indigo)': {
        'mandate': "IndiGo runs India's largest airline operation, where digital demand "
                   "generation and loyalty economics drive a huge share of bookings",
        'mapping': "large-funnel digital growth — acquisition, activation, repeat, measured "
                   "on unit economics — is work I've done across consumer banking at ICICI "
                   "and Axis for a decade",
    },
    'whizz hr': {
        'mandate': "Whizz HR is a founder-led hiring platform, where early growth has to be "
                   "built with a small team and a tight budget",
        'mapping': "I've worked both sides of that — operator growth inside scaled fintechs, "
                   "and shipping AI tooling solo — which is the mix a founder-led team needs",
    },
}
DEFAULT_MANDATE = ("the growth mandate in this role — brand plus performance, measured "
                   "on the same scoreboard")
DEFAULT_MAPPING = ("the levers are ones I've owned end-to-end: acquisition efficiency, "
                   "retention and repeat revenue across fintech and consumer businesses")


def route_resume(title):
    t = (title or '').lower()
    if AI_KW.search(t): return 'ai'
    if MKT_KW.search(t): return 'martech'
    if BIZ_KW.search(t): return 'digital'
    return 'martech'


def domain_of(company, title):
    blob = f"{company} {title}".lower()
    if re.search(r'whizz|recruit|staffing|\bhr\b|talent', blob): return 'hr'
    if re.search(r'fintech|lending|credit|nbfc|bank|payments|wealth|insurtech|capital|asset management|securities', blob):
        return 'fintech'
    if re.search(r'\b(ai|llm|agentic|data|devtool|developer)\b', blob): return 'ai'
    if re.search(r'd2c|ecommerce|e-commerce|retail|fmcg|consumer|brand|lifestyle|indigo|aviation', blob): return 'd2c'
    if re.search(r'saas|b2b|software|platform|email|mar ?tech|crm', blob): return 'saas'
    if re.search(r'agency|recruit|consult|kingston|stanley', blob): return 'agency'
    return 'default'


def approved_numbers():
    prof = json.load(open(PROFILE))
    nums = set()
    for key, vals in (prof.get('claims_approved') or {}).items():
        if key == '_comment':
            continue
        for v in vals:
            nums.update(re.findall(r'[\d][\d,.]*%?', v))
    return {_suffix_strip(n) for n in nums}


def _suffix_strip(s):
    return re.sub(r'\s*(?:%|Cr|K|M)$', '', s.strip())


def validate(text, allowed_nums, exempt=()):
    low = text.lower()
    for b in BANNED:
        if b in low:
            return False, f'banned:{b}'
    exempt_cores = {_suffix_strip(m2.group(0)) for e in exempt
                    for m2 in re.finditer(r'\b\d[\d,.]*', str(e))}
    for m in re.finditer(r'\b\d[\d,.]*\s*(?:%|Cr|K|M)?\b', text):
        raw = m.group(0).strip()
        core = _suffix_strip(raw)
        if core in allowed_nums or core in exempt_cores:
            continue
        if re.fullmatch(r'(11|90[- ]second|Week 1|1|91|79771|10915|20\d\d|1[0-2]|3[01]|[1-9])', core):
            continue
        ctx = text[max(0, m.start() - 12):m.end() + 8].replace('\n', ' ')
        return False, f'unapproved-number:{raw} @...{ctx}...'
    return True, 'ok'


def pick_proofs(domain, company, idx):
    """3 proofs: 2 domain-matched + 1 rotating third (per-row variety)."""
    base = list(DOMAIN_PROOFS.get(domain, DOMAIN_PROOFS['default']))
    third = THIRD_ROTATE[idx % len(THIRD_ROTATE)]
    if third in base:
        third = THIRD_ROTATE[(idx + 1) % len(THIRD_ROTATE)]
    if third in base:
        third = 'icici' if third != 'icici' else 'omni'
    return [PROOFS[base[0]], PROOFS[base[1]], PROOFS[third]]


def date_bit(applied_date, exempt_out):
    """Render applied date as '(2026-10-27)' and add its digit cores to exempt."""
    if not applied_date:
        return ""
    exempt_out.append(applied_date)
    return f" ({applied_date})"


def role_summary(t):
    """1-2 sentence factual summary of the applied role (user request)."""
    role = t.get('applied_role') or ''
    company = t.get('company') or ''
    date = t.get('applied_date') or ''
    panel = t.get('panel_note') or ''
    design = t.get('contact_designation') or ''
    bits = [f"Applied for {role} at {company}"]
    if date:
        bits[0] += f" on {date}"
    ctx = []
    if panel:
        ctx.append(f"panel: {panel}")
    if design:
        ctx.append(f"contact {design}")
    if t.get('wave'):
        ctx.append(f"wave {t['wave']}")
    s = bits[0] + "."
    if ctx:
        s += " (" + "; ".join(ctx) + ")"
    return s


def build_email(t, idx, allowed):
    first = (t.get('first_name') or (t.get('name') or '').split()[0]).strip()
    company = t.get('company') or ''
    role = t.get('applied_role') or ''
    design_raw = t.get('contact_designation') or ''
    design = re.sub(r'\s*\([^)]*\)', '', design_raw).strip()  # drop '(titan.email)'
    org = t.get('contact_org') or company
    applied = str(t.get('applied_date') or '')
    domain = domain_of(company, role)
    ask = (t.get('ask_clause') or f"how {company} is approaching growth and demand generation")
    dom_phrase = (t.get('domain_phrase') or 'brand and performance marketing')

    exempt = []
    d_bit = date_bit(applied, exempt)
    proofs = pick_proofs(domain, company, idx)
    ctx = COMPANY_CTX.get(company.lower(), {})
    mandate = ctx.get('mandate') or DEFAULT_MANDATE
    mapping = ctx.get('mapping') or DEFAULT_MAPPING

    # --- paragraph 1: personal hook (why THIS person) ---
    if design:
        hook = (f"I applied for the {role} role at {company}{d_bit} and, given your seat "
                f"as {design}, wanted to reach you directly rather than sit in the "
                f"application queue.")
    else:
        hook = (f"I applied for the {role} role at {company}{d_bit} and wanted to reach "
                f"you directly rather than sit in the application queue.")

    # --- paragraph 2: career-arc intro (canonical voice, NO proof duplication) ---
    intro = (f"A bit about me: 11 years of growth leadership across fintech, banking, "
             f"healthtech and consumer internet — owning acquisition, retention and P&L "
             f"end-to-end — and I still build AI tooling on the side.")

    # --- paragraph 3: Minto 3 bullets ---
    bullets = (f"Three things that map directly to what you're building:\n"
               f"— I {proofs[0]}.\n"
               f"— I {proofs[1]}.\n"
               f"— I {proofs[2]}.")

    # --- paragraph 4: mandate match ---
    if design:
        mandate_p = (f"Given your remit as {design} and what {company} is building — "
                     f"{mandate} — the intersection is direct: {mapping}.")
    else:
        mandate_p = (f"Given what {company} is building — {mandate} — the intersection "
                     f"is direct: {mapping}.")

    # --- paragraph 5: CTA ---
    cta = (f"I'd value a short conversation to hear {ask}. Available immediately, "
           f"{FRACTIONAL_LINE[0].lower() + FRACTIONAL_LINE[1:]}")

    body = (
        f"Hi {first},\n\n"
        f"{hook}\n\n"
        f"{intro}\n\n"
        f"{bullets}\n\n"
        f"{mandate_p}\n\n"
        f"{cta}\n\n"
        f"Resume attached — happy to share anything else useful.\n\n"
        f"Regards,\n"
        f"{SIG_NAME} — {SIG_TAG}\n"
        f"{PHONE} | {EMAIL} | linkedin.com/in/subhajitd"
    )
    subject = f"{role} — {company} — {SIG_NAME}"
    ok, why = validate(subject + ' ' + body, allowed, exempt=tuple(exempt))
    return subject, body, ok, why, domain


def main():
    appr = json.load(open(APPROVAL))
    try:
        decisions = json.load(open(DECISIONS))
    except Exception:
        decisions = {}
    try:
        tracker = json.load(open(TRACKER))
        contacts = {c.get('contact_name'): c for c in tracker.get('contacts', [])}
    except Exception:
        contacts = {}
    allowed = approved_numbers()

    out = []
    for idx, t in enumerate(appr.get('targets', [])):
        name = t.get('name', '')
        c = contacts.get(name, {})
        rkey = route_resume(t.get('applied_role', ''))
        subj, body, ok, why, domain = build_email(t, idx, allowed)
        dec = decisions.get(name, {}).get('status', 'PENDING')
        out.append({
            'name': name,
            'first': (t.get('first_name') or name.split()[0]).strip(),
            'company': t.get('company', ''),
            'role': t.get('applied_role', ''),
            'role_summary': role_summary(t),
            'designation': c.get('contact_designation') or t.get('contact_designation') or '',
            'applied_date': str(t.get('applied_date') or ''),
            'wave': t.get('wave'), 'tier': t.get('tier'),
            'decision': dec,
            'channel': 'LinkedIn DM + email',
            'resume_key': rkey,
            'resume_file': RESUMES[rkey][1],
            'resume_path': RESUMES[rkey][0],
            'email': c.get('email') or None,
            'email_status': 'have' if c.get('email') else 'ENRICH_PENDING',
            'subject': subj,
            'body': body,
            'body_len': len(body),
            'dm_message': t.get('message', ''),
            'domain': domain,
            'valid': ok, 'validity_note': why,
        })

    json.dump({'generated': '2026-11-17',
               'style': 'v2 rebuild: recovered Minto + authentic + mandate engines',
               'rows': out}, open(OUT, 'w'), indent=2, ensure_ascii=False)
    bad = [r for r in out if not r['valid']]
    lens = sorted(r['body_len'] for r in out)
    print(f"generated {len(out)} email drafts -> {OUT}")
    print(f"body chars min/median/max: {lens[0]}/{lens[len(lens)//2]}/{lens[-1]}")
    print(f"valid: {len(out) - len(bad)} | INVALID: {len(bad)}")
    for b in bad:
        print(f"  INVALID {b['name']}: {b['validity_note']}")


if __name__ == '__main__':
    main()
