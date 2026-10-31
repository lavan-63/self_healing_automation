"""Scan a new page and enrol its ids. Run it against a known-good build.

    python discover.py --page settings --file sample_app/site/v1/settings.html          # preview only
    python discover.py --page settings --file sample_app/site/v1/settings.html --write  # enrol + update seed_config.json
    python discover.py --page settings --url https://app.example/settings --all --write

By default only interactive elements (a, button, input, select, textarea) are listed; --all adds the rest.
Elements already in the repository are skipped, so it is safe to re-run when a page grows.
"""
import argparse
from pathlib import Path

from selenium import webdriver

from healing import Repository
from healing.discovery import INTERACTIVE, suggest_names
from healing.seeding import add_to_config
from healing.snapshot import capture, fingerprint

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True, help="logical page name, e.g. settings")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", help="local html file")
    target.add_argument("--url", help="page url")
    parser.add_argument("--all", action="store_true", help="include non-interactive elements (headings, containers)")
    parser.add_argument("--write", action="store_true", help="enrol into the repository and seed_config.json")
    parser.add_argument("--repo", default=str(ROOT / "repository" / "elements.json"))
    parser.add_argument("--config", default=str(ROOT / "repository" / "seed_config.json"))
    args = parser.parse_args()

    if args.file and not Path(args.file).is_file():
        parser.error(f"file not found: {Path(args.file).resolve()}\n"
                     "for the sample app, build it first: python -m sample_app.build")
    url = Path(args.file).resolve().as_uri() if args.file else args.url
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        if driver.current_url.startswith("chrome-error:"):
            parser.error(f"the browser could not load {url}")
        elements = capture(driver)
    finally:
        driver.quit()
    if not elements:
        parser.error(f"no elements with an id on {url}; nothing to enrol")

    repo = Repository(args.repo)
    known_ids = {e["id"] for e in repo.data["pages"].get(args.page, {}).get("elements", {}).values()}
    taken = set(repo.data["pages"].get(args.page, {}).get("elements", {}))
    wanted = [e for e in elements if (args.all or e["tag"] in INTERACTIVE) and e["id"] not in known_ids]
    names = suggest_names(wanted, taken)

    print(f"{args.page}: {len(elements)} ids on page, {len(wanted)} new\n")
    print(f"{'logical name':<30}{'tag':<10}{'id':<28}text")
    for e in wanted:
        print(f"{args.page + '.' + names[e['id']]:<30}{e['tag']:<10}{e['id']:<28}{e['text'] or e['label']}")

    if not args.write:
        print("\npreview only; add --write to enrol these")
        return
    for e in wanted:
        repo.enrol(args.page, names[e["id"]], e["id"], fingerprint(e), [x["id"] for x in elements], file=url)
        add_to_config(args.config, args.page, names[e["id"]], e["id"], url)
    repo.save()
    print(f"\nenrolled {len(wanted)} elements into {args.repo} and {args.config}")


if __name__ == "__main__":
    main()
