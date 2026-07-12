.PHONY: test lint corpus lab audit

test: lint
	python3 -m pytest

lint:
	ruff check src tests scripts

corpus:
	python3 scripts/anonymize.py

lab:
	@echo "make lab: not implemented yet — lands with Issue 10 (docs/issues/issue-10.md)."
	@exit 1

audit:
	@echo "make audit: not implemented yet — lands with Issue 9 (docs/issues/issue-09.md)."
	@exit 1
