"""Render `root/<path>:<line>` citations as links to the pinned ROOT commit.

The specification cites the reference implementation constantly, as a path plus a
line number (see `spec/00-conventions.md` §7). This turns each such citation into
a link into root-project/root at exactly the commit the `root/` submodule is
pinned to, so a citation resolves to the code it was written against rather than
to whatever `main` happens to say later.

It is a plain Python-Markdown treeprocessor rather than a site-generator hook, so
it works under any renderer built on Python-Markdown -- Zensical and MkDocs both
are. Keeping it engine-neutral is deliberate: see `PLAN.md`.

Only a `<code>` span whose *entire* content is a citation is linked, so ordinary
prose mentioning a file name is left alone.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

#: `root/<path>` with an optional `:<line>` or `:<line>-<line>` suffix.
CITATION = re.compile(
    r"""^root/
        (?P<path>[A-Za-z0-9_./+-]+\.(?:cxx|cxx\.in|hxx|h|c|cpp|cu|py|js|mjs|md|txt|yml))
        (?::(?P<line>\d+)(?:-(?P<end>\d+))?)?$""",
    re.VERBOSE,
)


def citation_url(text: str, base: str, commit: str) -> str | None:
    """Return the URL for a citation, or None if `text` is not one."""
    m = CITATION.match(text.strip())
    if m is None:
        return None
    url = f"{base}/blob/{commit}/{m['path']}"
    if m["line"]:
        url += f"#L{m['line']}"
        if m["end"]:
            url += f"-L{m['end']}"
    return url


class RootCiteTreeprocessor(Treeprocessor):
    def __init__(self, md, base: str, commit: str):
        super().__init__(md)
        self.base, self.commit = base.rstrip("/"), commit

    def run(self, root):
        # Every match is collected before anything is mutated. Inserting the
        # wrapper into a tree that is still being walked makes the walker descend
        # into the new element and wrap the same <code> again, without end.
        pending = []
        for parent in root.iter():
            if parent.tag == "a":
                continue
            for index, child in enumerate(parent):
                if child.tag == "code" and child.text:
                    url = citation_url(child.text, self.base, self.commit)
                    if url is not None:
                        pending.append((parent, index, child, url))

        for parent, index, child, url in pending:
            link = ET.Element("a", {"href": url, "class": "root-citation"})
            link.append(child)
            link.tail = child.tail
            child.tail = None
            parent.remove(child)
            parent.insert(index, link)
        return None


class RootCiteExtension(Extension):
    def __init__(self, **kwargs):
        self.config = {
            "base": ["https://github.com/root-project/root", "Repository URL"],
            "commit": ["", "Commit the root/ submodule is pinned to"],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        commit = self.getConfig("commit")
        if not commit:
            raise ValueError("tools.rootcite requires a 'commit' setting")
        md.treeprocessors.register(
            RootCiteTreeprocessor(md, self.getConfig("base"), commit), "rootcite", 2
        )


def makeExtension(**kwargs):
    return RootCiteExtension(**kwargs)
