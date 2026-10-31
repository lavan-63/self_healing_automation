"""Run after heals have been reviewed, against a green run of the current build.

    python rebaseline.py --site-dir sample_app/site/v2   # sample app: re-capture from the v2 pages
    python rebaseline.py                                 # real app: re-capture from the urls in seed_config.json
    python rebaseline.py --config-only                   # no browser: only copy current ids into seed_config.json

What it does:
  1. refreshes each element's stored fingerprint from the live page (if its current id is found there)
  2. replaces a page's known-id list, but only when every element on that page was found
  3. writes the repository's current ids into seed_config.json

Unapproved proposals are left out of seed_config.json until you run `python review.py approve ...`.
"""
import argparse
from pathlib import Path

from healing import Repository
from healing.rebaseline import rebaseline, sync_config

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT / "repository" / "elements.json"))
    parser.add_argument("--config", default=str(ROOT / "repository" / "seed_config.json"))
    parser.add_argument("--site-dir", help="folder holding the current build of local html pages")
    parser.add_argument("--config-only", action="store_true", help="skip the browser; just sync ids")
    args = parser.parse_args()

    repo = Repository(args.repo)
    if not args.config_only:
        from selenium import webdriver

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        try:
            report = rebaseline(driver, repo, args.config, args.site_dir)
        finally:
            driver.quit()
        print(f"fingerprints refreshed: {len(report['refreshed'])}")
        print(f"pages with baseline updated: {', '.join(report['baseline_updated']) or 'none'}")
        if report["baseline_kept"]:
            print(f"pages with baseline kept (some elements not found): {', '.join(report['baseline_kept'])}")
        for line in report["skipped"]:
            print(f"  skipped: {line}")

    changes = sync_config(repo, args.config)
    print(f"\nseed_config.json updated for {len(changes)} element(s)")
    for line in changes:
        print(f"  {line}")
    pending = repo.pending()
    if pending:
        print(f"\n{len(pending)} proposal(s) still unapproved and not written to the config: python review.py list")


if __name__ == "__main__":
    main()
