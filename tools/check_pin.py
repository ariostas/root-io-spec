#!/usr/bin/env python3
"""Assert that zensical.toml cites the commit the root/ submodule is pinned to.

The citation links in the built site are only trustworthy if the commit they point
at is the commit the specification was written against. That commit is recorded in
two places -- the git gitlink for `root/`, and the `tools.rootcite` setting in
zensical.toml -- and this check keeps them equal, so bumping the submodule without
updating the site configuration cannot silently produce links to the wrong code.

Reads the gitlink from the index, so the submodule need not be checked out.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def pinned_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD:root"], cwd=REPO,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def configured_commit() -> str:
    config = tomllib.loads((REPO / "zensical.toml").read_text())
    return config["project"]["markdown_extensions"]["tools.rootcite"]["commit"]


def main() -> int:
    pinned, configured = pinned_commit(), configured_commit()
    if pinned != configured:
        print(f"FAIL zensical.toml cites {configured}\n"
              f"     but root/ is pinned at {pinned}\n"
              f"     update the tools.rootcite commit setting", file=sys.stderr)
        return 1
    print(f"citation commit matches the pinned submodule: {pinned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
