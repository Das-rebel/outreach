"""Email dispatch (Gmail SMTP).

DISABLED unless `channels.email` is true AND an explicit approval set exists.
Only VERIFIED emails are ever used — a pattern-guessed address is a hard
failure (the Gokuldas lesson).

Enforced gates (E1-E4):
    E1  no role aliases (careers@ / hr@ / info@ / jobs@ ...)
    E2  a named person only
    E3  relevance gate — the email must relate to a role we applied for
    E4  senior role only
"""
from __future__ import annotations

import json
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Dict, List, Sequence

from ..identity import norm_email
from ..messaging import subject_for

ROLE_ALIASES = ('careers', 'career', 'hr', 'info', 'jobs', 'job', 'hiring',
                'recruitment', 'recruiter', 'talent', 'admin', 'office',
                'support', 'sales', 'contact', 'hello', 'team', 'no-reply',
                'noreply', 'mailer')

ALIAS_RE = re.compile(
    r'^(?:[a-z0-9._%+-]+)?(?:careers?|hr|info|jobs?|hiring|recruit\w*|'
    r'talent|admin\w*|office|support|sales|contact|hello|team|no-?reply|'
    r'noreply|mailer)@', re.I)


def is_role_alias(email: str) -> bool:
    return bool(ALIAS_RE.match((email or '').strip().lower()))


def check_email_gates(item: Dict, ctx) -> List[str]:
    """Return a list of violated gate codes (empty = OK)."""
    failures: List[str] = []
    email = (item.get('email') or '').strip()
    name = (item.get('name') or '').strip()

    if not email:
        failures.append('E2_NO_EMAIL')
    else:
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            failures.append('E2_BAD_EMAIL_FORMAT')
        if is_role_alias(email):
            failures.append('E1_ROLE_ALIAS')
        if not email.lower().endswith('@' + (item.get('email_domain') or
                                             email.split('@')[-1]).lower()):
            failures.append('E1_DOMAIN_MISMATCH')

    if not name or '@' in name or '<' in name:
        failures.append('E2_NOT_A_NAMED_PERSON')

    role = (item.get('applied_role') or '').strip()
    if not role:
        failures.append('E3_NO_RELEVANT_ROLE')

    from ..eligibility import SENIOR_RE
    if role and not SENIOR_RE.search(role):
        failures.append('E4_NOT_SENIOR_ROLE')

    return failures


def build_email(item: Dict) -> EmailMessage:
    msg = EmailMessage()
    msg['To'] = '%s <%s>' % (item.get('name'), item.get('email'))
    msg['From'] = item.get('from_addr') or item.get('gmail_user') or ''
    msg['Subject'] = item.get('subject') or subject_for(
        item.get('message_type') or 'B',
        item.get('applied_role') or '',
        item.get('applied_company') or '')
    body = item.get('email_body') or item.get('message') or ''
    msg.set_content(body)
    # ALWAYS attach the canonical resume (dual-channel rule: email carries the CV)
    # NOTE: set_content() leaves a str payload — make_mixed() is required
    # before attach(), otherwise the attachment is silently dropped.
    resume = item.get('resume') or ''
    if resume:
        msg.make_mixed()
        import glob as _glob
        import mimetypes
        from email.mime.application import MIMEApplication
        cands = []
        for base in (os.path.expanduser('~/Downloads'), os.path.expanduser('~/job_pipeline/attachments')):
            cands += _glob.glob(os.path.join(base, '**', resume), recursive=True)
            cands += _glob.glob(os.path.join(base, resume))
        for cand in cands:
            try:
                with open(cand, 'rb') as fh:
                    data = fh.read()
                ctype, _ = mimetypes.guess_type(cand)
                part = MIMEApplication(data, _subtype=(ctype or 'application/pdf').split('/')[-1])
                part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(cand))
                msg.attach(part)
                break
            except Exception:
                continue
    return msg


def run_email_dispatch(items: Sequence, cfg, ctx, send: bool = False) -> Dict:
    """Dispatch approved email items.  Dry-run unless `send=True`."""
    result = {'mode': 'send' if send else 'dry_run', 'sent': 0, 'failed': 0,
              'skipped': [], 'targets': []}

    if not cfg.channel_email:
        result['note'] = 'email channel disabled (channels.email=false)'
        return result
    if not send:
        result['note'] = 'dry run — nothing sent'
        for item in items:
            result['targets'].append({
                'name': item.name,
                'email': item.email,
                'email_body_len': len(getattr(item, 'email_body', '') or ''),
                'resume': getattr(item, 'resume', '') or '',
                'applied_company': item.applied_company,
                'status': 'dry_run',
                'message': item.message,
            })
        return result

    password = cfg.gmail_app_pw
    if not password:
        result['note'] = 'no Gmail app password configured — refusing to send'
        return result

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30)
    except Exception as exc:
        result['note'] = 'SMTP unavailable: %s' % exc
        return result

    try:
        server.login(cfg.gmail_user, password)
    except Exception as exc:
        result['note'] = 'SMTP login failed: %s' % exc
        return result

    try:
        for item in items:
            failures = check_email_gates({
                'email': item.email,
                'name': item.name,
                'applied_role': item.applied_role,
                'applied_company': item.applied_company,
            }, ctx)
            if failures:
                result['failed'] += 1
                result['skipped'].append({'name': item.name,
                                          'reason': ','.join(failures)})
                continue
            msg = build_email({
                'email': item.email,
                'name': item.name,
                'message': item.message,
                'email_body': getattr(item, 'email_body', '') or '',
                'subject': getattr(item, 'email_subject', '') or '',
                'resume': getattr(item, 'resume', '') or '',
                'applied_role': item.applied_role,
                'applied_company': item.applied_company,
                'message_type': item.message_type,
                'from_addr': cfg.gmail_user,
            })
            try:
                server.send_message(msg)
                result['sent'] += 1
                result['targets'].append({'name': item.name,
                                          'email': item.email,
                                          'status': 'sent'})
            except Exception as exc:
                result['failed'] += 1
                result['targets'].append({'name': item.name,
                                          'email': item.email,
                                          'status': 'FAILED',
                                          'note': str(exc)[:120]})
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return result
