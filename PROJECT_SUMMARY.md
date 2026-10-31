# Self-Healing Selenium Framework: Project Summary

Status: **code written, not yet run.** The development machine had no working Python (both installs were missing `python.exe`) and no Ollama, so nothing below has been executed. Expect to fix small issues on the first run.

---

## 1. Goal and constraints

| Item | Decision |
|---|---|
| Purpose | UI automation that repairs its own broken locators |
| Language / tool | Python + Selenium |
| What devs may change | **Only `id` attributes** (agreed with the dev team) |
| AI usage | As little as possible; token use must be measurable |
| Hardware | 8 GB RAM, so a small free local LLM only |
| Starting point | Fresh framework (the earlier Ollama prototype was dropped) |

Because only ids change, everything else on an element (tag, text, label, class, ancestors, neighbours) stays stable. The framework uses that stable context to recognise the element again.

---

## 2. Design decisions

1. **Tests use logical names, never raw locators.** `sh.find("login.button")` instead of `By.ID, "login-btn"`.
2. **The id is the key; context is the identity.** Each stored element has a fingerprint built from everything except its id.
3. **Deterministic first, LLM last.** Scoring is plain Python (`difflib`), so it costs no tokens. The LLM only breaks ties.
4. **Never guess when unsure.** Ambiguous or weak matches are queued for human approval, or fail with a candidate list.
5. **Every change is versioned** (history, approve, reject, rollback).
6. **Healed is not the same as passed.** Every heal is logged with method, confidence and reason.

---

## 3. How a lookup works (the ladder)

```
find("login.button")
 │
 0  Stored id still on the page and is the same tag?      → return it (no capture, no AI)
 │  no
 1  Earlier unapproved proposal still present?            → reuse it (no AI)
 2  Counter-style id (react-select-3-input → …-9-…)?      → one match: use it (no AI)
 3  Score candidates against the stored fingerprint       → policy decides (no AI)
 4  Scores too close to call?                             → local LLM picks among ≤3 (optional)
 5  Nothing safe?                                         → ElementHealingError listing top candidates
```

**Candidate pool.** Ids that did not exist at baseline are tried first (a renamed element's new id is by definition new). The search widens to all unclaimed ids only if that finds nothing. Ids already assigned to other repository elements, and ids a reviewer rejected, are excluded.

### Scoring (`healing/scoring.py`)

Twelve features, weights sum to 100:

| Feature | Weight | | Feature | Weight |
|---|---|---|---|---|
| tag | 10 | | href | 6 |
| text | 15 | | role / aria-label | 5 |
| label (for form fields) | 10 | | class | 7 |
| placeholder | 8 | | ancestor path | 12 |
| name | 6 | | nearest heading (context) | 8 |
| type | 6 | | previous/next sibling | 7 |

- Only features the stored element actually has are counted, then normalised to 0–100.
- **Gates:** a different tag, or a different `type`, rules a candidate out.
- **Thin evidence cap:** if too few features apply (under 40 weight), the score is capped at 69, so a bare `<div>` can never auto-heal.
- **Discriminators** (text, label, placeholder, name, href, context) are the fields that say *which* element this is. A candidate that disagrees on one is flagged as a probable look-alike.
- Fuzzy text similarity is squared, so near-misses like "Profile" vs "Billing" are punished.

### Decision policy (`healing/decide.py`)

| Condition | Action |
|---|---|
| score ≥ 90, runner-up ≥ 10 behind, no discriminator mismatch, name not on deny-list | **auto**: update repository, new version |
| score ≥ 70 and ≥ 10 ahead, but a mismatch, below 90, or deny-listed name | **pending**: use for this run, queue for approval |
| ambiguous, but candidates ≥ 50 | **llm**: ask the tie-breaker (if enabled) |
| otherwise | **fail** with candidate list |

Deny-list words: `delete`, `remove`, `pay`, `purchase`. An LLM answer is **never** applied automatically; it always goes to pending.

---

## 4. Token usage

| Rung | What | Tokens |
|---|---|---|
| 0–3 | id present, cached proposal, counter-style id, scoring | 0 |
| 4 | Ollama picks among ≤3 candidates (about 150 tokens of prompt per call plus a short reply, my estimate) | ~300–500 |
| 5 | fail | 0 |

Prompt size is kept small by sending only non-empty identifying fields, truncated to 40 characters, with at most 3 candidates. `SelfHealingDriver.summary()` reports the real token count from Ollama, so the estimate can be checked.

For the sample v2 (ids renamed only), the expected LLM usage is **zero**, and an end-to-end test asserts that.

---

## 5. Recommended local LLM (8 GB RAM)

| Model | RAM | Use when |
|---|---|---|
| **`qwen2.5:1.5b`** (default) | ~2 GB | Everyday tie-breaks |
| `llama3.2:1b` | ~1.5 GB | Machine is struggling |
| `qwen2.5:3b` | ~3.5 GB | 1.5b picks wrongly too often |

Avoid 7B models on 8 GB. No model training is needed: the "learning" is the versioned history in the repository. The LLM is **off by default** (`python run_demo.py --llm` turns it on).

LLM request settings: temperature 0, JSON-only output, max 80 output tokens, context 1024, model kept loaded for 5 minutes. A reply is accepted only if it names one of the offered ids.

---

## 6. What was built

```
SELF_HEALING_FRAMEWORK/
├── sample_app/
│   ├── templates/        login.html, register.html, dashboard.html ({{key}} placeholders for ids)
│   ├── ids_v1.json       original ids
│   ├── ids_v2.json       renamed ids (the "dev change")
│   ├── build.py          renders site/v1 and site/v2
│   └── __init__.py
├── healing/
│   ├── snapshot.py       one execute_script call captures every [id] element + context
│   ├── scoring.py        feature scoring, gates, evidence cap
│   ├── decide.py         Policy + decide(): auto / pending / llm / fail
│   ├── resolver.py       SelfHealingDriver and the ladder
│   ├── repository.py     versioned JSON store: history, approve, reject, rollback
│   ├── llm.py            optional Ollama tie-breaker with token accounting
│   ├── seeding.py        build the repository from a known-good build
│   └── __init__.py
├── repository/
│   └── seed_config.json  logical names → v1 ids (15 elements across 3 pages)
├── tests/
│   ├── test_scoring.py   11 browser-free tests of scoring, policy and LLM reply parsing
│   ├── test_e2e.py       5 real-browser tests
│   ├── conftest.py       Chrome/Edge headless fixture, site builder
│   └── __init__.py
├── run_demo.py           seed from v1, run on v2, print a heal table
├── review.py             list / approve / reject / rollback proposals
├── requirements.txt      selenium, pytest
├── pytest.ini
├── README.md             short setup and usage
└── PROJECT_SUMMARY.md    this file
```

### Sample app

Three pages (login, register, dashboard), each with a shared nav bar. 21 ids change between v1 and v2. Deliberate test cases built into it:

| Case | Where | Why it is hard |
|---|---|---|
| Two identical "Edit" buttons | dashboard Profile / Billing cards | Same text, class and tag; only the card heading and sibling text differ |
| Two password fields | register | Same tag and type; differ by name, label, placeholder |
| Counter-style id | dashboard country select (`react-select-3-input` → `…-9-…`) | Handled by the template rung with no scoring |
| Hidden element | login message `<p hidden>` | Must be found even when not visible |
| Checkbox with separate label | register terms | Label text comes from `element.labels` |

### Tests

**`test_scoring.py` (no browser):** pure rename scores 100; look-alike buttons are told apart; a look-alike alone is never auto-healed; tag/type gate; wrapper `<div>` added still heals (≥ 90); thin evidence capped at 69; deny-list forces pending; two equal candidates go to the LLM; no candidates fails; id template; LLM reply validation.

**`test_e2e.py` (real browser):** unchanged app needs no healing; every one of the 15 renamed ids is healed to the **correct** element (checked against the v1→v2 ground truth) with zero LLM tokens and no failures; a real login flow works on the renamed page; a second run after healing needs no new heals; a removed element raises `ElementHealingError` instead of guessing.

---

## 7. Using it in your own tests

```python
from healing import SelfHealingDriver, Repository

sh = SelfHealingDriver(driver, Repository("repository/elements.json"))
sh.find("login.username").send_keys("demo")
sh.find("login.button").click()
print(sh.summary())        # counts per status, LLM tokens used, one event per heal
```

To add elements: list them in `repository/seed_config.json` (logical name → current id), then re-seed from a known-good build with `seed_repository(...)`.

Managing proposals the framework was not sure about:

```
python review.py list
python review.py approve login.button
python review.py reject  login.button
python review.py rollback login.button
```

---

## 7b. Adding new pages and elements (added after first review)

| Situation | Use |
|---|---|
| Brand-new page | `python discover.py --page settings --url <url> --write` scans every id, suggests logical names (e.g. `profile_edit`), enrols them and appends to `seed_config.json`. Without `--write` it only previews. |
| Elements behind a click, a modal, or a login | `sh.find("settings.save", id="btn-save")` once. The first successful lookup stores the fingerprint and updates the config (`config_path=` on `SelfHealingDriver`). Later calls need no id. |
| Manual | Edit `seed_config.json` and re-seed |

- `seed_config.json` holds ids as of the last known-good build and is never overwritten by auto-enrolment; `repository/elements.json` is the current truth.
- Pages added automatically are stored with a `url`; if some of their elements need a click-path to appear, re-seeding skips them and lists them in `repo.skipped` instead of failing.
- The first sighting is trusted, so enrol from a green run on a good build.
- Calling `find()` with the wrong page name now produces an error that shows the current URL.
- `ids_v1.json` / `ids_v2.json` are sample-app data only. In a real project the dev team's own HTML supplies the ids.

New files: `healing/discovery.py` (name suggestions), `discover.py` (CLI). New tests: name suggestion, `Repository.enrol`, enrol-then-heal in a browser, and the "pass id=" error. Like the rest, these have not been run by me.

---

## 7c. How the files change over time in a real project

`sample_app/ids_v1.json` and `ids_v2.json` are **scaffolding for the sample app only**. They fill in the `{{placeholders}}` in the HTML templates so there is a "before" and an "after" build without a dev team; `ids_v2.json` stands in for developers renaming ids. A real project has neither file: the developers' own HTML supplies the ids.

### Lifecycle

| Step | Who / what | What changes |
|---|---|---|
| 1. App ships with ids in its own HTML | Developers | Nothing in this framework yet |
| 2. First enrolment | You run `discover.py --write`, or tests call `find(..., id=...)` on a good build | `elements.json` gets fingerprints. `seed_config.json` gets the page, its elements and their ids as of that build. |
| 3. Next sprint, devs rename some ids | Developers | Only the app's HTML. No file in this framework is touched. |
| 4. Tests run against the new build | `find("login.button")` | The old id is missing, so the framework heals it. Confident matches rewrite that element's id in `elements.json` (version +1, history entry). Uncertain matches are saved as `pending`. |
| 5. Someone reviews the pending ones | `python review.py approve / reject` | `elements.json` is updated for approved proposals |
| 6. Re-baseline, after a green run of the new build | `python rebaseline.py` | `seed_config.json` gets the current ids; fingerprints and each page's known-id list are refreshed from the live page |
| 7. New pages or elements are added | `discover.py --write` or `find(..., id=...)` | Both files gain entries. Existing entries are never changed by enrolment. |

### What each file means

| File | Meaning | Written by |
|---|---|---|
| `repository/elements.json` | Current truth: ids, fingerprints, version history, pending proposals, per-page known ids | The framework (do not edit by hand) |
| `repository/seed_config.json` | Ids as of the last known-good, re-baselined build. Used to re-seed and to tell `rebaseline.py` where each page lives. | Enrolment adds entries; `rebaseline.py` updates ids after heals and approvals |
| `sample_app/ids_v*.json` | Sample-app scaffolding | You, for the demo only |

### The re-baseline command

    python rebaseline.py --site-dir sample_app/site/v2   # sample app: re-capture from the v2 pages
    python rebaseline.py                                 # real app: re-capture from the urls in seed_config.json
    python rebaseline.py --config-only                   # no browser: only copy current ids into seed_config.json

Run it after heals have been reviewed, against a green run of the current build.

1. **Fingerprints refreshed.** For each element whose current id is found on the live page (same tag), the stored fingerprint is re-captured. This stops small drifts in text or class from accumulating.
2. **Known-id list replaced, but only if every element on that page was found.** If some elements were not found (still unhealed), the list is kept, because replacing it would hide the new ids those elements need as candidates.
3. **`seed_config.json` brought up to date.** Each element's id is set to the repository's current id.
4. **Pending proposals are not written to the config.** An element's id moves only once it is applied (auto-heal) or approved. The command reports how many proposals remain.

Pages whose elements only exist after a click (a modal, a dropdown that is not in the DOM until opened) will report "not found" on a plain page load and keep their old baseline. Enrol those from within a test instead.

### Typical cycle

    pytest                      # tests run, heals happen, uncertain ones are queued
    python review.py list       # look at what was queued
    python review.py approve settings.delete_account
    pytest                      # green run on the new build
    python rebaseline.py        # config and baselines catch up

New files for this: `healing/rebaseline.py`, `rebaseline.py`, `tests/test_rebaseline.py` (5 browser-free tests using a fake driver). Like the rest of this project's later additions, they have been written but not run by me.

---

## 7d. The demo report

`python run_demo.py` and `python run_demo.py --llm` each write a run record to `reports/runs/` and regenerate **`reports/demo_report.html`**, a single self-contained page (works offline, light and dark theme). Add `--open` to open it.

It contains:
- **Side by side** (once both modes have been run): healed / needs review / failed, correctness against ground truth, LLM calls and tokens, duration, and a list of every element whose outcome differs between the two runs.
- **Per run, four stage cards:** developers rename ids, seed from v1, run on v2, repository after the run.
- **Per run, an element table:** seeded id, the id the developers changed it to, the id the framework chose (tick or cross), result, which rung resolved it, confidence bar, version change (`v1 → v2`), time and tokens, and the reason.
- **An honest LLM note.** On the sample app every element is expected to be resolved by the deterministic rungs, so the `--llm` run will normally show **0 calls and 0 tokens, and no differences from the first run**. The report says so rather than implying the LLM helped. It only does something when scoring is genuinely ambiguous.

`run_demo.py` now records a failed lookup as a failed row instead of stopping, so one bad element no longer hides the rest.

**Seed data moved.** The demo and the tests now seed from `sample_app/demo_seed.json` (fixed v1 ids). Previously they read `repository/seed_config.json`, which `rebaseline.py` rewrites with the new ids, so they would have failed after the first re-baseline. `seed_config.json` is now purely your working config.

New files: `healing/report.py`, `sample_app/demo_seed.json`, `tests/test_report.py` (7 browser-free tests). Not run by me.

---

## 8. How to run it

1. Install **Python 3.11** (3.11 or newer works) from python.org and tick "Add python.exe to PATH".
2. Create a virtual environment: `py -3.11 -m venv .venv`, then `.venv\Scripts\activate`.
3. `pip install -r requirements.txt`
4. `python -m pytest tests/test_scoring.py` (fast, no browser)
5. `python -m pytest` (adds the browser tests; `set BROWSER=edge` to use Edge)
6. `python run_demo.py` (prints a table of what healed)
7. Optional LLM: install Ollama, `ollama pull qwen2.5:1.5b`, then `python run_demo.py --llm`

Chrome and Edge are both installed on the machine. Selenium Manager downloads the driver on first run.

---

## 9. Known limitations and risks

- **Never executed.** First-run fixes are likely. Treat the test results as the real status.
- **Thresholds are guesses.** 90 / 70 / margin 10 should be tuned on your real pages.
- **Only elements with ids are tracked.** Elements without an id cannot be healed.
- **Truly identical twins** (same text, same context, same position) cannot be told apart by id-only context. They go to the LLM or human review.
- **Counter-style ids** are re-resolved every run (a few cheap lookups, no version bump).
- **Untested assumptions:** the in-page JavaScript capture, `element.labels`, and Selenium Manager finding Chrome in `Program Files (x86)`.
- **Out of scope for now:** screenshots/vision, Shadow DOM, iframes, learned scoring weights, a dashboard.

---

## 10. Suggested next steps

1. Install Python and run the tests; fix whatever breaks.
2. Point `seed_config.json` at a few of your real pages and seed from a real build.
3. Run against a build where devs changed ids; look at the heal table and token count.
4. Tune the thresholds from what you see.
5. Only then consider extras (iframes, Shadow DOM, learned weights).
