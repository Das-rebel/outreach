"""LINKEDIN CDP node — company people pages / people search / enrichment.

Read-only.  The known-working harvest logic already exists in
`runs/outreach/harvest_fresh.py` (which wraps `harvest_people_v5.py`); this
adapter reuses it rather than re-implementing the scraper.

Two modes:
  * OFFLINE (default) — read the already-harvested JSONL pools
    (`runs/outreach/people_*.jsonl`).  Fast, no browser, fully offline.
  * LIVE (OE_LINKEDIN_LIVE=1) — invoke `runs/outreach/harvest_fresh.py` over
    CDP (port 9335) for the recently-applied companies.  Still read-only:
    it never logs in, never sends, never touches cookies.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
from typing import List

from ..models import Candidate

DEFAULT_POOL_GLOBS = (
    'runs/outreach/people_v6.jsonl',
    'runs/outreach/people_v6_fresh.jsonl',
    'runs/outreach/people_fresh_1112.jsonl',
    'runs/outreach/people_fresh_1112.json',
)

HARVEST_SCRIPT = 'runs/outreach/harvest_fresh.py'


def _pool_files(cfg) -> List[str]:
    if cfg.linkedin_people_files:
        return list(cfg.linkedin_people_files)
    out: List[str] = []
    for pattern in DEFAULT_POOL_GLOBS:
        p = os.path.join(cfg.repo_root, pattern)
        if os.path.exists(p):
            out.append(p)
    return out


def _clean_name(name: str, url: str) -> str:
    """The upstream harvester sometimes captured "Nikhil works here" as the
    profile name (LinkedIn renders "Nikhil\nworks here").  When that happens
    the real name is recoverable from the profile slug."""
    name = (name or '').strip()
    if not name:
        return ''
    if name.lower().endswith('works here'):
        slug = (url or '').rstrip('/').split('/')[-1].split('?')[0]
        slug = re.sub(r'-(?:[0-9a-f]{8,})$', '', slug)      # drop the hash
        parts = [p for p in slug.split('-') if p]
        if parts:
            return ' '.join(p.capitalize() for p in parts[:2])
    return name


def _row_to_candidate(row: dict, source: str) -> Candidate:
    url = (row.get('url') or row.get('linkedin') or '').strip()
    name = _clean_name(row.get('name') or '', url)
    headline = (row.get('headline') or row.get('role_text') or '').strip()
    company = (row.get('company') or row.get('company_applied') or '').strip()
    applied_company = (row.get('company_applied') or row.get('applied_company')
                       or '').strip()
    applied_role = (row.get('applied_role') or '').strip()
    applied_date = (row.get('applied_date') or '').strip()
    degree = (row.get('degree') or '').strip()

    cand = Candidate(
        name=name,
        contact_title=headline,
        company=company,
        applied_company=applied_company,
        applied_role=applied_role,
        applied_date=applied_date,
        applied_jid=str(row.get('jid') or ''),
        linkedin=url,
        email=(row.get('email') or '').strip(),
        degree=degree,
        kind='person',
        sources=[source],
    )
    ev = []
    if row.get('slug'):
        ev.append('linkedin company slug %s' % row['slug'])
    if row.get('company_header'):
        ev.append('company header %s' % row['company_header'])
    if row.get('ctx'):
        ev.append('profile context: %s' % str(row['ctx'])[:120])
    cand.evidence.extend(ev)
    return cand


def _live_harvest(ctx) -> None:
    """Invoke the known-working read-only harvester over CDP."""
    script = os.path.join(ctx.cfg.repo_root, HARVEST_SCRIPT)
    if not os.path.exists(script):
        ctx.warn('linkedin', 'harvest script missing: %s' % HARVEST_SCRIPT)
        return
    companies = sorted({c.applied_company for c in ctx.applications
                        if c.applied_company})[:12]
    if not companies:
        ctx.warn('linkedin', 'no applied companies to harvest for')
        return
    list_path = os.path.join(ctx.cfg.state_dir, '_linkedin_companies.json')
    os.makedirs(ctx.cfg.state_dir, exist_ok=True)
    with open(list_path, 'w', encoding='utf-8') as fh:
        json.dump(companies, fh)
    cmd = ['python3', script, '--company-list', list_path,
           '--out', os.path.join(ctx.cfg.state_dir, 'people_live.jsonl'),
           '--max-companies', str(len(companies))]
    env = dict(os.environ)
    env['LI_CDP_URL'] = ctx.cfg.li_cdp_url
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=600, env=env, cwd=ctx.cfg.repo_root)
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.warn('linkedin', 'live harvest failed: %s' % exc)
        return
    ctx.warn('linkedin', 'live harvest rc=%s %s'
             % (proc.returncode, (proc.stdout or '').strip()[-200:]))


def fetch(ctx) -> List[Candidate]:
    out: List[Candidate] = []

    live = os.environ.get('OE_LINKEDIN_LIVE', '').strip().lower() in \
        ('1', 'true', 'yes', 'on')
    if live:
        _live_harvest(ctx)
        live_pool = os.path.join(ctx.cfg.state_dir, 'people_live.jsonl')
        if os.path.exists(live_pool):
            _pool_files(ctx.cfg).append(live_pool)

    files = _pool_files(ctx.cfg)
    if not files:
        ctx.warn('linkedin', 'no harvested people pools found')
        return out

    for path in files:
        rows = []
        try:
            if path.endswith('.jsonl'):
                with open(path, encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            rows.append(json.loads(line))
            else:
                with open(path, encoding='utf-8') as fh:
                    data = json.load(fh)
                rows = data if isinstance(data, list) else (data.get('people') or [])
        except (OSError, json.JSONDecodeError):
            ctx.warn('linkedin', 'unreadable pool %s' % os.path.basename(path))
            continue
        source = 'linkedin:' + os.path.basename(path)
        for row in rows:
            if isinstance(row, dict) and (row.get('name') or '').strip():
                out.append(_row_to_candidate(row, source))
        ctx.warn('linkedin', '%s -> %d rows'
                 % (os.path.basename(path), len(rows)))

    if not live:
        ctx.warn('linkedin', 'live CDP harvest disabled '
                             '(set OE_LINKEDIN_LIVE=1 to enable)')
    return out
