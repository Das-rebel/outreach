"""LinkedIn DM dispatch (CDP / playwright).

KNOWN-WORKING MECHANICS (hard-won; do not "simplify"):

  * The working path is the PROFILE-PAGE messaging OVERLAY: open the target's
    real profile URL, click the "Message" button, and use the composer that
    appears in that overlay.  Navigating to /messaging/thread/new renders the
    full-page composer inside an iframe and breaks.
  * The composer may live in an IFRAME; reach it through that frame's
    document (`frame.contentDocument.querySelector('[contenteditable=true]')`).
  * To set the text: focus the editor, select its content
    (getSelection + Range.selectAllChildren), then
    `doc.execCommand('insertText', false, text)`.  Assigning innerText gets
    WIPED by React's re-render.
  * The Send button frequently DOES NOT render in the accessible DOM (main
    document or any iframe), and a dispatched Enter keydown does NOT send
    either.  In that case the message simply sits typed in the browser:
    log `typed_needs_manual_send`, screenshot, and MOVE ON.
  * Only log `sent` when a Send control was actually clicked.
  * NEVER send a connection request.  If only Connect/Follow exists the
    attempt fails with NO_MESSAGE_BUTTON.

Safety: dry-run by default.  `send=True` requires an explicit approval set.
Max 5 DMs per run, 20-40s between sends.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from ..identity import linkedin_slug, norm_email, norm_text

LOG_METHOD = 'outreach_engine.cdp_dm_overlay'

# --- JS snippets ----------------------------------------------------------
JS_SET_TEXT = """(text) => {
  const eds = Array.from(document.querySelectorAll('[contenteditable="true"]'));
  const ed = eds.find(e => e.getClientRects().length > 0) || eds[0];
  if (!ed) return {ok: false, reason: 'NO_EDITOR'};
  ed.focus();
  const doc = ed.ownerDocument;
  const win = doc.defaultView;
  const sel = win.getSelection();
  const range = doc.createRange();
  if (typeof range.selectNodeContents === 'function') {
    range.selectNodeContents(ed);
  } else if (typeof range.selectAllChildren === 'function') {
    range.selectAllChildren(ed);
  }
  sel.removeAllRanges();
  sel.addRange(range);
  doc.execCommand('insertText', false, text);
  return {ok: true, text: ed.innerText || ''};
}"""

JS_SET_TEXT_LINES = """(lines) => {
  const eds = Array.from(document.querySelectorAll('[contenteditable="true"]'));
  const ed = eds.find(e => e.getClientRects().length > 0) || eds[0];
  if (!ed) return {ok: false, reason: 'NO_EDITOR'};
  ed.focus();
  const doc = ed.ownerDocument;
  const win = doc.defaultView;
  const range = doc.createRange();
  if (typeof range.selectNodeContents === 'function') {
    range.selectNodeContents(ed);
  } else if (typeof range.selectAllChildren === 'function') {
    range.selectAllChildren(ed);
  }
  const sel = win.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  for (let i = 0; i < lines.length; i++) {
    if (i > 0) doc.execCommand('insertLineBreak');
    doc.execCommand('insertText', false, lines[i]);
  }
  return {ok: true, text: ed.innerText || ''};
}"""

JS_CLICK_SEND = """() => {
  const usable = (e) => {
    if (e.disabled) return false;
    if ((e.getAttribute('aria-disabled') || '').toLowerCase() === 'true') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const cands = Array.from(
    document.querySelectorAll('button,[role="button"],input[type="submit"],a'));
  for (const e of cands) {
    const label = ((e.innerText || e.textContent || '')).trim();
    const aria = (e.getAttribute('aria-label') || '').trim();
    if (!usable(e)) continue;
    if (/^send$/i.test(label) || /^send$/i.test(aria)) {
      e.click();
      return {clicked: true, label: label || aria};
    }
  }
  for (const e of cands) {
    if (!usable(e)) continue;
    const spans = Array.from(e.querySelectorAll('span')).map(
      s => (s.innerText || '').trim());
    if (spans.some(s => /^send$/i.test(s))) {
      e.click();
      return {clicked: true, label: spans.find(s => /^send$/i.test(s))};
    }
  }
  return {clicked: false};
}"""

JS_HAS_MESSAGE = """() => {
  const visible = (e) => e.getClientRects().length > 0;
  const cands = Array.from(document.querySelectorAll('button,[role="button"],a'));
  for (const e of cands) {
    const label = ((e.innerText || e.textContent || '')).trim();
    const aria = (e.getAttribute('aria-label') || '').trim();
    if (!visible(e)) continue;
    if (/^message$/i.test(label) || /^message$/i.test(aria)
        || /^message\\s/i.test(label) || /^message\\s/i.test(aria)) {
      return {message: true, connect: false};
    }
  }
  for (const e of cands) {
    const label = ((e.innerText || e.textContent || '')).trim();
    const aria = (e.getAttribute('aria-label') || '').trim();
    if (!visible(e)) continue;
    if (/^connect/i.test(label) || /^connect/i.test(aria)
        || /^follow/i.test(label) || /^follow/i.test(aria)) {
      return {message: false, connect: true};
    }
  }
  return {message: false, connect: false};
}"""

JS_CLICK_MESSAGE = """() => {
  const visible = (e) => e.getClientRects().length > 0;
  const cands = Array.from(document.querySelectorAll('button,[role="button"],a'));
  for (const e of cands) {
    const label = ((e.innerText || e.textContent || '')).trim();
    const aria = (e.getAttribute('aria-label') || '').trim();
    if (!visible(e)) continue;
    if (/^message$/i.test(label) || /^message$/i.test(aria)
        || /^message\\s/i.test(label) || /^message\\s/i.test(aria)) {
      e.click();
      return {clicked: true, label: label || aria};
    }
  }
  return {clicked: false};
}"""

JS_COMPOSER_EMPTY = """() => {
  const eds = Array.from(document.querySelectorAll('[contenteditable="true"]'));
  const ed = eds.find(e => e.getClientRects().length > 0) || eds[0];
  if (!ed) return {empty: true, missing: true};
  return {empty: !(ed.innerText || '').trim(), text: ed.innerText || ''};
}"""

JS_CLICK_ATTACH = """() => {
  const visible = (e) => e.getClientRects().length > 0;
  const cands = Array.from(
    document.querySelectorAll('button,[role="button"],[aria-label],input[type="file"]'));
  for (const e of cands) {
    const aria = (e.getAttribute('aria-label') || '').trim();
    const label = ((e.innerText || e.textContent || '')).trim();
    if (!visible(e)) continue;
    if (/attach/i.test(aria) || /^attach/i.test(label)
        || /attach\\s*(a\\s*)?(file|resume)/i.test(aria)) {
      e.click();
      return {clicked: true, label: aria || label};
    }
  }
  return {clicked: false};
}"""


def norm_words(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()


def slug_from_url(url: str) -> str:
    m = re.search(r'/in/([^/?#]+)', url or '')
    return m.group(1) if m else 'target'


def screen_safe(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (value or '').lower()).strip('-')[:40] or 'target'


# --------------------------------------------------------------------------
# Frame helpers
# --------------------------------------------------------------------------

def _frames(page) -> List:
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    if page not in frames:
        frames.insert(0, page)
    return frames


def _eval_all(page, script: str, arg=None) -> List:
    out = []
    for frame in _frames(page):
        try:
            if arg is None:
                res = frame.evaluate(script)
            else:
                res = frame.evaluate(script, arg)
        except Exception:
            continue
        if res:
            out.append((frame, res))
    return out


JS_FIND_EDITOR = """() => {
  const eds = Array.from(document.querySelectorAll('[contenteditable="true"]'));
  const ed = eds.find(e => e.getClientRects().length > 0) || eds[0];
  if (ed) return {kind: 'ce', ok: true};
  const tas = Array.from(document.querySelectorAll('textarea'));
  const ta = tas.find(e => e.getClientRects().length > 0) || tas[0];
  if (ta) return {kind: 'textarea', ok: true};
  return {kind: null, ok: false};
}"""


def _composer_frame(page):
    for frame in _frames(page):
        try:
            found = frame.evaluate(JS_FIND_EDITOR)
        except Exception:
            continue
        if found and found.get('ok'):
            return frame
    return None


JS_SET_TEXTAREA = """(text) => {
  const tas = Array.from(document.querySelectorAll('textarea'));
  const ta = tas.find(e => e.getClientRects().length > 0) || tas[0];
  if (!ta) return {ok: false, reason: 'NO_TEXTAREA'};
  ta.focus();
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, 'value').set;
  setter.call(ta, text);
  ta.dispatchEvent(new Event('input', {bubbles: true}));
  ta.dispatchEvent(new Event('change', {bubbles: true}));
  return {ok: true, text: ta.value || ''};
}"""


def _set_text(frame, message: str):
    res = frame.evaluate(JS_SET_TEXT, message)
    if not res or not res.get('ok'):
        res = frame.evaluate(JS_SET_TEXTAREA, message)
    if not res or not res.get('ok'):
        return False, ''
    typed = res.get('text') or ''
    if norm_words(typed) != norm_words(message):
        res2 = frame.evaluate(JS_SET_TEXT_LINES, message.split('\n'))
        if res2 and res2.get('ok'):
            typed = res2.get('text') or ''
    return True, typed


def _attach_resume(page, frame, resume_path: str):
    if not resume_path:
        return False, 'NO_RESUME_FILE'
    for fr in [frame] + [f for f in _frames(page) if f is not frame]:
        try:
            fi = fr.locator('input[type="file"]').first
            if fi.count():
                fi.set_input_files(resume_path)
                time.sleep(1.2)
                return True, ''
        except Exception:
            continue
    for fr in _frames(page):
        try:
            clicked = fr.evaluate(JS_CLICK_ATTACH)
        except Exception:
            continue
        if not clicked or not clicked.get('clicked'):
            continue
        try:
            with page.expect_file_chooser(timeout=8000) as fc:
                fr.evaluate(JS_CLICK_ATTACH)
            fc.value.set_files(resume_path)
            time.sleep(1.2)
            return True, ''
        except Exception:
            continue
    return False, 'ATTACH_FAILED'


def _screenshot(page, name: str, shot_dir: str) -> str:
    try:
        os.makedirs(shot_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        shot = os.path.join(shot_dir, '%s_%s.png' % (ts, screen_safe(name)))
        page.screenshot(path=shot, full_page=False)
        return shot
    except Exception:
        return ''


def send_one(browser, target: Dict, cfg) -> Dict:
    """Send one DM.  Returns a result dict with `status` in
    {sent, typed_needs_manual_send, FAILED}."""
    name = (target.get('name') or '').strip()
    url = target.get('linkedin') or ''
    message = target.get('message') or ''
    resume_path = target.get('resume_path') or ''

    page = browser.contexts[0].new_page()
    page.set_default_timeout(45000)
    try:
        last_err = None
        for attempt in range(3):
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(3.0)
        if last_err is not None:
            return {'status': 'FAILED', 'note': 'GOTO_FAILED:%s' % str(last_err)[:120]}
        page.wait_for_timeout(3500)

        if '/in/' not in page.url:
            return {'status': 'FAILED', 'note': 'WRONG_URL'}
        if '/messaging/thread/new' in page.url:
            return {'status': 'FAILED', 'note': 'FULLPAGE_COMPOSER_NOT_ALLOWED'}

        probe = _eval_all(page, JS_HAS_MESSAGE)
        has_message = any(r.get('message') for _f, r in probe)
        if not has_message:
            return {'status': 'FAILED', 'note': 'NO_MESSAGE_BUTTON'}

        clicked = _eval_all(page, JS_CLICK_MESSAGE)
        if not any(r.get('clicked') for _f, r in clicked):
            return {'status': 'FAILED', 'note': 'MESSAGE_BUTTON_NOT_CLICKABLE'}
        time.sleep(2.0)

        frame = None
        for _ in range(20):
            frame = _composer_frame(page)
            if frame is not None:
                break
            time.sleep(1.0)
        if frame is None:
            # second attempt: the Message overlay sometimes needs a re-click
            _eval_all(page, JS_CLICK_MESSAGE)
            time.sleep(2.0)
            for _ in range(15):
                frame = _composer_frame(page)
                if frame is not None:
                    break
                time.sleep(1.0)
        if frame is None:
            shot = _screenshot(page, slug_from_url(url), cfg.screenshot_dir)
            return {'status': 'FAILED',
                    'note': ('NO_TEXTBOX|' + shot) if shot else 'NO_TEXTBOX'}

        attach_ok, attach_note = _attach_resume(page, frame, resume_path)

        ok, typed = _set_text(frame, message)
        if not ok:
            return {'status': 'FAILED', 'note': 'NO_TEXTBOX'}
        if norm_words(typed) != norm_words(message):
            return {'status': 'FAILED', 'note': 'TEXT_MISMATCH'}

        time.sleep(0.8)
        send_res = _eval_all(page, JS_CLICK_SEND)
        send_clicked = next((r for _f, r in send_res if r.get('clicked')), None)

        if not send_clicked:
            shot = _screenshot(page, slug_from_url(url), cfg.screenshot_dir)
            note = 'NO_SEND_CONTROL_FOUND'
            if attach_note:
                note += ';' + attach_note
            return {'status': 'typed_needs_manual_send',
                    'note': (note + '|' + shot) if shot else note,
                    'screenshot': shot}

        cleared = False
        for _ in range(10):
            time.sleep(1.0)
            for _f, r in _eval_all(page, JS_COMPOSER_EMPTY):
                if r.get('empty'):
                    cleared = True
                    break
            if cleared:
                break
        shot = _screenshot(page, slug_from_url(url), cfg.screenshot_dir)
        if not cleared:
            note = 'SEND_CLICKED_BUT_COMPOSER_NOT_CLEARED'
            return {'status': 'typed_needs_manual_send',
                    'note': (note + '|' + shot) if shot else note,
                    'screenshot': shot}

        note = 'SEND_CLICKED:%s' % (send_clicked.get('label') or 'Send')
        if attach_note:
            note += ';' + attach_note
        return {'status': 'sent',
                'note': (note + '|' + shot) if shot else note,
                'screenshot': shot}
    except Exception as exc:
        return {'status': 'FAILED',
                'note': '%s:%s' % (type(exc).__name__, str(exc)[:80])}
    finally:
        try:
            page.close()
        except Exception:
            pass


def plan_targets(items: Sequence, cfg, ctx) -> List[Dict]:
    """Turn approved items into a send plan, applying the safety gates."""
    plan: List[Dict] = []
    skipped: List[Dict] = []
    limit = min(cfg.max_dms_per_day, 5)
    for item in items:
        if len(plan) >= limit:
            break
        url = item.linkedin or ''
        if not url:
            skipped.append({'name': item.name, 'reason': 'NO_LINKEDIN_URL'})
            continue
        if not (item.message or '').strip():
            skipped.append({'name': item.name, 'reason': 'EMPTY_MESSAGE'})
            continue
        if linkedin_slug(url) and linkedin_slug(url) in ctx.contacted_slugs:
            skipped.append({'name': item.name, 'reason': 'ALREADY_CONTACTED'})
            continue
        plan.append({
            'name': item.name,
            'company': item.their_org or item.applied_company,
            'linkedin': url,
            'message': item.message,
            'resume': item.resume,
            'resume_path': cfg.resume_path(item.resume) if item.resume else '',
        })
    return plan, skipped


def run_dispatch(items: Sequence, cfg, ctx, send: bool = False) -> Dict:
    """Dispatch approved items.  Dry-run unless `send=True`."""
    plan, skipped = plan_targets(items, cfg, ctx)
    result = {
        'mode': 'send' if send else 'dry_run',
        'sent': 0,
        'typed_needs_manual_send': 0,
        'failed': 0,
        'skipped': skipped,
        'targets': [],
    }

    if not plan:
        result['note'] = 'nothing to dispatch'
        return result

    if not send:
        for target in plan:
            result['targets'].append({
                'name': target['name'],
                'company': target['company'],
                'linkedin': target['linkedin'],
                'resume': target['resume'],
                'message': target['message'],
                'status': 'dry_run',
            })
        result['note'] = 'dry run — nothing sent'
        return result

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result['note'] = 'playwright not installed — cannot dispatch'
        return result

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cfg.li_cdp_url, timeout=30000)
        for index, target in enumerate(plan, start=1):
            outcome = send_one(browser, target, cfg)
            outcome['name'] = target['name']
            outcome['company'] = target['company']
            outcome['linkedin'] = target['linkedin']
            outcome['message'] = target['message']
            outcome['attachment'] = target['resume']
            result['targets'].append(outcome)
            status = outcome['status']
            if status == 'sent':
                result['sent'] += 1
                ctx.contacted_slugs.add(linkedin_slug(target['linkedin']))
                append_log(cfg, outcome)
            elif status == 'typed_needs_manual_send':
                result['typed_needs_manual_send'] += 1
                append_log(cfg, outcome)
            else:
                result['failed'] += 1
                append_log(cfg, outcome)
            if index < len(plan):
                time.sleep(random.randint(cfg.dm_pause_min_s, cfg.dm_pause_max_s))
    return result


def append_log(cfg, row: Dict) -> None:
    """Append one attempt to the engine's own DM log."""
    path = os.path.join(cfg.state_dir, 'li_dm_log.jsonl')
    os.makedirs(cfg.state_dir, exist_ok=True)
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name': row.get('name'),
        'company': row.get('company'),
        'status': row.get('status'),
        'note': row.get('note'),
        'linkedin_url': row.get('linkedin'),
        'message': row.get('message'),
        'attachment': row.get('attachment'),
        'method': LOG_METHOD,
    }
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
