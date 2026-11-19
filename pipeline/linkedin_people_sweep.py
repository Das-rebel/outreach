#!/usr/bin/env python3
"""$0 name sweep via LinkedIn's own people search (logged-in CDP session).

For each target company we read the people-search result cards and keep the
senior growth / marketing / brand / product leaders whose headline names the
company.  Output feeds the address resolver (pattern + SMTP verification).
"""
import asyncio, json, os, re, sys, urllib.parse
from playwright.async_api import async_playwright

MKT = re.compile(r'\b(marketing|growth|demand|brand|performance|communications?|gtm|digital|revenue|product|alliances?|partnerships?|business development|customer|merchant)\b', re.I)
SEN = re.compile(r'\b(head|director|vp|vice president|avp|chief|cmo|cgo|cpo|president|officer|lead|leading)\b', re.I)
BAD = re.compile(r'\b(founder|co-founder|intern|recruit|talent acquisition|analyst|associate\b|consultant|executive assistant|intern|campus)\b', re.I)

CARDS_JS = """() => {
  const out=[]; const seen=new Set();
  for (const a of document.querySelectorAll('a[href*="/in/"]')) {
    const href=(a.getAttribute('href')||'');
    if(!href) continue;
    const slug=(href.split('/in/')[1]||'').split('?')[0].split('/')[0];
    if(!slug||seen.has(slug)) continue; seen.add(slug);
    out.push({slug, text:(a.innerText||'').trim().slice(0,240)});
  }
  return out.slice(0,60);
}"""


async def people_for(page, company, limit=12):
    q = urllib.parse.quote(company)
    try:
        await page.goto(f'https://www.linkedin.com/search/results/people/?keywords={q}',
                        timeout=45000, wait_until='domcontentloaded')
    except Exception:
        return {}, 'nav-fail'
    cards = []
    for _ in range(10):
        await page.wait_for_timeout(1500)
        try:
            cards = await page.evaluate(CARDS_JS)
        except Exception:
            cards = []
        if cards:
            break
    if not cards:
        return {}, 'no-cards'
    txt = ''
    try:
        txt = await page.evaluate("document.body.innerText")
    except Exception:
        pass
    if 'sign in' in txt[:150].lower() and len(txt) < 600:
        return {}, 'login-wall'
    words = [w for w in re.split(r'[^a-z]+', company.lower()) if len(w) > 3]
    people = {}
    for c in cards:
        t = c['text'].strip()
        if not t or len(t) < 8:
            continue
        first = t.split('\n')[0].strip()
        if not first or len(first) > 38 or first.lower() == 'linkedin':
            continue
        if not MKT.search(t) or not SEN.search(t) or BAD.search(t):
            continue
        if words and not any(w in t.lower() for w in words):
            continue
        people.setdefault(first, t.replace('\n', ' | ')[:170])
        if len(people) >= limit:
            break
    return people, 'ok'


async def run(targets):
    out = {}
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp('http://127.0.0.1:9334')
        ctx = b.contexts[0]
        page = await ctx.new_page()
        try:
            for t in targets:
                people, st = await people_for(page, t['company'])
                if not people and st in ('nav-fail', 'no-cards'):
                    try:
                        await page.close()
                    except Exception:
                        pass
                    page = await ctx.new_page()
                out[t['company']] = {'company': t['company'], 'people': people, 'status': st}
                print(f"  {t['company'][:26]:26s} -> {len(people):2d} candidates ({st})", flush=True)
                for n, c in list(people.items())[:5]:
                    print(f"      {n[:26]:26s} {c[:96]}")
                await asyncio.sleep(2.0)
        finally:
            try:
                await page.close()
            except Exception:
                pass
    json.dump(out, open('LINKEDIN_PEOPLE.json', 'w'), indent=1, ensure_ascii=False)
    return out


if __name__ == '__main__':
    asyncio.run(run(json.load(open(sys.argv[1]))))
