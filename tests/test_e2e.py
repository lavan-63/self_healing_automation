"""Real-browser tests: seed from v1, then run against v2 where only ids were renamed."""
import json

import pytest

from healing import ElementHealingError, SelfHealingDriver, seed_repository
from healing.seeding import page_file
from sample_app import build

pytestmark = pytest.mark.e2e

# fixed v1 ids for the sample app; repository/seed_config.json is the working config and moves with rebaseline.py
CONFIG = json.loads((build.HERE / "demo_seed.json").read_text(encoding="utf-8"))
IDS_V1 = json.loads((build.HERE / "ids_v1.json").read_text(encoding="utf-8"))
IDS_V2 = json.loads((build.HERE / "ids_v2.json").read_text(encoding="utf-8"))
TRUTH = {IDS_V1[k]: IDS_V2[k] for k in IDS_V1}   # v1 id -> v2 id


@pytest.fixture
def repo(driver, site, tmp_path):
    return seed_repository(driver, CONFIG, site / "v1", tmp_path / "elements.json")


def _walk(driver, healer, site, version):
    for page, spec in CONFIG["pages"].items():
        driver.get((site / version / page_file(spec)).as_uri())
        for name in spec["elements"]:
            healer.find(f"{page}.{name}")


def test_unchanged_app_needs_no_healing(driver, site, repo):
    healer = SelfHealingDriver(driver, repo)
    _walk(driver, healer, site, "v1")
    assert healer.events == []


def test_every_renamed_id_is_healed_to_the_right_element(driver, site, repo):
    healer = SelfHealingDriver(driver, repo)          # no LLM at all
    _walk(driver, healer, site, "v2")
    for page, spec in CONFIG["pages"].items():
        for name, v1_id in spec["elements"].items():
            entry = repo.get(page, name)
            # deny-listed names (e.g. delete_account) are only proposed, not applied, until approved
            healed_to = entry["pending"]["id"] if entry.get("pending") else entry["id"]
            assert healed_to == TRUTH[v1_id], f"{page}.{name} healed to the wrong element"
    assert healer.summary()["llm_tokens"] == 0
    assert "failed" not in healer.summary()["counts"]


def test_user_flow_works_on_renamed_page(driver, site, repo):
    healer = SelfHealingDriver(driver, repo)
    driver.get((site / "v2" / "login.html").as_uri())
    healer.find("login.username").send_keys("demo")
    healer.find("login.password").send_keys("secret")
    healer.find("login.button").click()
    assert healer.find("login.message").text == "Welcome, demo"


def test_second_run_after_heal_is_free(driver, site, repo):
    healer = SelfHealingDriver(driver, repo)
    _walk(driver, healer, site, "v2")
    second = SelfHealingDriver(driver, repo)
    _walk(driver, second, site, "v2")
    # nothing is re-scored: only counter-style ids and still-unapproved proposals are re-resolved
    assert {e["method"] for e in second.events} <= {"id_template", "pending_cache"}


def test_enrol_on_first_success_then_heal(driver, site, tmp_path):
    from healing import Repository
    repo = Repository(tmp_path / "elements.json")
    config = tmp_path / "seed_config.json"
    healer = SelfHealingDriver(driver, repo, config_path=config)

    driver.get((site / "v1" / "login.html").as_uri())
    healer.find("login.button", id=IDS_V1["login_btn"])                  # unknown -> enrolled
    assert healer.events[0]["status"] == "enrolled"
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["pages"]["login"]["elements"]["button"] == IDS_V1["login_btn"]

    driver.get((site / "v2" / "login.html").as_uri())                    # dev renamed the id
    healer.find("login.button")                                          # no id needed any more
    assert repo.get("login", "button")["id"] == IDS_V2["login_btn"]


def test_unknown_element_without_id_explains_itself(driver, site, tmp_path):
    from healing import Repository
    healer = SelfHealingDriver(driver, Repository(tmp_path / "elements.json"))
    with pytest.raises(KeyError, match="pass id="):
        healer.find("login.button")


def test_removed_element_fails_with_candidates_instead_of_guessing(driver, site, repo):
    healer = SelfHealingDriver(driver, repo, wait_s=0.2)
    driver.get((site / "v2" / "login.html").as_uri())
    driver.execute_script("document.getElementById(arguments[0]).remove()", IDS_V2["login_forgot"])
    with pytest.raises(ElementHealingError):
        healer.find("login.forgot")
