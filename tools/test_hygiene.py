#!/usr/bin/env python3
"""Tests of the test suite itself.

A test module that defines two top-level classes or functions with the same
name keeps only the second: the first one's tests stop running, and unittest
reports nothing, because there is nothing left to report. That happened on
2026-09-24, when a new `ThisElement` class hid five older tests
(PLAN-review.md V32).

It also holds one check of the documents that no other tool can see: a table
row glued to the prose above it renders as text, and the strict site build
accepts it. `Record.md` §3.4 lost its large-layout row that way.
"""

import ast
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SPEC = TOOLS.parent / "spec"


class NoShadowedDefinitions(unittest.TestCase):
    def test_no_test_module_defines_a_name_twice(self):
        for path in sorted(TOOLS.glob("test_*.py")):
            seen: dict[str, int] = {}
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    with self.subTest(module=path.name, name=node.name):
                        self.assertNotIn(
                            node.name, seen,
                            f"{path.name}:{node.lineno} redefines {node.name} "
                            f"from line {seen.get(node.name)}")
                    seen[node.name] = node.lineno

    def test_no_test_class_defines_a_method_twice(self):
        for path in sorted(TOOLS.glob("test_*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.ClassDef):
                    continue
                seen: dict[str, int] = {}
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        with self.subTest(module=path.name,
                                          name=f"{node.name}.{item.name}"):
                            self.assertNotIn(item.name, seen)
                        seen[item.name] = item.lineno


class NoOrphanedTableRows(unittest.TestCase):
    def test_no_table_row_follows_a_line_of_prose(self):
        for path in sorted(SPEC.rglob("*.md")):
            lines = path.read_text().splitlines()
            fenced = False
            for i in range(1, len(lines)):
                if lines[i].startswith("```"):
                    fenced = not fenced
                above = lines[i - 1].strip()
                if (fenced or not lines[i].startswith("|") or not above
                        or above.startswith(("|", "<!--"))):
                    continue
                with self.subTest(at=f"{path.relative_to(SPEC)}:{i + 1}"):
                    self.fail(f"a table row directly under {above[:50]!r}")


if __name__ == "__main__":
    unittest.main()
