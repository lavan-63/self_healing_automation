"""End-to-end demo: seed from v1, run against v2 (ids renamed), print what healed, write an HTML report.

    python run_demo.py            # deterministic only (no LLM)
    python run_demo.py --llm      # also allow the local Ollama tie-breaker
    python run_demo.py --open     # open reports/demo_report.html afterwards

Run it both ways: the report puts the two runs side by side.
"""
import argparse
import json
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from selenium import webdriver

from healing import ElementHealingError, OllamaTiebreaker, SelfHealingDriver, seed_repository
from healing.report import save_run, write_report
from healing.seeding import page_file
from sample_app import build

ROOT = Path(__file__).resolve().parent
REPO_PATH = ROOT / "repository" / "elements.json"
RUNS_DIR = ROOT / "reports" / "runs"
REPORT_PATH = ROOT / "reports" / "demo_report.html"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="enable the Ollama tie-breaker")
    parser.add_argument("--model", default="qwen2.5:1.5b")
    parser.add_argument("--open", action="store_true", help="open the HTML report when done")
    args = parser.parse_args()

    build.main()
    site = build.HERE / "site"
    # fixed v1 ids, so the demo keeps working after rebaseline.py has updated repository/seed_config.json
    config = read_json(build.HERE / "demo_seed.json")
    ids_v1, ids_v2 = read_json(build.HERE / "ids_v1.json"), read_json(build.HERE / "ids_v2.json")
    expected = {ids_v1[k]: ids_v2[k] for k in ids_v1}          # v1 id -> what the developers renamed it to

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    rows = []
    try:
        print("1. seeding repository from v1 ...")
        repo = seed_repository(driver, config, site / "v1", REPO_PATH)
        before = {f"{p}.{n}": (e["id"], e["version"]) for p, s in repo.data["pages"].items()
                  for n, e in s["elements"].items()}
        seed_info = {"pages": {p: len(s["elements"]) for p, s in repo.data["pages"].items()},
                     "elements": len(before), "skipped": getattr(repo, "skipped", [])}

        llm = OllamaTiebreaker(args.model) if args.llm else None
        healer = SelfHealingDriver(driver, repo, llm=llm)
        print("2. running against v2 (ids renamed) ...")
        started = time.perf_counter()
        for page, spec in config["pages"].items():
            driver.get((site / "v2" / page_file(spec)).as_uri())
            for name in spec["elements"]:
                key = f"{page}.{name}"
                seen = len(healer.events)
                t0 = time.perf_counter()
                try:
                    healer.find(key)
                except ElementHealingError:
                    pass                                      # recorded as a "failed" event; keep going
                ms = round((time.perf_counter() - t0) * 1000)
                entry = repo.get(page, name)
                old_id, version_before = before[key]
                event = healer.events[seen] if len(healer.events) > seen else None
                rows.append({
                    "key": key, "old_id": old_id, "expected_id": expected.get(old_id),
                    "new_id": event["new_id"] if event else entry["id"],
                    "status": event["status"] if event else "unchanged",
                    "method": event["method"] if event else "stored id",
                    "confidence": event["confidence"] if event else 100.0,
                    "reason": event["reason"] if event else "stored id found on the page",
                    "llm_tokens": event["llm_tokens"] if event else 0,
                    "ms": ms, "version_before": version_before, "version_after": entry["version"],
                })
        duration = time.perf_counter() - started
        repo.save()
    finally:
        driver.quit()

    summary = healer.summary()
    run = {
        "mode": "llm" if args.llm else "no_llm",
        "label": f"With LLM ({args.model})" if args.llm else "Deterministic only",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(duration, 2),
        "seed": seed_info,
        "dev_changes": [{"key": r["key"], "old_id": r["old_id"], "expected_id": r["expected_id"]} for r in rows],
        "rows": rows,
        "llm": {"enabled": bool(llm), "model": args.model if llm else None,
                "calls": llm.stats["calls"] if llm else 0,
                "prompt_tokens": llm.stats["prompt_tokens"] if llm else 0,
                "completion_tokens": llm.stats["completion_tokens"] if llm else 0,
                "error": llm.last_error if llm else None},
    }
    save_run(run, RUNS_DIR)
    report = write_report(RUNS_DIR, REPORT_PATH)

    print(f"\n{'element':<30}{'status':<14}{'method':<14}{'conf':>6}  old id -> new id")
    for r in rows:
        print(f"{r['key']:<30}{r['status']:<14}{r['method']:<14}{r['confidence']:>6}  {r['old_id']} -> {r['new_id']}")
    print(f"\ncounts: {summary['counts']}   LLM tokens used: {summary['llm_tokens']}")
    print(f"repository written to {REPO_PATH}")
    print(f"report written to {report}")
    if args.open:
        webbrowser.open(report.as_uri())


if __name__ == "__main__":
    main()
