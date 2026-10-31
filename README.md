# Self-healing Selenium framework (id-only changes, minimal AI)

Devs may change only `id` attributes. Everything else (tag, text, label, class, ancestors,
neighbours) stays put, so it is used to recognise the element again.

## Setup (Windows)

1. Install Python 3.11 (3.11 or newer works) from python.org and tick "Add python.exe to PATH".
2. In the project folder, create an isolated environment so the other broken Python installs on this machine don't interfere:
   `py -3.11 -m venv .venv` then `.venv\Scripts\activate`
   `pip install -r requirements.txt`  (Chrome or Edge must be installed; Selenium Manager fetches the driver)
3. Optional LLM: install Ollama, then `ollama pull qwen2.5:1.5b`

## Run

    python -m pytest tests/test_scoring.py     # fast, no browser
    python -m pytest                           # + real-browser tests (set BROWSER=edge to use Edge)
    python run_demo.py                         # seed from v1, run on v2, print what healed
    python run_demo.py --llm                   # allow the Ollama tie-breaker
    python review.py list                      # proposals waiting for approval

## Use in your tests

    from healing import SelfHealingDriver, Repository
    sh = SelfHealingDriver(driver, Repository("repository/elements.json"))
    sh.find("login.username").send_keys("demo")      # "page.element", never a raw locator

## Adding new pages and elements

Three ways, all meant to be run against a known-good build:

1. **Scan a whole new page** (best for a brand-new page):

       python discover.py --page settings --file path\to\settings.html          # preview names
       python discover.py --page settings --url https://app/settings --write    # enrol + update seed_config.json

   Interactive elements only by default (`--all` adds headings/containers). Already-known elements are skipped,
   so re-running after the page grows only adds the new ones.

2. **Enrol on first success**, for pages reached by clicking through (menus, modals, a page behind a login):

       sh = SelfHealingDriver(driver, repo, config_path="repository/seed_config.json")
       sh.find("settings.save", id="btn-save")    # unknown -> fingerprint stored, config updated
       sh.find("settings.save")                   # from now on no id needed; heals if the id changes

   The test is already in the right state when it calls `find`, so the fingerprint is captured in context.

3. **Edit `repository/seed_config.json` by hand** and re-seed (`seed_repository`).

`seed_config.json` lists ids as of the last known-good build and is never overwritten by auto-enrolment.
`repository/elements.json` is the current truth (it moves when ids are healed).

Always enrol from a green run on a good build: the first sighting is trusted.

## HTML report of the demo

    python run_demo.py              # deterministic only
    python run_demo.py --llm --open # with the local LLM; opens the report

Each run is saved to `reports/runs/` and rendered into `reports/demo_report.html`. After running both modes
the report shows them side by side: results, LLM calls and tokens, and every element whose outcome differs.
For each run it shows what happened at each stage (ids renamed, seeded from v1, healed on v2, repository after)
and a per-element table with the confidence, the rung that resolved it, version change, time, and whether the
choice matches what the developers actually renamed it to.

The demo and the tests seed from `sample_app/demo_seed.json` (fixed v1 ids), not from
`repository/seed_config.json`, which belongs to you and moves when you run `rebaseline.py`.

## After ids are healed and approved: re-baseline

    python review.py list                                # proposals that were queued
    python review.py approve settings.delete_account
    python rebaseline.py --site-dir sample_app/site/v2   # sample app (real app: just `python rebaseline.py`)

This writes the repository's current ids into `seed_config.json` and refreshes fingerprints and each
page's known ids from the live page. Proposals still unapproved are left out. `--config-only` skips the browser.

## Where tokens are spent

| Rung | What | Tokens |
|---|---|---|
| 0 | stored id still present | 0 |
| 1 | reuse an unapproved proposal | 0 |
| 2 | counter-style id (`react-select-3-input`) | 0 |
| 3 | fingerprint scoring + policy | 0 |
| 4 | Ollama picks among <=3 candidates, only when rung 3 is ambiguous | ~300-500 |
| 5 | fail, with the candidate list | 0 |

`SelfHealingDriver.summary()` reports the LLM tokens actually used.

## Safety rules (healing/decide.py)

- auto-update only at score >= 90, runner-up at least 10 points behind, no discriminator mismatch
- 70-89, a mismatch, or a name containing delete/remove/pay/purchase: used for this run only, queued in `review.py`
- an LLM answer is never applied automatically
- tag/type must match; thin evidence is capped below the review threshold
