"""Human approval bundle.

Renders the approval pack in the EARLIER SESSION STYLE (see
`runs/outreach/APPROVAL_TOP30.md`):

    ### 1. <Name> — <their designation>
    🔗 LinkedIn DM
    **To:** <name> @ <company>
    **Their designation:** <contact_title> (<their org>)
    **Applied:** <role> at <applied_company> (<date>)
    **LinkedIn:** <url>
    **Resume:** <resume filename>
    ```
    <the EXACT full message, verbatim>
    ```

Also parses a decision file (approved names and/or ranks) back into an
approval set so `dispatch --approved <file>` can act on a human's choices.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence

from .models import ApprovalItem, Candidate
from .identity import norm_key
from . import messaging

CHANNEL_LABEL = {
    'linkedin': '\U0001f517 LinkedIn DM',
    'email': '\U0001f4e7 Email',
    'whatsapp': '\U0001f4f1 WhatsApp',
}


def channel_label(channel: str) -> str:
    return CHANNEL_LABEL.get((channel or '').lower(), channel or 'unknown')


def designation_for(cand: Candidate) -> str:
    """`contact_title` + their org — the brief's "THEIR DESIGNATION"."""
    title = (cand.contact_title or '').strip() or 'Contact'
    org = (cand.company or '').strip()
    if org:
        return '%s (%s)' % (title, org)
    return title


def build_items(candidates: Sequence[Candidate]) -> List[ApprovalItem]:
    items: List[ApprovalItem] = []
    for rank, cand in enumerate(candidates, start=1):
        score = cand.score or {}
        items.append(ApprovalItem(
            rank=rank,
            name=cand.name,
            channel=cand.channel or 'linkedin',
            designation=designation_for(cand),
            their_org=cand.company or '',
            applied_company=cand.applied_company or '',
            applied_role=cand.applied_role or '',
            applied_date=cand.applied_date or '',
            linkedin=cand.linkedin or '',
            resume=cand.resume or '',
            message=cand.message or '',
            tier=score.get('tier') or cand.tier or '',
            score=score.get('total', 0),
            email=cand.email or '',
            phone=cand.phone or '',
            message_type=cand.message_type or '',
            subject=messaging.subject_for(cand.message_type or 'B',
                                          cand.applied_role or '',
                                          cand.applied_company or ''),
            email_body=cand.email_body or '',
            email_subject=cand.email_subject or '',
        ))
    return items


def render_item(item: ApprovalItem) -> str:
    lines = []
    lines.append('### %d. %s — %s' % (item.rank, item.name, item.designation))
    lines.append(channel_label(item.channel))
    lines.append('**To:** %s @ %s' % (item.name, item.their_org or item.applied_company))
    lines.append('**Their designation:** %s' % item.designation)
    lines.append('**Applied:** %s at %s (%s)' % (
        item.applied_role or '—', item.applied_company or '—',
        item.applied_date or '—'))
    lines.append('**LinkedIn:** %s' % (item.linkedin or '—'))
    lines.append('**Resume:** %s' % (item.resume or '—'))
    lines.append('```')
    lines.append(item.message)
    lines.append('```')
    if item.email_body:
        lines.append('')
        lines.append('📧 **Email — Subject:** %s' % (item.email_subject or item.subject))
        lines.append('')
        lines.append('```')
        lines.append(item.email_body)
        lines.append('```')
    if item.email:
        lines.append('')
        lines.append('**Email:** %s' % item.email)
    return '\n'.join(lines)


def render_bundle(items: Sequence[ApprovalItem], meta: Optional[Dict] = None) -> str:
    meta = meta or {}
    lines = []
    lines.append('# Outreach Approval Package — Top %d Targets' % len(items))
    lines.append('')
    lines.append('**STATUS: DRAFTED — NOTHING SENT.** '
                 'Approve (or edit) before any DM goes out.')
    lines.append('')
    lines.append('Generated: %s' % (meta.get('generated') or ''))
    lines.append('')
    lines.append('Method: outreach_engine v2 — rule-first eligibility (15-day '
                 'window), house message format v3, claim whitelist enforced; '
                 'do_not_approach + companies_banned + already-contacted + '
                 'manager/analyst excluded; no pattern-guessed emails.')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    type_a = sum(1 for i in items if 'TYPE A' in (i.message or ''))
    lines.append('- Type A (status follow-up): %d' % type_a)
    lines.append('- Type B (market insight): %d' % (len(items) - type_a))
    lines.append('- Unique companies: %d'
                 % len({i.applied_company for i in items if i.applied_company}))
    lines.append('- Channels: %s' % ', '.join(sorted({
        channel_label(i.channel) for i in items})))
    lines.append('')
    lines.append('---')
    lines.append('')
    for item in items:
        lines.append(render_item(item))
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def write_bundle(items: Sequence[ApprovalItem], path: str,
                 meta: Optional[Dict] = None) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(render_bundle(items, meta))
    return path


# --------------------------------------------------------------------------
# Decision parsing
# --------------------------------------------------------------------------

_APPROVED_RE = re.compile(r'^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?'
                          r'(?:approved?|yes|keep)\b', re.I)
_REJECTED_RE = re.compile(r'^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?'
                          r'(?:rejected?|no|skip|decline)\b', re.I)


def parse_decision_file(path: str, items: Sequence[ApprovalItem]) -> List[ApprovalItem]:
    """Parse a human decision file into the set of APPROVED items.

    Supported formats (all best-effort, tolerant):
      * JSON  {"approved": ["Pankaj Juneja", 3, ...]} or a list of names
      * JSON  {"approved": [{"name": "...", "rank": 3}, ...]}
      * Markdown/plain text, one decision per line:
            1. Pankaj Juneja — approved
            3. Manish Pathania
            - Girish Gupta — rejected
    """
    if not path or not os.path.exists(path):
        raise FileNotFoundError(path)

    approved_names = set()
    approved_ranks = set()
    rejected_names = set()
    rejected_ranks = set()

    raw = open(path, encoding='utf-8').read()
    stripped = raw.strip()

    if stripped.startswith('{') or stripped.startswith('['):
        data = json.loads(stripped)
        rows = data.get('approved') if isinstance(data, dict) else data
        if rows is None:
            rows = []
        for row in rows or []:
            if isinstance(row, dict):
                if row.get('name'):
                    approved_names.add(norm_key(str(row['name'])))
                if row.get('rank') is not None:
                    approved_ranks.add(int(row['rank']))
            elif isinstance(row, int):
                approved_ranks.add(int(row))
            elif isinstance(row, str):
                if row.strip().isdigit():
                    approved_ranks.add(int(row.strip()))
                else:
                    approved_names.add(norm_key(row))
        rejected = data.get('rejected') if isinstance(data, dict) else []
        for row in rejected or []:
            if isinstance(row, int) or (isinstance(row, str) and row.strip().isdigit()):
                rejected_ranks.add(int(row))
            elif isinstance(row, dict) and row.get('name'):
                rejected_names.add(norm_key(str(row['name'])))
            elif isinstance(row, str):
                rejected_names.add(norm_key(row))
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^(?:#{1,6}\s*)?(?:item\s*)?(\d+)[.)\s:-]+(.*)$', line,
                         re.I)
            rank = None
            rest = line
            if m:
                rank = int(m.group(1))
                rest = m.group(2)
            if _REJECTED_RE.match(rest):
                if rank is not None:
                    rejected_ranks.add(rank)
                name = _name_from_line(rest)
                if name:
                    rejected_names.add(norm_key(name))
                continue
            if _APPROVED_RE.match(rest) or rank is not None:
                if rank is not None:
                    approved_ranks.add(rank)
                name = _name_from_line(rest)
                if name:
                    approved_names.add(norm_key(name))

    out = []
    for item in items:
        key = norm_key(item.name)
        if key in rejected_names or item.rank in rejected_ranks:
            continue
        if key in approved_names or item.rank in approved_ranks:
            out.append(item)
    return out


def _name_from_line(text: str) -> str:
    text = re.sub(r'^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?', '', text)
    text = re.sub(r'\b(approved?|rejected?|yes|no|keep|skip|decline)\b.*$',
                  '', text, flags=re.I)
    text = text.split('—')[0].split('--')[0].split('|')[0]
    text = text.split('@')[0]
    text = re.sub(r'\([^)]*\)', '', text)
    return text.strip(' .:,-—')
