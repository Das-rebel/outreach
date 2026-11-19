"""The shared engine context.

Holds the configuration, the canonical profile, the clock, the warning log
and the cross-node state (applications, suppression sets).  Every source
adapter receives this object as `ctx`; every eligibility gate reads its
canonical values from here.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Dict, List, Optional, Set

from .config import Config
from .eligibility import leadership_keywords
from .identity import norm_email, norm_key, norm_text


class EngineContext:
    def __init__(self, cfg: Optional[Config] = None, today: Optional[date] = None):
        self.cfg = cfg or Config()
        self.cfg.ensure_state_dir()
        if today is None:
            today = date.fromisoformat(self.cfg.now) if self.cfg.now \
                else date.today()
        self.today = today
        self.warnings: List[str] = []
        self.profile: Dict = {}
        self.applications: List = []
        self.candidates: List = []
        self.contacted_slugs: Set[str] = set()
        self.contacted_emails: Set[str] = set()
        self.contacted_name_company: Set = set()
        self._load_profile()
        self._load_suppression()

    def _load_suppression(self) -> None:
        """Contact-log suppression sets must be present in EVERY command
        (the eligibility gate reads them), not only after `ingest`."""
        try:
            from .sources.suppression import load_suppression_sets
            load_suppression_sets(self)
        except Exception as exc:  # never crash the pipeline
            self.warn('context', 'suppression load failed: %s' % exc)

    # -- warnings ---------------------------------------------------------
    def warn(self, node: str, message: str) -> None:
        line = '[%s] %s' % (node, message)
        self.warnings.append(line)

    # -- canonical profile ------------------------------------------------
    def _load_profile(self) -> None:
        path = self.cfg.canonical_profile
        if not os.path.exists(path):
            self.warn('context', 'canonical profile missing: %s' % path)
            self.profile = {}
            return
        try:
            with open(path, encoding='utf-8') as fh:
                self.profile = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            self.warn('context', 'canonical profile unreadable: %s' % exc)
            self.profile = {}

    # -- canonical rule values -------------------------------------------
    @property
    def banned_companies(self) -> List[str]:
        """`companies_banned` PLUS the company names that live in
        `claims_banned_written` (Paytm is banned there, not in
        companies_banned).  The list is built at runtime — never hardcoded."""
        terms = list(self.profile.get('companies_banned') or [])
        for key in (self.profile.get('claims_banned_written') or {}):
            terms.append(str(key))
        seen = set()
        out = []
        for term in terms:
            key = norm_key(term)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(term)
        return out

    @property
    def do_not_approach(self) -> Set[str]:
        return {norm_key(n) for n in (self.profile.get('do_not_approach') or [])}

    @property
    def leadership_keywords(self) -> List[str]:
        return leadership_keywords(self.profile)

    @property
    def identity(self) -> Dict:
        return self.profile.get('identity') or {}

    # -- helpers ----------------------------------------------------------
    def add_contacted(self, slug: str = '', email: str = '',
                      name: str = '', company: str = '') -> None:
        if slug:
            self.contacted_slugs.add(slug)
        if email:
            self.contacted_emails.add(norm_email(email))
        if name:
            self.contacted_name_company.add(
                (norm_text(name).replace(' ', ''),
                 norm_text(company).replace(' ', '')))

    def to_dict(self) -> Dict:
        return {
            'repo_root': self.cfg.repo_root,
            'state_dir': self.cfg.state_dir,
            'today': self.today.isoformat(),
            'banned_companies': len(self.banned_companies),
            'do_not_approach': len(self.do_not_approach),
            'leadership_keywords': self.leadership_keywords,
            'warnings': list(self.warnings),
        }
