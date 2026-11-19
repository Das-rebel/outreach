"""Engine configuration.

Every knob that the operator may need to change lives here and is overridable
by an environment variable (prefix `OE_`) or by a CLI flag.  NOTHING in this
module hardcodes a value that also lives in `pipeline_v2/canonical_profile.json`
— claims, banned companies and do-not-approach names are read at runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_path(name: str, default: str) -> str:
    return os.path.abspath(os.environ.get(name, os.path.join(REPO_ROOT, default)))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ''))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ''))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class ResumeVariants:
    """Resume routing table (filenames only — files live outside the repo)."""

    ai_gtm: str = 'Subhajit_Das_AI_GTM_Growth_Systems.pdf'
    digital_business: str = 'Subhajit_Das_Growth_Digital_Business.pdf'
    martech: str = 'Subhajit_Das_Growth_Marketing_MarTech.pdf'

    def search_dirs(self) -> List[str]:
        extra = os.environ.get('OE_RESUME_DIRS', '')
        dirs = [os.path.expanduser('~/Downloads')]
        dirs += [d for d in extra.split(os.pathsep) if d]
        return dirs


@dataclass
class Config:
    # ---- paths -----------------------------------------------------------
    repo_root: str = REPO_ROOT
    canonical_profile: str = field(default_factory=lambda: _env_path(
        'OE_CANONICAL_PROFILE', 'pipeline_v2/canonical_profile.json'))
    tracker: str = field(default_factory=lambda: _env_path(
        'OE_TRACKER', 'applied_companies_tracker.json'))
    decision_graph: str = field(default_factory=lambda: _env_path(
        'OE_DECISION_GRAPH', 'DECISION_GRAPH.md'))
    state_dir: str = field(default_factory=lambda: _env_path(
        'OE_STATE_DIR', 'runs/outreach/engine_state'))

    happenstance_dir: str = field(default_factory=lambda: os.environ.get(
        'OE_HAPPENSTANCE_DIR', os.path.expanduser('~/happenstance-agent-find')))
    dm_log: str = field(default_factory=lambda: _env_path(
        'OE_DM_LOG', 'attachments/outreach/li_dm_log.jsonl'))
    multi_channel_log: str = field(default_factory=lambda: _env_path(
        'OE_MULTI_CHANNEL_LOG', 'attachments/outreach/multi_channel_log.jsonl'))
    approval_dir: str = field(default_factory=lambda: _env_path(
        'OE_APPROVAL_DIR', 'runs/outreach'))
    jobspy_pool: str = field(default_factory=lambda: _env_path(
        'OE_JOBSPY_POOL', 'runs/jobspy_pool.jsonl'))
    linkedin_people_files: List[str] = field(default_factory=list)
    apollo_cache_files: List[str] = field(default_factory=list)

    # ---- rules -----------------------------------------------------------
    dm_eligibility_days: int = field(default_factory=lambda: _env_int(
        'OE_DM_WINDOW_DAYS', 15))
    max_dms_per_day: int = field(default_factory=lambda: _env_int(
        'OE_MAX_DMS_PER_DAY', 5))
    max_per_company: int = field(default_factory=lambda: _env_int(
        'OE_MAX_PER_COMPANY', 2))
    monid_outreach_budget_usd: float = field(default_factory=lambda: _env_float(
        'OE_MONID_OUTREACH_BUDGET_USD', 0.30))
    monid_balance_usd: float = field(default_factory=lambda: _env_float(
        'OE_MONID_BALANCE_USD', 3.19))
    max_body_chars: int = field(default_factory=lambda: _env_int(
        'OE_MAX_BODY_CHARS', 600))
    followup_offsets: List[int] = field(default_factory=lambda: [
        int(x) for x in os.environ.get('OE_FOLLOWUP_OFFSETS', '3,7,14').split(',')
        if x.strip().isdigit()])

    # ---- channels --------------------------------------------------------
    channel_linkedin: bool = field(default_factory=lambda: _env_bool(
        'OE_CHANNEL_LINKEDIN', True))
    channel_email: bool = field(default_factory=lambda: _env_bool(
        'OE_CHANNEL_EMAIL', False))
    channel_whatsapp: bool = field(default_factory=lambda: _env_bool(
        'OE_CHANNEL_WHATSAPP', False))

    # ---- panel -----------------------------------------------------------
    panel_backend: str = field(default_factory=lambda: os.environ.get(
        'OE_PANEL_BACKEND', 'rules_only'))
    panel_timeout_s: int = field(default_factory=lambda: _env_int(
        'OE_PANEL_TIMEOUT_S', 90))
    panel_models: List[str] = field(default_factory=lambda: [
        m.strip() for m in os.environ.get('OE_PANEL_MODELS', '').split(',')
        if m.strip()])

    # ---- dispatch --------------------------------------------------------
    li_cdp_url: str = field(default_factory=lambda: os.environ.get(
        'LI_CDP_URL', 'http://127.0.0.1:9335'))
    li_profile_dir: str = field(default_factory=lambda: os.environ.get(
        'OE_LI_PROFILE_DIR', os.path.join(REPO_ROOT, '.brave_headless_profile')))
    dm_pause_min_s: int = field(default_factory=lambda: _env_int('OE_DM_PAUSE_MIN', 20))
    dm_pause_max_s: int = field(default_factory=lambda: _env_int('OE_DM_PAUSE_MAX', 40))
    screenshot_dir: str = field(default_factory=lambda: os.environ.get(
        'OE_SCREENSHOT_DIR', '/tmp/dm_screenshots'))
    gmail_user: str = field(default_factory=lambda: os.environ.get(
        'OE_GMAIL_USER', 'sdas22@gmail.com'))
    gmail_app_pw: str = field(default_factory=lambda: os.environ.get(
        'OE_GMAIL_APP_PW', ''))
    whatsapp_endpoint: str = field(default_factory=lambda: os.environ.get(
        'OE_WHATSAPP_ENDPOINT', 'http://127.0.0.1:8090/send'))
    whatsapp_api_key: str = field(default_factory=lambda: os.environ.get(
        'OE_WHATSAPP_API_KEY', 'omniclaw-wa-secret'))
    whatsapp_phone: str = field(default_factory=lambda: os.environ.get(
        'OE_WHATSAPP_PHONE', '917977110915'))

    # ---- runtime ---------------------------------------------------------
    now: Optional[str] = None           # ISO date override (tests)

    # ------------------------------------------------------------------
    def artifact(self, name: str) -> str:
        return os.path.join(self.state_dir, name)

    def ensure_state_dir(self) -> str:
        os.makedirs(self.state_dir, exist_ok=True)
        return self.state_dir

    def resume_path(self, filename: str) -> str:
        for d in self.resume_variants.search_dirs():
            p = os.path.join(d, filename)
            if os.path.exists(p):
                return p
        return ''

    resume_variants: ResumeVariants = field(default_factory=ResumeVariants)


DEFAULT = Config()
