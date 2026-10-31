"""Suggest logical names for the ids found on a page, so a new page can be enrolled in one command."""
import re

INTERACTIVE = ("a", "button", "input", "select", "textarea")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:30]


def suggest_names(elements, taken=()):
    """{id: logical_name}. Names are unique, never contain '.', and avoid `taken`."""
    used, names = set(taken), {}
    for e in elements:
        base = _slug(e["label"] or e["text"] or e["placeholder"] or e["name"] or e["id"]) or "element"
        candidates = [base]
        if e["ctx"]:
            candidates.append(f"{_slug(e['ctx'])}_{base}")   # two "Edit" buttons -> profile_edit, billing_edit
        name = next((c for c in candidates if c not in used), None)
        n = 2
        while name is None:
            name = f"{base}_{n}" if f"{base}_{n}" not in used else None
            n += 1
        used.add(name)
        names[e["id"]] = name
    return names
