"""Approval workflow for proposals the framework was not confident enough to apply.

    python review.py list
    python review.py approve login.button
    python review.py reject  login.button
    python review.py rollback login.button
"""
import argparse
from pathlib import Path

from healing import Repository

DEFAULT_REPO = Path(__file__).resolve().parent / "repository" / "elements.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["list", "approve", "reject", "rollback"])
    parser.add_argument("key", nargs="?", help="page.element")
    parser.add_argument("--repo", default=str(DEFAULT_REPO))
    args = parser.parse_args()

    repo = Repository(args.repo)
    if args.command == "list":
        for page, name, p in repo.pending():
            print(f"{page}.{name}: {repo.get(page, name)['id']} -> {p['id']}  "
                  f"({p['method']}, {p['confidence']})  {p['reason']}")
        return
    if not args.key:
        parser.error(f"{args.command} needs page.element")
    page, name = args.key.split(".", 1)
    getattr(repo, args.command)(page, name)
    repo.save()
    print(f"{args.command}: {args.key} -> now '{repo.get(page, name)['id']}' (v{repo.get(page, name)['version']})")


if __name__ == "__main__":
    main()
