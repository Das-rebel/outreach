"""Dataclasses shared by every stage of the outreach engine.

Deliberately plain dataclasses (stdlib only, no ORM, no framework) so the
JSON artifacts written under `runs/outreach/engine_state/` round-trip
losslessly through `asdict()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Application:
    """One row of `applied_companies_tracker.json`."""

    company: str
    role: str = ''
    jid: str = ''
    url: str = ''
    date: str = ''            # ISO date (YYYY-MM-DD) when parseable
    status: str = ''
    resume: str = ''
    category: str = ''
    source: str = ''
    alias: str = ''
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    """A person we could contact, plus the application context we own.

    `company` is where the person works NOW.  `applied_company` / `applied_role`
    / `applied_date` describe OUR application that the outreach refers to.
    `linkedin` / `email` are the only two ways we can reach them.
    """

    name: str = ''
    contact_title: str = ''        # their designation
    company: str = ''              # their current org
    applied_company: str = ''      # the company we applied to
    applied_role: str = ''
    applied_date: str = ''
    applied_jid: str = ''
    applied_status: str = ''
    linkedin: str = ''
    email: str = ''
    phone: str = ''
    degree: str = ''               # '1st' / '2nd' / '3rd' when known
    kind: str = 'person'           # 'person' | 'application'
    needs_identity_resolution: bool = False
    sources: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    # populated by the ranking / drafting stages
    score: Optional[Dict[str, Any]] = None
    reasons: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    tier: str = ''
    rank: int = 0
    message: str = ''
    message_type: str = ''         # 'A' (status follow-up) | 'B' (insight)
    email_body: str = ''           # detailed cover-letter style body (email lane)
    email_subject: str = ''
    resume: str = ''
    channel: str = ''
    panel: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Candidate':
        known = {f for f in cls.__dataclass_fields__}          # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class Score:
    """Deterministic rule score for one candidate."""

    total: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    tier: str = ''
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Draft:
    """A generated message, ready for human review."""

    candidate_name: str
    channel: str
    message: str
    message_type: str
    resume: str
    subject: str = ''
    to_name: str = ''
    to_company: str = ''
    designation: str = ''
    linkedin: str = ''
    applied_company: str = ''
    applied_role: str = ''
    applied_date: str = ''
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalItem:
    """One numbered entry of the human approval bundle."""

    rank: int
    name: str
    channel: str
    designation: str
    their_org: str
    applied_company: str
    applied_role: str
    applied_date: str
    linkedin: str
    resume: str
    message: str
    tier: str = ''
    score: float = 0.0
    email: str = ''
    phone: str = ''
    message_type: str = ''
    subject: str = ''
    email_body: str = ''
    email_subject: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
