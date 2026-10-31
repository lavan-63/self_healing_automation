"""Versioned element repository (one JSON file). Every id change is a history entry."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_entry(element_id, fp):
    return {
        "id": element_id, "fingerprint": fp, "version": 1,
        "history": [{"version": 1, "id": element_id, "fingerprint": fp, "method": "seed",
                     "confidence": 100.0, "reason": "baseline capture", "at": _now()}],
        "stats": {"runs": 0, "heals": 0},
    }


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"schema": 1, "pages": {}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- lookups -------------------------------------------------------
    def page(self, page):
        return self.data["pages"][page]

    def elements(self, page):
        return self.data["pages"][page]["elements"]

    def get(self, page, name):
        try:
            return self.data["pages"][page]["elements"][name]
        except KeyError:
            raise KeyError(f"unknown element '{page}.{name}' - add it to repository/seed_config.json") from None

    def lookup(self, page, name):
        """Like get(), but None instead of an error when the element is not enrolled yet."""
        return self.data["pages"].get(page, {}).get("elements", {}).get(name)

    def set_page(self, page, file, baseline_ids, elements):
        self.data["pages"][page] = {"file": file, "baseline_ids": sorted(baseline_ids), "elements": elements}

    def enrol(self, page, name, element_id, fp, page_ids, file=None):
        """Add one element (and every id currently on the page) to a known-good baseline."""
        spec = self.data["pages"].setdefault(page, {"file": file, "baseline_ids": [], "elements": {}})
        spec["baseline_ids"] = sorted(set(spec["baseline_ids"]) | set(page_ids))
        spec["elements"][name] = new_entry(element_id, fp)

    # ---- writes --------------------------------------------------------
    def touch(self, entry):
        entry["stats"]["runs"] += 1

    def set_dynamic(self, entry, new_id):
        """Counter-style ids change every run; track the latest value without bumping the version."""
        entry["id"] = new_id
        entry["dynamic"] = True

    def apply_heal(self, entry, new_id, fp, method, confidence, reason):
        entry["version"] += 1
        entry["id"], entry["fingerprint"] = new_id, fp
        entry["stats"]["heals"] += 1
        entry.pop("pending", None)
        entry["history"].append({"version": entry["version"], "id": new_id, "fingerprint": fp,
                                 "method": method, "confidence": confidence, "reason": reason, "at": _now()})

    def set_pending(self, entry, new_id, fp, method, confidence, reason):
        entry["pending"] = {"id": new_id, "fingerprint": fp, "method": method,
                            "confidence": confidence, "reason": reason, "at": _now()}

    def approve(self, page, name):
        entry = self.get(page, name)
        p = entry.get("pending")
        if not p:
            raise ValueError(f"{page}.{name} has no pending proposal")
        self.apply_heal(entry, p["id"], p["fingerprint"], p["method"] + "+approved", p["confidence"], p["reason"])

    def reject(self, page, name):
        entry = self.get(page, name)
        p = entry.pop("pending", None)
        if not p:
            raise ValueError(f"{page}.{name} has no pending proposal")
        entry.setdefault("rejected", []).append(p["id"])

    def rollback(self, page, name):
        entry = self.get(page, name)
        earlier = [h for h in entry["history"][:-1] if h["id"] != entry["id"]]
        if not earlier:
            raise ValueError(f"{page}.{name} has no earlier version to roll back to")
        target = earlier[-1]
        self.apply_heal(entry, target["id"], target["fingerprint"], "rollback", 100.0,
                        f"rolled back to v{target['version']}")

    def pending(self):
        return [(page, name, e["pending"]) for page, spec in self.data["pages"].items()
                for name, e in spec["elements"].items() if e.get("pending")]
