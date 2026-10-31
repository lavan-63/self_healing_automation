"""Re-baseline: bring seed_config.json and each page's stored baseline in line with the repository
after ids have been healed and proposals approved.

    sync_config   no browser: copy the repository's current ids into seed_config.json
    rebaseline    browser:    also re-capture fingerprints and the page's known ids from the live page
"""
import json
from pathlib import Path

from .seeding import page_file
from .snapshot import capture, fingerprint


def load_config(config_path):
    path = Path(config_path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pages": {}}


def save_config(config_path, config):
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def sync_config(repo, config_path):
    """Write the repository's current ids into seed_config.json. Returns the list of changes.

    Unapproved proposals are not included: an element's id only moves once it is applied or approved.
    """
    config = load_config(config_path)
    changes = []
    for page, spec in repo.data["pages"].items():
        cspec = config["pages"].setdefault(page, {"elements": {}})
        if "file" not in cspec and "url" not in cspec:
            source = spec.get("file") or ""
            cspec["url" if "://" in source else "file"] = source
        for name, entry in spec["elements"].items():
            old = cspec["elements"].get(name)
            if old != entry["id"]:
                cspec["elements"][name] = entry["id"]
                changes.append(f"{page}.{name}: {old or '(new)'} -> {entry['id']}")
    save_config(config_path, config)
    return changes


def _target(cspec, site_dir):
    if site_dir:
        if "file" not in cspec and "url" not in cspec:
            return None
        return (Path(site_dir).resolve() / page_file(cspec)).as_uri()
    return cspec.get("url")


def rebaseline(driver, repo, config_path, site_dir=None):
    """Re-capture each page and refresh what is stored for it.

    For every element whose stored id is found on the live page (same tag), the fingerprint is refreshed.
    The page's known-id list is replaced only if *all* its elements were found; otherwise it is left alone,
    because replacing it would hide the new ids that still-unhealed elements need as candidates.
    site_dir: render local pages from this folder (sample app); omit for real apps and use the urls in the config.
    """
    config = load_config(config_path)
    report = {"refreshed": [], "skipped": [], "baseline_updated": [], "baseline_kept": []}
    for page, spec in repo.data["pages"].items():
        target = _target(config["pages"].get(page, {}), site_dir)
        if not target:
            report["skipped"].append(f"{page}: no url in seed_config.json (pass --site-dir for local pages)")
            continue
        driver.get(target)
        by_id = {e["id"]: e for e in capture(driver)}
        unresolved = 0
        for name, entry in spec["elements"].items():
            live = by_id.get(entry["id"])
            if live is None or live["tag"] != entry["fingerprint"]["tag"]:
                unresolved += 1
                report["skipped"].append(f"{page}.{name}: id '{entry['id']}' not found on {target}")
                continue
            entry["fingerprint"] = fingerprint(live)
            report["refreshed"].append(f"{page}.{name}")
        if unresolved:
            report["baseline_kept"].append(page)
        else:
            spec["baseline_ids"] = sorted(by_id)
            report["baseline_updated"].append(page)
    repo.save()
    return report
