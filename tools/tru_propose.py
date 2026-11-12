#!/usr/bin/env python3
"""TRU proposer — pull a public repo into a pack, then stage it for the shelf.

Links github_pull.py → tru_shelf.py propose.

stdlib only. Uses the same CLI surface as github_pull for repo specs.

Usage:
  python tools/tru_propose.py owner/repo
  python tools/tru_propose.py owner/repo@v1.2 --out /tmp/packs
  python tools/tru_propose.py owner/repo --min-age-days 0 --offline   # local test only
  GITHUB_TOKEN=... python tools/tru_propose.py owner/repo

Flow:
  1. Run github_pull against each spec → write pack JSON
  2. Run tru_shelf propose on each resulting pack
  3. Report staged ids (or rejection reasons)

Staging never touches the shelf. Approve is still a separate, deliberate step.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PULL = ROOT / "tools" / "github_pull.py"
SHELF = ROOT / "tools" / "tru_shelf.py"


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(ROOT), env=env, text=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Pull public GitHub repos into packs and stage them for the TRU shelf."
    )
    ap.add_argument("repos", nargs="+", help="owner/repo[@ref] or a github.com URL")
    ap.add_argument("--out", default=None,
                    help="scratch dir for packs (default: temp dir, cleaned after)")
    ap.add_argument("--include", action="append", default=[], metavar="GLOB")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    ap.add_argument("--max-file-kb", type=int, default=256)
    ap.add_argument("--max-total-mb", type=float, default=8.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--min-age-days", type=int, default=6,
                    help="passed to tru_shelf propose (default 6 — verification buffer)")
    ap.add_argument("--offline", action="store_true",
                    help="pass --offline to tru_shelf (skip live GitHub age/reachability)")
    ap.add_argument("--dry-run", action="store_true",
                    help="only run github_pull --dry-run; do not propose")
    ap.add_argument("--keep-packs", action="store_true",
                    help="do not delete the scratch pack files after propose")
    args = ap.parse_args(argv)

    if not PULL.is_file():
        die(f"missing {PULL}")
    if not SHELF.is_file():
        die(f"missing {SHELF}")

    env = os.environ.copy()

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
        tmp = None
    else:
        tmp = tempfile.TemporaryDirectory(prefix="tru-propose-")
        out_dir = Path(tmp.name)
        cleanup = not args.keep_packs

    try:
        pull_cmd = [
            sys.executable, str(PULL),
            *args.repos,
            "--out", str(out_dir),
            "--max-file-kb", str(args.max_file_kb),
            "--max-total-mb", str(args.max_total_mb),
            "--workers", str(args.workers),
        ]
        for g in args.include:
            pull_cmd.extend(["--include", g])
        for g in args.exclude:
            pull_cmd.extend(["--exclude", g])
        if args.dry_run:
            pull_cmd.append("--dry-run")

        rc = run(pull_cmd, env=env).returncode
        if rc != 0:
            print(f"github_pull exited {rc}", file=sys.stderr)
            return rc
        if args.dry_run:
            return 0

        packs = sorted(out_dir.glob("*.tru-github-pack.json"))
        if not packs:
            die("github_pull wrote no packs")

        failures = 0
        for pack_path in packs:
            propose_cmd = [
                sys.executable, str(SHELF),
                "--min-age-days", str(args.min_age_days),
                "propose", str(pack_path),
            ]
            if args.offline:
                propose_cmd = [
                    sys.executable, str(SHELF),
                    "--min-age-days", str(args.min_age_days),
                    "--offline",
                    "propose", str(pack_path),
                ]
            prc = run(propose_cmd, env=env).returncode
            if prc != 0:
                failures += 1
                print(f"  propose failed for {pack_path.name}", file=sys.stderr)

        if failures:
            print(f"{failures} pack(s) failed propose", file=sys.stderr)
            return 1
        print("all packs staged — review with: python tools/tru_shelf.py list")
        return 0
    finally:
        if cleanup and tmp is not None:
            try:
                tmp.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
