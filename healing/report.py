"""Self-contained HTML report for the demo: what changed at each stage, and how a run
with the local LLM compares with a deterministic-only run.

    save_run(run, runs_dir)            store one run as JSON (reports/runs/<mode>.json)
    write_report(runs_dir, out_path)   render every stored run into one HTML file
"""
import html
import json
from pathlib import Path

E = html.escape

MODES = ("no_llm", "llm")
STATUS_LABEL = {
    "unchanged": "Unchanged", "healed": "Auto-healed", "resolved": "Resolved (counter id)",
    "needs_review": "Needs review", "failed": "Failed",
}
METHOD_LABEL = {
    "stored id": "Stored id found", "fingerprint": "Fingerprint score", "id_template": "Counter-style id",
    "pending_cache": "Earlier proposal", "llm": "Local LLM", "first_success": "Enrolled",
    "ambiguous": "Ambiguous", "fail": "No candidate", "llm_none": "LLM gave no answer",
}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--muted:#5d6672;--line:#e3e6ea;--accent:#1d5fd1;
--ok:#127a43;--ok-bg:#e2f4ea;--warn:#8a5a00;--warn-bg:#fdf1d8;--bad:#b3261e;--bad-bg:#fbe4e2;
--info:#1d5fd1;--info-bg:#e4edfc;--grey:#5d6672;--grey-bg:#eceff2}
@media (prefers-color-scheme:dark){:root{--bg:#0f1318;--card:#171c23;--ink:#e8ebef;--muted:#9aa4b0;
--line:#272e38;--accent:#8ab4ff;--ok:#5fd493;--ok-bg:#12301f;--warn:#f0c15a;--warn-bg:#352a0f;
--bad:#ff8a80;--bad-bg:#3a1714;--info:#8ab4ff;--info-bg:#15264a;--grey:#9aa4b0;--grey-bg:#222931}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
padding:24px 20px 64px}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:20px;margin:36px 0 12px}
h3{font-size:15px;margin:22px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.sub{color:var(--muted);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.tile .v{font-size:28px;font-weight:700;line-height:1.1}
.tile .l{color:var(--muted);font-size:13px;margin-top:4px}
.tile .n{color:var(--muted);font-size:12px;margin-top:2px}
.tile.good .v{color:var(--ok)}.tile.warn .v{color:var(--warn)}.tile.bad .v{color:var(--bad)}.tile.info .v{color:var(--info)}
.stages{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;counter-reset:s}
.stage{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;position:relative}
.stage:before{counter-increment:s;content:counter(s);position:absolute;top:12px;right:14px;width:24px;height:24px;
border-radius:50%;background:var(--info-bg);color:var(--info);font-weight:700;font-size:13px;display:grid;place-items:center}
.stage b{display:block;margin-bottom:6px;padding-right:30px}
.stage ul{margin:0;padding-left:18px;color:var(--muted);font-size:13.5px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:var(--grey-bg);white-space:nowrap}
tr:last-child td{border-bottom:0}
code{font:12.5px ui-monospace,Consolas,monospace;background:var(--grey-bg);padding:1px 6px;border-radius:5px;white-space:nowrap}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.s-unchanged{background:var(--grey-bg);color:var(--grey)}
.s-healed,.s-resolved{background:var(--ok-bg);color:var(--ok)}
.s-needs_review{background:var(--warn-bg);color:var(--warn)}
.s-failed{background:var(--bad-bg);color:var(--bad)}
.bar{display:inline-block;width:70px;height:7px;border-radius:4px;background:var(--grey-bg);vertical-align:middle;margin-right:6px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--ok)}
.bar.mid i{background:var(--warn)}.bar.low i{background:var(--bad)}
.chk.good{color:var(--ok);font-weight:700}.chk.bad{color:var(--bad);font-weight:700}
.muted{color:var(--muted)}
.note{border-left:4px solid var(--info);background:var(--info-bg);padding:10px 14px;border-radius:0 10px 10px 0;margin:12px 0}
.note.warn{border-color:var(--warn);background:var(--warn-bg)}
.note.good{border-color:var(--ok);background:var(--ok-bg)}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.flow span.step{padding:4px 10px;border-radius:8px;background:var(--grey-bg);font-size:13px}
details{margin:14px 0}
summary{cursor:pointer;color:var(--accent)}
pre{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;font-size:12px}
.badge{display:inline-block;padding:2px 10px;border-radius:8px;background:var(--info-bg);color:var(--info);font-size:12px;font-weight:600;margin-left:8px;vertical-align:middle}
.cmp td.diff{background:var(--warn-bg)}
@media (max-width:600px){body{padding:16px 14px 48px}h1{font-size:22px}}
"""


# ---------------------------------------------------------------- storage
def save_run(run, runs_dir):
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run['mode']}.json").write_text(json.dumps(run, indent=2), encoding="utf-8")


def load_runs(runs_dir):
    runs = {}
    for mode in MODES:
        path = Path(runs_dir) / f"{mode}.json"
        if path.exists():
            runs[mode] = json.loads(path.read_text(encoding="utf-8"))
    return runs


def write_report(runs_dir, out_path):
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(load_runs(runs_dir)), encoding="utf-8")
    return out


# ---------------------------------------------------------------- numbers
def metrics(run):
    rows = run.get("rows", [])
    llm = run.get("llm", {})
    count = lambda status: sum(1 for r in rows if r["status"] == status)
    checked = [r for r in rows if r.get("expected_id") and r.get("new_id")]
    llm_rows = [r for r in rows if r.get("method") == "llm"]
    return {
        "total": len(rows), "unchanged": count("unchanged"), "healed": count("healed"),
        "resolved": count("resolved"), "review": count("needs_review"), "failed": count("failed"),
        "checked": len(checked), "correct": sum(1 for r in checked if r["new_id"] == r["expected_id"]),
        "llm_rows": len(llm_rows),
        "calls": llm.get("calls", 0),
        "tokens": llm.get("prompt_tokens", 0) + llm.get("completion_tokens", 0),
        "duration": run.get("duration_s", 0),
    }


# ---------------------------------------------------------------- pieces
def _tile(label, value, note="", tone=""):
    extra = f'<div class="n">{E(note)}</div>' if note else ""
    return f'<div class="tile {tone}"><div class="v">{E(str(value))}</div><div class="l">{E(label)}</div>{extra}</div>'


def _bar(conf):
    conf = max(0.0, min(100.0, float(conf or 0)))
    tone = "" if conf >= 90 else ("mid" if conf >= 70 else "low")
    return f'<span class="bar {tone}"><i style="width:{conf:.0f}%"></i></span>{conf:g}'


def _pill(status):
    return f'<span class="pill s-{E(status)}">{E(STATUS_LABEL.get(status, status))}</span>'


def _row_html(r):
    check = ""
    if r.get("expected_id") and r.get("new_id"):
        if r["new_id"] == r["expected_id"]:
            check = ' <span class="chk good">&#10003;</span>'
        else:
            check = f' <span class="chk bad">&#10007; expected {E(r["expected_id"])}</span>'
    chosen = f"<code>{E(r['new_id'])}</code>{check}" if r.get("new_id") else '<span class="muted">none</span>'
    expected = f"<code>{E(r['expected_id'])}</code>" if r.get("expected_id") else '<span class="muted">n/a</span>'
    before, after = r.get("version_before", 1), r.get("version_after", 1)
    version = f"v{before} &rarr; v{after}" if after != before else f"v{after}"
    if r["status"] == "needs_review":
        version += ' <span class="muted">(proposal, not applied)</span>'
    tokens = r.get("llm_tokens", 0)
    return (
        f"<tr><td><b>{E(r['key'])}</b></td><td><code>{E(r['old_id'])}</code></td><td>{expected}</td>"
        f"<td>{chosen}</td><td>{_pill(r['status'])}</td>"
        f"<td>{E(METHOD_LABEL.get(r.get('method'), str(r.get('method'))))}</td>"
        f"<td>{_bar(r.get('confidence'))}</td><td>{version}</td>"
        f"<td>{r.get('ms', 0)} ms{f' &middot; {tokens} tok' if tokens else ''}</td>"
        f"<td class='muted'>{E(r.get('reason', ''))}</td></tr>"
    )


def _run_section(run):
    m = metrics(run)
    llm = run.get("llm", {})
    seed = run.get("seed", {})
    versions_up = sum(1 for r in run["rows"] if r.get("version_after", 1) > r.get("version_before", 1))
    parts = [f'<h2>{E(run["label"])}<span class="badge">{E(run.get("started_at", ""))}</span></h2>']

    parts.append('<div class="tiles">' + "".join([
        _tile("elements checked", m["total"]),
        _tile("healed without AI", m["healed"] + m["resolved"], "auto-applied", "good"),
        _tile("needs review", m["review"], "queued for approval", "warn" if m["review"] else ""),
        _tile("failed", m["failed"], "", "bad" if m["failed"] else ""),
        _tile("correct vs. ground truth", f"{m['correct']}/{m['checked']}", "sample app knows the answer",
              "good" if m["checked"] and m["correct"] == m["checked"] else "bad"),
        _tile("LLM calls", m["calls"], "enabled" if llm.get("enabled") else "disabled", "info"),
        _tile("LLM tokens", m["tokens"], "prompt + reply", "info"),
        _tile("duration", f"{m['duration']:.1f}s", "healing pass"),
    ]) + "</div>")

    parts.append("<h3>What happened at each stage</h3>")
    pages = ", ".join(f"{E(p)} ({n})" for p, n in seed.get("pages", {}).items())
    stage_items = [
        ("Developers rename ids", [f"{len(run.get('dev_changes', []))} tracked ids renamed v1 &rarr; v2",
                                   "only the id attribute changed; text, class, structure did not"]),
        ("Seed from v1", [f"{seed.get('elements', 0)} elements fingerprinted", f"pages: {pages}",
                          "every element starts at version 1"]
         + ([f"skipped: {E(', '.join(seed['skipped']))}"] if seed.get("skipped") else [])),
        ("Run tests on v2", [f"{m['healed']} auto-healed, {m['resolved']} counter-style resolved",
                             f"{m['review']} sent to review, {m['failed']} failed",
                             f"LLM {'enabled: ' + E(str(llm.get('model'))) if llm.get('enabled') else 'not used'}"]),
        ("Repository after the run", [f"{versions_up} elements moved to a new version",
                                      f"{m['review']} pending proposals waiting for approval",
                                      "next: review.py approve, then rebaseline.py"]),
    ]
    parts.append('<div class="stages">' + "".join(
        f'<div class="stage"><b>{title}</b><ul>' + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>"
        for title, items in stage_items) + "</div>")

    if llm.get("enabled"):
        if llm.get("calls", 0) == 0:
            parts.append('<div class="note good"><b>The LLM was available but never called.</b> The deterministic '
                         "rungs (stored id, counter-style id, fingerprint scoring) resolved every element, so "
                         "0 tokens were spent.</div>")
        else:
            parts.append(f'<div class="note">The LLM was asked {llm["calls"]} time(s): '
                         f'{llm.get("prompt_tokens", 0)} prompt + {llm.get("completion_tokens", 0)} reply tokens. '
                         "Its answers are never applied automatically; they go to review.</div>")
        if llm.get("error"):
            parts.append(f'<div class="note warn">LLM problem: {E(str(llm["error"]))}. '
                         "Is Ollama running and the model pulled?</div>")

    parts.append("<h3>Element by element</h3>")
    parts.append('<div class="scroll"><table><thead><tr><th>Element</th><th>Seeded id (v1)</th>'
                 "<th>Developers changed it to</th><th>Framework chose</th><th>Result</th><th>How</th>"
                 "<th>Confidence</th><th>Version</th><th>Time</th><th>Reason</th></tr></thead><tbody>"
                 + "".join(_row_html(r) for r in run["rows"]) + "</tbody></table></div>")
    parts.append(f"<details><summary>Raw run data (JSON)</summary><pre>{E(json.dumps(run, indent=2))}</pre></details>")
    return "".join(parts)


def _comparison(a, b):
    ma, mb = metrics(a), metrics(b)
    lines = [
        ("Healed automatically", ma["healed"] + ma["resolved"], mb["healed"] + mb["resolved"]),
        ("Needs review", ma["review"], mb["review"]),
        ("Failed", ma["failed"], mb["failed"]),
        ("Correct vs. ground truth", f"{ma['correct']}/{ma['checked']}", f"{mb['correct']}/{mb['checked']}"),
        ("Resolved by the LLM", ma["llm_rows"], mb["llm_rows"]),
        ("LLM calls", ma["calls"], mb["calls"]),
        ("LLM tokens", ma["tokens"], mb["tokens"]),
        ("Healing pass duration", f"{ma['duration']:.1f}s", f"{mb['duration']:.1f}s"),
    ]
    body = "".join(
        f"<tr><td>{E(name)}</td><td{'' if x == y else ' class=diff'}>{E(str(x))}</td>"
        f"<td{'' if x == y else ' class=diff'}>{E(str(y))}</td></tr>" for name, x, y in lines)
    rows_b = {r["key"]: r for r in b["rows"]}
    diffs = []
    for ra in a["rows"]:
        rb = rows_b.get(ra["key"])
        if rb and (ra["status"], ra["new_id"], ra.get("method")) != (rb["status"], rb["new_id"], rb.get("method")):
            diffs.append(
                f"<tr><td><b>{E(ra['key'])}</b></td><td>{_pill(ra['status'])} <code>{E(str(ra['new_id']))}</code> "
                f"<span class='muted'>{E(METHOD_LABEL.get(ra.get('method'), str(ra.get('method'))))}</span></td>"
                f"<td>{_pill(rb['status'])} <code>{E(str(rb['new_id']))}</code> "
                f"<span class='muted'>{E(METHOD_LABEL.get(rb.get('method'), str(rb.get('method'))))}</span></td></tr>")
    if diffs:
        diff_html = ('<h3>Elements where the outcome differs</h3><div class="scroll"><table><thead><tr>'
                     f"<th>Element</th><th>{E(a['label'])}</th><th>{E(b['label'])}</th></tr></thead><tbody>"
                     + "".join(diffs) + "</tbody></table></div>")
    else:
        diff_html = ('<div class="note good"><b>No element ended up differently.</b> Both runs reached the same '
                     "result for every element. Adding the LLM changed nothing here because the deterministic "
                     "rungs had already resolved everything.</div>")
    return ('<h2>Side by side</h2><div class="scroll"><table class="cmp"><thead><tr><th>Measure</th>'
            f"<th>{E(a['label'])}</th><th>{E(b['label'])}</th></tr></thead><tbody>{body}</tbody></table></div>"
            + diff_html)


def render_html(runs):
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>Healing Demo Report</title><style>{CSS}</style></head><body><div class=\"wrap\">",
           "<h1>Self-healing demo report</h1>"]
    if not runs:
        out.append('<p class="sub">No runs recorded yet. Run <code>python run_demo.py</code> first.</p>')
    else:
        out.append('<p class="sub">Sample app: v1 is the baseline, v2 is the same app with only the id attributes '
                   "renamed. Each run seeds a fresh repository from v1, then heals against v2.</p>")
        out.append('<div class="flow"><span class="step">1 stored id</span>&rarr;<span class="step">2 counter-style id'
                   '</span>&rarr;<span class="step">3 fingerprint scoring</span>&rarr;<span class="step">'
                   "4 local LLM (only if ambiguous)</span>&rarr;<span class=\"step\">5 fail with candidates</span></div>")
        if "no_llm" in runs and "llm" in runs:
            out.append(_comparison(runs["no_llm"], runs["llm"]))
        elif len(runs) == 1:
            other = "python run_demo.py --llm" if "no_llm" in runs else "python run_demo.py"
            out.append(f'<div class="note">Run <code>{other}</code> as well to add a side-by-side comparison.</div>')
        for mode in MODES:
            if mode in runs:
                out.append(_run_section(runs[mode]))
    out.append("</div></body></html>")
    return "".join(out)
