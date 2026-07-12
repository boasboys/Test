.PHONY: test lint corpus lab audit

test: lint
	python3 -m pytest

lint:
	ruff check src tests scripts

corpus:
	python3 scripts/anonymize.py

lab:
	python3 scripts/build_lab.py

audit:
	python3 -m tokenlens.cli audit
