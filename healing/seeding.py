"""Build the repository from a known-good build of the app, and keep seed_config.json in step."""
import json
from pathlib import Path
from urllib.parse import urlparse

from .repository import Repository, new_entry
from .snapshot import capture, fingerprint


def page_file(spec):
    """File name of a configured page, whether it was written by hand ("file") or enrolled automatically ("url")."""
    return spec.get("file") or Path(urlparse(spec["url"]).path).name


def seed_repository(driver, config, site_dir, repo_path):
    """config: {"pages": {page: {"file" | "url": ..., "elements": {logical_name: id}}}}

    Pages with a "file" are strict: a missing id is an error (usually a typo).
    Pages with a "url" were added automatically (enrol / discover) and may need a click-path to
    reach some elements, so missing ids are skipped and listed in repo.skipped.
    """
    repo = Repository(repo_path)
    repo.data = {"schema": 1, "pages": {}}
    repo.skipped = []
    for page, spec in config["pages"].items():
        strict = "file" in spec
        driver.get((Path(site_dir).resolve() / spec["file"]).as_uri() if strict else spec["url"])
        by_id = {e["id"]: e for e in capture(driver)}
        elements = {}
        for name, element_id in spec["elements"].items():
            if element_id not in by_id:
                if strict:
                    raise ValueError(f"seed: '{page}.{name}' expects id '{element_id}' but the page has no such id")
                repo.skipped.append(f"{page}.{name}")
                continue
            elements[name] = new_entry(element_id, fingerprint(by_id[element_id]))
        repo.set_page(page, spec.get("file") or spec["url"], by_id.keys(), elements)
    repo.save()
    return repo


def add_to_config(config_path, page, name, element_id, source_url):
    """Record a newly enrolled element. Existing entries are never overwritten:
    the config holds ids as of the last known-good build."""
    path = Path(config_path)
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pages": {}}
    spec = config["pages"].setdefault(page, {"elements": {}})
    if "file" not in spec and "url" not in spec:
        spec["url"] = source_url
    spec["elements"].setdefault(name, element_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
