"""SelfHealingDriver: the only object tests talk to.

    sh = SelfHealingDriver(driver, repo)
    sh.find("login.username").send_keys("demo")

Resolution ladder, cheapest first. A passing lookup never leaves rung 0.
    0  stored id still on the page            (no capture, no AI)
    1  reuse an earlier unapproved proposal   (no AI)
    2  counter-style id, one match            (no AI)
    3  fingerprint scoring + policy           (no AI)
    4  local LLM picks among <=3 candidates   (only if scoring is ambiguous)
    5  fail with the candidate list
"""
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .decide import Policy, decide
from .scoring import rank
from .seeding import add_to_config
from .snapshot import capture, fingerprint, id_template


class ElementHealingError(Exception):
    """The element is gone and no safe replacement exists."""


class SelfHealingDriver:
    def __init__(self, driver, repo, llm=None, policy=None, wait_s=2.0, config_path=None):
        self.driver, self.repo, self.llm = driver, repo, llm
        self.policy = policy or Policy()
        self.wait_s = wait_s
        self.config_path = config_path   # if set, newly enrolled elements are appended to this seed_config.json
        self.events = []

    # ---- public --------------------------------------------------------
    def find(self, key, id=None):
        """Find "page.element". `id` is only used the first time, to enrol an element not yet known."""
        page, name = key.split(".", 1)
        entry = self.repo.lookup(page, name)
        if entry is None:
            return self._enrol(page, name, id)
        wait = 0 if entry.get("dynamic") else self.wait_s
        element = self._by_id(entry["id"], entry["fingerprint"]["tag"], wait)
        if element is not None:
            self.repo.touch(entry)
            return element
        return self._heal(page, name, entry)

    def summary(self):
        counts = {}
        for event in self.events:
            counts[event["status"]] = counts.get(event["status"], 0) + 1
        return {"counts": counts, "llm_tokens": sum(e["llm_tokens"] for e in self.events),
                "events": self.events}

    # ---- internals -----------------------------------------------------
    def _by_id(self, element_id, tag, wait):
        if wait:
            try:
                WebDriverWait(self.driver, wait).until(lambda d: d.find_elements(By.ID, element_id))
            except TimeoutException:
                return None
        found = self.driver.find_elements(By.ID, element_id)
        # an id that now belongs to a different kind of element counts as missing
        if found and found[0].tag_name.lower() == tag:
            return found[0]
        return None

    def _enrol(self, page, name, element_id):
        """First sighting of an element: trust the page as it is now and store its fingerprint."""
        key = f"{page}.{name}"
        if element_id is None:
            raise KeyError(f"unknown element '{key}': pass id=... the first time so it can be enrolled")
        elements = capture(self.driver)
        by_id = {e["id"]: e for e in elements}
        if element_id not in by_id:
            raise ElementHealingError(
                f"{key}: cannot enrol, no element with id '{element_id}' on {self.driver.current_url}. "
                f"Is the right page/state open, and is '{page}' the right page name?")
        url = self.driver.current_url
        self.repo.enrol(page, name, element_id, fingerprint(by_id[element_id]), by_id.keys(), file=url)
        if self.config_path:
            add_to_config(self.config_path, page, name, element_id, url)
        self.repo.save()
        self._log(key, "enrolled", "first_success", 100.0, None, element_id,
                  "first successful lookup; fingerprint stored")
        return self.driver.find_element(By.ID, element_id)

    def _tokens(self):
        return self.llm.tokens if self.llm else 0

    def _log(self, key, status, method, confidence, old_id, new_id, reason, tokens=0):
        self.events.append({"key": key, "status": status, "method": method, "confidence": confidence,
                            "old_id": old_id, "new_id": new_id, "reason": reason, "llm_tokens": tokens})

    def _heal(self, page, name, entry):
        key, old_id, old_fp = f"{page}.{name}", entry["id"], entry["fingerprint"]
        by_id = {e["id"]: e for e in capture(self.driver)}

        pending = entry.get("pending")
        if pending and pending["id"] in by_id:
            self._log(key, "needs_review", "pending_cache", pending["confidence"], old_id, pending["id"],
                      "reusing unapproved proposal")
            return self.driver.find_element(By.ID, pending["id"])

        claimed = {e["id"] for n, e in self.repo.elements(page).items() if n != name}
        excluded = claimed | set(entry.get("rejected", [])) | {old_id}
        pool = [e for i, e in by_id.items() if i not in excluded]
        known = set(self.repo.page(page)["baseline_ids"])
        orphans = [e for e in pool if e["id"] not in known]   # ids that did not exist at baseline

        template = id_template(old_id)
        if template != old_id:
            same = [e for e in pool if id_template(e["id"]) == template and e["tag"] == old_fp["tag"]]
            if len(same) == 1:
                new_id = same[0]["id"]
                self.repo.set_dynamic(entry, new_id)
                self._log(key, "resolved", "id_template", 99.0, old_id, new_id, "counter-style id")
                return self.driver.find_element(By.ID, new_id)

        decision = decide(rank(old_fp, orphans), name, self.policy)
        if decision.action == "fail":
            decision = decide(rank(old_fp, pool), name, self.policy)   # widen: the id may have been reused

        if decision.action in ("auto", "pending"):
            return self._accept(key, entry, decision.candidate, "fingerprint", decision.reason,
                                auto=decision.action == "auto")

        if decision.action == "llm" and self.llm:
            before = self._tokens()
            pick = self.llm.choose(old_fp, decision.shortlist)
            spent = self._tokens() - before
            chosen = next((c for c in decision.shortlist if pick and c["id"] == pick["choice"]), None)
            if chosen and chosen["score"] >= self.policy.review:
                return self._accept(key, entry, chosen, "llm", pick["reason"], auto=False, tokens=spent)
            decision.reason += "; LLM gave no usable answer" if spent else "; LLM unavailable"

        self._log(key, "failed", decision.action, 0.0, old_id, None, decision.reason)
        top = ", ".join(f"{c['id']}={c['score']}" for c in decision.shortlist[:3]) or "none"
        raise ElementHealingError(
            f"{key}: id '{old_id}' is gone and no safe replacement was found ({decision.reason}). "
            f"Top candidates: {top}. Current page: {self.driver.current_url} "
            f"(if that is not the '{page}' page, the wrong page name was used)")

    def _accept(self, key, entry, candidate, method, reason, auto, tokens=0):
        new_id, old_id = candidate["id"], entry["id"]
        fp = fingerprint(candidate["fp"])
        if auto:
            self.repo.apply_heal(entry, new_id, fp, method, candidate["score"], reason)
        else:
            self.repo.set_pending(entry, new_id, fp, method, candidate["score"], reason)
        self._log(key, "healed" if auto else "needs_review", method, candidate["score"],
                  old_id, new_id, reason, tokens)
        return self.driver.find_element(By.ID, new_id)
