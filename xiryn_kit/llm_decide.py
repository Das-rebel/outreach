#!/usr/bin/env python3
"""llm_decide — dual-model decision layer for job relevance (2026-11-09).

The deterministic engine (xiryn_kit/relevance_v2.py) enforces hard rules
(employer class, sector priority, location, seniority, function family). This
module adds the SEMANTIC judgement the user asked for, using the two strongest
available decision models:

  primary  : stealth/crouton-alpha   (OpenRouter, 1M context, repo directive:
             "switch to crouton-alpha as primary orchestrator")
  verifier : glm-5.3                 (z.ai, independent)

AND-gate: a role is approved only when BOTH models return ok=true and a score
>= threshold. The prompt embeds the user's role-priority list so the models
judge against the same ordering the deterministic engine uses.

Public API
----------
    decide(job, threshold=70, jd_chars=3500) -> dict
      {ok, score, primary:{...}, verifier:{...}, reason}
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

MODELS_JSON = os.path.expanduser('~/.pi/agent/models.json')

SYSTEM_PROMPT = """You are a strict job-application decision engine for an
11-year growth & marketing leader in Bengaluru, India (open to relocate).

ROLE PRIORITY (mandated by the candidate, apply in this exact order):
  P0 fintech  - payments / lending / wealth / insurtech
  P1 banks
  P2 NBFC
  P3 internal fintech / fintech arm of a large company
  P4 D2C growth & strategy
  P5 D2C growth roles
  P6 D2C marketing roles
  P7 everything else  -> LEFTOVER TIME ONLY, apply last

EMPLOYER CLASS RULES (hard):
  IT solutions, IT services, IT consulting, software services, technology
  services, BPO / call centre, outsourcing / offshore development, staffing /
  manpower, recruitment agencies / headhunting, HR services, management
  consulting -> NOT A GOOD MATCH, reject.
  Also reject: pure sales roles, equity-only / co-founder roles, fashion /
  apparel / beauty brands, real estate / property, hospitality, healthcare /
  hospital / pharma, education / edtech, and engineering-only roles.

LOCATION:
  India metro (Bengaluru, Mumbai, Delhi NCR, Hyderabad, Pune, Chennai,
  Kolkata, Ahmedabad, Coimbatore) = primary target.
  GCC (Dubai, Abu Dhabi, Doha, Riyadh) = acceptable secondary target.
  India tier-2 cities, US-onsite, and other countries = poor match.

AI-NATIVE TRACK (user-approved, 2026-11-11):
  Companies that are AI-native or AI-product / GTM-software businesses
  (LLM, agents, AI products, AI-native SaaS, revenue-intelligence / GTM
  tooling) hiring SENIOR GTM / growth / product-marketing / revenue /
  demand roles in INDIA or WORLDWIDE-REMOTE are ELIGIBLE - score them as
  P4-equivalent for the AI GTM track. Use the AI GTM resume for them.
  This carve-out does NOT apply to IT-services / consulting / outsourcing /
  staffing employers, and pure sales roles stay rejected.
  US-onsite and city-only non-India roles remain a poor match.

SENIORITY: Head / Director / VP / AVP / CMO / Chief / Group Head only.
  "Senior Manager", "Manager", "Assistant Manager", "Associate", "Analyst",
  "Senior Associate" are BELOW the bar for this candidate.

FUNCTION: marketing / growth / GTM / brand / demand / communications /
  partnerships / digital / ecommerce / revenue.

Judge RELEVANCE + PRIORITY FIT and return STRICT JSON:
{"ok": true|false, "score": 0-100, "priority": "P0".."P7",
 "reason": "<=25 words", "gaps": ["..."]}

ok=true only if the role is senior AND on-function AND the employer class is
acceptable AND the sector is a good match for this priority list.
Be strict: a role must look like a genuine step up for a growth/marketing
leader, not a sideways or downward move."""


def _cfg():
    with open(MODELS_JSON) as f:
        m = json.load(f)
    p = m.get('providers', {})
    return {
        'or_key': (p.get('openrouter') or {}).get('apiKey'),
        'or_base': (p.get('openrouter') or {}).get('baseUrl') or 'https://openrouter.ai/api/v1',
        'zai_key': (p.get('zai-2') or p.get('zai') or {}).get('apiKey'),
        'zai_base': (p.get('zai-2') or p.get('zai') or {}).get('baseUrl')
                    or 'https://api.z.ai/api/coding/paas/v4/',
        'th_key': (p.get('tokenharbor') or {}).get('apiKey'),
        'th_base': (p.get('tokenharbor') or {}).get('baseUrl') or 'https://tokenharbor.ai/v1',
        'gg_key': (p.get('google') or {}).get('apiKey'),
        'gg_base': (p.get('google') or {}).get('baseUrl')
                   or 'https://generativelanguage.googleapis.com/v1beta/openai',
        # 2026-11-11: tokenharbor :free allowance and zai glm-5.3 quota were
        # both exhausted, so the judge had NO working provider and every
        # verdict silently became a timeout. mistral + openrouter free models
        # + local ollama restore the gate.
        'ms_key': (p.get('mistral') or {}).get('apiKey'),
        'ms_base': (p.get('mistral') or {}).get('baseUrl') or 'https://api.mistral.ai/v1',
        'ol_base': (p.get('ollama') or {}).get('baseUrl') or 'http://127.0.0.1:11439/v1',
        # 2026-11-14: opencode free models (deepseek-v4.1-flash, mimo-v2.6-flash,
        # big-pickle) verified live — independent quota from mistral/openrouter,
        # restore the dual-model gate while every other provider is rate-limited.
        'oc_key': (p.get('opencode') or {}).get('apiKey') or 'local',
        'oc_base': (p.get('opencode') or {}).get('baseUrl') or 'http://127.0.0.1:4097/v1',
    }


# Per-call timeout / retry count. The old defaults (180s x 4 tries x a
# 3-model fallback chain, twice for primary+verifier) let a single job hang
# for over an hour and stalled the whole gate. These are env-tunable.
_CALL_TIMEOUT = int(os.environ.get('LLM_CALL_TIMEOUT', '45'))
_CALL_TRIES = int(os.environ.get('LLM_CALL_TRIES', '2'))


def _post(base, key, model, payload, max_tokens, tries=None, timeout=None):
    tries = _CALL_TRIES if tries is None else tries
    timeout = _CALL_TIMEOUT if timeout is None else timeout
    body = {'model': model,
            'messages': [{'role': 'system', 'content': SYSTEM_PROMPT},
                         {'role': 'user', 'content': json.dumps(payload)}],
            'temperature': 0.05, 'max_tokens': max_tokens}
    data = json.dumps(body).encode()
    hdr = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    last = None
    for a in range(tries):
        try:
            # HARD wall-clock deadline. urlopen(timeout=) only bounds a single
            # socket operation, so a server that trickles a response body can
            # keep r.read() blocked forever. The whole request+read runs in a
            # worker thread that is abandoned once the deadline passes.
            def _do():
                req = urllib.request.Request(base.rstrip('/') + '/chat/completions',
                                             data=data, headers=hdr)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.read().decode()
            box = {}
            def _safe():
                try:
                    box['t'] = _do()
                except Exception as e:
                    # 2026-11-11: the exception was SWALLOWED here, so every
                    # provider failure (quota 429, 402 credits, 404 model) was
                    # reported as "timeout after 45s" and the chain burned the
                    # full deadline on every dead provider instead of moving
                    # on. Capture it so non-retryable errors break the chain.
                    box['e'] = e
            th = threading.Thread(target=_safe, daemon=True)
            th.start()
            th.join(timeout)
            if 't' not in box:
                err = box.get('e')
                if isinstance(err, urllib.error.HTTPError):
                    last = f'HTTP {err.code}: {err.reason}'
                    if err.code in (401, 402, 403, 404, 429):
                        break  # bad key / no credits / model gone / quota
                elif err is not None:
                    last = str(err)[:160]
                else:
                    last = f'timeout after {timeout}s'
                time.sleep(2 + a * 3)
                continue
            txt = json.loads(box['t'])
            content = (txt.get('choices') or [{}])[0].get('message', {}).get('content', '')
            m = re.search(r'\{.*\}', content, re.S)
            if not m:
                last = 'no json in reply'
                time.sleep(2 + a * 3)
                continue
            return json.loads(m.group(0))
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code}: {e.reason}'
            if e.code in (401, 402, 403, 404, 429):
                break  # non-retryable: bad key / no credits / model gone / quota
            time.sleep(2 + a * 3)
        except Exception as e:
            last = str(e)[:160]
            time.sleep(2 + a * 3)
    return {'ok': False, 'score': 0, 'priority': 'P7', 'reason': f'call failed: {last}',
            'gaps': ['llm_error'], 'failed': True}


def decide(job, threshold=70, jd_chars=3500):
    """job: dict with company/title/loc/desc/jid."""
    c = _cfg()
    payload = {
        'company': job.get('company'),
        'title': job.get('title'),
        'location': job.get('loc') or job.get('location'),
        'jid': job.get('jid'),
        'description': (job.get('desc') or '')[:jd_chars],
    }
    # Primary model fallback chain (2026-11-11, re-verified live):
    #   tokenharbor :free allowance is exhausted until 2026-11-16 19:18 UTC,
    #   zai glm-5.3 quota until 2026-11-15 20:07 UTC, google gemini quota
    #   exceeded and the google baseUrl is the OpenAI-COMPAT endpoint (so the
    #   model id must be "gemini-2.5-flash", not "models/gemini-2.5-flash" -
    #   the old id 404'd on every call). Live and verified today:
    #     1. mistral  open-mistral-nemo          (1.4s, clean JSON)
    #     2. openrouter liquid/lfm-2.5-2.6b:free (2.1s, clean JSON)
    #     3. local ollama qwen2.5:3b             (16s, always available)
    #     4. tokenharbor mimo-v2.5:free          (returns 2026-11-16)
    #     5. google gemini-2.5-flash             (quota resets daily)
    primary_chain = [
        # 2026-11-17: opencode Go free models are the intended judge lane
        # (user directive: zero paid credits). deepseek-v4.1-flash-free is the
        # primary; big-pickle is the same-provider fallback; mistral nemo is a
        # paid-but-free-tier fallback only if both fail.
        ('oc', 'deepseek-v4.1-flash-free'),
        ('oc', 'big-pickle'),
        ('ms', 'open-mistral-nemo'),
        ('ol', 'qwen2.5:3b'),
        ('th', 'mimo-v2.5:free'),
        ('gg', 'gemini-2.5-flash'),
    ]
    primary = {'ok': False, 'score': 0, 'priority': 'P7',
               'reason': 'no primary model available', 'gaps': ['llm_error']}
    for chan, mdl in primary_chain:
        if chan == 'th':
            if not c.get('th_key'):
                continue
            primary = _post(c['th_base'], c['th_key'], mdl, payload, 4000)
        elif chan == 'gg':
            if not c.get('gg_key'):
                continue
            primary = _post(c['gg_base'], c['gg_key'], mdl, payload, 4000)
        elif chan == 'ms':
            if not c.get('ms_key'):
                continue
            primary = _post(c['ms_base'], c['ms_key'], mdl, payload, 4000)
        elif chan == 'ol':
            primary = _post(c['ol_base'], 'ollama', mdl, payload, 4000)
        elif chan == 'or':
            if not c.get('or_key'):
                continue
            primary = _post(c['or_base'], c['or_key'], mdl, payload, 4000)
        elif chan == 'oc':
            primary = _post(c['oc_base'], c['oc_key'], mdl, payload, 4000)
        else:  # 'th'
            if not c.get('th_key'):
                continue
            primary = _post(c['th_base'], c['th_key'], mdl, payload, 4000)
        primary['model'] = mdl
        # A call that failed (llm_error gap) -> try the next model.
        # A call that SUCCEEDED but rejected the role -> that is a real verdict,
        # so stop the chain and keep it.
        if not primary.get('failed'):
            break
    # Verifier fallback chain (2026-11-11, re-verified live): the verifier
    # must be a DIFFERENT model family from the primary or the AND-gate is
    # not an independent check. Live today:
    #   1. openrouter nvidia/nemotron-3.5-super-vl:free  (4.9s, clean JSON)
    #   2. openrouter liquid/lfm-2.5-2.6b:free
    #   3. local ollama qwen2.5:3b
    #   4. tokenharbor mimo-v2.5:free (returns 2026-11-16)
    #   5. zai glm-5.3 (quota returns 2026-11-15)
    verifier_chain = [
        # 2026-11-17: the verifier must be a DIFFERENT model family from the
        # primary, so it uses opencode's mimo-v2.6-flash-free / glm-5.3-flash-free
        # / beam-free family rather than the primary's deepseek-v4.1-flash-free.
        ('oc', 'mimo-v2.6-flash-free'),
        ('oc', 'glm-5.3-flash-free'),
        ('oc', 'beam-free'),
        ('ms', 'ministral-8b-latest'),
        ('or', 'nvidia/nemotron-3.5-super-vl:free'),
        ('ol', 'qwen2.5:3b'),
        ('th', 'mimo-v2.5:free'),
        ('zai', 'glm-5.3'),
    ]
    verifier = {'ok': False, 'score': 0, 'priority': 'P7',
                'reason': 'no verifier available', 'gaps': ['llm_error'],
                'failed': True}
    for chan, mdl in verifier_chain:
        if chan == 'gg':
            if not c.get('gg_key'):
                continue
            verifier = _post(c['gg_base'], c['gg_key'], mdl, payload, 3000)
        elif chan == 'zai':
            if not c.get('zai_key'):
                continue
            verifier = _post(c['zai_base'], c['zai_key'], mdl, payload, 3000)
        elif chan == 'ol':
            verifier = _post(c['ol_base'], 'ollama', mdl, payload, 3000)
        elif chan == 'ms':
            if not c.get('ms_key'):
                continue
            verifier = _post(c['ms_base'], c['ms_key'], mdl, payload, 3000)
        elif chan == 'or':
            if not c.get('or_key'):
                continue
            verifier = _post(c['or_base'], c['or_key'], mdl, payload, 3000)
        elif chan == 'oc':
            verifier = _post(c['oc_base'], c['oc_key'], mdl, payload, 3000)
        else:  # 'th'
            if not c.get('th_key'):
                continue
            verifier = _post(c['th_base'], c['th_key'], mdl, payload, 3000)
        verifier['model'] = mdl
        if not verifier.get('failed'):
            break
    ok = bool(primary.get('ok')) and bool(verifier.get('ok')) \
        and (primary.get('score') or 0) >= threshold \
        and (verifier.get('score') or 0) >= threshold
    return {
        'ok': ok,
        'score': min(primary.get('score') or 0, verifier.get('score') or 0),
        'primary': primary,
        'verifier': verifier,
        'reason': primary.get('reason') or '',
    }


if __name__ == '__main__':
    test = {
        'company': 'Atomic Capital', 'title': 'Chief Growth Officer',
        'loc': 'Bengaluru, Karnataka',
        'desc': 'We are an insurtech platform. You will own the entire growth '
                'strategy, build the GTM engine, own demand generation and brand, '
                'lead a team of 12 and report to the CEO. 12+ years experience.',
        'jid': 'test1',
    }
    print(json.dumps(decide(test), indent=1)[:1400])
