# Lab corpus

`raw/` holds the anonymized snapshot of the founder's `~/.claude/projects`,
produced by `make corpus` (`scripts/anonymize.py`). It is **gitignored** and
**append-only**: re-snapshot weekly, never edit files in place.

Content is stripped before anything lands here — only structure, usage
metadata, timestamps, and model/version fields survive.
