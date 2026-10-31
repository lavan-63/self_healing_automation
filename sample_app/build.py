"""Render sample_app/templates into site/v1 and site/v2.

v2 differs from v1 only in id values, which is exactly the change the dev team
has agreed to make. Run: python -m sample_app.build
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = ("v1", "v2")


def main():
    ids = {v: json.loads((HERE / f"ids_{v}.json").read_text(encoding="utf-8")) for v in VERSIONS}
    for template in sorted((HERE / "templates").glob("*.html")):
        source = template.read_text(encoding="utf-8")
        for version in VERSIONS:
            rendered = re.sub(r"\{\{(\w+)\}\}", lambda m: ids[version][m.group(1)], source)
            dest = HERE / "site" / version
            dest.mkdir(parents=True, exist_ok=True)
            (dest / template.name).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
    print("built sample_app/site/v1 and sample_app/site/v2")
