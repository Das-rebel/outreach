#!/usr/bin/env python3
"""LinkedIn DM sender with resume attachment — authentic-voice messages, brave cookies + Playwright."""
import json, time, os, sys
from datetime import datetime
import browser_cookie3
from playwright.sync_api import sync_playwright

DM_LOG = '/Users/Subho/job_pipeline/attachments/outreach/li_dm_log.jsonl'
SHOTS = '/tmp/dm_screenshots'
os.makedirs(SHOTS, exist_ok=True)

TARGETS = [
    {"name": "Mohak Jhaveri", "company": "Mastercard", "verify": "mastercard",
     "urls": ["https://www.linkedin.com/in/mohak-jhaveri"],
     "resume": "/Users/Subho/Downloads/Subhajit_Das_AI_GTM_Growth_Systems.pdf",
     "msg": "Hi Mohak — I had applied for the Pre-Sales GTM role at Mastercard (Sep 30). My background is fintech growth — scaled Groww's credit book 8x to $36M, ran a ₹1500Cr portfolio at Axis Bank. Resume attached. Would love to learn more about the team from you sometime."},
    {"name": "Dheeraj Mathur", "company": "Kuhoo Finance", "verify": "kuhoo",
     "urls": ["https://www.linkedin.com/in/dheeraj-mathur"],
     "resume": "/Users/Subho/Downloads/Subhajit_Das_Growth_Digital_Business.pdf",
     "msg": "Hi Dheeraj — applied for a growth role at Kuhoo last week. I've spent 11 years building credit and lending growth — ₹70Cr/mo disbursals at Niro, ₹0→₹100Cr book at ABFL, Groww 8x. Resume attached. I'd welcome the chance to discuss how I could contribute."},
    {"name": "Premanshu Singh", "company": "super.money", "verify": "super.money",
     "urls": ["https://www.linkedin.com/in/premanshu-singh",
              "https://www.linkedin.com/in/premanshu-singh-5b516723b",
              "https://www.linkedin.com/in/premanshu-singh-616b2b12"],
     "resume": "/Users/Subho/Downloads/Subhajit_Das_Growth_Marketing_MarTech.pdf",
     "msg": "Hi Premanshu — applied for the Marketing Manager role at super.money (Oct 8). Grew Groww's credit book 8x and ICICI's customer base 3x. Resume attached — happy to connect anytime."},
    {"name": "Tanya Arora", "company": "MetaMorph", "verify": "metamorph",
     "urls": ["https://www.linkedin.com/in/tanya-aroraa"],
     "resume": "/Users/Subho/Downloads/Subhajit_Das_Growth_Digital_Business.pdf",
     "msg": "Hi Tanya — I applied for the Head of Growth – Marketplaces role you'd posted (Oct 12). 11 years in fintech growth — Groww, Axis Bank, Niro. Resume attached. Happy to share anything else the client needs."},
]

def log_send(name, company, status, note="", resume=""):
    e = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": name,
         "company": company, "status": status, "note": note, "attachment": resume,
         "method": "playwright_dm_attach"}
    with open(DM_LOG, 'a') as f:
        f.write(json.dumps(e) + "\n")

def human_pause(a=1.2, b=2.5):
    time.sleep(a + (b - a) * (time.time() % 1))

def resolve_profile(page, t):
    """Open candidate URL(s), verify company match in page content."""
    for url in t["urls"]:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        human_pause(2, 3.5)
        content = page.content().lower()
        if t["verify"] in content:
            return url
        # authwall check
        if "authwall" in page.url:
            return None
    return None

def send_dm(page, t):
    """Compose DM on profile page: Message → attach resume → type → send."""
    # find Message button
    btn = page.locator('button[aria-label*="Message" i], a[aria-label*="Message" i]').first
    if btn.count() == 0:
        btn = page.get_by_role("button", name="Message", exact=False).first
    if btn.count() == 0:
        return "NO_MESSAGE_BUTTON"
    btn.click()
    human_pause(2, 3)
    # message textbox
    box = page.locator('div[role="textbox"][aria-label*="Write a message" i]').first
    if box.count() == 0:
        box = page.locator('.msg-form__contenteditable').first
    if box.count() == 0:
        return "NO_TEXTBOX"
    box.click()
    human_pause(0.5, 1)
    # attach resume FIRST (paperclip / add attachment)
    attach = page.locator('input[type="file"]').first
    if attach.count() == 0:
        clip = page.locator('button[aria-label*="attach" i], button[aria-label*="Add a file" i], .msg-form__attachment-button').first
        if clip.count() > 0:
            clip.click()
            human_pause(1, 2)
            attach = page.locator('input[type="file"]').first
    if attach.count() > 0:
        attach.set_input_files(t["resume"])
        human_pause(3, 5)  # wait upload
    else:
        return "NO_ATTACH_INPUT"
    # type message (real char-by-char to trigger events)
    page.keyboard.type(t["msg"], delay=15)
    human_pause(1, 2)
    # send
    send_btn = page.locator('button.msg-form__send-button:has-text("Send"):not([disabled])').first
    if send_btn.count() == 0:
        send_btn = page.locator('button[type="submit"]:has-text("Send")').first
    if send_btn.count() == 0:
        return "NO_SEND_BTN"
    send_btn.click()
    human_pause(2, 3)
    return "SENT"

def main(only_name=None):
    src = os.environ.get('LI_COOKIE_SRC', 'chromium')
    cookies = (browser_cookie3.chromium if src == 'chromium' else browser_cookie3.brave)(domain_name='.linkedin.com')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1382, "height": 900})
        ctx.add_cookies([{"name": c.name, "value": c.value, "domain": c.domain,
                          "path": c.path, "secure": c.secure, "httpOnly": c.http_only}
                         for c in cookies])
        page = ctx.new_page()
        # validate session
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        human_pause(2, 3)
        if "authwall" in page.url or "login" in page.url:
            print("❌ SESSION DEAD — extract fresh Brave cookies (open linkedin.com in Brave first)")
            browser.close(); sys.exit(2)
        print("✅ session alive")
        for t in TARGETS:
            if only_name and only_name.lower() not in t["name"].lower():
                continue
            try:
                url = resolve_profile(page, t)
                if not url:
                    print(f"⚠️ {t['name']}: profile not resolved (authwall/mismatch)")
                    log_send(t["name"], t["company"], "FAILED", "profile not resolved", t["resume"])
                    continue
                page.screenshot(path=f"{SHOTS}/{t['name'].replace(' ','_')}_profile.png")
                status = send_dm(page, t)
                page.screenshot(path=f"{SHOTS}/{t['name'].replace(' ','_')}_after.png")
                print(f"{'✅' if status=='SENT' else '⚠️'} {t['name']}: {status}")
                log_send(t["name"], t["company"], status if status == "SENT" else "FAILED",
                         status, t["resume"])
                human_pause(8, 15)  # cooldown between DMs
            except Exception as ex:
                print(f"❌ {t['name']}: {ex}")
                log_send(t["name"], t["company"], "ERROR", str(ex)[:120], t["resume"])
                try: page.goto("https://www.linkedin.com/feed/")
                except: pass
        browser.close()

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    main(only)
