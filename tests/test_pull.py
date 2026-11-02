#!/usr/bin/env python3
"""Unit tests for tools/github_pull.py (stdlib only, no network)."""
import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("github_pull", ROOT / "tools" / "github_pull.py")
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)


def kind(path, include=(), exclude=()):
    k, _ = gp.classify(path, include, exclude)
    return k


class Classify(unittest.TestCase):
    def test_keeps_docs_config_manifest(self):
        self.assertEqual(kind("README.md"), "readme")
        self.assertEqual(kind("docs/guide.md"), "doc")
        self.assertEqual(kind("notes/idea.md"), "knowledge")
        self.assertEqual(kind("LICENSE"), "manifest")
        self.assertEqual(kind("package.json"), "config")
        self.assertEqual(kind(".github/workflows/ci.yml"), "config")
        self.assertEqual(kind("requirements.txt"), "config")
        self.assertEqual(kind("pyproject.toml"), "config")

    def test_drops_noise(self):
        self.assertIsNone(kind("src/main.py"))
        self.assertIsNone(kind("node_modules/x/index.js"))
        self.assertIsNone(kind("package-lock.json"))
        self.assertIsNone(kind("dist/app.min.js"))
        self.assertIsNone(kind("assets/logo.svg"))
        self.assertIsNone(kind("tests/fixtures/data.json"))

    def test_globs(self):
        self.assertEqual(kind("src/schema.sql", include=["*.sql"]), "extra")
        self.assertIsNone(kind("docs/internal.md", exclude=["docs/internal*"]))


class Select(unittest.TestCase):
    def tree(self):
        return [
            {"type": "tree", "path": "docs"},
            {"type": "blob", "path": "README.md", "size": 100, "sha": "a"},
            {"type": "blob", "path": "docs/a.md", "size": 200, "sha": "b"},
            {"type": "blob", "path": "docs/huge.md", "size": 999999, "sha": "c"},
            {"type": "blob", "path": "src/x.py", "size": 50, "sha": "d"},
            {"type": "blob", "path": "notes/n.md", "size": 300, "sha": "e"},
        ]

    def test_sizes_and_noise(self):
        kept, skipped, noise = gp.select_files(self.tree(), max_file=1000)
        self.assertEqual([f["path"] for f in kept], ["README.md", "docs/a.md", "notes/n.md"])
        self.assertEqual(skipped, [{"path": "docs/huge.md", "reason": "too-large", "size": 999999}])
        self.assertEqual(noise["code-or-other"], 1)

    def test_budget_drops_lowest_priority_first(self):
        kept, skipped, _ = gp.select_files(self.tree(), max_file=1000, max_total=350)
        self.assertEqual([f["path"] for f in kept], ["README.md", "docs/a.md"])
        self.assertIn({"path": "notes/n.md", "reason": "over-budget", "size": 300}, skipped)


class Misc(unittest.TestCase):
    def test_parse_spec(self):
        self.assertEqual(gp.parse_spec("a/b"), ("a", "b", None))
        self.assertEqual(gp.parse_spec("a/b@v1.2"), ("a", "b", "v1.2"))
        self.assertEqual(gp.parse_spec("https://github.com/a/b.git"), ("a", "b", None))
        self.assertEqual(gp.parse_spec("https://github.com/a/b/tree/dev/x"), ("a", "b", "dev/x"))
        with self.assertRaises(ValueError):
            gp.parse_spec("justone")
        with self.assertRaises(ValueError):
            gp.parse_spec("https://example.com/a/b")

    def test_digest_is_order_independent(self):
        f1 = {"path": "a", "sha256": "1"}
        f2 = {"path": "b", "sha256": "2"}
        self.assertEqual(gp.pack_digest([f1, f2]), gp.pack_digest([f2, f1]))
        want = hashlib.sha256(b"a\t1\nb\t2").hexdigest()
        self.assertEqual(gp.pack_digest([f2, f1]), want)

    def test_decode_text(self):
        self.assertEqual(gp.decode_text("h\u00e9llo".encode()), "h\u00e9llo")
        self.assertIsNone(gp.decode_text(b"\x00\x01"))
        self.assertIsNone(gp.decode_text(b"\xff\xfe\xfa"))


if __name__ == "__main__":
    unittest.main()
