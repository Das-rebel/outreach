"""Source adapters.

Every adapter exposes `fetch(ctx) -> list[Candidate]` and MUST be safe to run
when its data file or API is missing: it returns `[]` and appends a warning to
`ctx.warnings` rather than raising.  A missing node never breaks the pipeline.
"""
from __future__ import annotations

from . import tracker, happenstance, apollo, linkedin, gmail, jobspy, suppression

ADAPTERS = (
    ('tracker', tracker.fetch),
    ('happenstance', happenstance.fetch),
    ('apollo', apollo.fetch),
    ('linkedin', linkedin.fetch),
    ('gmail', gmail.fetch),
    ('jobspy', jobspy.fetch),
    ('suppression', suppression.fetch),
)

__all__ = ['ADAPTERS', 'tracker', 'happenstance', 'apollo', 'linkedin',
           'gmail', 'jobspy', 'suppression']
