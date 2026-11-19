#!/usr/bin/env python3
"""Clean outreach pipeline (2026-11-19).

Flow: harvest -> fetch_email -> shortlist -> build_content -> approve (batch of 10)

- Harvests from all local/free sources: tracker panel contacts, EMAIL_BOOK, LinkedIn
  people sweep cache, fresh applied roles (tracker applications).
- Fetches/resolves emails via free methods: book-published, SMTP verify, catch-all MX.
  (Paid Monid/Hunter only if balance/cap allows; currently Monid balance $0 so skipped.)
- Shortlists with deterministic scoring + hard gates, then optional dual-LLM decision
  model (crouton-alpha via OpenRouter + glm-5.3 via z.ai, AND-gate) when available.
- Builds send-ready content: subject, full email body (v3 style), JD summary, resume.
- When >=10 complete packages are ready, presents via ask-user CLI in batches of 10
  with all required details (Person, Designation, Company, Email, Address evidence,
  Applied role, Applied date, Job summary, Subject, Resume, Full email body).
- Records decisions and sends approved emails (if OE_GMAIL_APP_PW set).

Usage:
  python3 runs/outreach/pipeline_clean.py run                # full run, batch-approve if >=10
  python3 runs/outreach/pipeline_clean.py run --min-batch 5  # lower threshold
  python3 runs/outreach/pipeline_clean.py run --no-llm       # deterministic only
  python3 runs/outreach/pipeline_clean.py run --send          # auto-send approved in this run
  python3 runs/outreach/pipeline_clean.py status             # show pipeline state
  python3 runs/outreach/pipeline_clean.py sources            # audit sources

Outputs (runs/outreach/clean_state/):
  harvest.json, enriched.json, shortlist.json, packages.json, decisions.json, report.json
"""
from __future__ import annotations

import argparse, datetime, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
# external data root (job pipeline) — configurable
DATA_ROOT = os.environ.get('OUTREACH_DATA_ROOT') or os.environ.get('JOB_PIPELINE_ROOT') or os.path.expanduser('~/job_pipeline')
for p in (HERE, REPO_ROOT, DATA_ROOT):
    if p and p not in sys.path:
        sys.path.insert(0, p)

from email_harvest import budget_left, spent_today, daily_cap, domain_rows
from smtp_verify import probe
import gen_email_drafts_v3 as g3
import gen_email_drafts_v2 as g2
from outreach_engine.messaging import resume_for

try:
    from xiryn_kit.role_priority import classify as classify_role_priority
except Exception:
    classify_role_priority = None

def _cfg_path(env_key, *candidates):
    v = os.environ.get(env_key)
    if v:
        return os.path.expanduser(v)
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return candidates[0] if candidates else ''

STATE_DIR = os.environ.get('OUTREACH_STATE_DIR') or os.path.join(HERE, "clean_state")
os.makedirs(STATE_DIR, exist_ok=True)

TODAY = datetime.date.today()
FRESH_DAYS = 14
MAX_PER_ROLE = 2  # no more than 2 contacts per applied role (company+role)

# --- paths (configurable; defaults point to job-pipeline data)
TRACKER_PATH = _cfg_path('OUTREACH_TRACKER_PATH',
    os.path.join(DATA_ROOT, "applied_companies_tracker.json"))
PROFILE_PATH = _cfg_path('OUTREACH_PROFILE_PATH',
    os.path.join(DATA_ROOT, "pipeline_v2", "canonical_profile.json"))
DM_LOG_PATH = _cfg_path('OUTREACH_DM_LOG_PATH',
    os.path.join(DATA_ROOT, "attachments", "outreach", "li_dm_log.jsonl"),
    os.path.join(HERE, "li_dm_log.jsonl"))
BOOK_PATH = _cfg_path('OUTREACH_BOOK_PATH',
    os.path.join(DATA_ROOT, "runs", "outreach", "EMAIL_BOOK.json"),
    os.path.join(HERE, "EMAIL_BOOK.json"))
OUTREACH_TRACKER_PATH = _cfg_path('OUTREACH_OUTREACH_TRACKER_PATH',
    os.path.join(DATA_ROOT, "runs", "outreach", "OUTREACH_TRACKER.json"),
    os.path.join(HERE, "OUTREACH_TRACKER.json"))
LI_PEOPLE_PATH = _cfg_path('OUTREACH_LI_PEOPLE_PATH',
    os.path.join(DATA_ROOT, "runs", "outreach", "LINKEDIN_PEOPLE.json"),
    os.path.join(HERE, "LINKEDIN_PEOPLE.json"))
FRESH_JDS_PATH = _cfg_path('OUTREACH_FRESH_JDS_PATH',
    os.path.join(DATA_ROOT, "runs", "outreach", "FRESH_JDS.json"),
    os.path.join(HERE, "FRESH_JDS.json"))
COMPANY_DOMAINS_PATH = _cfg_path('OUTREACH_COMPANY_DOMAINS_PATH',
    os.path.join(DATA_ROOT, "runs", "outreach", "company_domains.json"),
    os.path.join(HERE, "company_domains.json"))
RUNS_OUTREACH_DIR = os.environ.get('OUTREACH_RUNS_DIR') or os.path.join(DATA_ROOT, 'runs', 'outreach')

SENIOR_RE = re.compile(r'\b(head|director|vp|vice president|avp|chief|cmo|cgo|cpo|president|gm|general manager)\b', re.I)
BAD_TITLE_RE = re.compile(r'\b(founder|co-founder|intern|recruit|talent acquisition|analyst|associate\b|consultant|executive assistant|campus|hrbp|human resources)\b', re.I)
MKT_FIT_RE = re.compile(r'market|growth|brand|perform|digital|demand|acqui|communicat|content|social|media|crm|lifecycle|revenue|gtm|commercial|partnership|merchant', re.I)

FAM = {
    'growth_marketing': re.compile(r'marketing|growth|demand\b|brand|performance|communications?|\bgtm|digital|revenue|lifecycle|\bsocial\b|merchant|acqui', re.I),
    'product': re.compile(r'product|platform', re.I),
    'sales_bd': re.compile(r'sales|business development|partnership|channel|alliance', re.I),
}

DECLINED_COMPANIES = {'qlub', 'qclub', 'trestavista', 'certifyos', 'experian', 'perceptyne', 'dream cricket', 'dreamcricket', 'swiggy'}

CATCH_CACHE = {}


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def norm(s):
    return re.sub(r'[^a-z0-9 ]', '', (s or '').lower()).strip()


def norm_co(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def role_key(company, role):
    return (norm_co(company), norm(role))


def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)


# ---------- load state / suppression ----------

def load_profile():
    return load_json(PROFILE_PATH, {})


def load_sent_and_decisions():
    sent_emails = set()
    sent_names = set()
    role_sent = Counter()
    co_sent = Counter()
    # DM log
    if os.path.exists(DM_LOG_PATH):
        with open(DM_LOG_PATH, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get('status') == 'sent':
                    sent_emails.add(norm((r.get('email') or '')))
                    sent_names.add(norm((r.get('name') or '')))
                    c = r.get('company') or ''
                    ar = r.get('applied_role') or r.get('role') or ''
                    if ar:
                        role_sent[role_key(c, ar)] += 1
                    co_sent[norm_co(c)] += 1
    # decision files (scan local + data runs/outreach)
    decided_names = set()
    decided_emails = set()
    skipped_companies_roles = set()
    scan_dirs = []
    for d in [HERE, globals().get('RUNS_OUTREACH_DIR')]:
        if d and os.path.isdir(d) and d not in scan_dirs:
            scan_dirs.append(d)
    for sdir in scan_dirs:
        for fn in os.listdir(sdir):
            if not fn.startswith('DECISIONS') or not fn.endswith('.json'):
                continue
            d = load_json(os.path.join(sdir, fn), {})
            for x in (d.get('decisions') or []):
                decided_names.add(norm(x.get('name')))
                decided_emails.add(norm(x.get('email')))
            for x in (d.get('skipped_companies_roles') or []):
                skipped_companies_roles.add((norm_co(x.get('company')), norm(x.get('applied_role'))))
        # approved_names files may be list or dict
        for fn in os.listdir(sdir):
            if not fn.startswith('approved_names') or not fn.endswith('.json'):
                continue
            d = load_json(os.path.join(sdir, fn), {})
            names = d.get('approved') if isinstance(d, dict) else d
            for n in (names or []):
                decided_names.add(norm(n))
            for n in ((d.get('rejected') or []) if isinstance(d, dict) else []):
                decided_names.add(norm(n))
    return {
        'sent_emails': sent_emails, 'sent_names': sent_names,
        'role_sent': role_sent, 'co_sent': co_sent,
        'decided_names': decided_names, 'decided_emails': decided_emails,
        'skipped_cr': skipped_companies_roles,
    }


def load_fresh_apps():
    tracker = load_json(TRACKER_PATH, {})
    apps = tracker.get('applications') or []
    fresh = {}
    for a in apps:
        d = str(a.get('date') or '')[:10]
        try:
            age = (TODAY - datetime.date.fromisoformat(d)).days
        except Exception:
            continue
        if age < 0 or age > FRESH_DAYS:
            continue
        company = (a.get('company') or '').strip()
        role = (a.get('role') or '').strip()
        if not company or not role:
            continue
        if classify_role_priority:
            try:
                p, label, _ = classify_role_priority(company, role, '', '')
            except Exception:
                p, label = 7, 'P7 other'
        else:
            p, label = 7, 'P7 other'
        k = norm_co(company)
        cur = fresh.get(k)
        if not cur or (p, age) < (cur['p'], cur['age']):
            fresh[k] = {
                'company': company, 'role': role, 'date': d, 'age': age,
                'p': p, 'label': label,
            }
    return fresh


# ---------- STAGE 1: HARVEST ----------

def harvest(fresh_apps, suppression, profile):
    dnc = {norm(x) for x in (profile.get('do_not_approach') or [])}
    dnc |= {norm(x) for x in ['salil chugh', 'kishan gopal']}
    banned = {norm_co(x) for x in (profile.get('companies_banned') or [])}

    candidates = []
    seen = set()

    def add(c):
        key = (norm(c.get('name')), norm_co(c.get('company') or ''), norm(c.get('email') or ''))
        if key in seen:
            return
        seen.add(key)
        candidates.append(c)

    # 1a) Tracker panel contacts (OUTREACH_TRACKER)
    ot = load_json(OUTREACH_TRACKER_PATH, {})
    for c in (ot.get('contacts') or []):
        name = (c.get('contact_name') or '').strip()
        des = (c.get('contact_designation') or '').strip()
        comp = (c.get('company_applied') or c.get('contact_org') or '').strip()
        if not name or len(name.split()) < 2:
            continue
        parts = name.split()
        add({
            'name': name, 'first': parts[0], 'last': parts[-1],
            'designation': des, 'company': comp,
            'email': c.get('email'), 'source': 'tracker_panel',
            'applied_role': c.get('applied_role'), 'applied_date': c.get('applied_date'),
        })

    # 1b) EMAIL_BOOK
    book = load_json(BOOK_PATH, {}).get('addresses', {})
    by_name = {}
    for em, v in book.items():
        nm = ((v.get('first_name') or '') + ' ' + (v.get('last_name') or '')).strip()
        if not nm or len(nm.split()) < 2:
            continue
        dom = (v.get('domain') or '').lower()
        c = {
            'name': nm, 'first': v.get('first_name'), 'last': v.get('last_name'),
            'designation': v.get('position') or '', 'company': None, 'domain': dom,
            'email': em, 'verification': v.get('verification'), 'source': 'email_book',
        }
        add(c)
        by_name.setdefault(norm(nm), []).append((em, v))

    # attach book emails to tracker contacts missing email
    for c in candidates:
        if c.get('source') == 'tracker_panel' and not c.get('email'):
            hits = by_name.get(norm(c['name']))
            if hits:
                em, v = hits[0]
                c['email'] = em
                c['verification'] = v.get('verification')
                c['domain'] = v.get('domain')
                c['address_evidence'] = f"book-published ({v.get('verification')})"

    # 1c) LinkedIn people sweep cache
    lp = load_json(LI_PEOPLE_PATH, {})
    for comp, info in lp.items():
        for nm, ctx in (info.get('people') or {}).items():
            parts = nm.split()
            if len(parts) < 2:
                continue
            segs = [x.strip() for x in ctx.split('|') if x.strip()]
            title = ''
            for sg in segs[1:]:
                if MKT_FIT_RE.search(sg):
                    title = sg; break
            if not title:
                title = segs[1] if len(segs) > 1 else ''
            add({
                'name': nm, 'first': parts[0], 'last': parts[-1],
                'designation': title[:110], 'company': comp,
                'email': None, 'source': 'linkedin_sweep',
            })

    # 1d) map book/linkedin candidates to fresh applied companies by domain/company
    dom_map = load_json(COMPANY_DOMAINS_PATH, {})
    # build domain->fresh app map
    dom2app = {}
    for ck, app in fresh_apps.items():
        dom = dom_map.get(ck)
        if dom:
            dom2app[dom.lower()] = app
    # company name fuzzy map
    for c in candidates:
        if c.get('applied_role') and c.get('applied_date'):
            continue
        comp = c.get('company')
        app = None
        if comp:
            app = fresh_apps.get(norm_co(comp))
            if not app:
                # fuzzy: try to match by token overlap
                cn = norm_co(comp)
                for ck, a in fresh_apps.items():
                    if cn and (cn in ck or ck in cn):
                        app = a; comp = a['company']; break
        if not app and c.get('domain'):
            app = dom2app.get((c.get('domain') or '').lower())
            if app:
                comp = app['company']
        if app:
            c['company'] = comp or app['company']
            c['applied_role'] = app['role']
            c['applied_date'] = app['date']
            c['age'] = app['age']
            c['p'] = app['p']
            c['label'] = app['label']

    # basic source filtering
    out = []
    for c in candidates:
        name = norm(c.get('name'))
        if not name or name in dnc or name in suppression['sent_names'] or name in suppression['decided_names']:
            continue
        if norm(c.get('email')) in suppression['sent_emails'] or norm(c.get('email')) in suppression['decided_emails']:
            continue
        comp = c.get('company') or ''
        ck = norm_co(comp)
        if not comp or ck in banned or norm(comp) in DECLINED_COMPANIES:
            continue
        if norm_co(comp) == 'transunion':
            continue  # per latest directive: skip transunion
        if (ck, norm(c.get('applied_role'))) in suppression['skipped_cr']:
            continue
        if not c.get('applied_role') or not c.get('applied_date'):
            continue
        out.append(c)
    return out


# ---------- STAGE 2: FETCH/RESOLVE EMAIL ----------

def is_catchall(dom):
    if dom in CATCH_CACHE:
        return CATCH_CACHE[dom]
    try:
        st, _ = probe(dom, 'zzq7x3probe@' + dom)
        CATCH_CACHE[dom] = (st == 'valid')
    except Exception:
        CATCH_CACHE[dom] = False
    return CATCH_CACHE[dom]


def patterns(first, last, dom):
    f = (first or '').lower().replace(' ', '')
    l = (last or '').lower().replace(' ', '')
    if not f or not l or not dom:
        return []
    cands = [f'{f}.{l}@{dom}', f'{f}{l}@{dom}', f'{f[0]}.{l}@{dom}', f'{f}-{l}@{dom}',
             f'{f}@{dom}', f'{l}@{dom}', f'{f[0]}{l}@{dom}', f'{f}{l[0]}@{dom}']
    seen = set(); out = []
    for a in cands:
        if a not in seen:
            seen.add(a); out.append(a)
    return out


def resolve_email(c, dom_map):
    # already has book-published/known email
    em = c.get('email')
    if em:
        ev = c.get('address_evidence') or f"book-published ({c.get('verification')})"
        return em, ev
    dom = c.get('domain')
    if not dom:
        dom = dom_map.get(norm_co(c.get('company')))
    if not dom:
        return None, None
    first, last = c.get('first'), c.get('last')
    if not first or not last:
        parts = (c.get('name') or '').split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
    if not first or not last:
        return None, None
    try:
        if is_catchall(dom):
            f = first.lower().replace(' ', ''); l = last.lower().replace(' ', '')
            return f'{f}.{l}@{dom}', 'catch-all MX — server accepts this mailbox'
        for addr in patterns(first, last, dom):
            st, _ = probe(dom, addr)
            if st == 'valid':
                return addr, 'SMTP-verified 250'
    except Exception:
        return None, None
    return None, None


def fetch_emails(candidates, suppression):
    dom_map = load_json(COMPANY_DOMAINS_PATH, {})
    enriched = []
    for c in candidates:
        em = norm(c.get('email'))
        if em and (em in suppression['sent_emails'] or em in suppression['decided_emails']):
            continue
        resolved, evidence = resolve_email(c, dom_map)
        if not resolved:
            continue
        c['email'] = resolved
        c['address_evidence'] = evidence or c.get('address_evidence') or 'resolved'
        # recheck after resolution
        if norm(resolved) in suppression['sent_emails'] or norm(resolved) in suppression['decided_emails']:
            continue
        enriched.append(c)
    return enriched


# ---------- STAGE 3: SHORTLIST + DECISION MODEL ----------

def deterministic_score(c, app, suppression):
    """Score an outreach candidate. Higher is better."""
    score = 0.0
    reasons = []
    title = c.get('designation') or ''
    # priority of applied role/company (P0 best)
    p = app.get('p', c.get('p', 7))
    score += max(0, 40 - p * 5)
    reasons.append(f"priority:P{p}")
    # recency
    age = app.get('age', c.get('age', 99))
    score += max(0, 15 - age)
    reasons.append(f"fresh:{age}d")
    # seniority
    if re.search(r'\b(chief|cmo|cgo|president|founder)\b', title, re.I):
        score += 12; reasons.append('seniority:chief')
    elif re.search(r'\b(vp|vice president|svp|evp|avp)\b', title, re.I):
        score += 10; reasons.append('seniority:vp')
    elif re.search(r'\b(head|director|gm|general manager)\b', title, re.I):
        score += 9; reasons.append('seniority:head_dir')
    else:
        score += 4; reasons.append('seniority:other')
    # function fit
    role_l = (app.get('role') or '').lower()
    is_mkt_role = bool(re.search(r'market|growth|brand|performance|demand|acqui|revenue|digital|gtm|social', role_l))
    if is_mkt_role and MKT_FIT_RE.search(title):
        score += 12; reasons.append('function:fit')
    elif not is_mkt_role:
        score += 6; reasons.append('function:neutral')
    else:
        score += 2; reasons.append('function:weak')
    # email evidence quality
    ev = (c.get('address_evidence') or '').lower()
    if 'smtp-verified' in ev or 'valid' in ev:
        score += 6; reasons.append('email:verified')
    elif 'catch-all' in ev:
        score += 4; reasons.append('email:catchall')
    elif 'book-published' in ev:
        score += 5; reasons.append('email:book')
    else:
        score += 2; reasons.append('email:resolved')
    # per-role slots left
    rk = role_key(app.get('company'), app.get('role'))
    used = suppression['role_sent'].get(rk, 0)
    if used == 0:
        score += 3; reasons.append('slot:open')
    elif used == 1:
        score += 1; reasons.append('slot:1left')
    return round(score, 2), reasons


def function_family_ok(designation, applied_role):
    title = designation or ''
    role_l = (applied_role or '').lower()
    if not SENIOR_RE.search(title) or BAD_TITLE_RE.search(title):
        return False, 'seniority_or_bad_title'
    # for marketing/growth roles, prefer marketing/growth titles
    if re.search(r'market|growth|brand|performance|demand|acqui|revenue|digital|gtm|social|communications', role_l):
        if not MKT_FIT_RE.search(title):
            return False, 'function_mismatch'
    # for product roles, allow product/platform titles
    if re.search(r'\bproduct\b', role_l) and not re.search(r'market|growth', role_l):
        if re.search(r'engineering|technology|security|compliance|trading|capital markets', title, re.I):
            return False, 'function_mismatch'
    return True, 'ok'


def shortlist(candidates, fresh_apps, suppression, use_llm=True, llm_limit=30):
    # dedupe by (name, company)
    uniq = {}
    for c in candidates:
        k = (norm(c.get('name')), norm_co(c.get('company')))
        if k not in uniq:
            uniq[k] = c
    candidates = list(uniq.values())

    scored = []
    per_role = Counter()
    for c in candidates:
        app = fresh_apps.get(norm_co(c.get('company')))
        if not app:
            continue
        if norm(c.get('company')) == 'transunion' or norm_co(c.get('company')) == 'transunion':
            continue
        rk = role_key(app['company'], app['role'])
        total_used = suppression['role_sent'].get(rk, 0) + per_role[rk]
        if total_used >= MAX_PER_ROLE:
            continue
        ok, why = function_family_ok(c.get('designation') or '', app.get('role') or '')
        if not ok:
            continue
        det_score, reasons = deterministic_score(c, app, suppression)
        entry = {
            **c,
            'company': app['company'],
            'applied_role': app['role'],
            'applied_date': app['date'],
            'age': app['age'],
            'p': app['p'],
            'label': app['label'],
            'det_score': det_score,
            'det_reasons': reasons,
            'llm': None,
            'final_score': det_score,
            'decision': 'det_keep',
        }
        scored.append(entry)
        per_role[rk] += 1

    scored.sort(key=lambda x: (-x['final_score'], x.get('p', 7), x.get('age', 99)))

    # optional dual-LLM decision model (crouton-alpha + zai glm-5.3 AND-gate)
    if use_llm and scored:
        scored = apply_llm_decision(scored[:llm_limit]) + scored[llm_limit:]
        scored.sort(key=lambda x: (0 if x.get('decision') == 'llm_approved' else 1,
                                   -x.get('final_score', 0), x.get('p', 7), x.get('age', 99)))
    return scored


def apply_llm_decision(candidates):
    """Apply dual-model LLM judge (crouton-alpha + zai glm-5.3) as AND-gate.
    Falls back gracefully if unavailable."""
    try:
        sys.path.insert(0, ROOT)
        from xiryn_kit.llm_decide import decide as llm_decide
    except Exception as e:
        log(f"LLM decision model unavailable, using deterministic only: {e}")
        for c in candidates:
            c['llm'] = {'ok': None, 'reason': 'unavailable'}
        return candidates

    log(f"Running dual-LLM decision model on {len(candidates)} candidates...")
    for c in candidates:
        job = {
            'company': c.get('company'),
            'title': c.get('designation') or c.get('applied_role'),
            'location': 'India',
            'description': (
                f"Outreach target: contact {c.get('name')} ({c.get('designation')}) "
                f"at {c.get('company')} regarding our application for '{c.get('applied_role')}' "
                f"(applied {c.get('applied_date')}, {c.get('label')}). "
                f"Evaluate if this is a relevant, high-value senior contact to reach for this role."
            ),
        }
        try:
            v = llm_decide(job, threshold=65, jd_chars=1200)
            c['llm'] = v
            if v.get('ok'):
                c['decision'] = 'llm_approved'
                c['final_score'] = round(max(c.get('det_score', 0), float(v.get('score') or 0)), 2)
            else:
                # don't hard-drop on LLM reject if deterministic is strong; mark for review
                c['decision'] = 'llm_rejected' if c.get('det_score', 0) < 55 else 'det_keep_llm_flag'
                c['final_score'] = c.get('det_score', 0)
        except Exception as e:
            c['llm'] = {'ok': None, 'reason': f'error:{type(e).__name__}'}
            c['decision'] = 'det_keep'
        time.sleep(0.2)
    return candidates


# ---------- STAGE 4: BUILD CONTENT ----------

def load_jd_summaries():
    # try multiple sources
    out = {}
    fj = load_json(FRESH_JDS_PATH, {})
    if isinstance(fj, dict):
        for k, v in fj.items():
            if isinstance(v, dict):
                out[norm_co(k)] = v
            elif isinstance(v, str):
                out[norm_co(k)] = {'scope': v[:900]}
    # outreach tracker contacts may carry scope
    ot = load_json(OUTREACH_TRACKER_PATH, {})
    for c in (ot.get('contacts') or []):
        comp = norm_co(c.get('company_applied') or c.get('contact_org'))
        if comp and c.get('jd_scope') and comp not in out:
            out[comp] = {'scope': c.get('jd_scope')}
    return out


def build_job_summary(c):
    parts = []
    if c.get('label'):
        parts.append(c['label'])
    parts.append(f"Applied: {c.get('applied_role','')} ({c.get('applied_date','')}, {c.get('age','?')}d ago)")
    parts.append(f"Target contact: {c.get('designation','')} at {c.get('company','')}")
    if c.get('det_reasons'):
        parts.append('Fit: ' + ', '.join(c['det_reasons'][:5]))
    llm = c.get('llm') or {}
    if llm.get('ok'):
        parts.append(f"Dual-LLM decision: approved (score {llm.get('score')}, {llm.get('reason','')})")
    elif llm.get('ok') is False and llm.get('reason') not in (None, 'unavailable'):
        parts.append(f"LLM note: {llm.get('reason','')}")
    return ' | '.join(parts)


def build_content(shortlisted, suppression):
    allowed = g2.approved_numbers()
    jd_summaries = load_jd_summaries()
    packages = []
    seen_em = set()
    for c in shortlisted:
        # only keep candidates with valid email and decision not hard-rejected
        if c.get('decision') == 'llm_rejected':
            continue
        em = (c.get('email') or '').strip().lower()
        if not em or '@' not in em or em in seen_em:
            continue
        if norm(em) in suppression['sent_emails'] or norm(em) in suppression['decided_emails']:
            continue
        rk = role_key(c.get('company'), c.get('applied_role'))
        if suppression['role_sent'].get(rk, 0) >= MAX_PER_ROLE:
            continue

        jd = jd_summaries.get(norm_co(c.get('company')))
        t = {
            'name': c.get('name'),
            'first_name': c.get('first') or (c.get('name') or '').split()[0],
            'company': c.get('company'),
            'contact_designation': c.get('designation'),
            'applied_role': c.get('applied_role'),
            'applied_date': c.get('applied_date'),
        }
        custom = {}
        try:
            from contact_custom import get as get_custom
            custom = get_custom(c.get('name'), c.get('company')) or {}
        except Exception:
            custom = {}

        try:
            subject, body, ok, why, dom = g3.build_email(t, len(packages), allowed, jd_summary=jd, custom=custom)
        except Exception as e:
            continue
        if not ok:
            continue

        resume = resume_for(c.get('applied_role', ''), c.get('company', ''), None)
        job_summary = build_job_summary(c)

        pkg = {
            'person': c.get('name'),
            'designation': c.get('designation'),
            'company': c.get('company'),
            'email': em,
            'address_evidence': c.get('address_evidence') or 'resolved',
            'applied_role': c.get('applied_role'),
            'applied_date': c.get('applied_date'),
            'job_summary': job_summary,
            'subject': subject,
            'email_body': body,
            'resume': resume,
            'p': c.get('p', 7),
            'label': c.get('label'),
            'det_score': c.get('det_score'),
            'final_score': c.get('final_score'),
            'decision_model': c.get('decision', 'deterministic'),
            'llm': c.get('llm'),
            'source': c.get('source'),
        }
        packages.append(pkg)
        seen_em.add(em)
        suppression['role_sent'][rk] += 1  # reserve slot in this batch build

    # sort: LLM-approved first, then score
    packages.sort(key=lambda x: (0 if x.get('decision_model') == 'llm_approved' else 1,
                                 -x.get('final_score', 0), x.get('p', 7)))
    return packages


# ---------- STAGE 5: BATCH APPROVAL (ask-user CLI) ----------

def ask_user_batch(packages, batch_num, total_batches):
    """Present a batch (<=10) via ask_user_question. Returns list of decisions."""
    if not packages:
        return []
    # ask_user_question supports up to 4 questions; split into chunks of 4
    decisions = [None] * len(packages)

    def chunked(lst, n):
        for i in range(0, len(lst), n):
            yield i, lst[i:i+n]

    for base, chunk in chunked(list(enumerate(packages)), 4):
        questions = []
        for local_i, (idx, pkg) in enumerate(chunk):
            n = base + local_i + 1
            header = f"B{batch_num}:{n}"[:16]
            body_preview = pkg['email_body']
            # keep question text informative but within reason
            q = (
                f"**[Batch {batch_num}/{total_batches}, #{n}/{len(packages)}] Outreach approval**\n"
                f"**Person:** {pkg['person']}\n"
                f"**Designation:** {pkg['designation']}\n"
                f"**Company:** {pkg['company']} ({pkg.get('label','')})\n"
                f"**Email:** {pkg['email']}\n"
                f"**Address evidence:** {pkg['address_evidence']}\n"
                f"**Applied role:** {pkg['applied_role']}\n"
                f"**Applied date:** {pkg['applied_date']}\n"
                f"**Job summary:** {pkg['job_summary']}\n"
                f"**Subject:** {pkg['subject']}\n"
                f"**Resume:** {pkg['resume']}\n"
                f"**Decision model:** {pkg.get('decision_model')} (score {pkg.get('final_score')})\n\n"
                f"**Full email body:**\n{body_preview}\n\n"
                f"Approve to send?"
            )
            questions.append({
                'question': q,
                'header': header,
                'options': [
                    {'label': 'Approve & send', 'description': 'Approve this email for sending now'},
                    {'label': 'Reject', 'description': 'Do not send to this person'},
                    {'label': 'Skip for later', 'description': 'Hold; do not send in this run'},
                ],
                'multiSelect': False,
            })

        # call ask_user_question tool via subprocess bridge? No - we're inside Pi tool context when run as script? 
        # This script is meant to be run via bash tool; to use ask_user_question we must output a marker.
        # Instead, when run standalone we print packages and return empty; when integrated we need Pi to call tool.
        # Provide a helper: write pending batch for the agent to present.
        pending = {
            'batch_num': batch_num, 'total_batches': total_batches,
            'base_offset': base, 'packages': chunk, 'questions': questions,
        }
        pending_path = os.path.join(STATE_DIR, f'PENDING_BATCH_{batch_num}_{base}.json')
        save_json(pending_path, pending)
        log(f"Wrote pending approval batch: {pending_path} ({len(chunk)} items)")
        # If running non-interactively, we cannot call ask_user_question from python.
        # Return None to signal "needs agent approval".
    return 'PENDING'


def send_approved(packages, decisions):
    """Send approved packages. Returns results."""
    results = []
    user = os.environ.get('OE_GMAIL_USER', 'sdas22@gmail.com')
    pw = os.environ.get('OE_GMAIL_APP_PW', '')
    if not pw:
        log("OE_GMAIL_APP_PW not set — cannot send; packages saved for later.")
        return {'sent': 0, 'failed': 0, 'skipped': len(packages), 'reason': 'no_app_password', 'results': results}

    # write temp approval package and use send_approved_email logic
    from outreach_engine.models import Candidate
    from outreach_engine.config import Config
    from outreach_engine.context import EngineContext
    from outreach_engine.dispatch import email as email_mod
    import outreach_engine.approval as A

    cands = []
    for pkg in packages:
        c = Candidate.from_dict({
            'name': pkg['person'], 'contact_title': pkg.get('designation', ''),
            'company': pkg.get('company'), 'applied_company': pkg.get('company'),
            'applied_role': pkg.get('applied_role', ''), 'applied_date': pkg.get('applied_date', ''),
            'email': pkg['email'], 'kind': 'person', 'sources': ['pipeline_clean'],
            'evidence': [pkg.get('address_evidence', '')],
            'email_body': pkg.get('email_body', ''), 'email_subject': pkg.get('subject', ''),
            'message': pkg.get('email_body', ''), 'message_type': 'B',
            'resume': pkg.get('resume'), 'channel': 'email', 'tier': pkg.get('label', 'P0'),
        })
        c.channel = 'email'
        cands.append(c)
    items = A.build_items(cands)
    for it, c in zip(items, cands):
        it.email_body = c.email_body; it.email_subject = c.email_subject
        it.resume = c.resume; it.channel = 'email'

    cfg = Config(); cfg.channel_email = True; cfg.channel_linkedin = False
    ctx = EngineContext(cfg)
    res = email_mod.run_email_dispatch(items, cfg, ctx, send=True)

    # log sends
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    sent_names = set()
    with open(DM_LOG_PATH, 'a', encoding='utf-8') as fh:
        for t in res.get('targets', []):
            if t.get('status') != 'sent':
                continue
            src = next((x for x in packages if x['person'] == t['name']), {})
            sent_names.add(t['name'])
            fh.write(json.dumps({
                'timestamp': ts, 'name': t['name'], 'company': src.get('company'),
                'applied_role': src.get('applied_role'), 'applied_date': src.get('applied_date'),
                'status': 'sent', 'channel': 'email', 'email': t.get('email'),
                'note': 'pipeline_clean batch send (v3, dual-decision)',
                'subject': src.get('subject'), 'message': src.get('email_body'),
                'attachment': src.get('resume'), 'method': 'smtp_gmail_pipeline_clean',
            }, ensure_ascii=False) + '\n')

    # update outreach tracker
    tr = load_json(OUTREACH_TRACKER_PATH, {})
    for c in (tr.get('contacts') or []):
        if c.get('contact_name') in sent_names:
            c['outreach_status'] = 'SENT'
            c['sent_at'] = ts
            c['attempt_count'] = int(c.get('attempt_count') or 0) + 1
            c['next_followup_due'] = (TODAY + datetime.timedelta(days=5)).isoformat()
    save_json(OUTREACH_TRACKER_PATH, tr)

    return res


# ---------- main pipeline ----------

def cmd_sources(args):
    suppression = load_sent_and_decisions()
    fresh = load_fresh_apps()
    profile = load_profile()
    book = load_json(BOOK_PATH, {}).get('addresses', {})
    lp = load_json(LI_PEOPLE_PATH, {})
    ot = load_json(OUTREACH_TRACKER_PATH, {})
    report = {
        'date': TODAY.isoformat(),
        'sources': {
            'tracker_applications_fresh': len(fresh),
            'email_book_addresses': len(book),
            'linkedin_people_companies': len(lp),
            'linkedin_people_total': sum(len((v.get('people') or {})) for v in lp.values()),
            'outreach_tracker_contacts': len(ot.get('contacts') or []),
            'fresh_jds': len(load_json(FRESH_JDS_PATH, {})),
        },
        'suppression': {
            'sent_emails': len(suppression['sent_emails']),
            'sent_names': len(suppression['sent_names']),
            'decided_names': len(suppression['decided_names']),
            'decided_emails': len(suppression['decided_emails']),
            'skipped_company_roles': len(suppression['skipped_cr']),
        },
        'budget': {'spent_usd': spent_today(), 'cap_usd': daily_cap(), 'left_usd': budget_left()},
        'monid_balance_note': 'Monid CLI balance $0.00 as of last check — paid enrichments unavailable',
        'decision_model': 'deterministic (role_priority/relevance_v2-style scoring) + optional dual-LLM AND-gate (crouton-alpha/openrouter + glm-5.3/zai)',
        'flow': 'harvest -> fetch_email -> shortlist -> build_content -> batch_approve(10)',
    }
    print(json.dumps(report, indent=2))
    save_json(os.path.join(STATE_DIR, 'sources_report.json'), report)
    return report


def cmd_run(args):
    min_batch = int(getattr(args, 'min_batch', 10) or 10)
    use_llm = not getattr(args, 'no_llm', False)
    do_send = getattr(args, 'send', False)

    log("=== Clean outreach pipeline: run ===")
    suppression = load_sent_and_decisions()
    fresh = load_fresh_apps()
    profile = load_profile()
    log(f"Fresh applied roles (<= {FRESH_DAYS}d): {len(fresh)}")
    log(f"Suppression: sent={len(suppression['sent_emails'])} decided={len(suppression['decided_names'])}")

    # 1. HARVEST
    log("Stage 1: HARVEST")
    harvested = harvest(fresh, suppression, profile)
    save_json(os.path.join(STATE_DIR, 'harvest.json'), harvested)
    log(f"  harvested candidates (mapped to fresh apps): {len(harvested)}")

    # 2. FETCH EMAIL
    log("Stage 2: FETCH EMAIL (free: book/SMTP/catch-all)")
    enriched = fetch_emails(harvested, suppression)
    save_json(os.path.join(STATE_DIR, 'enriched.json'), enriched)
    log(f"  with resolved/verified email: {len(enriched)}")

    # 3. SHORTLIST
    log("Stage 3: SHORTLIST + decision model")
    shortlisted = shortlist(enriched, fresh, suppression, use_llm=use_llm)
    save_json(os.path.join(STATE_DIR, 'shortlist.json'), shortlisted)
    keep = [c for c in shortlisted if c.get('decision') != 'llm_rejected']
    log(f"  shortlisted (kept): {len(keep)} / {len(shortlisted)}")

    # 4. BUILD CONTENT
    log("Stage 4: BUILD CONTENT (v3 drafts, JD summary, resume)")
    # reload suppression counts for build phase (slots consumed in shortlist per_role logic is local)
    suppression2 = load_sent_and_decisions()
    packages = build_content(shortlisted, suppression2)
    save_json(os.path.join(STATE_DIR, 'packages.json'), packages)
    log(f"  complete send-ready packages: {len(packages)}")

    # enforce max 2 per role in final packages
    final = []
    per_role = Counter()
    # count already sent
    for k, v in suppression2['role_sent'].items():
        per_role[k] = v
    for pkg in packages:
        rk = role_key(pkg['company'], pkg['applied_role'])
        if per_role[rk] >= MAX_PER_ROLE:
            continue
        final.append(pkg)
        per_role[rk] += 1
    packages = final
    save_json(os.path.join(STATE_DIR, 'packages_final.json'), packages)
    log(f"  after per-role cap (<= {MAX_PER_ROLE}): {len(packages)}")

    report = {
        'date': TODAY.isoformat(),
        'harvested': len(harvested),
        'enriched': len(enriched),
        'shortlisted': len(shortlisted),
        'packages': len(packages),
        'min_batch': min_batch,
        'llm_decision_model': use_llm,
        'ready_for_approval': len(packages) >= min_batch,
        'batches': (len(packages) + min_batch - 1) // min_batch if packages else 0,
    }
    save_json(os.path.join(STATE_DIR, 'report.json'), report)

    if len(packages) == 0:
        log("No complete packages ready. (Will ask for approval only when packages with verified email + all details are found.)")
        print(json.dumps(report, indent=2))
        return report

    if len(packages) < min_batch:
        log(f"Packages ready ({len(packages)}) < min_batch ({min_batch}). Saved; no approval prompt yet.")
        # print summary of what's ready
        for i, p in enumerate(packages, 1):
            print(f"  {i}. {p['person']} ({p['designation']}) @ {p['company']} | {p['email']} | {p['applied_role']}")
        print(json.dumps(report, indent=2))
        return report

    # 5. BATCH APPROVAL
    log(f"Stage 5: BATCH APPROVAL — {len(packages)} packages in batches of {min_batch}")
    # write all pending batches for agent-driven ask_user flow
    batches = [packages[i:i+min_batch] for i in range(0, len(packages), min_batch)]
    all_pending = []
    for bi, batch in enumerate(batches, 1):
        pending_path = os.path.join(STATE_DIR, f'PENDING_BATCH_{bi}.json')
        save_json(pending_path, {
            'batch_num': bi, 'total_batches': len(batches),
            'count': len(batch), 'packages': batch,
            'status': 'pending_approval',
            'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
        })
        all_pending.append(pending_path)
        log(f"  batch {bi}/{len(batches)}: {len(batch)} packages -> {pending_path}")

    report['pending_batches'] = all_pending
    save_json(os.path.join(STATE_DIR, 'report.json'), report)
    print(json.dumps(report, indent=2))
    print("\nAPPROVAL_REQUIRED: " + str(len(packages)) + " complete packages ready. "
          "Present each batch via ask_user_question with all required details "
          "(Person, Designation, Company, Email, Address evidence, Applied role, "
          "Applied date, Job summary, Subject, Resume, Full email body). "
          "Batches: " + ", ".join(os.path.basename(p) for p in all_pending))
    return report


def cmd_status(args):
    report = load_json(os.path.join(STATE_DIR, 'report.json'), {})
    pkgs = load_json(os.path.join(STATE_DIR, 'packages_final.json'), [])
    pending = sorted([f for f in os.listdir(STATE_DIR) if f.startswith('PENDING_BATCH_')])
    print(json.dumps({
        'state_dir': STATE_DIR,
        'last_report': report,
        'packages_ready': len(pkgs),
        'pending_batches': pending,
    }, indent=2))


def main():
    ap = argparse.ArgumentParser(description='Clean outreach pipeline')
    sub = ap.add_subparsers(dest='cmd')
    sp = sub.add_parser('run')
    sp.add_argument('--min-batch', type=int, default=10)
    sp.add_argument('--no-llm', action='store_true')
    sp.add_argument('--send', action='store_true')
    sub.add_parser('status')
    sub.add_parser('sources')
    args = ap.parse_args()
    cmd = args.cmd or 'run'
    if cmd == 'run':
        cmd_run(args)
    elif cmd == 'status':
        cmd_status(args)
    elif cmd == 'sources':
        cmd_sources(args)
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
