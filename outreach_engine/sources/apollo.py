"""APOLLO / MONID node — free people search (balance $3.19).

Apollo's free tier returns an OBFUSCATED last name ("Sa***a") and no email
address.  Such a record is NOT a contactable person: there is no way to write
"Hi Sanjay — ..." without guessing.  Every Apollo row is therefore emitted with
`needs_identity_resolution=True` and is hard-blocked by the
`apollo_obfuscated_unresolved` eligibility gate until a real name + URL is
resolved by another node (LinkedIn harvest).

Offline by default: the adapter reads the cached `runs/outreach/apollo_*.json`
harvests.  A live search is only performed when explicitly enabled with
`OE_APOLLO_LIVE=1`, and only while the daily outreach budget (R53:
$0.30/day for the OUTREACH bucket) allows it.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
from datetime import date
from typing import List

from ..models import Candidate

DEFAULT_CACHE_GLOBS = (
    'runs/outreach/apollo_*.json',
    'runs/outreach/OUTREACH_TABLE_v3.jsonl',
)

# Apollo people-search title filter (same vocabulary the earlier
# `runs/outreach/apollo_verify.py` used).
TITLES = ['head', 'director', 'vp', 'chief', 'cmo', 'founder', 'president',
          'general manager', 'gm', 'group head']


def _cache_files(cfg) -> List[str]:
    if cfg.apollo_cache_files:
        return list(cfg.apollo_cache_files)
    out: List[str] = []
    for pattern in DEFAULT_CACHE_GLOBS:
        out.extend(sorted(glob.glob(os.path.join(cfg.repo_root, pattern))))
    return out


def _people_from(obj):
    if isinstance(obj, dict):
        for key in ('people', 'results', 'entries', 'contacts'):
            if isinstance(obj.get(key), list):
                return obj[key]
        return []
    return []


def _row_to_candidate(row: dict, source: str) -> Candidate:
    first = (row.get('first_name') or '').strip()
    obf = (row.get('last_name_obfuscated') or row.get('last_name') or '').strip()
    org = ((row.get('organization') or {}).get('name')
           or row.get('org') or row.get('company') or '').strip()
    title = (row.get('title') or '').strip()
    email = (row.get('email') or '').strip()
    linkedin = (row.get('linkedin_url') or row.get('linkedin') or '').strip()

    obfuscated = bool(obf) and '*' in obf
    name = (first + ' ' + obf).strip() if first else obf
    if not obfuscated and first and obf:
        name = (first + ' ' + obf).strip()

    cand = Candidate(
        name=name,
        contact_title=title,
        company=org,
        linkedin=linkedin,
        email=email,
        kind='person',
        sources=[source],
        evidence=['apollo id %s' % row.get('id')] if row.get('id') else [],
    )
    if obfuscated:
        cand.needs_identity_resolution = True
        cand.evidence.append('apollo obfuscated last name %r' % obf)
    if not email:
        cand.evidence.append('apollo free tier: no email')
    return cand


def _spend_today(cfg) -> float:
    path = os.path.join(cfg.state_dir, 'monid_spend.json')
    if not os.path.exists(path):
        return 0.0
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return 0.0
    today = str(date.today())
    return float((data.get('days') or {}).get(today, 0.0))


def _record_spend(cfg, amount: float, note: str) -> None:
    os.makedirs(cfg.state_dir, exist_ok=True)
    path = os.path.join(cfg.state_dir, 'monid_spend.json')
    data = {'days': {}}
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            data = {'days': {}}
    days = data.setdefault('days', {})
    today = str(date.today())
    days[today] = round(float(days.get(today, 0.0)) + amount, 6)
    data.setdefault('log', []).append({'date': today, 'usd': amount, 'note': note})
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)


def _live_search(cfg, company: str) -> List[dict]:
    """One Apollo free people search via the monid CLI. Returns [] on any error."""
    domain = ''.join(ch for ch in (company or '').lower() if ch.isalnum())
    if not domain:
        return []
    payload = {
        'person_titles': TITLES,
        'person_seniorities': ['head', 'director', 'vp', 'c_suite',
                               'general_manager', 'partner'],
        'person_locations': ['India'],
        'q_organization_domains_list': [domain + '.com', domain + '.in',
                                        domain + '.co.in'],
        'per_page': 8,
    }
    try:
        proc = subprocess.run(
            ['monid', 'run', '-p', 'apollo', '-e', '/mixed_people/api_search',
             '-i', json.dumps(payload), '-w', '-j'],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return []
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    if data.get('status') != 'COMPLETED':
        return []
    return (data.get('output') or {}).get('people') or []


def fetch(ctx) -> List[Candidate]:
    out: List[Candidate] = []

    for path in _cache_files(ctx.cfg):
        if not os.path.exists(path):
            continue
        try:
            if path.endswith('.jsonl'):
                rows = []
                with open(path, encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            rows.append(json.loads(line))
            else:
                with open(path, encoding='utf-8') as fh:
                    rows = _people_from(json.load(fh))
        except (OSError, json.JSONDecodeError):
            ctx.warn('apollo', 'unreadable cache %s' % os.path.basename(path))
            continue
        source = 'apollo_cache:' + os.path.basename(path)
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(_row_to_candidate(row, source))
        ctx.warn('apollo', '%s -> %d rows' % (os.path.basename(path), len(rows)))

    live = os.environ.get('OE_APOLLO_LIVE', '').strip().lower() in \
        ('1', 'true', 'yes', 'on')
    if live:
        spent = _spend_today(ctx.cfg)
        budget = ctx.cfg.monid_outreach_budget_usd
        if spent >= budget:
            ctx.warn('apollo', 'daily outreach budget exhausted '
                                '($%.2f >= $%.2f) — skipping live search'
                     % (spent, budget))
        else:
            companies = sorted({c.applied_company for c in ctx.applications
                                if c.applied_company})[:10]
            for company in companies:
                rows = _live_search(ctx.cfg, company)
                for row in rows:
                    out.append(_row_to_candidate(row, 'apollo_live'))
                _record_spend(ctx.cfg, 0.0, 'apollo free search %s' % company)
                ctx.warn('apollo', 'live search %s -> %d rows'
                         % (company, len(rows)))
    else:
        ctx.warn('apollo', 'live search disabled (set OE_APOLLO_LIVE=1 to '
                            'enable; free tier still obfuscates last names)')

    return out
