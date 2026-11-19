"""Pluggable multi-model decision panel.

The panel is a SECOND opinion on top of the deterministic rules.  It may only
DEMOTE or RE-ORDER a candidate that already passed every hard gate — it can
never resurrect a blocked candidate and it can never bypass a reason code
(see `eligibility.py`).  This is rule R57.

Backends
    RULES_ONLY  deterministic fallback, always available, no external calls
    CLI_PANEL   shells out to an external multi-model CLI when one is present
                (`tmlpd`, `agent`, or `ollama run <model>`), with a timeout.
                On timeout / missing CLI / unparsable output it degrades to
                RULES_ONLY and logs the degradation.

Every backend returns verdicts of the shape:

    {"keep": bool, "reason": str, "angle": str, "confidence": float}
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Dict, List, Optional

from .identity import candidate_keys, norm_key

PANEL_PROMPT_HEADER = (
    'You are triaging outreach targets for a job application. For each target '
    'decide whether to message them, the single best angle, and your '
    'confidence. Reply with ONLY a JSON array of objects with keys '
    '"name", "company", "keep" (true/false), "reason", "angle", '
    '"confidence" (0-1).'
)


class Verdict(dict):
    """A panel verdict (a plain dict with attribute-ish helpers)."""

    @property
    def keep(self) -> bool:
        return bool(self.get('keep', True))

    @property
    def reason(self) -> str:
        return str(self.get('reason') or '')

    @property
    def angle(self) -> str:
        return str(self.get('angle') or '')

    @property
    def confidence(self) -> float:
        try:
            return float(self.get('confidence', 0.0))
        except (TypeError, ValueError):
            return 0.0


def _verdict(keep: bool, reason: str, angle: str = '', confidence: float = 1.0) -> Verdict:
    return Verdict({'keep': keep, 'reason': reason, 'angle': angle,
                    'confidence': confidence})


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

class RulesOnlyBackend:
    """Deterministic no-model backend — every candidate is kept."""

    name = 'RULES_ONLY'

    def available(self) -> bool:
        return True

    def rank(self, candidates: List, k: int = 20) -> Dict[str, Verdict]:
        out: Dict[str, Verdict] = {}
        for cand in candidates:
            for key in candidate_keys(cand):
                out.setdefault(key, _verdict(True, 'rules-only: no panel available',
                                             confidence=0.0))
                break
        return out


class CliPanelBackend:
    """Shell out to an external multi-model CLI.

    The CLI is expected to print a JSON array of verdicts.  Any failure —
    binary missing, non-zero exit, timeout, unparsable output — degrades to
    the rules-only backend and is logged through `ctx.warn`.
    """

    name = 'CLI_PANEL'

    def __init__(self, cfg, ctx=None):
        self.cfg = cfg
        self.ctx = ctx

    # -- backend discovery -------------------------------------------------
    def _bin(self) -> Optional[str]:
        for name in ('tmlpd', 'agent', 'ollama'):
            path = shutil.which(name)
            if path:
                return name
        return None

    def available(self) -> bool:
        return self._bin() is not None

    def _cmd(self, bin_name: str, prompt: str) -> List[str]:
        if bin_name == 'tmlpd':
            return ['tmlpd', 'run', '-p', prompt]
        if bin_name == 'agent':
            return ['agent', '--print', prompt]
        # ollama
        model = (self.cfg.panel_models or ['qwen2.5-coder:1.5b'])[0]
        return ['ollama', 'run', model, prompt]

    # -- invocation -------------------------------------------------------
    def rank(self, candidates: List, k: int = 20) -> Dict[str, Verdict]:
        bin_name = self._bin()
        if not bin_name:
            self._warn('no panel CLI found (tmlpd/agent/ollama) — rules only')
            return RulesOnlyBackend().rank(candidates, k)

        payload = [{
            'name': c.name,
            'company': c.applied_company or c.company,
            'role': c.applied_role,
            'designation': c.contact_title,
            'linkedin': c.linkedin,
            'sources': list(c.sources or []),
            'score': getattr(c, 'score', None) or {},
        } for c in candidates[:max(k, 1) * 3]]

        prompt = PANEL_PROMPT_HEADER + '\n\n' + json.dumps(payload, indent=1)
        cmd = self._cmd(bin_name, prompt)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.cfg.panel_timeout_s)
        except subprocess.TimeoutExpired:
            self._warn('panel CLI timeout after %ss — rules only'
                       % self.cfg.panel_timeout_s)
            return RulesOnlyBackend().rank(candidates, k)
        except (OSError, subprocess.SubprocessError) as exc:
            self._warn('panel CLI failed (%s) — rules only' % type(exc).__name__)
            return RulesOnlyBackend().rank(candidates, k)

        if proc.returncode != 0:
            self._warn('panel CLI rc=%s — rules only' % proc.returncode)
            return RulesOnlyBackend().rank(candidates, k)

        parsed = self._parse(proc.stdout)
        if parsed is None:
            self._warn('panel CLI output unparsable — rules only')
            return RulesOnlyBackend().rank(candidates, k)

        out: Dict[str, Verdict] = {}
        by_name = {}
        for cand in candidates:
            by_name.setdefault(norm_key(cand.name), cand)
        for row in parsed:
            if not isinstance(row, dict):
                continue
            name = norm_key(str(row.get('name') or ''))
            cand = by_name.get(name)
            if cand is None:
                continue
            verdict = _verdict(
                keep=bool(row.get('keep', True)),
                reason=str(row.get('reason') or 'panel'),
                angle=str(row.get('angle') or ''),
                confidence=float(row.get('confidence') or 0.0),
            )
            for key in candidate_keys(cand):
                out.setdefault(key, verdict)
                break
        # candidates the panel said nothing about stay (panel may only demote)
        for cand in candidates:
            if not any(k in out for k in candidate_keys(cand)):
                for key in candidate_keys(cand):
                    out.setdefault(key, _verdict(True, 'panel silent — kept',
                                                 confidence=0.0))
                    break
        self._warn('panel verdicts: %d' % len(out))
        return out

    @staticmethod
    def _parse(text: str) -> Optional[List]:
        if not text:
            return None
        text = text.strip()
        start = text.find('[')
        end = text.rfind(']')
        if start >= 0 and end > start:
            text = text[start:end + 1]
        else:
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                text = '[%s]' % text[start:end + 1]
            else:
                return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None

    def _warn(self, message: str) -> None:
        if self.ctx is not None and hasattr(self.ctx, 'warn'):
            self.ctx.warn('llm_panel', message)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def get_backend(cfg, ctx=None):
    """Return the configured panel backend."""
    backend = (cfg.panel_backend or 'rules_only').strip().lower()
    if backend in ('cli_panel', 'cli', 'panel'):
        cli = CliPanelBackend(cfg, ctx)
        return cli
    return RulesOnlyBackend()


def run_panel(cfg, ctx, candidates: List, k: int = 20) -> Dict[str, Verdict]:
    backend = get_backend(cfg, ctx)
    verdicts = backend.rank(candidates, k)
    return verdicts


def apply_panel(verdicts: Dict[str, Verdict], candidates: List):
    """Apply panel verdicts to an already-eligible candidate list.

    The panel may only DEMOTE (keep=False removes) and RE-ORDER (a confident
    verdict with an angle is bubbled up).  It can never ADD a candidate.
    """
    kept = []
    demoted = []
    for cand in candidates:
        verdict = None
        for key in candidate_keys(cand):
            if key in verdicts:
                verdict = verdicts[key]
                break
        if verdict is None or verdict.keep:
            cand.panel = dict(verdict) if verdict else {}
            kept.append(cand)
        else:
            cand.panel = dict(verdict)
            cand.reasons = list(cand.reasons or []) + ['panel_demoted']
            demoted.append(cand)
    return kept, demoted
