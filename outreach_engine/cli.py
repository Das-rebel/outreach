"""`python3 -m outreach_engine <command>`.

Commands
    ingest     read every source node -> unified candidate pool
    eligible   apply the hard gates -> reason codes
    rank       score + tier + diversity cap -> ranked list
    panel      run the decision panel over the eligible list
    draft      generate house-format messages
    approval   export the human approval bundle
    dispatch   act on an approval file (dry-run unless --send)
    outcomes   the outcome state machine
    status     pipeline state summary

Every command prints a JSON summary and writes its artifact under
`runs/outreach/engine_state/`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Dict, List, Optional

from . import approval as approval_mod
from . import eligibility, llm_panel, messaging, scoring, tracking
from .config import Config
from .context import EngineContext
from .identity import candidate_keys, merge_candidates, norm_key, resolve_company
from .models import Candidate
from .sources import ADAPTERS


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _write_json(path: str, data) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path


def _write_text(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def _load_pool(ctx: EngineContext):
    path = ctx.cfg.artifact('candidates.json')
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _pool_to_candidates(rows: List[Dict]) -> List[Candidate]:
    return [Candidate.from_dict(r) for r in rows if isinstance(r, dict)]


def _dedupe(candidates: List[Candidate]) -> List[Candidate]:
    """Merge candidates that share a dedupe key (LinkedIn slug > email >
    normalised company+name > name)."""
    groups: Dict[str, List[Candidate]] = {}
    order: List[str] = []
    for cand in candidates:
        keys = candidate_keys(cand)
        key = keys[0] if keys else ('raw:' + (cand.name or ''))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(cand)
    out: List[Candidate] = []
    for key in order:
        group = groups[key]
        # richest first: LinkedIn URL > email > evidence count
        group = sorted(group, key=lambda c: (
            1 if c.linkedin else 0,
            1 if c.email else 0,
            len(c.evidence or []),
        ), reverse=True)
        merged = group[0]
        for other in group[1:]:
            merged = merge_candidates(merged, other)
        out.append(merged)
    return out


def _candidate_dict(cand: Candidate) -> Dict:
    data = cand.to_dict()
    return data


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_ingest(ctx: EngineContext, args) -> Dict:
    per_node: Dict[str, int] = {}
    all_candidates: List[Candidate] = []

    for name, fetch in ADAPTERS:
        try:
            rows = fetch(ctx)
        except Exception as exc:
            ctx.warn(name, 'adapter failed: %s: %s' % (type(exc).__name__, exc))
            rows = []
        per_node[name] = len(rows)
        all_candidates.extend(rows)

    people = [c for c in all_candidates if c.kind == 'person']
    applications = [c for c in all_candidates if c.kind == 'application']
    suppression = [c for c in all_candidates if c.kind == 'suppression']

    # Drop rows whose "name" is not a person (notification senders, bare
    # email addresses, empty names).  These are never contactable.
    non_person = 0
    kept_people = []
    for cand in people:
        name = (cand.name or '').strip()
        if not name or '@' in name or 'noreply' in name.lower() or \
                'no-reply' in name.lower() or '@' in (cand.company or ''):
            non_person += 1
            continue
        kept_people.append(cand)
    people = kept_people
    ctx.warn('ingest', 'dropped %d non-person rows (email senders, empty names)'
             % non_person)

    # Attach application context (role/company/date) to people by company.
    by_company: Dict[str, List] = {}
    for app in applications:
        by_company.setdefault(resolve_company(app.applied_company or
                                              app.company or ''), []).append(app)

    linked = 0
    for cand in people:
        key = resolve_company(cand.applied_company or cand.company or '')
        apps = by_company.get(key) or []
        if not apps:
            continue
        apps = sorted(apps, key=lambda a: a.applied_date or '', reverse=True)
        app = apps[0]
        cand.applied_company = cand.applied_company or app.applied_company
        cand.applied_role = cand.applied_role or app.applied_role
        cand.applied_date = cand.applied_date or app.applied_date
        cand.applied_jid = cand.applied_jid or app.applied_jid
        cand.applied_status = cand.applied_status or app.applied_status
        linked += 1

    deduped = _dedupe(people)
    ctx.candidates = deduped

    path = ctx.cfg.artifact('candidates.json')
    _write_json(path, [_candidate_dict(c) for c in deduped])

    summary = {
        'command': 'ingest',
        'nodes': per_node,
        'people_raw': len(people),
        'people_deduped': len(deduped),
        'applications': len(applications),
        'suppression_rows': len(suppression),
        'linked_to_application': linked,
        'artifact': path,
        'warnings': list(ctx.warnings),
    }
    _write_json(ctx.cfg.artifact('ingest_summary.json'), summary)
    return summary


def _eligible_candidates(ctx: EngineContext, args) -> List[Candidate]:
    rows = _load_pool(ctx)
    candidates = _pool_to_candidates(rows)
    out = []
    for cand in candidates:
        reasons = eligibility.check(cand, ctx)
        cand.reasons = reasons
        if reasons:
            cand.blocked = reasons
        else:
            out.append(cand)
    return out


def cmd_eligible(ctx: EngineContext, args) -> Dict:
    rows = _load_pool(ctx)
    candidates = _pool_to_candidates(rows)
    eligible = []
    blocked_counts: Dict[str, int] = {}
    for cand in candidates:
        reasons = eligibility.check(cand, ctx)
        cand.reasons = reasons
        if reasons:
            cand.blocked = reasons
            for reason in reasons:
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
        else:
            eligible.append(cand)

    path = ctx.cfg.artifact('eligible.json')
    _write_json(path, [_candidate_dict(c) for c in eligible])

    summary = {
        'command': 'eligible',
        'eligible': len(eligible),
        'total_considered': len(candidates),
        'blocked_by_reason': blocked_counts,
        'artifact': path,
        'warnings': list(ctx.warnings),
    }
    _write_json(ctx.cfg.artifact('eligible_summary.json'), summary)
    return summary


def cmd_rank(ctx: EngineContext, args) -> Dict:
    candidates = _eligible_candidates(ctx, args)
    for cand in candidates:
        score = scoring.score_candidate(cand, ctx)
        cand.score = score
        cand.tier = score['tier']
    ranked = sorted(candidates,
                    key=lambda c: (-(c.score['total'] or 0),
                                   (c.applied_company or '').lower()))
    kept, dropped = scoring.apply_diversity_cap(ranked, ctx.cfg.max_per_company)

    path = ctx.cfg.artifact('ranked.json')
    _write_json(path, [_candidate_dict(c) for c in kept])

    summary = {
        'command': 'rank',
        'eligible': len(candidates),
        'kept_after_cap': len(kept),
        'dropped_by_cap': len(dropped),
        'max_per_company': ctx.cfg.max_per_company,
        'top': [{
            'rank': i,
            'name': c.name,
            'company': c.applied_company or c.company,
            'tier': c.tier,
            'score': c.score['total'],
            'components': c.score['components'],
            'reasons': c.reasons,
        } for i, c in enumerate(kept[:20], start=1)],
        'artifact': path,
    }
    _write_json(ctx.cfg.artifact('rank_summary.json'), summary)
    return summary


def cmd_panel(ctx: EngineContext, args) -> Dict:
    candidates = _eligible_candidates(ctx, args)
    for cand in candidates:
        score = scoring.score_candidate(cand, ctx)
        cand.score = score
        cand.tier = score['tier']
    ranked = sorted(candidates, key=lambda c: -(c.score['total'] or 0))
    kept, _dropped = scoring.apply_diversity_cap(ranked, ctx.cfg.max_per_company)

    backend = llm_panel.get_backend(ctx.cfg, ctx)
    verdicts = llm_panel.run_panel(ctx.cfg, ctx, kept, args.top)
    survived, demoted = llm_panel.apply_panel(verdicts, kept)

    path = ctx.cfg.artifact('panel.json')
    _write_json(path, [{
        'name': c.name,
        'company': c.applied_company or c.company,
        'tier': c.tier,
        'score': c.score['total'],
        'panel': c.panel,
        'reasons': c.reasons,
    } for c in kept])

    summary = {
        'command': 'panel',
        'backend': backend.name,
        'input': len(kept),
        'survived': len(survived),
        'demoted': len(demoted),
        'demoted_names': [c.name for c in demoted],
        'artifact': path,
        'warnings': list(ctx.warnings),
    }
    _write_json(ctx.cfg.artifact('panel_summary.json'), summary)
    return summary


def _draft_candidates(ctx: EngineContext, args) -> List[Candidate]:
    rows = _load_pool(ctx)
    if not rows:
        rows = []
    candidates = _pool_to_candidates(rows)
    eligible = []
    for cand in candidates:
        reasons = eligibility.check(cand, ctx)
        cand.reasons = reasons
        if not reasons:
            eligible.append(cand)
    for cand in eligible:
        score = scoring.score_candidate(cand, ctx)
        cand.score = score
        cand.tier = score['tier']
    ranked = sorted(eligible, key=lambda c: -(c.score['total'] or 0))
    kept, _dropped = scoring.apply_diversity_cap(ranked, ctx.cfg.max_per_company)

    drafted = []
    for cand in kept:
        mtype = messaging.message_type_for(cand.contact_title)
        try:
            message = messaging.build_message(
                mtype, cand.name, cand.applied_role, cand.applied_company,
                cand.applied_date, cand.contact_title, cand.company,
                profile=ctx.profile, max_body_chars=ctx.cfg.max_body_chars)
        except messaging.ClaimViolation as exc:
            ctx.warn('draft', 'claim violation for %s: %s' % (cand.name, exc))
            continue
        cand.message = message
        cand.message_type = mtype
        cand.resume = messaging.resume_for(cand.applied_role,
                                            cand.applied_company, cand.tier)
        cand.channel = 'linkedin' if (cand.linkedin or '').strip() else 'email'
        drafted.append(cand)
    return drafted


def cmd_draft(ctx: EngineContext, args) -> Dict:
    drafted = _draft_candidates(ctx, args)
    path = ctx.cfg.artifact('drafts.json')
    _write_json(path, [{
        'name': c.name,
        'company': c.applied_company or c.company,
        'their_org': c.company,
        'designation': c.contact_title,
        'applied_role': c.applied_role,
        'applied_date': c.applied_date,
        'linkedin': c.linkedin,
        'email': c.email,
        'tier': c.tier,
        'score': c.score['total'],
        'message_type': c.message_type,
        'resume': c.resume,
        'channel': c.channel,
        'message': c.message,
    } for c in drafted])

    summary = {
        'command': 'draft',
        'drafted': len(drafted),
        'type_a': sum(1 for c in drafted if c.message_type == 'A'),
        'type_b': sum(1 for c in drafted if c.message_type == 'B'),
        'artifact': path,
        'warnings': list(ctx.warnings),
    }
    _write_json(ctx.cfg.artifact('draft_summary.json'), summary)
    return summary


def cmd_approval(ctx: EngineContext, args) -> Dict:
    drafted = _draft_candidates(ctx, args)
    items = approval_mod.build_items(drafted)
    path = ctx.cfg.artifact('APPROVAL_bundle.md')
    approval_mod.write_bundle(items, path, meta={
        'generated': date.today().isoformat(),
    })
    json_path = ctx.cfg.artifact('APPROVAL_bundle.json')
    _write_json(json_path, [i.to_dict() for i in items])

    summary = {
        'command': 'approval',
        'items': len(items),
        'artifact': path,
        'json_artifact': json_path,
    }
    _write_json(ctx.cfg.artifact('approval_summary.json'), summary)
    return summary


def cmd_dispatch(ctx: EngineContext, args) -> Dict:
    from .dispatch import email as email_mod
    from .dispatch import linkedin_dm as li_mod
    from .dispatch import whatsapp as wa_mod

    if not args.approved:
        raise SystemExit('dispatch requires --approved <decision file>')

    drafted = _draft_candidates(ctx, args)
    items = approval_mod.build_items(drafted)
    approved = approval_mod.parse_decision_file(args.approved, items)

    li_result = {'mode': 'dry_run', 'sent': 0, 'failed': 0}
    if ctx.cfg.channel_linkedin and approved:
        li_result = li_mod.run_dispatch(approved, ctx.cfg, ctx, send=args.send)
    email_result = {'mode': 'dry_run', 'sent': 0, 'failed': 0}
    if ctx.cfg.channel_email and approved:
        email_result = email_mod.run_email_dispatch(approved, ctx.cfg, ctx,
                                                    send=args.send)
    wa_result = {'mode': 'dry_run', 'sent': 0, 'failed': 0}
    if ctx.cfg.channel_whatsapp and approved:
        wa_result = wa_mod.run_whatsapp_dispatch(approved, ctx.cfg, ctx,
                                                 send=args.send)

    summary = {
        'command': 'dispatch',
        'approved_items': len(approved),
        'approved_names': [i.name for i in approved],
        'send': bool(args.send),
        'linkedin': li_result,
        'email': email_result,
        'whatsapp': wa_result,
    }
    _write_json(ctx.cfg.artifact('dispatch_summary.json'), summary)
    return summary


def cmd_outcomes(ctx: EngineContext, args) -> Dict:
    if args.set:
        parts = args.set.split('|')
        if len(parts) < 3:
            raise SystemExit('--set expects "company|role|state"')
        company, role, state = parts[0], parts[1], parts[2]
        try:
            tracking.set_state(ctx.cfg, company, role, state,
                               note=args.note or '', contact=args.contact or '')
        except ValueError as exc:
            raise SystemExit(str(exc))
    summary = {
        'command': 'outcomes',
        **tracking.summary(ctx.cfg),
    }
    _write_json(ctx.cfg.artifact('outcomes_summary.json'), summary)
    return summary


def cmd_status(ctx: EngineContext, args) -> Dict:
    pool = _load_pool(ctx)
    eligible_path = ctx.cfg.artifact('eligible.json')
    ranked_path = ctx.cfg.artifact('ranked.json')
    drafts_path = ctx.cfg.artifact('drafts.json')
    approval_path = ctx.cfg.artifact('APPROVAL_bundle.md')

    def _count(path):
        if not os.path.exists(path):
            return 0
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            return len(data) if isinstance(data, list) else 0
        except (OSError, json.JSONDecodeError):
            return 0

    summary = {
        'command': 'status',
        'today': ctx.today.isoformat(),
        'state_dir': ctx.cfg.state_dir,
        'candidates': len(pool),
        'eligible': _count(eligible_path),
        'ranked': _count(ranked_path),
        'drafts': _count(drafts_path),
        'approval_bundle_exists': os.path.exists(approval_path),
        'channels': {
            'linkedin': ctx.cfg.channel_linkedin,
            'email': ctx.cfg.channel_email,
            'whatsapp': ctx.cfg.channel_whatsapp,
        },
        'rules': {
            'dm_eligibility_days': ctx.cfg.dm_eligibility_days,
            'max_dms_per_day': ctx.cfg.max_dms_per_day,
            'max_per_company': ctx.cfg.max_per_company,
            'monid_outreach_budget_usd': ctx.cfg.monid_outreach_budget_usd,
            'followup_offsets': ctx.cfg.followup_offsets,
        },
        'panel_backend': ctx.cfg.panel_backend,
        'outcomes': tracking.summary(ctx.cfg),
        'warnings': list(ctx.warnings),
    }
    _write_json(ctx.cfg.artifact('status.json'), summary)
    return summary


COMMANDS = {
    'ingest': cmd_ingest,
    'eligible': cmd_eligible,
    'rank': cmd_rank,
    'panel': cmd_panel,
    'draft': cmd_draft,
    'approval': cmd_approval,
    'dispatch': cmd_dispatch,
    'outcomes': cmd_outcomes,
    'status': cmd_status,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='python3 -m outreach_engine',
        description='Outreach engine v2 — rule-first, human-gated outreach.')
    parser.add_argument('--state-dir', help='override the state directory')
    parser.add_argument('--today', help='override "today" (ISO date)')
    sub = parser.add_subparsers(dest='command', required=True)

    for name in ('ingest', 'eligible', 'rank', 'panel', 'draft', 'approval',
                 'status'):
        p = sub.add_parser(name)
        p.add_argument('--top', type=int, default=20)

    p = sub.add_parser('dispatch')
    p.add_argument('--approved', help='decision file (JSON or markdown)')
    p.add_argument('--send', action='store_true',
                   help='actually send (default is a dry run)')

    p = sub.add_parser('outcomes')
    p.add_argument('--set', help='company|role|state')
    p.add_argument('--note', default='')
    p.add_argument('--contact', default='')
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = Config()
    if args.state_dir:
        cfg.state_dir = os.path.abspath(args.state_dir)
    if args.today:
        cfg.now = args.today
    ctx = EngineContext(cfg)
    if getattr(args, 'today', None):
        ctx.today = date.fromisoformat(args.today)

    handler = COMMANDS[args.command]
    summary = handler(ctx, args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
