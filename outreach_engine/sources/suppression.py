"""CONTACT LOGS node — suppression.

Reads every record of a previous contact:
  * `attachments/outreach/li_dm_log.jsonl`        (71 rows / 48 sent)
  * `attachments/outreach/multi_channel_log.jsonl` (181 rows)
  * every prior approval pack `runs/outreach/APPROVAL*.json` — a person who
    was already PROPOSED (and possibly approved) must not be proposed again
    silently.

The adapter returns Candidates flagged `already_contacted`; the eligibility
gate turns them into the `already_contacted` reason code.  The node also
populates `ctx.contacted_slugs` / `ctx.contacted_emails` /
`ctx.contacted_name_company` so the gate is O(1).
"""
from __future__ import annotations

import glob
import json
import os
from typing import List

from ..models import Candidate
from ..identity import norm_email, norm_key, norm_text, linkedin_slug


def _iter_jsonl(path: str):
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def _iter_approval_packs(approval_dir: str):
    for path in sorted(glob.glob(os.path.join(approval_dir, 'APPROVAL*.json'))):
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        rows = data if isinstance(data, list) else (data.get('targets') or [])
        for row in rows:
            if isinstance(row, dict):
                yield row


def load_suppression_sets(ctx) -> None:
    """Populate `ctx.contacted_*` from the contact logs and prior approval
    packs, WITHOUT emitting candidates.  Used by every command that applies
    the eligibility gates (the sets must be present even when `ingest` was
    run in an earlier process)."""
    cfg = ctx.cfg
    slugs = set()
    emails = set()
    pairs = set()

    def collect(row: dict) -> None:
        url = (row.get('linkedin') or row.get('linkedin_url') or row.get('url')
               or '').strip()
        mail = (row.get('email') or '').strip()
        name = (row.get('name') or '').strip()
        company = (row.get('company') or row.get('contact_company') or '').strip()
        slug = linkedin_slug(url)
        if slug:
            slugs.add(slug)
        if mail:
            emails.add(norm_email(mail))
        if name:
            pairs.add((norm_text(name).replace(' ', ''),
                       norm_text(company).replace(' ', '')))

    for path in (cfg.dm_log, cfg.multi_channel_log):
        for row in _iter_jsonl(path):
            if isinstance(row, dict):
                collect(row)
    for row in _iter_approval_packs(cfg.approval_dir):
        collect(row)

    ctx.contacted_slugs = slugs
    ctx.contacted_emails = emails
    ctx.contacted_name_company = pairs


def fetch(ctx) -> List[Candidate]:
    cfg = ctx.cfg
    out: List[Candidate] = []
    slugs = set()
    emails = set()
    pairs = set()

    def record(row: dict, source: str) -> None:
        name = (row.get('name') or '').strip()
        company = (row.get('company') or row.get('contact_company')
                   or '').strip()
        url = (row.get('linkedin') or row.get('linkedin_url') or row.get('url')
               or '').strip()
        mail = (row.get('email') or '').strip()
        slug = linkedin_slug(url)
        if slug:
            slugs.add(slug)
        if mail:
            emails.add(norm_email(mail))
        if name:
            pairs.add((norm_text(name).replace(' ', ''),
                       norm_text(company).replace(' ', '')))
        if not name and not url and not mail:
            return
        cand = Candidate(
            name=name,
            contact_title=(row.get('title') or row.get('designation') or '').strip(),
            company=company,
            linkedin=url,
            email=mail,
            kind='suppression',
            sources=[source],
            evidence=['previously contacted/proposed via %s' % source],
        )
        out.append(cand)

    for path, source in ((cfg.dm_log, 'dm_log'),
                         (cfg.multi_channel_log, 'multi_channel_log')):
        rows = list(_iter_jsonl(path))
        for row in rows:
            if not isinstance(row, dict):
                continue
            # A FAILED attempt (NO_TEXTBOX, timeout, JS error) means we never
            # reached the person -> NOT a contact.  Only a confirmed send
            # counts, otherwise the people we failed to reach are blocked
            # forever.
            st = str(row.get('status') or row.get('outcome') or '').strip().lower()
            if st in ('failed', 'error', 'skipped', 'dry_run', 'typed_needs_manual_send',
                      'not_sent', 'attempted'):
                continue
            record(row, source)
        ctx.warn('suppression', '%s -> %d rows'
                 % (os.path.basename(path), len(rows)))

    packs = list(_iter_approval_packs(cfg.approval_dir))
    for row in packs:
        # Prior approval packs are DRAFTS (proposals), not deliveries.  They
        # must suppress a duplicate EMAIL (same address) but must NOT block a
        # person we never actually reached.
        mail = str(row.get('email') or '').strip()
        if not mail:
            continue
        emails.add(norm_email(mail))
        record({k: v for k, v in row.items() if k == 'email'}, 'approval_pack_email')
    ctx.warn('suppression', '%d prior approval pack rows' % len(packs))

    ctx.contacted_slugs = slugs
    ctx.contacted_emails = emails
    ctx.contacted_name_company = pairs
    return out
