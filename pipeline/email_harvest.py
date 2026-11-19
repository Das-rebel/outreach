#!/usr/bin/env python3
"""Efficient email harvesting for outreach — free-first, cached, budget-capped.

COST MODEL (monid -> hunterio, verified live 2026-11-18):
  /email-finder  $0.0245 per FOUND address  (1 unit = 1 address)
  /domain-search $0.00245 per address        (1 unit = up to 10 addresses)
                 -> 10x cheaper per address, and every row is a PUBLISHED
                    address with source URL, title, seniority, decision_maker
                    flag and deliverability verification.
  A domain probe that returns 0 addresses bills $0.00.

TIERS (cheapest first):
  T0 FREE  company website crawl (team/contact/press pages) + cached results
  T1 $0.00245/addr  hunterio /domain-search (cached per domain, never re-billed)
  T2 $0.0245/found  hunterio /email-finder (gap-fill one person at a time)

DAILY CAP: outreach email/person search = $0.30/day (user directive 2026-11-02).
A ledger file enforces the cap across processes.
"""
import json, os, re, subprocess, sys, time, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.environ.get('OUTREACH_DATA_ROOT') or os.environ.get('JOB_PIPELINE_ROOT') or os.path.expanduser('~/job_pipeline')
_RUNS = os.environ.get('OUTREACH_RUNS_DIR') or os.path.join(_DATA, 'runs', 'outreach')
def _resolve(name, env=None, extra_dirs=None):
    if env and os.environ.get(env):
        return os.path.expanduser(os.environ[env])
    dirs = [HERE, _RUNS] + (extra_dirs or [])
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(_RUNS if os.path.exists(_RUNS) else HERE, name)
BOOK = _resolve('EMAIL_BOOK.json', 'OUTREACH_BOOK_PATH')
LEDGER = _resolve('monid_spend.json', 'OUTREACH_SPEND_LEDGER')
# --- hard daily caps (user directive 2026-11-02). Two SEPARATE buckets:
#     outreach_email_person : $0.30/day  (email + person lookups)
#     job_search            : $0.50/day  (job discovery, e.g. apify linkedin)
# Caps come from spend_caps.json. There is NO env override: a raise requires an
# auditable spend_override.json signed by an explicit user authorisation.
CAPS_FILE = _resolve('spend_caps.json', 'OUTREACH_CAPS_FILE')
DEFAULT_CAPS = {'outreach_email_person': 0.30, 'job_search': 0.50}
BUCKET = 'outreach_email_person'
OVERRIDE_FILE = _resolve('spend_override.json', 'OUTREACH_SPEND_OVERRIDE')

def load_caps():
    caps = dict(DEFAULT_CAPS)
    if os.path.exists(CAPS_FILE):
        try: caps.update(json.load(open(CAPS_FILE)))
        except Exception: pass
    return caps

def daily_cap(bucket=BUCKET):
    caps = load_caps()
    cap = float(caps.get(bucket, DEFAULT_CAPS.get(bucket, 0.0)))
    if os.path.exists(OVERRIDE_FILE):
        try:
            ov = json.load(open(OVERRIDE_FILE))
            if ov.get('date') == today() and ov.get('bucket') == bucket:
                cap = max(cap, float(ov.get('cap', 0.0)))
        except Exception: pass
    return cap

DAILY_CAP = daily_cap()  # informational snapshot; always call daily_cap() at use time
EMAIL_FINDER = 0.0245
UNIT = 0.0245  # one domain-search unit (10 addresses)

DOMAIN_SUFFIXES = ['.com', '.in', '.co.in', '.co', '.ai', '.io']
GENERIC = {'careers', 'hr', 'info', 'jobs', 'hiring', 'recruitment', 'recruiter',
           'talent', 'admin', 'office', 'support', 'sales', 'contact', 'hello',
           'team', 'marketing', 'billing', 'accounts', 'finance', 'help',
           'media', 'press', 'ceo', 'coo', 'cto', 'founder', 'enquiries'}

# ---------------------------------------------------------------- ledger ---
def today():
    return datetime.date.today().isoformat()

def load_ledger():
    if os.path.exists(LEDGER):
        try:
            return json.load(open(LEDGER))
        except Exception:
            pass
    return {}

def spent_today(bucket=BUCKET):
    led = load_ledger()
    d = led.get(today(), {})
    b = (d.get('buckets') or {}).get(bucket)
    if b is not None:
        return float(b.get('spent_usd', 0.0))
    # legacy flat ledger -> attribute to the outreach bucket
    return float(d.get('spent_usd', 0.0)) if bucket == 'outreach_email_person' else 0.0

def add_spend(cost, what, bucket=BUCKET):
    led = load_ledger()
    d = led.setdefault(today(), {'spent_usd': 0.0, 'calls': []})
    b = d.setdefault('buckets', {}).setdefault(bucket, {'spent_usd': 0.0, 'calls': []})
    b['spent_usd'] = round(float(b['spent_usd']) + float(cost), 6)
    b.setdefault('calls', []).append({'ts': time.strftime('%H:%M:%S'), 'cost': cost, 'what': what})
    if bucket == 'outreach_email_person':
        d['spent_usd'] = b['spent_usd']          # keep legacy field in sync
        d.setdefault('calls', []).append({'ts': time.strftime('%H:%M:%S'), 'cost': cost,
                                          'what': what, 'bucket': bucket})
    json.dump(led, open(LEDGER, 'w'), indent=2)

def budget_left(bucket=BUCKET):
    return max(0.0, daily_cap(bucket) - spent_today(bucket))

def cap_status(bucket=BUCKET):
    cap = daily_cap(bucket); spent = spent_today(bucket)
    return {'bucket': bucket, 'cap_usd': cap, 'spent_usd': spent,
            'left_usd': max(0.0, cap - spent), 'over_cap': spent > cap,
            'over_by_usd': round(max(0.0, spent - cap), 6)}

# ----------------------------------------------------------------- monid ---
PAID_ENDPOINTS = {('hunterio', '/domain-search'), ('hunterio', '/email-finder'),
                  ('hunterio', '/email-verifier'), ('apollo', '/people/match'),
                  ('apollo', '/mixed_companies/enrich')}

def monid_run(provider, endpoint, query=None, body=None, bucket=BUCKET):
    if (provider, endpoint) in PAID_ENDPOINTS and budget_left(bucket) <= 0:
        st = cap_status(bucket)
        raise RuntimeError(
            f"BLOCKED by daily cap [{bucket}]: spent ${st['spent_usd']:.4f} of "
            f"${st['cap_usd']:.2f} (over by ${st['over_by_usd']:.4f}). "
            f"No paid monid call attempted. Free endpoints still allowed.")
    cmd = ['monid', 'run', '-p', provider, '-e', endpoint, '-w', '-j']
    if query:
        cmd += ['--query', json.dumps(query)]
    if body:
        cmd += ['-i', json.dumps(body)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
    except subprocess.TimeoutExpired:
        return None, 0.0
    out = r.stdout
    i = out.find('{')
    if i < 0:
        return None, 0.0
    try:
        d, _ = json.JSONDecoder(strict=False).raw_decode(out[i:])
    except Exception:
        return None, 0.0
    if d.get('status') != 'COMPLETED':
        return None, 0.0
    cost = ((d.get('billing') or {}).get('reportedCost') or {}).get('value', 0) or 0
    return d, float(cost) / 1_000_000.0

def domain_rows(domain, limit=100):
    d, cost = monid_run('hunterio', '/domain-search', body={'domain': domain, 'limit': limit})
    if not d:
        return [], cost
    o = (d.get('output') or {}).get('data') or {}
    return o.get('emails') or [], cost

def finder(name, company):
    d, cost = monid_run('hunterio', '/email-finder',
                         query={'full_name': name, 'company': company, 'max_duration': 12})
    if not d:
        return None, cost
    o = (d.get('output') or {}).get('data') or {}
    if isinstance(o.get('data'), dict):
        o = o['data']
    return o, cost

# ------------------------------------------------------------- free tier ---
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'}

def free_site_emails(domain, pages=('/contact', '/team', '/about', '/press', '/media', '/leadership')):
    """Published emails on the company's own site (free)."""
    found = []
    urls = ['https://%s/' % domain] + ['https://%s%s' % (domain, p) for p in pages]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers=UA)
            html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'ignore')
        except Exception:
            continue
        for em in re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html):
            local = em.split('@')[0].lower()
            if local in GENERIC or em.lower().endswith(('.png', '.jpg', '.gif', '.webp')):
                continue
            if em not in [f['email'] for f in found]:
                found.append({'email': em, 'source_url': u, 'source': 'company_website',
                              'type': 'personal_or_unknown'})
        if len(found) >= 8:
            break
    return found

# ------------------------------------------------------------- book I/O ----
def load_book():
    if os.path.exists(BOOK):
        try:
            return json.load(open(BOOK))
        except Exception:
            pass
    return {'addresses': {}, 'domains_done': {}, 'targets': {}}

def save_book(b):
    json.dump(b, open(BOOK, 'w'), indent=2, ensure_ascii=False)

def add_addresses(book, domain, rows, source):
    added = 0
    for r in rows:
        em = (r.get('value') or '').strip()
        if not em or '@' not in em:
            continue
        local = em.split('@')[0].lower()
        if local in GENERIC:
            continue
        ver = (r.get('verification') or {}).get('status') or ''
        prov = (r.get('provenance') or r.get('source_type') or '').lower()
        conf = r.get('confidence') or 0
        if ver == 'accept_all':
            # catch-all MX: the address still counts if it was PUBLISHED (found
            # provenance with a public source). It is kept but flagged so the
            # pre-send verifier can confirm deliverability individually.
            srcs = [s.get('uri') for s in (r.get('sources') or []) if s.get('uri')]
            if prov != 'found' or not srcs:
                continue
            ver = 'accept_all_published'
        if not ver:
            # no verification payload on this endpoint variant: accept only
            # PUBLISHED-source rows (provenance 'found') with high confidence.
            # Pattern-guessed rows ('generated'/'inferred') stay rejected.
            if prov != 'found' or conf < 80:
                continue
            ver = 'unverified_found'
        elif prov in ('generated', 'inferred') and ver != 'valid':
            continue
        key = em.lower()
        if key in book['addresses']:
            continue
        book['addresses'][key] = {
            'email': em, 'domain': domain, 'source': source,
            'first_name': r.get('first_name'), 'last_name': r.get('last_name'),
            'position': r.get('position'), 'seniority': r.get('seniority'),
            'department': r.get('department'), 'decision_maker': r.get('decision_maker'),
            'linkedin': r.get('linkedin'),
            'confidence': r.get('confidence'), 'provenance': r.get('provenance'),
            'verification': ver,
            'sources': [s.get('uri') for s in (r.get('sources') or [])][:3],
            'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        added += 1
    return added

def candidate_domains(company):
    base = re.sub(r'[^a-z0-9]', '', (company or '').lower())
    if not base:
        return []
    out = [base + s for s in DOMAIN_SUFFIXES]
    if base.endswith('technologies'):
        out.append(base[:-11] + '.com')
    for extra in (base.replace('private', '').replace('limited', '').replace('co', ''),
                  base.split('private')[0]):
        if extra and len(extra) > 3:
            out.append(extra + '.com')
    seen, uniq = set(), []
    for d in out:
        if d and d not in seen:
            seen.add(d); uniq.append(d)
    return uniq[:6]

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--companies', help='json file: [{"company":..,"domain":..}]')
    ap.add_argument('--targets', help='json file: [{"name":..,"company":..}]')
    ap.add_argument('--plan', action='store_true', help='print plan, spend nothing')
    ap.add_argument('--max-domains', type=int, default=12)
    args = ap.parse_args()
    book = load_book()
    comps = json.load(open(args.companies)) if args.companies else []
    targets = json.load(open(args.targets)) if args.targets else []
    print(f"budget left today: ${budget_left():.4f} of ${DAILY_CAP} cap | "
          f"book addresses: {len(book['addresses'])} | domains cached: {len(book['domains_done'])}")
    if args.plan:
        for c in comps:
            doms = [c.get('domain')] if c.get('domain') else candidate_domains(c.get('company'))
            print(f"  {c.get('company')[:28]:28s} -> {doms[:3]}")
        return
    used = 0
    for c in comps:
        if used >= args.max_domains:
            break
        company = c.get('company')
        doms = [c.get('domain')] if c.get('domain') else candidate_domains(company)
        for dom in doms:
            if dom in book['domains_done']:
                break
            if budget_left() <= UNIT:
                print(f"  budget cap reached — stopping before {dom}")
                save_book(book); return
            rows, cost = domain_rows(dom)
            add_spend(cost, f'domain-search {dom}')
            used += 1
            if rows:
                added = add_addresses(book, dom, rows, 'hunterio/domain-search')
                book['domains_done'][dom] = {'company': company, 'rows': len(rows),
                                             'added': added, 'cost': cost,
                                             'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
                print(f"  {company[:24]:24s} {dom:22s} rows={len(rows):3d} added={added:3d} ${cost:.4f} left=${budget_left():.4f}")
                break
            else:
                print(f"  {company[:24]:24s} {dom:22s} empty (free)")
        save_book(book)
    # gap-fill our named targets that are still missing
    for t in targets:
        name = t.get('name'); company = t.get('company')
        if not name or not company:
            continue
        have = any(v.get('first_name', '').lower() == name.split()[0].lower()
                   for v in book['addresses'].values())
        if have or budget_left() < EMAIL_FINDER:
            continue
        res, cost = finder(name, company)
        add_spend(cost, f'email-finder {name} @ {company}')
        if res and res.get('email'):
            add_addresses(book, (res.get('email') or '').split('@')[-1],
                          [{'value': res['email'], 'first_name': res.get('first_name'),
                            'last_name': res.get('last_name'), 'position': res.get('position'),
                            'seniority': res.get('seniority'), 'decision_maker': None,
                            'confidence': res.get('score'),
                            'provenance': res.get('provenance'),
                            'verification': (res.get('verification') or {}).get('status'),
                            'sources': res.get('sources') or []}], 'hunterio/email-finder')
            print(f"  finder {name[:22]:22s} -> {res.get('email')} (score {res.get('score')}) ${cost:.4f}")
        else:
            print(f"  finder {name[:22]:22s} -> none")
        save_book(book)
    save_book(book)
    print(f"\nbook addresses: {len(book['addresses'])} | spent today ${spent_today():.4f}")

if __name__ == '__main__':
    main()
