"""House-format message generation (v3 / Oct 31) with HARD claim enforcement.

The house format is ONE paragraph, then exactly one blank line, then the
signature block:

    TYPE A  Hi {first} — I applied for the {role} role at {company} ({Mon D})
            and couldn't find an update on my application. 11 years in
            {domain_phrase} — {proof}. Resume attached. Could you share where
            my application stands, or let me know what would strengthen my
            profile?

    TYPE B  Hi {first} — I applied for the {role} role at {company} ({Mon D}).
            11 years in {domain_phrase} — {proof}. Resume attached — Would love
            to learn more about {ask_clause}.

CLAIM ENFORCEMENT (hard, fail-closed)
    Every number that appears in a message body must be traceable to
    `canonical_profile.json -> claims_approved`.  A number that cannot be
    traced raises `ClaimViolation`.  The banned written strings
    (`claims_banned_written` — "$5M to $36M", "$8M MRR", "Paytm") plus the
    never-written tokens "8x" must be absent.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .eligibility import parse_date
from .identity import first_name

SIGNATURE = ('Regards,\nSubhajit Das\n+91 79771 10915\n'
             'linkedin.com/in/subhajitd')

# --- banned tokens -------------------------------------------------------
# "$5M to $36M", "$8M MRR" and "Paytm" come from canonical claims_banned_written
# at runtime.  "8x" is a NEVER-WRITTEN growth multiple (it is a verbal-only
# claim in the earlier packs) — kept here as a constant because the canonical
# file lists the sentence form but not the bare multiple.
EXTRA_BANNED_WRITTEN = ['8x']

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# --- domain phrasing -----------------------------------------------------
DOMAIN_PHRASE_FINTECH = 'fintech growth'
DOMAIN_PHRASE_GTM = 'growth and GTM ops'
DOMAIN_PHRASE_MARKETING = 'brand and performance marketing'
DOMAIN_PHRASE_DEFAULT = 'fintech and consumer growth'

DOMAIN_KEYWORDS = [
    (DOMAIN_PHRASE_FINTECH,
     re.compile(r'fintech|lending|credit|bank|wealth|insurance|payments?|financ',
                re.I)),
    (DOMAIN_PHRASE_GTM,
     re.compile(r'growth|gtm|go[- ]?to[- ]?market|partnerships|channel|merchant|'
                r'revops|revenue operations|commercial', re.I)),
    (DOMAIN_PHRASE_MARKETING,
     re.compile(r'marketing|brand|demand|performance|content|campaign|customer|'
                r'lifecycle', re.I)),
]

# --- proof points (verbatim from canonical claims_approved) ----------------
PROOF_FINTECH = ["Groww's 60% credit revenue growth",
                 "Axis Bank's ₹1,500 Cr digital revenue AOP"]
PROOF_GTM = ["Groww's 60% credit revenue growth",
             "Axis Bank's ₹1,500 Cr digital revenue AOP"]
PROOF_MARKETING = ["Groww's 60% credit revenue growth",
                   "Orange Health's +60% repeat engagement and 2x retention"]
PROOF_AI = ["Omniclaw's 31K+ npm downloads",
            "A3M Router's 10K downloads in first 14 days and 80+ model providers"]

AI_OPEN_SOURCE_SENTENCE = (' I also build in the open — github.com/Das-rebel '
                            'and huggingface.co/Hayasuki.')

ASK_CLAUSE_RULES = [
    ('credit_book',
     re.compile(r'lending|credit|bank|financ', re.I),
     'how {company} is scaling its credit book'),
    ('partner_growth',
     re.compile(r'merchant|channel|partnership|alliance', re.I),
     'how {company} is building partner-led growth'),
    ('ai_gtm',
     re.compile(r'\bai\b|llm|agent|genai', re.I),
     'how {company} is putting AI into its go-to-market'),
    ('brand',
     re.compile(r'brand|content|creative|perception', re.I),
     "{company}'s brand and perception work"),
    ('demand',
     re.compile(r'performance|demand|acquisition|growth|marketing', re.I),
     'how {company} is approaching growth and demand generation'),
]
ASK_CLAUSE_DEFAULT = 'the team at {company}'

TYPE_A_ASK = ('Could you share where my application stands, or let me know what '
              'would strengthen my profile?')


class ClaimViolation(Exception):
    """Raised when a message carries a number or string that is not approved."""


# --------------------------------------------------------------------------
# Claim enforcement
# --------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r'(?:₹|\$|rs\.?\s*)?\d[\d,]*\.?\d*\s*(?:%|x\b|cr\b|lakh|lpa|k\b|m\b|bn\b)?',
    re.I)


def _normalise_number(token: str) -> str:
    t = token.strip().lower()
    t = re.sub(r'\s+', ' ', t)
    t = t.replace('₹', '').replace('$', '').replace('rs.', '').replace('rs ', '')
    t = re.sub(r'[,\s]', '', t)
    t = re.sub(r'(cr|lakh|lpa|bn|m|k)$', '', t) if t[-1:] in 'clmbk' else t
    return t.rstrip('.')


def approved_numbers(profile: Dict) -> set:
    """Every numeric token that appears in canonical `claims_approved`."""
    allowed = set()
    for values in (profile.get('claims_approved') or {}).values():
        if isinstance(values, str):
            values = [values]
        for value in values or []:
            for match in _NUMBER_RE.finditer(str(value)):
                norm = _normalise_number(match.group(0))
                if norm:
                    allowed.add(norm)
                    # also allow the bare number without its unit
                    bare = norm.rstrip('%x')
                    if bare:
                        allowed.add(bare)
    return allowed


def banned_written(profile: Dict) -> List[str]:
    banned = [str(k) for k in (profile.get('claims_banned_written') or {})]
    for extra in EXTRA_BANNED_WRITTEN:
        if extra not in banned:
            banned.append(extra)
    return banned


def assert_claims(message: str, profile: Dict, max_body_chars: int = 600) -> None:
    """Raise `ClaimViolation` unless the message is claim-clean."""
    body = message.split('\n\nRegards,')[0]

    for banned in banned_written(profile):
        if banned and banned.lower() in message.lower():
            raise ClaimViolation('banned written string %r in message' % banned)

    allowed = approved_numbers(profile)
    # The house format itself contributes two numbers: "11 years" and the
    # application date. Both are structural, not claims.
    allowed.add('11')
    for month in MONTHS:
        allowed.add(month.lower())

    for match in _NUMBER_RE.finditer(body):
        token = match.group(0).strip()
        if not token:
            continue
        norm = _normalise_number(token)
        if not norm:
            continue
        if norm.lower() in allowed or norm.lower() in {m.lower() for m in MONTHS}:
            continue
        if norm in allowed:
            continue
        # dates inside the body: "(Oct 28)" — the day number is structural
        if re.fullmatch(r'\d{1,2}', norm) and _in_date_context(body, token):
            continue
        raise ClaimViolation('unapproved number %r in message body' % token)

    if len(body) > max_body_chars:
        raise ClaimViolation('message body %d chars > %d'
                             % (len(body), max_body_chars))


def _in_date_context(body: str, token: str) -> bool:
    """True when the number is the DAY of a "(Mon D)" application date."""
    idx = body.find(token)
    if idx < 0:
        return False
    before = body[max(0, idx - 16):idx]
    return bool(re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*$',
                          before, re.I))


def assert_house_format(message: str, name: str = '') -> None:
    """Structural assertions on the house format."""
    body = message.split('\n\nRegards,')[0]
    label = name or 'message'
    if not message.endswith(SIGNATURE):
        raise ClaimViolation('signature block wrong for %s' % label)
    if 'Resume attached' not in message:
        raise ClaimViolation('missing "Resume attached" for %s' % label)
    if '11 years in' not in message:
        raise ClaimViolation('missing "11 years in" for %s' % label)
    if ' role at ' not in message:
        raise ClaimViolation('missing " role at " for %s' % label)
    if message.count('\n\nRegards,') != 1:
        raise ClaimViolation('blank line before Regards wrong for %s' % label)
    if '\n\n' in body:
        raise ClaimViolation('body is not a single paragraph for %s' % label)
    if not body.startswith('Hi '):
        raise ClaimViolation('greeting wrong for %s' % label)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def month_day(applied_date: str) -> str:
    d = parse_date(applied_date)
    if d is None:
        return 'recently'
    return '%s %d' % (MONTHS[d.month - 1], d.day)


def domain_phrase_for(applied_role: str, applied_company: str) -> str:
    blob = ' '.join([applied_role or '', applied_company or ''])
    for phrase, rx in DOMAIN_KEYWORDS:
        if rx.search(blob):
            return phrase
    return DOMAIN_PHRASE_DEFAULT


def proof_points_for(domain_phrase: str, is_ai_native: bool) -> List[str]:
    if is_ai_native:
        return list(PROOF_AI)
    if domain_phrase == DOMAIN_PHRASE_MARKETING:
        return list(PROOF_MARKETING)
    if domain_phrase == DOMAIN_PHRASE_GTM:
        return list(PROOF_GTM)
    return list(PROOF_FINTECH)


def ask_clause_for(applied_role: str, applied_company: str,
                    contact_title: str, contact_company: str) -> str:
    blob = ' '.join([applied_role or '', applied_company or '',
                     contact_title or ''])
    if contact_company:
        blob = blob.replace(contact_company, ' ')
    for _key, rx, template in ASK_CLAUSE_RULES:
        if rx.search(blob):
            return template.format(company=applied_company)
    return ASK_CLAUSE_DEFAULT.format(company=applied_company)


def is_ai_native(applied_role: str, applied_company: str) -> bool:
    blob = ' '.join([applied_role or '', applied_company or ''])
    return bool(re.search(r'\b(ai|artificial intelligence|llm|genai|agentic|'
                          r'machine learning)\b', blob, re.I))


def build_message(message_type: str, name: str, applied_role: str,
                  applied_company: str, applied_date: str,
                  contact_title: str = '', contact_company: str = '',
                  profile: Optional[Dict] = None,
                  max_body_chars: int = 600) -> str:
    """Build one house-format message.

    `profile` is the canonical profile dict; when given, the generated message
    is claim-checked before it is returned.
    """
    fn = first_name(name) or 'there'
    role = applied_role or 'role'
    dtxt = month_day(applied_date)
    domain_phrase = domain_phrase_for(applied_role, applied_company)
    proofs = proof_points_for(domain_phrase,
                              is_ai_native(applied_role, applied_company))
    proof_block = ', '.join(proofs)
    if is_ai_native(applied_role, applied_company):
        proof_block += AI_OPEN_SOURCE_SENTENCE

    if message_type == 'A':
        body = (f'Hi {fn} — I applied for the {role} role at {applied_company} '
                f'({dtxt}) and couldn\'t find an update on my application. '
                f'11 years in {domain_phrase} — {proof_block}. Resume attached. '
                f'{TYPE_A_ASK}')
    else:
        clause = ask_clause_for(applied_role, applied_company, contact_title,
                                contact_company)
        body = (f'Hi {fn} — I applied for the {role} role at {applied_company} '
                f'({dtxt}). 11 years in {domain_phrase} — {proof_block}. '
                f'Resume attached — Would love to learn more about {clause}.')

    message = body + '\n\n' + SIGNATURE
    assert_house_format(message, name)
    if profile:
        assert_claims(message, profile, max_body_chars)
    else:
        if len(body) > max_body_chars:
            raise ClaimViolation('message body %d chars > %d'
                                 % (len(body), max_body_chars))
    return message


# --------------------------------------------------------------------------
# Resume routing
# --------------------------------------------------------------------------
RESUME_AI = 'Subhajit_Das_AI_GTM_Growth_Systems.pdf'
RESUME_BUSINESS = 'Subhajit_Das_Growth_Digital_Business.pdf'
RESUME_MARKETING = 'Subhajit_Das_Growth_Marketing_MarTech.pdf'


def resume_for(applied_role: str, company: str, tier: str = '') -> str:
    """Resume variant routing (spec order):

      AI / GTM / founder / CoS / revops        -> AI_GTM
      lending / credit / bank / fintech / NBFC / business -> Digital_Business
      marketing / brand / demand / performance / content  -> MarTech
    """
    blob = ' '.join([applied_role or '', company or ''])
    if re.search(r'\b(ai|artificial intelligence|llm|genai|gtm|go[- ]to[- ]market|'
                 r'founder|co[- ]?founder|chief of staff|\bcos\b|revops|'
                 r'revenue operations)\b', blob, re.I):
        return RESUME_AI
    if tier in ('P0', 'P1', 'P2'):
        return RESUME_BUSINESS
    if re.search(r'\b(lending|loan|credit|bank|financ|nbfc|fintech|business)\b',
                 blob, re.I):
        return RESUME_BUSINESS
    if re.search(r'\b(marketing|brand|demand|performance|content)\b', blob, re.I):
        return RESUME_MARKETING
    return RESUME_BUSINESS


# --------------------------------------------------------------------------
# Type selection
# --------------------------------------------------------------------------
def message_type_for(contact_title: str) -> str:
    """TYPE A = recruiter / TA (status follow-up); TYPE B = business leader."""
    from .eligibility import RECRUITER_RE
    return 'A' if RECRUITER_RE.search(contact_title or '') else 'B'


# --------------------------------------------------------------------------
# Email subject lines (from outreach_email_drafting_context.md)
# --------------------------------------------------------------------------
SUBJECT_TYPE_A = 'Application: {role} at {company} — Subhajit Das'
SUBJECT_TYPE_B = 'Growth Leadership — Ex-Groww/Axis/ICICI | {company}'


def subject_for(message_type: str, role: str, company: str) -> str:
    if message_type == 'A':
        return SUBJECT_TYPE_A.format(role=role, company=company)
    return SUBJECT_TYPE_B.format(company=company)
