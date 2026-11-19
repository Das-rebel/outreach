"""GMAIL node — read-only mining of recruiter replies.

Reads the user's Gmail over IMAP (no send path exists in this module, ever)
and extracts recruiter replies: sender name, the company they wrote about,
which applied role/company the reply concerns, and the reply date.  A reply is
the strongest possible warmth signal — the recruiter already engaged.

Credentials come from `OE_GMAIL_APP_PW` (or `OE_GMAIL_USER`).  When they are
absent the adapter returns [] with a warning — it never raises.
"""
from __future__ import annotations

import email as emailmod
import imaplib
import os
import re
from datetime import date, timedelta
from email.header import decode_header
from typing import List, Optional, Tuple

from ..models import Candidate
from ..identity import norm_key, norm_text, resolve_company

# Known recruiter / ATS sender markers.
RECRUITER_HINTS = re.compile(
    r'(recruit|talent|hiring|hr\b|careers|jobs|intern|program|university|'
    r'campus|job alert|job opening|novelty|naukri|linkedin|indeed|'
    r'foundit|shine|hirade|jobstreet|wellfound|applicant)', re.I)

APPLIED_ROLE_HINTS = re.compile(
    r'(applied|application|applied for|your application|resume|cv\b|'
    r'interview|your profile|role|position|job)', re.I)

# Company names already in the tracker — used to attribute a reply to one of
# OUR applications rather than to an unrelated newsletter.
_STOP_PREFIX = re.compile(r'^(no-reply|noreply|donotreply|notifications?|'
                           r'alerts?|updates?|newsletter|do-not-reply)')

# Job boards / alert digests are NOT recruiters: a reply from one of these is
# a broadcast, not a person answering our application.
_BOARD_DOMAINS = ('linkedin.com', 'indeed.com', 'naukri.com', 'wellfound.com',
                  'foundit.com', 'shine.com', 'glassdoor.com', 'monster.com',
                  'monsterindia.com', 'ziprecruiter.com', 'jobbatical.com',
                  'workable.com', 'greenhouse.io', 'lever.co', 'ashbyhq.com',
                  'jora.com', 'apna.co', 'internshala.com', 'cutshort.io',
                  'iimjobs.com', 'experteer.com', 'jobrapido.com',
                  'timesjobs.com', 'jobstreet.com', 'bayt.com', 'hh.ru',
                  'stepstone.de', 'xing.com', 'angellist.com', 'welcometothejungle.com',
                  'medelaunchpad.com', 'companytal.com', 'hirebee.com',
                  'simplify.jobs', 'otta.com', 'dice.com', 'builtin.com',
                  'join.com', 'smartrecruiters.com', 'workday.com',
                  'icims.com', 'taleo.net', 'cornerstoneondemand.com',
                  'personio.de', 'jobvite.com', 'bamboohr.com', 'paylocity.com',
                  'recruitee.com', 'jobstreet.com', 'emailjobboard.com')

# Sender display names that are organisations, not people.
_ORG_SENDER = re.compile(r'\b(jobs?|alerts?|careers?|recruit\w*|hiring|'
                          r'no-reply|noreply|team|support|info|news|'
                          r'digest|updates?|marketing|sales)\b', re.I)

# A recruiter reply comes from a named person: a given name and a family
# name.  One token is a handle or a queue, not a person.
def _looks_like_person(display_name: str) -> bool:
    tokens = [t for t in re.split(r'\s+', (display_name or '').strip())
              if t and not re.search(r'[^\w.\-\']', t)]
    if len(tokens) < 2:
        return False
    if any(len(t) < 2 for t in tokens):
        return False
    return True

# A real recruiter reply talks about an application, an interview, or a
# specific role — not about "jobs you may be interested in".
_REPLY_MARKER = re.compile(
    r'(your application|application (status|update|for)|we (have )?(received|reviewed)|'
    r'interview|resume|your profile|shortlist|offer|rejected|applied for|'
    r'thank you for applying|application)', re.I)

_ALERT_MARKER = re.compile(r'you may (be )?be interested|job alerts?|saved jobs|'
                           r'jobs for you|new jobs|recommended jobs|'
                           r'newsletter|this week|weekly digest', re.I)

_CRED_RE = re.compile(r"GMAIL_APP_PW\s*=\s*['\"]([^'\"]+)['\"]")


def _resolve_password(cfg) -> str:
    if cfg.gmail_app_pw:
        return cfg.gmail_app_pw
    # Fall back to the app password already present in the repo (never write
    # the secret into this package — read it at runtime).
    for rel in ('multi_source/multi_source_harvest.py',
                'pipeline_v2/apply_parallel.py'):
        path = os.path.join(cfg.repo_root, rel)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                m = _CRED_RE.search(fh.read())
            if m:
                return m.group(1)
        except OSError:
            continue
    return ''


def _decode(value: str) -> str:
    if not value:
        return ''
    try:
        parts = decode_header(value)
    except Exception:
        return str(value)
    out = ''
    for text, charset in parts:
        if isinstance(text, bytes):
            out += text.decode(charset or 'utf-8', errors='ignore')
        else:
            out += text
    return out


def _sender_name(msg) -> str:
    frm = _decode(msg.get('From', ''))
    m = re.match(r'^\s*"?([^"<]*?)"?\s*<', frm)
    name = (m.group(1) if m else frm).strip()
    name = re.sub(r'\s*\(.*?\)\s*$', '', name).strip()
    return name


def _sender_email(msg) -> str:
    frm = _decode(msg.get('From', ''))
    m = re.search(r'<([^>]+)>', frm)
    return (m.group(1) if m else frm).strip().lower()


def _body_text(msg) -> str:
    body = ''
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode('utf-8', errors='ignore')
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='ignore')
    except Exception:
        body = ''
    return body[:4000]


def _reply_date(msg) -> str:
    for hdr in ('Date', 'Delivered-To'):
        raw = msg.get(hdr)
        if not raw:
            continue
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(raw).date().isoformat()
        except Exception:
            continue
    return ''


def _match_company(text: str, companies: List[str]) -> str:
    """Attribute a reply to one of our applied companies (longest match wins)."""
    low = ' ' + norm_text(text) + ' '
    best = ''
    for company in companies:
        key = norm_text(company)
        if len(key) < 3:
            continue
        if ' ' + key + ' ' in low and len(key) > len(best):
            best = key
    return best


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _seq_of(item_key) -> str:
    """IMAP returns `b"12 (BODY[HEADER] {345})"` as the key of a fetch tuple.

    The message id is NOT recoverable from it, but the *sequence number* is —
    and a sequence number is a valid fetch target, which is all we need to
    pull the body of the message we just looked at.
    """
    if isinstance(item_key, bytes):
        item_key = item_key.decode('ascii', 'ignore')
    m = re.match(r'\s*(\d+)', item_key or '')
    return m.group(1) if m else ''


def _bulk_headers(mail, ids):
    """Fetch headers for many messages in one IMAP round-trip.

    Returns a list of (sequence_number, header_bytes).  Fetching bodies one
    message at a time is the bottleneck (one round-trip each); headers are
    enough to filter out job boards and newsletters before any body is
    downloaded.
    """
    out = []
    for group in _chunk(ids, 10):
        spec = ','.join(i.decode() for i in group)
        try:
            _typ, data = mail.fetch(spec, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE))')
        except Exception:
            continue
        for item in data or []:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            raw = item[1]
            if not isinstance(raw, bytes):
                continue
            seq = _seq_of(item[0])
            if not seq:
                continue
            out.append((seq, raw))
    return out


def fetch(ctx) -> List[Candidate]:
    cfg = ctx.cfg
    if os.environ.get('OE_GMAIL', '1').strip().lower() in ('0', 'false', 'no', 'off'):
        ctx.warn('gmail', 'disabled (OE_GMAIL=0)')
        return []
    password = _resolve_password(cfg)
    if not password:
        ctx.warn('gmail', 'no Gmail app password available — '
                          'set OE_GMAIL_APP_PW to enable recruiter-reply mining')
        return []

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(cfg.gmail_user, password)
        mail.select('inbox')
    except Exception as exc:
        ctx.warn('gmail', 'IMAP unavailable (%s) — skipping' % type(exc).__name__)
        return []

    since = (date.today() - timedelta(days=60)).strftime('%d-%b-%Y')
    try:
        _, data = mail.search(None, '(SINCE "%s")' % since)
        ids = data[0].split()[-400:]
    except Exception:
        ids = []

    companies = sorted({c.applied_company for c in ctx.applications
                        if c.applied_company})
    out: List[Candidate] = []
    try:
        headers = _bulk_headers(mail, list(reversed(ids)))
        for seq, raw in headers:
            try:
                msg = emailmod.message_from_bytes(raw)
            except Exception:
                continue
            subject = _decode(msg.get('Subject', ''))
            sender = _sender_name(msg)
            sender_email = _sender_email(msg)
            head_blob = subject + ' ' + sender + ' ' + sender_email

            # --- cheap header-level filters (no body download) -----------
            if _STOP_PREFIX.match(sender_email):
                continue
            domain = sender_email.split('@')[-1].lower()
            if any(domain.endswith(d) for d in _BOARD_DOMAINS):
                continue
            if _ORG_SENDER.search(sender):
                continue
            if _ALERT_MARKER.search(head_blob):
                continue
            # A recruiter is a person: first name + last name.  This is a
            # stronger signal than any "recruit"/"talent" keyword — genuine
            # recruiters rarely put those words in their display name, and
            # ATS mailboxes always do.
            if not _looks_like_person(sender):
                continue

            # --- only now fetch the body ---------------------------------
            try:
                _, msg_data = mail.fetch(seq, '(RFC822)')
                full = emailmod.message_from_bytes(msg_data[0][1])
            except Exception:
                full = msg
            body = _body_text(full)
            blob = head_blob + ' ' + body

            # The reply must concern one of OUR applications: it has to name
            # a company we applied to and talk about a role.
            company = _match_company(blob, companies)
            if not company:
                continue
            if not APPLIED_ROLE_HINTS.search(blob):
                continue
            if not _REPLY_MARKER.search(blob):
                continue

            cand = Candidate(
                name=sender,
                contact_title='Recruiter',
                company=company,
                applied_company=company,
                email=sender_email,
                applied_date=_reply_date(full),
                kind='person',
                sources=['gmail'],
                evidence=['recruiter reply on %s'
                          % (_reply_date(full) or 'unknown date'),
                          'subject: %s' % subject[:120]],
            )
            cand.evidence.append('gmail:reply')
            out.append(cand)
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    ctx.warn('gmail', 'mined %d recruiter replies from %d recent messages'
             % (len(out), len(ids)))
    return out
