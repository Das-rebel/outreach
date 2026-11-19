"""JOBSPY node — company source only (R54).

`runs/jobspy_pool.jsonl` holds job postings discovered via JobSpy.  JobSpy
rows are NOT people: they are postings.  This adapter therefore contributes
COMPANY context only — it never produces a contactable person.

The pool is large (~150 MB), so it is STREAMED line by line and filtered to
the companies we have actually applied to (from the tracker).  When the file
is absent the adapter returns [] with a warning.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

from ..models import Candidate
from ..identity import norm_key, resolve_company


def _cache_path(ctx) -> str:
    return os.path.join(ctx.cfg.state_dir, 'jobspy_companies.json')


def _scan_pool(path: str, limit: int = 200000) -> Dict[str, dict]:
    """Stream the pool and keep one row per company.  Returns
    {resolved_company_key: {company, role}}."""
    found: Dict[str, dict] = {}
    scanned = 0
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            scanned += 1
            if scanned > limit:      # bounded scan
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            company = (row.get('company') or row.get('company_name')
                       or row.get('company_display') or '').strip()
            if not company:
                continue
            key = resolve_company(company)
            if key and key not in found:
                found[key] = {
                    'company': company,
                    'role': (row.get('title') or row.get('role') or '').strip(),
                }
    return found


def fetch(ctx) -> List[Candidate]:
    path = ctx.cfg.jobspy_pool
    if not os.path.exists(path):
        ctx.warn('jobspy', 'pool missing: %s' % path)
        return []

    applied = {resolve_company(c.applied_company or c.company or '')
               for c in ctx.applications}
    if not applied:
        ctx.warn('jobspy', 'no applied companies to filter against — skipped')
        return []

    # The pool is large (~150 MB), so the company index is cached next to the
    # engine state and reused until the pool changes.
    cache = _cache_path(ctx)
    found: Dict[str, dict] = None
    try:
        if os.path.exists(cache) and \
                os.path.getmtime(cache) >= os.path.getmtime(path):
            with open(cache, encoding='utf-8') as fh:
                found = json.load(fh)
    except (OSError, json.JSONDecodeError):
        found = None

    if found is None:
        try:
            found = _scan_pool(path)
        except OSError as exc:
            ctx.warn('jobspy', 'unreadable pool: %s' % exc)
            return []
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, 'w', encoding='utf-8') as fh:
                json.dump(found, fh, ensure_ascii=False)
        except OSError:
            pass

    out: List[Candidate] = []
    for key in sorted(applied):
        row = found.get(key)
        if not row:
            continue
        cand = Candidate(
            name='',
            company=row['company'],
            applied_company=row['company'],
            applied_role=row.get('role') or '',
            kind='company_source',
            sources=['jobspy'],
            evidence=['jobspy posting %s' % (row.get('role') or row['company'])],
        )
        out.append(cand)

    ctx.warn('jobspy', '%s -> %d companies indexed, %d applied companies seen'
             % (os.path.basename(path), len(found), len(out)))
    return out
