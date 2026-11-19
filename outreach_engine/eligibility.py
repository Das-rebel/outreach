"""Hard eligibility gates.

Every gate returns a stable reason code.  A candidate is eligible only when
NO gate fires.  The codes are part of the engine's contract (R56) — they are
printed in the `eligible` summary and recorded in the state files.

    window_expired            application older than the DM window (15d)
    banned_company            canonical companies_banned (word-boundary)
    do_not_approach           canonical do_not_approach
    r39_manager               title contains "manager"
    r40_analyst               title contains "analyst"
    already_contacted         present in a contact log or a prior approval pack
    apollo_obfuscated_unresolved  Apollo gave an obfuscated name, no identity
    no_url_no_email           no LinkedIn URL and no email
    not_senior                no leadership keyword in the designation
    off_function              designation is neither in-family nor TA/recruiter
    ta_or_business_dual       designation matches BOTH the recruiter set and
                              the business set — the message type is ambiguous
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .identity import norm_key, norm_text, norm_url, norm_email, linkedin_slug

REASON_CODES: Tuple[str, ...] = (
    'window_expired',
    'banned_company',
    'do_not_approach',
    'r39_manager',
    'r40_analyst',
    'already_contacted',
    'apollo_obfuscated_unresolved',
    'no_url_no_email',
    'not_senior',
    'off_function',
    'ta_or_business_dual',
)

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

# R39 — the user's ladder is Head / Director / VP / AVP / Chief / GM.
_MANAGER_RE = re.compile(r'\bmanager\b', re.I)
# R40 — "ai analyst is wrong role".
_ANALYST_RE = re.compile(r'\banalyst\b', re.I)

# Recruiter / TA / people function (TYPE A in the house message format).
RECRUITER_RE = re.compile(
    r'\b(recruit\w*|talent\s?acquisition|talent\s?partner|talent\s?specialist|'
    r'sourc\w*|headhunter|staffing|hrbp|human\s?resources?|hr\s?manager|'
    r'people\s?(?:ops|partner|officer)|hiring\s?manager)\b', re.I)

# In-family business function (TYPE B) — growth / marketing / brand / GTM /
# revenue / commercial / partnerships.  This is the "off_function" allowlist.
IN_FAMILY_RE = re.compile(
    r'\b(growth|marketing|brand\w*|demand\s?gen\w*|go[- ]?to[- ]?market|gtm|'
    r'revenue\s?operations|revops|business\s?development|bd\b|partnership\w*|'
    r'merchant|channel|acquisition|commercial\w*|marketplace|ecommerce|'
    r'e[- ]?commerce|digital|lifecycle|retention|engagement|crm|'
    r'content|communications?\b|product\s?marketing|category\s?marketing|'
    r'performance|customer\s?growth|leadership|operations)\b', re.I)

# Title used to detect "this person is a TA contact" for message typing.
TA_TITLE_RE = RECRUITER_RE

# Seniority of the ROLE WE APPLIED FOR (email gate E4).
SENIOR_RE = re.compile(
    r'\b(head|chief|c[toimfp]|vp|svp|evp|avp|president|founder|'
    r'co[- ]?founder|director|general\s+manager|gm|lead|principal|'
    r'partner|senior|sr\.?)\b', re.I)

# Strong in-family signals only — used for the dual-role gate, where a weak
# token like "digital" in "Talent Acquisition Specialist - Digital" must not
# make a recruiter look like a business leader.
STRONG_IN_FAMILY_RE = re.compile(
    r'\b(growth|marketing|brand\w*|demand\s?gen\w*|go[- ]?to[- ]?market|gtm|'
    r'revenue\s?operations|revops|business\s?development|partnership\w*|'
    r'merchant|commercial\w*|marketplace|ecommerce|e[- ]?commerce|'
    r'product\s?marketing|category\s?marketing|performance\s?marketing|'
    r'customer\s?growth|lifecycle|retention)\b', re.I)


def leadership_keywords(profile: Dict) -> List[str]:
    return list((profile.get('seniority') or {}).get('leadership_keywords') or [])


def banned_company_hit(company: str, banned_terms: Sequence[str]) -> Optional[str]:
    """Return the banned entry that matches `company`, or None.

    Matching rules (word-boundary only — a short banned entry must never match
    inside a longer word):
      1. exact equality on the alphanumeric-only key
      2. whole-token / word-boundary match on the normalised company string
      3. plain substring ONLY for meaningful multi-char entries (>= 5 chars)

    So "nit" never matches "UnitedHealth Group", but "paytm" matches
    "Paytm Payments".
    """
    cn = norm_text(company)
    ck = norm_key(company)
    if not cn:
        return None
    for term in banned_terms or []:
        tn = norm_text(term)
        if not tn:
            continue
        tk = norm_key(term)
        if ck and ck == tk:
            return term
        if re.search(r'(?<![a-z0-9])' + re.escape(tn) + r'(?![a-z0-9])', cn):
            return term
        if len(tk) >= 5 and tk in ck:
            return term
    return None


def parse_date(value) -> Optional[date]:
    """Parse the date shapes the tracker uses (ISO date, ISO datetime, epoch)."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d',
                '%Y/%m/%d', '%d-%m-%Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(s[:len(s)] if fmt == '%Y-%m-%dT%H:%M:%S%z'
                                     else s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------

def _gate_window(cand, ctx) -> Optional[str]:
    applied = parse_date(getattr(cand, 'applied_date', ''))
    if applied is None:
        return 'window_expired'
    days = (ctx.today - applied).days
    if days > ctx.cfg.dm_eligibility_days or days < 0:
        return 'window_expired'
    return None


def _gate_banned_company(cand, ctx) -> Optional[str]:
    for company in (getattr(cand, 'company', ''),
                    getattr(cand, 'applied_company', '')):
        hit = banned_company_hit(company, ctx.banned_companies)
        if hit:
            return 'banned_company'
    return None


def _gate_do_not_approach(cand, ctx) -> Optional[str]:
    nm = norm_key(getattr(cand, 'name', ''))
    if nm and nm in ctx.do_not_approach:
        return 'do_not_approach'
    return None


def _gate_r39(cand, ctx) -> Optional[str]:
    title = getattr(cand, 'contact_title', '') or ''
    if _MANAGER_RE.search(title):
        return 'r39_manager'
    return None


def _gate_r40(cand, ctx) -> Optional[str]:
    title = getattr(cand, 'contact_title', '') or ''
    if _ANALYST_RE.search(title):
        return 'r40_analyst'
    return None


def _gate_already_contacted(cand, ctx) -> Optional[str]:
    slug = linkedin_slug(getattr(cand, 'linkedin', ''))
    if slug and slug in ctx.contacted_slugs:
        return 'already_contacted'
    mail = norm_email(getattr(cand, 'email', ''))
    if mail and mail in ctx.contacted_emails:
        return 'already_contacted'
    key = (norm_text(getattr(cand, 'name', '')).replace(' ', ''),
           norm_text(getattr(cand, 'company', '')).replace(' ', ''))
    if key != ('', '') and key in ctx.contacted_name_company:
        return 'already_contacted'
    return None


def _gate_apollo_obfuscated(cand, ctx) -> Optional[str]:
    if getattr(cand, 'needs_identity_resolution', False):
        return 'apollo_obfuscated_unresolved'
    return None


def _gate_no_url_no_email(cand, ctx) -> Optional[str]:
    if not (getattr(cand, 'linkedin', '') or '').strip() and \
       not (getattr(cand, 'email', '') or '').strip():
        return 'no_url_no_email'
    return None


def _gate_not_senior(cand, ctx) -> Optional[str]:
    """The seniority ladder (Head / Director / VP / AVP / Chief / GM) applies
    to BUSINESS leaders.  Recruiters are gated by function instead (TYPE A),
    so a "Talent Acquisition Specialist" is not dropped for lacking "Head"."""
    title = getattr(cand, 'contact_title', '') or ''
    if not title.strip():
        return 'not_senior'
    if RECRUITER_RE.search(title):
        return None
    low = title.lower()
    for kw in ctx.leadership_keywords:
        if kw.lower() in low:
            return None
    return 'not_senior'


def _gate_off_function(cand, ctx) -> Optional[str]:
    title = getattr(cand, 'contact_title', '') or ''
    if not title.strip():
        return 'off_function'
    if RECRUITER_RE.search(title):
        return None
    if IN_FAMILY_RE.search(title):
        return None
    return 'off_function'


def _gate_dual(cand, ctx) -> Optional[str]:
    """A designation that is BOTH recruiter-shaped and business-shaped.

    We cannot pick TYPE A (status follow-up) or TYPE B (market insight)
    without guessing, and guessing produces the wrong message.  Drop it.
    """
    title = getattr(cand, 'contact_title', '') or ''
    if RECRUITER_RE.search(title) and STRONG_IN_FAMILY_RE.search(title):
        return 'ta_or_business_dual'
    return None


GATES = (
    _gate_window,
    _gate_banned_company,
    _gate_do_not_approach,
    _gate_r39,
    _gate_r40,
    _gate_already_contacted,
    _gate_apollo_obfuscated,
    _gate_no_url_no_email,
    _gate_not_senior,
    _gate_off_function,
    _gate_dual,
)


def check(cand, ctx) -> List[str]:
    """Return every reason code that fires for `cand` (empty == eligible)."""
    reasons: List[str] = []
    for gate in GATES:
        reason = gate(cand, ctx)
        if reason:
            reasons.append(reason)
    return reasons


def first_reason(cand, ctx) -> Optional[str]:
    """The single most actionable reason (gates run in REASON_CODES order)."""
    reasons = check(cand, ctx)
    return reasons[0] if reasons else None
