"""WhatsApp dispatch — DISABLED BY DEFAULT.

Reference implementation only.  The GoWA wrapper listens on
`http://127.0.0.1:8090/send` with header `x-api-key` and body
`{"phone": "...", "message": "..."}`.

Hard rules:
  * DISABLED unless `channels.whatsapp` is explicitly turned on.
  * Only a candidate with a PHONE number may be dispatched.
  * Only after an explicit human approval set exists.
  * Nothing in this module is called during the offline demo.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Sequence

from ..identity import norm_text


def has_phone(item) -> bool:
    return bool((getattr(item, 'phone', '') or '').strip())


def build_payload(item, cfg) -> Dict:
    return {
        'phone': (item.phone or '').strip(),
        'message': item.message or '',
    }


def run_whatsapp_dispatch(items: Sequence, cfg, ctx, send: bool = False) -> Dict:
    result = {'mode': 'send' if send else 'dry_run', 'sent': 0, 'failed': 0,
              'skipped': [], 'targets': [], 'note': ''}

    if not cfg.channel_whatsapp:
        result['note'] = 'whatsapp channel disabled (default)'
        return result

    if not send:
        result['note'] = 'dry run — nothing sent'
        for item in items:
            result['targets'].append({'name': item.name,
                                      'has_phone': has_phone(item),
                                      'status': 'dry_run'})
        return result

    for item in items:
        if not has_phone(item):
            result['failed'] += 1
            result['skipped'].append({'name': item.name,
                                      'reason': 'NO_PHONE'})
            continue
        payload = build_payload(item, cfg)
        try:
            req = urllib.request.Request(
                cfg.whatsapp_endpoint,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json',
                         'x-api-key': cfg.whatsapp_api_key},
                method='POST')
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode('utf-8', 'replace')[:200]
            result['sent'] += 1
            result['targets'].append({'name': item.name, 'status': 'sent',
                                      'response': body})
        except (urllib.error.URLError, OSError) as exc:
            result['failed'] += 1
            result['targets'].append({'name': item.name, 'status': 'FAILED',
                                      'note': str(exc)[:120]})
    return result
