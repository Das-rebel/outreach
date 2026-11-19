"""outreach_engine — v2 outreach architecture.

One deterministic, rule-first, human-gated outreach pipeline replacing the
ad-hoc scripts in `runs/outreach/`.  See `docs/adr/002-outreach-engine-architecture.md`.

Public surface is intentionally small: everything goes through `cli.main()`.
"""

__version__ = '2.0.0'
