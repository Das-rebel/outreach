"""TRACKER node — applied applications, deduped.

Reads `applied_companies_tracker.json` (`applications[]`) and produces one
Candidate per application.  Dedupe key: company+jid, else normalised
company+role.  These candidates carry no person — they are the APPLICATION
half of the model (`kind='application'`) and are joined to people by company
in `identity.resolve_company`.
"""
from __future__ import annotations

import json
import os
from typing import List

from ..models import Candidate
from ..identity import norm_key, norm_text, resolve_company


def _role_of(row: dict) -> str:
    for k in ('role', 'title', 'position', 'designation'):
        v = row.get(k)
        if v:
            return str(v)
    return ''


def _date_of(row: dict) -> str:
    for k in ('date', 'applied_at', 'applied_date', 'timestamp', 'ts'):
        v = row.get(k)
        if v:
            return str(v)
    return ''


def load_rows(cfg) -> list:
    path = cfg.tracker
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return list(data.get('applications') or [])
    return list(data or [])


def dedupe_key(row: dict) -> str:
    company = (row.get('company') or row.get('company_display') or '')
    jid = (row.get('jid') or row.get('job_id') or '').strip()
    if jid:
        return 'cj:' + norm_key(company) + '|' + jid
    return 'cr:' + resolve_company(company) + '|' + norm_key(_role_of(row))


def fetch(ctx) -> List[Candidate]:
    path = ctx.cfg.tracker
    if not os.path.exists(path):
        ctx.warn('tracker', 'tracker file missing: %s' % path)
        return []
    rows = load_rows(ctx.cfg)
    if not rows:
        ctx.warn('tracker', 'tracker file empty or unreadable: %s' % path)
        return []

    seen = set()
    out: List[Candidate] = []
    for row in rows:
        company = (row.get('company') or row.get('company_display') or '').strip()
        if not company or company.startswith('confidential-'):
            continue
        key = dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        role = _role_of(row)
        cand = Candidate(
            name='',
            contact_title='',
            company=company,
            applied_company=company,
            applied_role=role,
            applied_date=_date_of(row),
            applied_jid=str(row.get('jid') or row.get('job_id') or ''),
            applied_status=str(row.get('status') or ''),
            kind='application',
            sources=['tracker'],
            evidence=['tracker application %s' % (row.get('jid') or role or company)],
        )
        out.append(cand)

    ctx.applications = out
    ctx.warn('tracker', 'loaded %d applications (%d unique) from %s'
             % (len(rows), len(out), os.path.basename(path)))
    return out
