"""Deterministic rule scoring.

No model, no randomness — the same candidate always scores the same.  The
score is a sum of weighted components; every component is reported so an
operator can see WHY a candidate is at the top (and why one is not).

Components
    seniority         ladder weight of the contact's designation
    function_fit      in-family (growth/marketing/GTM) vs recruiter (TA)
    tier              company tier P0..P7 via xiryn_kit.role_priority.classify
    recency           how recent OUR application at that company was
    warmth            1st-degree network, 2nd-degree, or a recruiter reply
    reachability      LinkedIn URL > verified email
    diversity         cap of 2 contacts per company (applied at selection)
"""
from __future__ import annotations

import importlib.util
import os
import re
from typing import Dict, List, Optional, Tuple

from .eligibility import IN_FAMILY_RE, RECRUITER_RE, parse_date
from .identity import norm_text

# --------------------------------------------------------------------------
# Seniority ladder weights (the user's ladder: Head / Director / VP / AVP /
# Chief / GM — R39/R40 keep Manager and Analyst out of the ladder).
SENIORITY_LADDER: List[Tuple[str, float]] = [
    (r'\b(chief|founder|co[- ]?founder|owner|president|ceo|md)\b', 30.0),
    (r'\b(general manager|gm)\b', 28.0),
    (r'\b(vp|vice president|svp|evp|avp|associate vice president)\b', 26.0),
    (r'\b(head)\b', 24.0),
    (r'\b(director)\b', 22.0),
    (r'\b(partner)\b', 20.0),
    (r'\b(lead|principal)\b', 16.0),
    (r'\b(senior|sr\.?)\b', 12.0),
]

FUNCTION_FIT = {
    'growth_marketing': 18.0,
    'gtm_commercial': 15.0,
    'recruiter_ta': 12.0,
    'other': 5.0,
}

TIER_WEIGHT = {
    'P0': 22.0,   # fintech
    'P1': 20.0,   # banks
    'P2': 19.0,   # NBFC
    'P3': 16.0,   # internal fintech
    'P4': 14.0,   # D2C growth & strategy
    'P5': 12.0,   # D2C growth
    'P6': 10.0,   # D2C marketing
    'P7': 6.0,    # everything else — ordering priority, NOT exclusion (R50)
}

RECENCY_WEIGHT = [
    (0, 20.0), (3, 16.0), (7, 12.0), (11, 8.0), (15, 4.0),
]

WARMTH_WEIGHT = {
    'gmail_reply': 25.0,
    'first_degree': 20.0,
    'second_degree': 12.0,
    'third_degree': 6.0,
    'none': 0.0,
}

REACH_LINKEDIN = 8.0
REACH_EMAIL = 6.0
REACH_BOTH = 10.0
REACH_NONE = 0.0


def _classify_module():
    """Load xiryn_kit/role_priority.py without importing the package
    (xiryn_kit has no __init__.py)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'xiryn_kit', 'role_priority.py')
    if not os.path.exists(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location('_oe_role_priority', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


_ROLE_PRIORITY = None
_ROLE_PRIORITY_TRIED = False


def classify_tier(company: str, title: str) -> Tuple[str, str]:
    """Return (tier_label, basis). Falls back to P7 when the classifier is
    unavailable (it must never crash the pipeline)."""
    global _ROLE_PRIORITY, _ROLE_PRIORITY_TRIED
    if not _ROLE_PRIORITY_TRIED:
        _ROLE_PRIORITY = _classify_module()
        _ROLE_PRIORITY_TRIED = True
    if _ROLE_PRIORITY is None:
        return 'P7', 'classifier-unavailable'
    try:
        priority, label, basis = _ROLE_PRIORITY.classify(company, title)
    except Exception:
        return 'P7', 'classifier-error'
    return 'P%d' % priority, basis


def seniority_component(title: str) -> Tuple[float, str]:
    for pattern, weight in SENIORITY_LADDER:
        if re.search(pattern, title or '', re.I):
            return weight, pattern
    return 0.0, 'no-ladder-match'


def function_component(title: str) -> Tuple[float, str]:
    if RECRUITER_RE.search(title or ''):
        return FUNCTION_FIT['recruiter_ta'], 'recruiter'
    if IN_FAMILY_RE.search(title or ''):
        return FUNCTION_FIT['growth_marketing'], 'in-family'
    return FUNCTION_FIT['other'], 'off-family'


def recency_component(applied_date: str, today) -> Tuple[float, int]:
    d = parse_date(applied_date)
    if d is None:
        return 0.0, -1
    age = (today - d).days
    weight = 0.0
    for limit, w in RECENCY_WEIGHT:
        if age <= limit:
            weight = w
    return weight, age


def warmth_component(cand) -> Tuple[float, str]:
    sources = set(cand.sources or [])
    if 'gmail' in sources:
        return WARMTH_WEIGHT['gmail_reply'], 'gmail_reply'
    degree = (cand.degree or '').strip().lower()
    if degree in ('1st', '1', 'first', 'first-degree'):
        return WARMTH_WEIGHT['first_degree'], 'first_degree'
    if degree in ('2nd', '2', 'second', 'second-degree'):
        return WARMTH_WEIGHT['second_degree'], 'second_degree'
    if degree in ('3rd', '3', 'third', 'third-degree'):
        return WARMTH_WEIGHT['third_degree'], 'third_degree'
    if 'happenstance_match' in sources or 'happenstance_priority' in sources:
        # A network contact with no recorded degree is treated as warm-but-not
        # confirmed: give it the 2nd-degree weight rather than nothing.
        return WARMTH_WEIGHT['second_degree'], 'network_ungraded'
    return WARMTH_WEIGHT['none'], 'no_warmth'


def reachability_component(cand) -> Tuple[float, str]:
    has_li = bool((cand.linkedin or '').strip())
    has_mail = bool((cand.email or '').strip())
    if has_li and has_mail:
        return REACH_BOTH, 'linkedin+email'
    if has_li:
        return REACH_LINKEDIN, 'linkedin'
    if has_mail:
        return REACH_EMAIL, 'email'
    return REACH_NONE, 'none'


def score_candidate(cand, ctx) -> Dict[str, object]:
    """Score one candidate.  Returns a plain dict (JSON-serialisable)."""
    title = cand.contact_title or ''
    components: Dict[str, float] = {}
    notes: List[str] = []

    value, basis = seniority_component(title)
    components['seniority'] = value
    notes.append('seniority:%s' % basis)

    value, basis = function_component(title)
    components['function_fit'] = value
    notes.append('function:%s' % basis)

    tier, tier_basis = classify_tier(cand.applied_company or cand.company,
                                      cand.applied_role or title)
    components['tier'] = TIER_WEIGHT.get(tier, 0.0)
    notes.append('tier:%s(%s)' % (tier, tier_basis))

    value, age = recency_component(cand.applied_date, ctx.today)
    components['recency'] = value
    notes.append('recency:%sd' % age)

    value, basis = warmth_component(cand)
    components['warmth'] = value
    notes.append('warmth:%s' % basis)

    value, basis = reachability_component(cand)
    components['reachability'] = value
    notes.append('reach:%s' % basis)

    total = round(sum(components.values()), 2)
    return {
        'total': total,
        'components': components,
        'tier': tier,
        'tier_basis': tier_basis,
        'notes': notes,
        'applied_age_days': age,
    }


def apply_diversity_cap(ranked: List, max_per_company: int) -> Tuple[List, List]:
    """Cap the number of contacts per company.  Returns (kept, dropped)."""
    kept: List = []
    dropped: List = []
    counts: Dict[str, int] = {}
    for cand in ranked:
        company = (cand.applied_company or cand.company or '').lower()
        if counts.get(company, 0) >= max_per_company:
            dropped.append(cand)
            continue
        counts[company] = counts.get(company, 0) + 1
        kept.append(cand)
    return kept, dropped
