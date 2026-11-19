"""Normalisation, dedupe keys and org/alias resolution.

Two organisations can carry different names in different systems (the tracker
uses "Liquiloans", a contact's LinkedIn headline says "NDX Financial
Services").  Without an alias map the engine treats them as two companies and
either double-counts a company or loses the application link.  The alias table
below is the ONLY place in the engine where an org identity is asserted; it is
deliberately explicit rather than fuzzy so that a wrong merge is reviewable.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Set, Tuple

# Words that carry no identity in a company name.
_COMPANY_STOP = {
    'the', 'and', 'of', 'pvt', 'private', 'ltd', 'limited', 'inc', 'llp',
    'llc', 'corp', 'corporation', 'co', 'company', 'technologies',
    'technology', 'tech', 'labs', 'services', 'solutions', 'india',
    'global', 'group', 'holdings', 'india limited', 'pvt ltd',
}

# Alias groups: every member resolves to the FIRST member (the canonical id).
# Discovered from tracker rows (`alias`, `alias_raw_company`) and from the
# contact/company mismatches seen in the Nov-2026 approval packs.
ALIAS_GROUPS: List[List[str]] = [
    ['liquiloans', 'ndx financial services', 'ndx'],
    ['titan email', 'titan company', 'titan'],
    ['fitspire', 'fitspire health wellness', 'fitspire health'],
    ['lifestyle max', 'lifestyle'],
]


def norm_text(s: str) -> str:
    """Lowercase, collapse everything that is not alphanumeric into a space."""
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def norm_key(s: str) -> str:
    """Alphanumeric-only key (no spaces) — used for equality comparisons."""
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def norm_name(s: str) -> str:
    """Normalised person name: 'First  M.  Last' -> 'first m last'."""
    return norm_text(s)


def norm_company_key(company: str) -> str:
    """Normalised company key: drop filler words, keep the distinctive tokens.

    'Fitspire - Health | Wellness' -> 'fitspire'
    'BharatPe'                     -> 'bharatpe'
    """
    text = norm_text(company)
    if not text:
        return ''
    parts = [p for p in text.split() if p not in _COMPANY_STOP]
    if not parts:
        parts = text.split()
    return ' '.join(parts)


def norm_company(company: str) -> str:
    """Full normalised company string (no filler removal) for word-boundary
    matching against the canonical banned-company list."""
    return norm_text(company)


def norm_email(email: str) -> str:
    return (email or '').strip().lower()


def linkedin_slug(url: str) -> str:
    """'/in/some-slug-123' -> 'some-slug-123' (empty when not a profile URL)."""
    m = re.search(r'/in/([^/?#]+)', url or '')
    return m.group(1).lower().rstrip('/') if m else ''


def norm_url(url: str) -> str:
    u = (url or '').strip().lower().split('?')[0].split('#')[0]
    u = re.sub(r'^https?://', '', u).rstrip('/')
    return u[4:] if u.startswith('www.') else u


def first_name(full_name: str) -> str:
    for part in (full_name or '').split():
        if part:
            return part.strip()
    return ''


def resolve_company(company: str) -> str:
    """Resolve a company name through the alias table.

    Returns the canonical alias id when the company is a known alias member,
    otherwise the normalised company key.
    """
    key = norm_company_key(company)
    if not key:
        return ''
    for group in ALIAS_GROUPS:
        for member in group:
            if norm_company_key(member) == key:
                return norm_company_key(group[0])
    return key


def same_company(a: str, b: str) -> bool:
    """True when two company names resolve to the same employer."""
    if not a or not b:
        return False
    return resolve_company(a) == resolve_company(b)


def dedupe_keys(name: str, company: str, linkedin: str, email: str) -> List[str]:
    """Ordered dedupe keys for one person.

    A LinkedIn slug or a verified email is a hard identity.  Name+company is a
    soft identity (used only when neither is available).
    """
    keys: List[str] = []
    slug = linkedin_slug(linkedin)
    if slug:
        keys.append('li:' + slug)
    mail = norm_email(email)
    if mail:
        keys.append('em:' + mail)
    nm = norm_name(name)
    co = resolve_company(company)
    if nm and co:
        keys.append('nc:' + nm + '|' + co)
    elif nm:
        keys.append('n:' + nm)
    return keys


def candidate_keys(cand) -> List[str]:
    """Dedupe keys for a Candidate-like object."""
    return dedupe_keys(getattr(cand, 'name', ''),
                       getattr(cand, 'company', ''),
                       getattr(cand, 'linkedin', ''),
                       getattr(cand, 'email', ''))


def dedupe_key_set(cands: Iterable) -> dict:
    """Map hard/soft identity keys -> candidate, keeping the richest record.

    'Richest' = has a LinkedIn URL, then an email, then more evidence.
    """
    best: dict = {}

    def richness(c) -> Tuple[int, int, int]:
        return (1 if getattr(c, 'linkedin', '') else 0,
                1 if getattr(c, 'email', '') else 0,
                len(getattr(c, 'evidence', []) or []))

    for c in cands:
        for k in dedupe_keys(getattr(c, 'name', ''), getattr(c, 'company', ''),
                             getattr(c, 'linkedin', ''), getattr(c, 'email', '')):
            cur = best.get(k)
            if cur is None or richness(c) > richness(cur):
                best[k] = c
    return best


def merge_candidates(existing, incoming):
    """Merge `incoming` into `existing` (same person), returning the merged one.

    Union of sources and evidence; the first non-empty contact field wins.
    """
    for attr in ('contact_title', 'company', 'linkedin', 'email', 'phone',
                 'degree', 'applied_company', 'applied_role', 'applied_date',
                 'applied_jid', 'applied_status'):
        if not getattr(existing, attr, '') and getattr(incoming, attr, ''):
            setattr(existing, attr, getattr(incoming, attr))
    for s in getattr(incoming, 'sources', []) or []:
        if s not in existing.sources:
            existing.sources.append(s)
    for e in getattr(incoming, 'evidence', []) or []:
        if e not in existing.evidence:
            existing.evidence.append(e)
    if incoming.needs_identity_resolution and not existing.needs_identity_resolution:
        existing.needs_identity_resolution = True
    return existing
