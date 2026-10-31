"""Browser-free tests for scoring and policy. These are the mutation bench for the matcher."""
from healing.decide import Policy, decide
from healing.llm import parse_choice
from healing.scoring import rank, score
from healing.snapshot import fingerprint, id_template

CARD_PATH = ["body", "main", "section.card"]


def el(id_="x", **kw):
    base = {"id": id_, "tag": "button", "type": "button", "name": "", "cls": "btn", "text": "Edit",
            "label": "", "placeholder": "", "role": "", "href": "", "ctx": "Profile",
            "path": CARD_PATH, "prev": "p|Name, email and avatar", "next": "", "visible": True}
    base.update(kw)
    return base


PROFILE = el("edit-profile")
BILLING = el("edit-billing", ctx="Billing", prev="p|Cards and invoices")
POLICY = Policy()


def test_pure_id_rename_scores_100():
    renamed = el("btn-edit-1")
    assert score(fingerprint(PROFILE), renamed)["score"] == 100.0


def test_lookalike_buttons_are_disambiguated():
    ranked = rank(fingerprint(PROFILE), [el("btn-edit-2", ctx="Billing", prev="p|Cards and invoices"), el("btn-edit-1")])
    assert ranked[0]["id"] == "btn-edit-1"
    assert decide(ranked, "edit_profile", POLICY).action == "auto"


def test_lookalike_alone_is_never_auto_healed():
    # the real element was deleted; only the Billing button is left
    ranked = rank(fingerprint(PROFILE), [BILLING])
    assert decide(ranked, "edit_profile", POLICY).action != "auto"


def test_tag_and_type_gate():
    assert score(fingerprint(PROFILE), el("a1", tag="a")) is None
    field = el("f", tag="input", type="password")
    assert score(fingerprint(field), el("g", tag="input", type="text")) is None


def test_wrapper_added_still_heals():
    wrapped = el("btn-edit-1", path=CARD_PATH + ["div.row"])
    result = score(fingerprint(PROFILE), wrapped)
    assert result["score"] >= 90


def test_thin_evidence_is_capped():
    bare = {"id": "a", "tag": "div", "path": ["body"], "cls": "", "text": "", "label": "",
            "placeholder": "", "name": "", "type": "", "href": "", "role": "", "ctx": "", "prev": "", "next": ""}
    assert score(fingerprint(bare), dict(bare, id="b"))["score"] <= 69.0


def test_deny_list_blocks_auto():
    ranked = rank(fingerprint(PROFILE), [el("btn-edit-1")])
    assert decide(ranked, "delete_account", POLICY).action == "pending"


def test_two_close_candidates_go_to_llm():
    ranked = rank(fingerprint(PROFILE), [el("a"), el("b")])
    d = decide(ranked, "edit_profile", POLICY)
    assert d.action == "llm" and len(d.shortlist) == 2


def test_no_candidates_fails():
    assert decide([], "edit_profile", POLICY).action == "fail"


def test_id_template():
    assert id_template("react-select-3-input") == id_template("react-select-9-input")
    assert id_template("login-btn") == "login-btn"


def test_suggested_names_are_unique_and_dot_free():
    from healing.discovery import suggest_names
    edit_a = el("a", text="Edit", ctx="Profile")
    edit_b = el("b", text="Edit", ctx="Billing")
    save = el("c", text="Save.draft!", ctx="")
    names = suggest_names([edit_a, edit_b, save], taken={"save_draft"})
    assert names["a"] == "edit" and names["b"] == "billing_edit"
    assert "." not in names["c"] and names["c"] != "save_draft"


def test_enrol_adds_element_and_page_baseline():
    from healing.repository import Repository
    repo = Repository("unused.json")
    repo.enrol("settings", "save", "btn-save", fingerprint(el("btn-save")), ["btn-save", "frm"], file="file:///x")
    assert repo.lookup("settings", "save")["id"] == "btn-save"
    assert repo.page("settings")["baseline_ids"] == ["btn-save", "frm"]
    assert repo.lookup("settings", "nope") is None and repo.lookup("other", "save") is None


def test_llm_reply_must_name_an_offered_id():
    assert parse_choice('{"choice":"a","reason":"same text"}', {"a", "b"})["choice"] == "a"
    assert parse_choice('{"choice":"zzz"}', {"a", "b"}) is None
    assert parse_choice("not json", {"a"}) is None
    assert parse_choice('{"choice":null}', {"a"}) is None
