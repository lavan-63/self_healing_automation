"""Browser-free tests for the HTML report."""
from healing.report import load_runs, metrics, render_html, save_run, write_report


def row(key, new_id, status="healed", method="fingerprint", expected=None, **kw):
    base = {"key": key, "old_id": "old-" + key, "expected_id": expected or new_id, "new_id": new_id,
            "status": status, "method": method, "confidence": 100.0, "reason": "same text",
            "llm_tokens": 0, "ms": 12, "version_before": 1, "version_after": 2}
    base.update(kw)
    return base


def make_run(mode, rows, calls=0, tokens=0):
    return {"mode": mode, "label": "Deterministic only" if mode == "no_llm" else "With LLM (qwen2.5:1.5b)",
            "started_at": "2026-11-01 10:00:00", "duration_s": 3.2,
            "seed": {"pages": {"login": len(rows)}, "elements": len(rows), "skipped": []},
            "dev_changes": [], "rows": rows,
            "llm": {"enabled": mode == "llm", "model": "qwen2.5:1.5b" if mode == "llm" else None,
                    "calls": calls, "prompt_tokens": tokens, "completion_tokens": 0, "error": None}}


def test_metrics_count_statuses_and_correctness():
    run = make_run("no_llm", [
        row("a.x", "n1"), row("a.y", "n2", status="needs_review"),
        row("a.z", "wrong", expected="right"), row("a.w", None, status="failed", expected="q")])
    m = metrics(run)
    assert (m["healed"], m["review"], m["failed"]) == (2, 1, 1)
    assert (m["checked"], m["correct"]) == (3, 2)        # the failed row has no choice to check


def test_report_escapes_untrusted_text():
    run = make_run("no_llm", [row("a.x", "n1", reason="<script>alert(1)</script>")])
    html = render_html({"no_llm": run})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_single_run_suggests_the_other_one():
    assert "run_demo.py --llm" in render_html({"no_llm": make_run("no_llm", [row("a.x", "n1")])})


def test_comparison_says_nothing_differs_when_outcomes_match():
    rows = [row("a.x", "n1")]
    html = render_html({"no_llm": make_run("no_llm", rows), "llm": make_run("llm", rows)})
    assert "Side by side" in html and "No element ended up differently" in html
    assert "never called" in html                    # LLM enabled, zero calls


def test_comparison_lists_elements_that_differ():
    a = make_run("no_llm", [row("a.x", None, status="failed", method="fail")])
    b = make_run("llm", [row("a.x", "n1", status="needs_review", method="llm", llm_tokens=300)], calls=1, tokens=300)
    html = render_html({"no_llm": a, "llm": b})
    assert "Elements where the outcome differs" in html and "Local LLM" in html


def test_save_load_and_write(tmp_path):
    save_run(make_run("llm", [row("a.x", "n1")]), tmp_path / "runs")
    assert list(load_runs(tmp_path / "runs")) == ["llm"]
    out = write_report(tmp_path / "runs", tmp_path / "out" / "r.html")
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_empty_report_tells_you_what_to_do(tmp_path):
    assert "python run_demo.py" in render_html({})
