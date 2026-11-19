#!/usr/bin/env python3
"""Shared daily-cap guard for every paid monid call site.

Buckets (user directive 2026-11-02):
  outreach_email_person : $0.30/day
  job_search            : $0.50/day

Usage:
    from spend_guard import check, record, status
    check('outreach_email_person', 'hunterio /domain-search stashfin.com')
    ... run monid ...
    record('outreach_email_person', cost_usd, 'hunterio /domain-search stashfin.com')
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CAPS_FILE = os.path.join(HERE, 'spend_caps.json')
DEFAULT_CAPS = {'outreach_email_person': 0.30, 'job_search': 0.50}
OVERRIDE_FILE = os.path.join(HERE, 'spend_override.json')
LEDGER = os.path.join(HERE, 'monid_spend.json')

def today():
    return time.strftime('%Y-%m-%d')

def load_caps():
    caps = dict(DEFAULT_CAPS)
    if os.path.exists(CAPS_FILE):
        try: caps.update(json.load(open(CAPS_FILE)))
        except Exception: pass
    return caps

def load_ledger():
    if os.path.exists(LEDGER):
        try: return json.load(open(LEDGER))
        except Exception: return {}
    return {}

def daily_cap(bucket):
    cap = float(load_caps().get(bucket, DEFAULT_CAPS.get(bucket, 0.0)))
    if os.path.exists(OVERRIDE_FILE):
        try:
            ov = json.load(open(OVERRIDE_FILE))
            if ov.get('date') == today() and ov.get('bucket') == bucket:
                cap = max(cap, float(ov.get('cap', 0.0)))
        except Exception: pass
    return cap

def spent_today(bucket):
    d = load_ledger().get(today(), {})
    b = (d.get('buckets') or {}).get(bucket)
    if b is not None: return float(b.get('spent_usd', 0.0))
    return float(d.get('spent_usd', 0.0)) if bucket == 'outreach_email_person' else 0.0

def budget_left(bucket):
    return max(0.0, daily_cap(bucket) - spent_today(bucket))

def status(bucket='outreach_email_person'):
    cap = daily_cap(bucket); spent = spent_today(bucket)
    return {'bucket': bucket, 'cap_usd': cap, 'spent_usd': spent,
            'left_usd': max(0.0, cap - spent), 'over_cap': spent > cap,
            'over_by_usd': round(max(0.0, spent - cap), 6)}

def check(bucket, what, est=0.0):
    """Raise BEFORE spending if the bucket cannot cover this call."""
    left = budget_left(bucket)
    if left <= 0 or (est and est > left):
        st = status(bucket)
        raise RuntimeError(
            f"BLOCKED by daily cap [{bucket}] before calling monid: "
            f"spent ${st['spent_usd']:.4f} of ${st['cap_usd']:.2f} "
            f"(over by ${st['over_by_usd']:.4f}). Refused: {what}. "
            f"Free endpoints (apollo people search, hunterio domain-finder) still allowed.")
    return left

def record(bucket, cost, what):
    led = load_ledger()
    d = led.setdefault(today(), {'spent_usd': 0.0, 'calls': []})
    b = d.setdefault('buckets', {}).setdefault(bucket, {'spent_usd': 0.0, 'calls': []})
    b['spent_usd'] = round(float(b['spent_usd']) + float(cost), 6)
    b.setdefault('calls', []).append({'ts': time.strftime('%H:%M:%S'), 'cost': cost, 'what': what})
    if bucket == 'outreach_email_person':
        d['spent_usd'] = b['spent_usd']
        d.setdefault('calls', []).append({'ts': time.strftime('%H:%M:%S'), 'cost': cost,
                                         'what': what, 'bucket': bucket})
    json.dump(led, open(LEDGER, 'w'), indent=2)

if __name__ == '__main__':
    for b in DEFAULT_CAPS:
        print(json.dumps(status(b)))
