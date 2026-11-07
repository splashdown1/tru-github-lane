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

    def test_keeps_tools_py(self):
        self.assertEqual(kind("tools/github_pull.py"), "extra")
        self.assertEqual(kind("tools/tru_shelf.py"), "extra")
        self.assertEqual(kind("tools/nested/util.py"), "extra")
        # still noise outside tools/
        self.assertIsNone(kind("src/main.py"))
        self.assertIsNone(kind("lib/helper.py"))
        # --exclude wins
        self.assertIsNone(kind("tools/github_pull.py", exclude=("tools/**",)))

    def test_drops_noise(self):
        self.assertIsNone(kind("src/main.py"))
        self.assertIsNone(kind("node_modules/x/index.js"))
        self.assertIsNone(kind("package-lock.json"))
        self.assertIsNone(kind("dist/app.min.js"))
        self.assertIsNone(kind("assets/logo.svg"))
        self.assertIsNone(kind("tests/fixtures/data.json"))

    def test_globs(self):
        self.assertEqual(kind("src/main.py", include=("src/**",)), "extra")
        self.assertIsNone(kind("docs/x.md", exclude=("docs/**",)))


class Select(unittest.TestCase):
    def test_sizes_and_noise(self):
        entries = [
            {"path": "README.md", "type": "blob", "size": 10, "sha": "a"},
            {"path": "src/x.py", "type": "blob", "size": 10, "sha": "b"},
            {"path": "docs/a.md", "type": "blob", "size": 10, "sha": "c"},
        ]
        kept, skipped, noise = gp.select_files(entries)
        paths = {f["path"] for f in kept}
        self.assertIn("README.md", paths)
        self.assertIn("docs/a.md", paths)
        self.assertNotIn("src/x.py", paths)
        self.assertGreaterEqual(noise.get("code-or-other", 0), 1)

    def test_budget_drops_lowest_priority_first(self):
        entries = [
            {"path": "README.md", "type": "blob", "size": 100, "sha": "a"},
            {"path": "notes/n.md", "type": "blob", "size": 300, "sha": "b"},
            {"path": "LICENSE", "type": "blob", "size": 50, "sha": "c"},
        ]
        kept, skipped, noise = gp.select_files(entries, max_total=200)
        paths = {f["path"] for f in kept}
        self.assertIn("README.md", paths)
        self.assertIn("LICENSE", paths)
        self.assertNotIn("notes/n.md", paths)
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
