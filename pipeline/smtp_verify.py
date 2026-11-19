#!/usr/bin/env python3
"""FREE deliverability verification by direct SMTP probe against the domain MX.

No paid endpoint: resolve MX, open a session, MAIL FROM:<> + RCPT TO:<addr> and
read the reply code.  250 => mailbox exists, 550/551/553 => does not exist,
252 / 4xx => inconclusive, and a random-address control detects catch-all MX.

Used to (a) upgrade published-but-unverified addresses in EMAIL_BOOK and
(b) test firstname.lastname@domain candidates for target companies, so only
deliverable addresses are ever emailed.
"""
import json, os, random, socket, string, sys, time
from concurrent.futures import ThreadPoolExecutor

def mx_records(domain):
    import subprocess
    try:
        out = subprocess.run(['dig', '+short', 'MX', domain], capture_output=True,
                             text=True, timeout=12).stdout.strip()
    except Exception:
        return []
    recs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            recs.append((int(parts[0]), parts[1].rstrip('.')))
    return [h for _, h in sorted(recs)] or [domain]

def probe(domain, address, timeout=12):
    """Return (status, code) from the RCPT TO reply."""
    hosts = mx_records(domain)
    for host in hosts[:3]:
        try:
            s = socket.create_connection((host, 25), timeout=timeout)
        except Exception:
            continue
        try:
            s.settimeout(timeout)
            def rd():
                """Read a (possibly multi-line) SMTP reply; return the final code."""
                last = ''
                while True:
                    try:
                        line = s.recv(512).decode(errors='ignore')
                    except Exception:
                        break
                    if not line:
                        break
                    last = line.strip()
                    if len(line) < 4 or line[3] != '-':
                        break
                return last
            rd()                                   # banner
            for cmd in ('EHLO verifier.local', 'MAIL FROM:<verify@verifier.local>'):
                s.sendall((cmd + '\r\n').encode()); rd()
            s.sendall(f'RCPT TO:<{address}>\r\n'.encode())
            resp = rd()
            try:
                s.sendall(b'QUIT\r\n')
            except Exception:
                pass
            s.close()
            code = resp.split()[0] if resp.split() else ''
            if code.startswith('250'):
                return ('valid', code)
            if code.startswith('55'):
                return ('invalid', code)
            if code.startswith('252'):
                return ('catch_all', code)
            if code.startswith('45') or code.startswith('42') or code.startswith('4'):
                return ('inconclusive', code)
            return ('inconclusive', code)
        except Exception:
            try: s.close()
            except Exception: pass
            continue
    return ('unreachable', '')

def is_catch_all(domain, timeout=12):
    """Control probe with a random mailbox."""
    rnd = ''.join(random.choice(string.ascii_lowercase) for _ in range(14))
    st, code = probe(domain, f'{rnd}@' + domain, timeout)
    return st in ('valid', 'catch_all')

def verify(address, timeout=12):
    dom = address.split('@')[-1].lower()
    st, code = probe(dom, address, timeout)
    if st == 'valid':
        # confirm it is not a catch-all MX (which accepts every address)
        if is_catch_all(dom, timeout):
            return ('catch_all_mx', code)
        return ('valid', code)
    return (st, code)

def bulk(addresses, workers=6, timeout=12):
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for a, (st, code) in zip(addresses, ex.map(lambda x: verify(x, timeout), addresses)):
            out[a] = {'status': st, 'code': code}
    return out

if __name__ == '__main__':
    addrs = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else []
    if isinstance(addrs, dict): addrs = list(addrs)
    res = bulk(addrs)
    for a, r in sorted(res.items(), key=lambda kv: kv[1]['status']):
        print(f"  {r['status']:14s} {r['code']:5s} {a}")
    json.dump(res, open('smtp_verify_result.json', 'w'), indent=1)
