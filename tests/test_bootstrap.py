"""Issue 0 skeleton smoke tests: package imports, CLI stubs, anonymizer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import anonymize  # noqa: E402
from tokenlens import cli  # noqa: E402


def test_package_imports():
    import tokenlens
    import tokenlens.classify  # noqa: F401
    import tokenlens.forensics  # noqa: F401
    import tokenlens.ingest  # noqa: F401
    import tokenlens.pricing  # noqa: F401
    import tokenlens.pricing.engine  # noqa: F401
    import tokenlens.reconcile  # noqa: F401
    import tokenlens.reconcile.api_client  # noqa: F401
    import tokenlens.reconcile.tieout  # noqa: F401
    import tokenlens.report  # noqa: F401

    assert tokenlens.__version__


def test_cli_stub_commands_exit_2(capsys):
    for command in ("reconcile", "audit"):
        assert cli.main([command]) == 2
        assert "not implemented" in capsys.readouterr().err


def test_anonymizer_strips_content_keeps_usage(tmp_path):
    source = tmp_path / "projects" / "-Users-someone-secret-project"
    source.mkdir(parents=True)
    entry = {
        "type": "assistant",
        "uuid": "u1",
        "sessionId": "s1",
        "version": "1.0.44",
        "timestamp": "2026-07-01T10:00:00.000Z",
        "cwd": "/Users/someone/secret-project",
        "gitBranch": "feature/secret",
        "requestId": "req_1",
        "message": {
            "id": "msg_1",
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "SENSITIVE PROSE"},
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"path": "/x"}},
            ],
            "usage": {
                "input_tokens": 5,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 200,
                "output_tokens": 42,
            },
        },
    }
    (source / "session.jsonl").write_text(
        json.dumps(entry) + "\n" + "{not json\n", encoding="utf-8"
    )
    dest = tmp_path / "corpus"
    manifest = anonymize.snapshot(tmp_path / "projects", dest)

    (out_file,) = [p for p in dest.rglob("*.jsonl")]
    text = out_file.read_text()
    # Content, cwd, and branch are gone; usage and structure survive.
    assert "SENSITIVE PROSE" not in text
    assert "secret" not in text  # neither cwd nor the project dir name leaks
    assert "gitBranch" not in text
    lines = text.splitlines()
    assert lines[1] == anonymize.MALFORMED_MARKER
    kept = json.loads(lines[0])
    assert kept["message"]["usage"]["output_tokens"] == 42
    assert kept["message"]["content"][1] == {"type": "tool_use", "id": "toolu_1", "name": "Read"}
    assert (dest / "manifest.json").exists()
    assert manifest["files"][str(out_file.relative_to(dest))]["malformed"] == 1


def test_anonymizer_is_deterministic(tmp_path):
    source = tmp_path / "projects" / "-some-project-dir"
    source.mkdir(parents=True)
    (source / "a.jsonl").write_text('{"type": "user", "uuid": "u1"}\n', encoding="utf-8")
    dest1, dest2 = tmp_path / "one", tmp_path / "two"
    anonymize.snapshot(tmp_path / "projects", dest1)
    anonymize.snapshot(tmp_path / "projects", dest2)
    files1 = {p.relative_to(dest1): p.read_text() for p in dest1.rglob("*") if p.is_file()}
    files2 = {p.relative_to(dest2): p.read_text() for p in dest2.rglob("*") if p.is_file()}
    assert files1 == files2
