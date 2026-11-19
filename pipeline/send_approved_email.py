#!/usr/bin/env python3
"""Send the CLI-approved email targets (the email half of approve_cli.py).

Reads the approval package + runs/outreach/approved_names.json, sends every
approved target's email with the resume attached via Gmail SMTP, logs each
send to attachments/outreach/li_dm_log.jsonl and updates OUTREACH_TRACKER.json.

  python3 runs/outreach/send_approved_email.py --package runs/outreach/APPROVAL_STASHFIN.json
  python3 runs/outreach/send_approved_email.py --dry-run
"""
import argparse, json, os, sys, time

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.abspath(os.path.join(HERE,'..','..'))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)

def load(p):
    with open(p, encoding='utf-8') as fh: return json.load(fh)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--package', default=os.path.join(HERE,'APPROVAL_STASHFIN.json'))
    ap.add_argument('--approved-file', default=os.path.join(HERE,'approved_names.json'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--only', action='append', default=[])
    a=ap.parse_args()

    pkg=load(a.package)
    targets=pkg.get('targets') or []
    dec=load(a.approved_file)
    approved=dec.get('approved') if isinstance(dec, dict) else dec
    approved=[str(n).strip().lower() for n in (approved or [])]
    sel=[t for t in targets if str(t.get('name','')).strip().lower() in approved]
    if a.only:
        sel=[t for t in sel if t.get('name') in a.only]
    print(f'package: {os.path.basename(a.package)} | approved names: {len(approved)} | targets to send: {len(sel)}')
    for t in sel:
        print(f"  {t.get('name')} -> {t.get('email')} | {t.get('email_subject','')}")
    if not sel:
        print('  nothing approved to send'); return
    if a.dry_run:
        print('  (dry run — nothing sent)'); return

    from outreach_engine import approval as A
    from outreach_engine.models import Candidate
    from outreach_engine.config import Config
    from outreach_engine.context import EngineContext
    from outreach_engine.dispatch import email as email_mod
    cands=[]
    for t in sel:
        c=Candidate.from_dict({'name':t['name'],'contact_title':t.get('contact_designation',''),
            'company':t.get('company'),'applied_company':t.get('company'),
            'applied_role':t.get('applied_role',''),'applied_date':t.get('applied_date',''),
            'linkedin':t.get('linkedin',''),'email':t['email'],'kind':'person',
            'sources':['cli_approved'],'evidence':[t.get('panel_note','')],
            'email_body':t.get('email_body') or t.get('message',''),
            'email_subject':t.get('email_subject',''),'message':t.get('message',''),
            'message_type':'B','resume':t.get('resume'),'channel':'email','tier':t.get('tier','P0')})
        c.channel='email'; cands.append(c)
    items=A.build_items(cands)
    for it,c in zip(items,cands):
        it.email_body=c.email_body; it.email_subject=c.email_subject; it.resume=c.resume; it.channel='email'
    cfg=Config(); cfg.channel_email=True; cfg.channel_linkedin=False
    if not cfg.gmail_app_pw:
        print('  ERROR: no Gmail app password (set OE_GMAIL_APP_PW)'); return
    ctx=EngineContext(cfg)
    res=email_mod.run_email_dispatch(items, cfg, ctx, send=True)
    print(json.dumps({k:v for k,v in res.items() if k!='targets'}, indent=1))
    LOG=os.path.join(ROOT,'attachments','outreach','li_dm_log.jsonl')
    ts=time.strftime('%Y-%m-%d %H:%M:%S'); n=0
    with open(LOG,'a') as fh:
        for t in res.get('targets',[]):
            if t.get('status')!='sent': continue
            src=next((x for x in sel if x['name']==t['name']), {})
            n+=1
            fh.write(json.dumps({'timestamp':ts,'name':t['name'],'company':src.get('company'),
                'status':'sent','channel':'email','email':t.get('email'),
                'note':'CLI-approved email lane (short form), resume attached',
                'linkedin_url':src.get('linkedin',''),'subject':src.get('email_subject'),
                'message':src.get('email_body') or src.get('message',''),
                'attachment':src.get('resume'),'method':'smtp_gmail_email_lane_v3'}, ensure_ascii=False)+'\n')
    print(f'logged {n} sends')
    trp=os.path.join(HERE,'OUTREACH_TRACKER.json'); tr=load(trp)
    for c in tr.get('contacts',[]):
        if c.get('contact_name') in {t['name'] for t in sel}:
            c['outreach_status']='SENT'; c['sent_at']=ts; c['attempt_count']=int(c.get('attempt_count') or 0)+1
            c['next_followup_due']='2026-11-23'
    json.dump(tr, open(trp,'w'), indent=2, ensure_ascii=False)
    print('tracker updated')

if __name__=='__main__':
    main()
