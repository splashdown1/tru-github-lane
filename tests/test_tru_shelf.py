#!/usr/bin/env python3
"""Unit tests for tools/tru_shelf.py (stdlib only, offline)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import tru_shelf as ts  # noqa: E402


def make_minimal_pack(
    owner: str = "acme",
    repo: str = "widget",
    sha: str = "a" * 40,
    text: str = "hello world\n",
) -> dict:
    file_hash = ts.sha256_text(text)
    files = [{"path": "README.md", "kind": "readme", "text": text, "sha256": file_hash, "size": len(text)}]
    lines = "\n".join(f"{f['path']}\t{f['sha256']}" for f in sorted(files, key=lambda x: x["path"]))
    pack_digest = ts.sha256_text(lines)
    return {
        "version": "2.1.0",
        "source": {
            "owner": owner,
            "repo": repo,
            "commit_sha": sha,
            "ref": "main",
            "url": f"https://github.com/{owner}/{repo}",
        },
        "files": files,
        "pack_digest": pack_digest,
        "generator": "test",
    }


class TestHashes(unittest.TestCase):
    def test_file_hash_roundtrip(self):
        pack = make_minimal_pack()
        errs = ts.recompute_file_hashes(pack)
        self.assertEqual(errs, [])

    def test_file_hash_mismatch(self):
        pack = make_minimal_pack()
        pack["files"][0]["sha256"] = "0" * 64
        errs = ts.recompute_file_hashes(pack)
        self.assertTrue(any("mismatch" in e for e in errs))

    def test_pack_digest(self):
        pack = make_minimal_pack()
        errs = ts.check_pack_digest(pack)
        self.assertEqual(errs, [])

    def test_pack_digest_mismatch(self):
        pack = make_minimal_pack()
        pack["pack_digest"] = "0" * 64
        errs = ts.check_pack_digest(pack)
        self.assertTrue(any("mismatch" in e for e in errs))


class TestIds(unittest.TestCase):
    def test_pack_id(self):
        pack = make_minimal_pack(sha="abcdef0123456789" + "0" * 24)
        pid = ts.pack_id_from_meta(pack)
        self.assertEqual(pid, "acme__widget@abcdef0")

    def test_parse_id(self):
        o, r, s = ts.parse_id("acme__widget@abcdef0")
        self.assertEqual((o, r, s), ("acme", "widget", "abcdef0"))


class TestEstablishedOffline(unittest.TestCase):
    def test_rejects_short_sha(self):
        pack = make_minimal_pack(sha="abc1234")
        errs = ts.run_established_checks(pack, token=None, min_age_days=0, skip_network=True)
        self.assertTrue(any("40-hex" in e for e in errs))

    def test_accepts_full_sha_shape(self):
        pack = make_minimal_pack()
        errs = ts.run_established_checks(pack, token=None, min_age_days=0, skip_network=True)
        self.assertEqual(errs, [])


class TestManifestChain(unittest.TestCase):
    def test_empty_prev(self):
        with tempfile.TemporaryDirectory() as td:
            old = ts.MANIFEST
            ts.MANIFEST = Path(td) / "manifest.jsonl"
            try:
                self.assertEqual(ts.last_manifest_hash(), "0" * 64)
                ts.append_manifest({"id": "a__b@1234567", "n": 1})
                h1 = ts.last_manifest_hash()
                self.assertNotEqual(h1, "0" * 64)
                ts.append_manifest({"id": "c__d@7654321", "n": 2})
                entries = ts.read_manifest()
                self.assertEqual(len(entries), 2)
                self.assertEqual(entries[1]["prev"], h1)
            finally:
                ts.MANIFEST = old


if __name__ == "__main__":
    unittest.main()
