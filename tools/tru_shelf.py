#!/usr/bin/env python3
"""TRU Shelf intake — propose, approve, reject, check.

stdlib only. Staging never touches the shelf. Only approve does,
and it re-runs every check first.

Usage:
  python tools/tru_shelf.py propose  path/to/x.tru-github-pack.json
  python tools/tru_shelf.py list
  python tools/tru_shelf.py approve  owner__repo@abc1234 --by you
  python tools/tru_shelf.py reject   owner__repo@abc1234 --reason "..."
  python tools/tru_shelf.py check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SHELF_DIR = ROOT / "shelf"
STAGING_DIR = SHELF_DIR / "staging"
PACKS_DIR = SHELF_DIR / "packs"
MANIFEST = SHELF_DIR / "manifest.jsonl"

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^([A-Za-z0-9_.-]+)__([A-Za-z0-9_.-]+)@([0-9a-f]{7,40})$")


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def github_get(url: str, token: str | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tru-shelf/0.1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        die(f"GitHub HTTP {e.code} for {url}: {body}")
    except urllib.error.URLError as e:
        die(f"GitHub unreachable ({e.reason}). Fails closed.")


def pack_id_from_meta(meta: dict) -> str:
    src = meta.get("source") or {}
    owner = src.get("owner") or meta.get("owner") or "unknown"
    repo = src.get("repo") or meta.get("repo") or "unknown"
    sha = str(src.get("commit_sha") or meta.get("commit") or "")
    if not FULL_SHA_RE.match(sha):
        short = sha[:7] if sha else "nosha"
    else:
        short = sha[:7]
    return f"{owner}__{repo}@{short}"


def parse_id(pack_id: str) -> tuple[str, str, str]:
    m = ID_RE.match(pack_id)
    if not m:
        die(f"bad pack id: {pack_id!r} (want owner__repo@sha)")
    return m.group(1), m.group(2), m.group(3)


def recompute_file_hashes(pack: dict) -> list[str]:
    errors = []
    files = pack.get("files") or []
    for f in files:
        path = f.get("path", "<unknown>")
        text = f.get("text")
        expected = f.get("sha256")
        if text is None:
            errors.append(f"{path}: missing text")
            continue
        if not expected:
            errors.append(f"{path}: missing sha256")
            continue
        got = sha256_text(text)
        if got != expected:
            errors.append(f"{path}: sha256 mismatch (got {got[:12]}…)")
    return errors


def recompute_pack_digest(pack: dict) -> str | None:
    files = pack.get("files") or []
    if not files:
        return None
    lines = []
    for f in sorted(files, key=lambda x: x.get("path") or ""):
        path = f.get("path") or ""
        digest = f.get("sha256") or ""
        lines.append(f"{path}\t{digest}")
    return sha256_text("\n".join(lines))


def check_pack_digest(pack: dict) -> list[str]:
    errors = []
    expected = pack.get("pack_digest")
    if not expected:
        errors.append("missing pack_digest")
        return errors
    got = recompute_pack_digest(pack)
    if got is None:
        errors.append("no files to digest")
    elif got != expected:
        errors.append(f"pack_digest mismatch (got {got[:12]}…)")
    return errors


def check_source_commit(pack: dict, token: str | None, min_age_days: int) -> list[str]:
    errors = []
    src = pack.get("source") or {}
    owner = src.get("owner")
    repo = src.get("repo")
    sha = str(src.get("commit_sha") or "")
    if not owner or not repo:
        errors.append("source.owner/repo missing")
        return errors
    if not FULL_SHA_RE.match(sha):
        errors.append(f"commit_sha is not a full 40-hex SHA: {sha!r}")
        return errors

    commit = github_get(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}", token)
    commit_date_str = (commit.get("commit") or {}).get("committer", {}).get("date") or \
                      (commit.get("commit") or {}).get("author", {}).get("date")
    if not commit_date_str:
        errors.append("could not read commit date")
        return errors

    try:
        commit_dt = datetime.fromisoformat(commit_date_str.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"unparseable commit date: {commit_date_str}")
        return errors
    age_days = (datetime.now(timezone.utc) - commit_dt).total_seconds() / 86400
    if age_days < min_age_days:
        errors.append(f"commit is only {age_days:.1f} days old (min {min_age_days})")

    repo_info = github_get(f"https://api.github.com/repos/{owner}/{repo}", token)
    default_branch = repo_info.get("default_branch") or "main"
    try:
        compare = github_get(
            f"https://api.github.com/repos/{owner}/{repo}/compare/{default_branch}...{sha}",
            token,
        )
        status = compare.get("status")
        if status not in ("behind", "identical", "ahead"):
            if status == "diverged":
                errors.append(
                    f"commit {sha[:7]} is not a clean ancestor of {default_branch} "
                    f"(compare status={status})"
                )
    except SystemExit:
        raise
    except Exception as e:
        errors.append(f"could not verify reachability from {default_branch}: {e}")

    return errors


def already_on_shelf(pack_id: str) -> bool:
    if not MANIFEST.exists():
        return False
    with MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("id") == pack_id:
                return True
    return False


def run_established_checks(
    pack: dict,
    token: str | None,
    min_age_days: int,
    skip_network: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(recompute_file_hashes(pack))
    errors.extend(check_pack_digest(pack))
    if not skip_network:
        errors.extend(check_source_commit(pack, token, min_age_days))
    else:
        src = pack.get("source") or {}
        sha = str(src.get("commit_sha") or "")
        if not FULL_SHA_RE.match(sha):
            errors.append(f"commit_sha is not a full 40-hex SHA: {sha!r}")
    return errors


def last_manifest_hash() -> str:
    if not MANIFEST.exists() or MANIFEST.stat().st_size == 0:
        return "0" * 64
    last = ""
    with MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line.rstrip("\n")
    return sha256_text(last)


def append_manifest(entry: dict) -> None:
    prev = last_manifest_hash()
    entry = dict(entry)
    entry["prev"] = prev
    line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_manifest() -> list[dict]:
    entries = []
    if not MANIFEST.exists():
        return entries
    with MANIFEST.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"manifest.jsonl line {i}: {e}")
    return entries


def cmd_propose(args: argparse.Namespace) -> None:
    path = Path(args.pack)
    if not path.is_file():
        die(f"not a file: {path}")
    pack = load_json(path)
    pack_id = pack_id_from_meta(pack)

    if already_on_shelf(pack_id):
        die(f"{pack_id} is already on the shelf")

    token = os.environ.get("GITHUB_TOKEN")
    errors = run_established_checks(pack, token, args.min_age_days, skip_network=args.offline)
    if errors:
        print("propose REJECTED — checks failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    dest = STAGING_DIR / f"{pack_id}.tru-github-pack.json"
    write_json(dest, pack)
    meta = {
        "id": pack_id,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(path),
        "pack_digest": pack.get("pack_digest"),
    }
    write_json(STAGING_DIR / f"{pack_id}.meta.json", meta)
    print(f"staged {pack_id}")
    print(f"  {dest}")


def cmd_list(args: argparse.Namespace) -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    metas = sorted(STAGING_DIR.glob("*.meta.json"))
    if not metas:
        print("staging is empty")
        return
    for mpath in metas:
        meta = load_json(mpath)
        print(f"{meta.get('id')}  staged {meta.get('staged_at', '?')}")


def cmd_approve(args: argparse.Namespace) -> None:
    pack_id = args.pack_id
    by = args.by or os.environ.get("USER") or "unknown"
    owner, repo, short = parse_id(pack_id)

    staged = STAGING_DIR / f"{pack_id}.tru-github-pack.json"
    if not staged.is_file():
        die(f"not in staging: {pack_id}")

    pack = load_json(staged)
    token = os.environ.get("GITHUB_TOKEN")
    errors = run_established_checks(pack, token, args.min_age_days, skip_network=args.offline)
    if errors:
        print("approve REJECTED — re-check failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)

    if already_on_shelf(pack_id):
        die(f"{pack_id} is already on the shelf")

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PACKS_DIR / f"{pack_id}.tru-github-pack.json"
    write_json(dest, pack)
    pack_file_hash = sha256_file(dest)

    entry = {
        "id": pack_id,
        "owner": owner,
        "repo": repo,
        "commit_short": short,
        "commit_sha": (pack.get("source") or {}).get("commit_sha"),
        "pack_digest": pack.get("pack_digest"),
        "pack_file": str(dest.relative_to(ROOT)),
        "pack_file_sha256": pack_file_hash,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": by,
        "tier": "intact+provenance",
    }
    append_manifest(entry)

    staged.unlink(missing_ok=True)
    (STAGING_DIR / f"{pack_id}.meta.json").unlink(missing_ok=True)

    print(f"approved {pack_id}")
    print(f"  pack  → {dest}")
    print(f"  entry → shelf/manifest.jsonl")


def cmd_reject(args: argparse.Namespace) -> None:
    pack_id = args.pack_id
    reason = args.reason or "no reason given"
    staged = STAGING_DIR / f"{pack_id}.tru-github-pack.json"
    meta_path = STAGING_DIR / f"{pack_id}.meta.json"
    if not staged.is_file() and not meta_path.is_file():
        die(f"not in staging: {pack_id}")
    staged.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    print(f"rejected {pack_id}: {reason}")


def cmd_check(args: argparse.Namespace) -> None:
    entries = read_manifest()
    if not entries:
        print("shelf is empty — nothing to check")
        return

    problems = []
    prev_hash = "0" * 64
    seen_ids = set()

    for i, entry in enumerate(entries):
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        actual_prev = entry.get("prev")
        if actual_prev != prev_hash:
            problems.append(f"entry {i} ({entry.get('id')}): prev chain broken")
        prev_hash = sha256_text(line)

        pid = entry.get("id")
        if pid in seen_ids:
            problems.append(f"duplicate id: {pid}")
        seen_ids.add(pid)

        rel = entry.get("pack_file")
        if not rel:
            problems.append(f"{pid}: missing pack_file")
            continue
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"{pid}: pack file missing: {rel}")
            continue
        got = sha256_file(path)
        expected = entry.get("pack_file_sha256")
        if expected and got != expected:
            problems.append(f"{pid}: pack file hash mismatch")

    if PACKS_DIR.exists():
        for p in PACKS_DIR.glob("*.tru-github-pack.json"):
            stem = p.name.replace(".tru-github-pack.json", "")
            if stem not in seen_ids:
                problems.append(f"orphan pack file: {p.relative_to(ROOT)}")

    if problems:
        print(f"CHECK FAILED — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(2)
    print(f"CHECK OK — {len(entries)} entry(ies), chain intact, packs present")


def main() -> None:
    ap = argparse.ArgumentParser(description="TRU Shelf intake")
    ap.add_argument("--min-age-days", type=int, default=0,
                    help="minimum age of source commit in days (default 0 = open pipe)")
    ap.add_argument("--offline", action="store_true",
                    help="skip live GitHub checks (still requires full SHA shape)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_prop = sub.add_parser("propose", help="validate and stage a pack")
    p_prop.add_argument("pack", help="path to .tru-github-pack.json")

    sub.add_parser("list", help="list staged packs")

    p_app = sub.add_parser("approve", help="re-check and promote to shelf")
    p_app.add_argument("pack_id", help="owner__repo@sha")
    p_app.add_argument("--by", default=None, help="who is approving")

    p_rej = sub.add_parser("reject", help="remove from staging")
    p_rej.add_argument("pack_id")
    p_rej.add_argument("--reason", default="")

    sub.add_parser("check", help="offline audit of the shelf")

    args = ap.parse_args()
    {
        "propose": cmd_propose,
        "list": cmd_list,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "check": cmd_check,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
