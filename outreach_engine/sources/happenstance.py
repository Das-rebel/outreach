"""HAPPENSTANCE node — warm 1st/2nd-degree contacts.

Reads three files from `~/happenstance-agent-find`:

  priority_connections.json    1128 rows (name, role, url, company, position,
                               connected_on, source)
  connections_data.json          62 rows (same shape)
  network_applied_matches.json   73 rows — contacts already matched to an
                               applied company (name, title, url, company,
                               applied_as, w=weight)

Warm contacts carry the highest conversion signal, so they are kept as first
class candidates even when the company also appears from another node.
"""
from __future__ import annotations

import json
import os
from typing import List

from ..models import Candidate
from ..identity import norm_key, resolve_company

PRIORITY_FILE = 'priority_connections.json'
CONNECTIONS_FILE = 'connections_data.json'
MATCHES_FILE = 'network_applied_matches.json'


def _read_json(path: str):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _rows(data):
    if data is None:
        return []
    if isinstance(data, dict):
        return list(data.get('connections') or data.get('matches') or [])
    return list(data)


def _degree(row: dict) -> str:
    """Degree from whatever the file carries; '' when unknown."""
    for key in ('degree', 'connection_degree', 'closeness'):
        v = row.get(key)
        if v:
            return str(v).strip()
    return ''


def fetch(ctx) -> List[Candidate]:
    base = ctx.cfg.happenstance_dir
    out: List[Candidate] = []
    if not base or not os.path.isdir(base):
        ctx.warn('happenstance', 'happenstance dir missing: %s' % base)
        return []

    seen = set()

    def add(row: dict, source: str, extra_evidence: str = '') -> None:
        name = (row.get('name') or '').strip()
        if not name:
            return
        url = (row.get('url') or row.get('linkedin') or '').strip()
        key = norm_key(name) + '|' + (url or resolve_company(
            row.get('company') or ''))
        if key in seen:
            return
        seen.add(key)
        company = (row.get('company') or '').strip()
        title = (row.get('position') or row.get('title') or '').strip()
        if not title:
            # "Director at SAPPHIRE MANAGEMENT CONSULTANCY LIMITED" -> position
            role_text = (row.get('role') or '').strip()
            if ' at ' in role_text:
                title = role_text.split(' at ')[0].strip()
        cand = Candidate(
            name=name,
            contact_title=title,
            company=company,
            linkedin=url,
            degree=_degree(row),
            kind='person',
            sources=[source],
            evidence=[extra_evidence] if extra_evidence else [],
        )
        if row.get('connected_on'):
            cand.evidence.append('connected_on %s' % row['connected_on'])
        out.append(cand)

    for fname, source in ((PRIORITY_FILE, 'happenstance_priority'),
                          (CONNECTIONS_FILE, 'happenstance_connections')):
        data = _read_json(os.path.join(base, fname))
        if data is None:
            ctx.warn('happenstance', '%s missing or unreadable' % fname)
            continue
        rows = _rows(data)
        for row in rows:
            add(row, source)
        ctx.warn('happenstance', '%s -> %d rows' % (fname, len(rows)))

    matches = _read_json(os.path.join(base, MATCHES_FILE))
    if matches is None:
        ctx.warn('happenstance', '%s missing or unreadable' % MATCHES_FILE)
    else:
        rows = _rows(matches)
        for row in rows:
            add(row, 'happenstance_match',
                'matched applied company %s' % (row.get('applied_as')
                                                or row.get('company') or ''))
        ctx.warn('happenstance', '%s -> %d rows' % (MATCHES_FILE, len(rows)))

    return out
