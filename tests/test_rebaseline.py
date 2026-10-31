"""Browser-free tests for re-baselining, using a fake driver that serves canned captures."""
import json

from healing.rebaseline import rebaseline, sync_config
from healing.repository import Repository
from healing.snapshot import fingerprint


def el(id_, **kw):
    base = {"id": id_, "tag": "button", "type": "button", "name": "", "cls": "btn", "text": "Save",
            "label": "", "placeholder": "", "role": "", "href": "", "ctx": "Notifications",
            "path": ["body", "main"], "prev": "", "next": "", "visible": True}
    base.update(kw)
    return base


class FakeDriver:
    def __init__(self, pages):
        self.pages, self.current = pages, None

    def get(self, url):
        self.current = url

    def execute_script(self, _js):
        return self.pages[self.current]


def make_repo(tmp_path):
    repo = Repository(tmp_path / "elements.json")
    repo.enrol("settings", "save", "notif-save", fingerprint(el("notif-save")), ["notif-save", "other"], file="http://app/s")
    repo.enrol("settings", "delete_account", "delete-account",
               fingerprint(el("delete-account", text="Delete account")), ["delete-account"], file="http://app/s")
    return repo


def write_config(tmp_path):
    path = tmp_path / "seed_config.json"
    path.write_text(json.dumps({"pages": {"settings": {"url": "http://app/s", "elements": {
        "save": "notif-save", "delete_account": "delete-account"}}}}), encoding="utf-8")
    return path


def test_sync_config_follows_applied_heals_but_not_pending(tmp_path):
    repo, config = make_repo(tmp_path), write_config(tmp_path)
    repo.apply_heal(repo.get("settings", "save"), "btn-save", fingerprint(el("btn-save")), "fingerprint", 100.0, "t")
    repo.set_pending(repo.get("settings", "delete_account"), "btn-remove", fingerprint(el("btn-remove")), "fingerprint", 100.0, "t")

    changes = sync_config(repo, config)

    saved = json.loads(config.read_text(encoding="utf-8"))["pages"]["settings"]["elements"]
    assert saved == {"save": "btn-save", "delete_account": "delete-account"}   # pending not applied yet
    assert changes == ["settings.save: notif-save -> btn-save"]

    repo.approve("settings", "delete_account")
    sync_config(repo, config)
    assert json.loads(config.read_text(encoding="utf-8"))["pages"]["settings"]["elements"]["delete_account"] == "btn-remove"


def test_sync_config_adds_pages_missing_from_config(tmp_path):
    repo = make_repo(tmp_path)
    config = tmp_path / "new_config.json"
    sync_config(repo, config)
    saved = json.loads(config.read_text(encoding="utf-8"))["pages"]["settings"]
    assert saved["url"] == "http://app/s" and saved["elements"]["save"] == "notif-save"


def test_rebaseline_refreshes_fingerprint_and_baseline_when_all_found(tmp_path):
    repo, config = make_repo(tmp_path), write_config(tmp_path)
    repo.apply_heal(repo.get("settings", "save"), "btn-save", fingerprint(el("btn-save")), "fingerprint", 100.0, "t")
    repo.apply_heal(repo.get("settings", "delete_account"), "btn-remove",
                    fingerprint(el("btn-remove", text="Delete account")), "fingerprint", 100.0, "t")
    live = [el("btn-save", cls="btn primary"), el("btn-remove", text="Delete account"), el("brand-new")]

    report = rebaseline(FakeDriver({"http://app/s": live}), repo, config)

    assert report["baseline_updated"] == ["settings"] and not report["skipped"]
    assert repo.page("settings")["baseline_ids"] == ["brand-new", "btn-remove", "btn-save"]
    assert repo.get("settings", "save")["fingerprint"]["cls"] == "btn primary"


def test_rebaseline_keeps_baseline_when_an_element_is_unresolved(tmp_path):
    repo, config = make_repo(tmp_path), write_config(tmp_path)
    old_baseline = list(repo.page("settings")["baseline_ids"])
    live = [el("notif-save"), el("some-new-id")]          # delete-account is gone and not healed

    report = rebaseline(FakeDriver({"http://app/s": live}), repo, config)

    assert report["baseline_kept"] == ["settings"] and report["baseline_updated"] == []
    assert repo.page("settings")["baseline_ids"] == old_baseline
    assert any("delete_account" in line for line in report["skipped"])


def test_rebaseline_without_url_or_site_dir_skips_page(tmp_path):
    repo = make_repo(tmp_path)
    config = tmp_path / "empty.json"
    report = rebaseline(FakeDriver({}), repo, config)
    assert report["refreshed"] == [] and "no url" in report["skipped"][0]
