"""Outcome state machine.

Per application/company:

    applied -> contacted -> replied -> interview -> offer
                    |           |          |
                    +-----------+----------+--> rejected / no_reply

Follow-ups are due at +3, +7 and +14 days after `contacted`.  State is
persisted append-only to `runs/outreach/engine_state/outcomes.jsonl`
(see ADR-001: JSONL is the source of truth, derived files are rebuilt).
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Dict, List, Optional

STATES = ('applied', 'contacted', 'replied', 'interview', 'offer',
          'rejected', 'no_reply')

TERMINAL = ('offer', 'rejected', 'no_reply')

TRANSITIONS = {
    'applied': ('contacted', 'rejected', 'no_reply'),
    'contacted': ('replied', 'rejected', 'no_reply', 'interview'),
    'replied': ('interview', 'rejected', 'no_reply'),
    'interview': ('offer', 'rejected', 'no_reply'),
    'offer': (),
    'rejected': (),
    'no_reply': ('contacted',),
}


def outcomes_path(cfg) -> str:
    return os.path.join(cfg.state_dir, 'outcomes.jsonl')


def load_outcomes(cfg) -> Dict[str, Dict]:
    """Latest record per (company, role) key."""
    path = outcomes_path(cfg)
    records: Dict[str, Dict] = {}
    if not os.path.exists(path):
        return records
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record_key(row.get('company'), row.get('role'))
            records[key] = row
    return records


def record_key(company: str, role: str) -> str:
    from .identity import norm_key, resolve_company
    return '%s|%s' % (resolve_company(company or ''), norm_key(role or ''))


def append_outcome(cfg, company: str, role: str, state: str,
                   note: str = '', contact: str = '') -> Dict:
    path = outcomes_path(cfg)
    os.makedirs(cfg.state_dir, exist_ok=True)
    row = {
        'company': company,
        'role': role,
        'state': state,
        'note': note,
        'contact': contact,
        'updated': date.today().isoformat(),
    }
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    return row


def can_transition(current: str, new: str) -> bool:
    if new not in STATES:
        return False
    if current is None:
        return new == 'contacted'
    if current == new:
        return True
    return new in TRANSITIONS.get(current, ())


def set_state(cfg, company: str, role: str, new_state: str, note: str = '',
              contact: str = '') -> Dict:
    """Move an outcome to `new_state` (validated against the machine)."""
    records = load_outcomes(cfg)
    key = record_key(company, role)
    current = (records.get(key) or {}).get('state')
    if not can_transition(current, new_state):
        raise ValueError('illegal transition %s -> %s' % (current, new_state))
    return append_outcome(cfg, company, role, new_state, note, contact)


def followups_due(cfg, today: Optional[date] = None) -> List[Dict]:
    """Records whose next follow-up offset (+3/+7/+14) has come due."""
    today = today or date.today()
    records = load_outcomes(cfg)
    due: List[Dict] = []
    for row in records.values():
        if row.get('state') not in ('contacted', 'replied'):
            continue
        stamp = row.get('contacted_on') or row.get('updated')
        if not stamp:
            continue
        try:
            contacted = date.fromisoformat(str(stamp)[:10])
        except ValueError:
            continue
        age = (today - contacted).days
        offsets = list(cfg.followup_offsets or [3, 7, 14])
        for offset in offsets:
            if age >= offset:
                due.append({
                    'company': row.get('company'),
                    'role': row.get('role'),
                    'state': row.get('state'),
                    'contacted_on': str(contacted),
                    'age_days': age,
                    'due_offset': offset,
                    'next_offset': next((o for o in offsets if o > age), None),
                })
                break
    due.sort(key=lambda r: (-r['age_days'], r['company'] or ''))
    return due


def summary(cfg) -> Dict:
    records = load_outcomes(cfg)
    counts: Dict[str, int] = {state: 0 for state in STATES}
    for row in records.values():
        state = row.get('state') or 'applied'
        counts[state] = counts.get(state, 0) + 1
    due = followups_due(cfg)
    return {
        'total_tracked': len(records),
        'by_state': counts,
        'followups_due': due,
        'followups_due_count': len(due),
        'outcomes_path': outcomes_path(cfg),
    }
