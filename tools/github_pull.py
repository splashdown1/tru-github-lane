#!/usr/bin/env python3
"""
github_pull.py - pull public GitHub repos into TRU packs (tru-github-pack 2.1.0).

Stdlib only. For each repo it resolves a ref to an exact commit, reads the git
tree, keeps only docs / knowledge / config / manifest files (no code noise),
fetches them from raw.githubusercontent.com at that commit, hashes everything,
and writes one pack JSON per repo. Anything not kept is counted or listed in
"skipped" - a gap stays a gap.

Usage:
  python tools/github_pull.py owner/repo
  python tools/github_pull.py owner/repo@v1.2 https://github.com/o/r --out packs
  python tools/github_pull.py owner/repo --dry-run
  GITHUB_TOKEN=... python tools/github_pull.py owner/repo   # higher API rate limit
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

PACK_SCHEMA = "tru-github-pack"
PACK_VERSION = "2.1.0"
GENERATOR = {"name": "github_pull.py", "version": "2.1.0"}
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# ---------------------------------------------------------------- rules ----

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "third_party", "dist", "build", "out",
    "target", "__pycache__", ".venv", "venv", ".next", ".nuxt", "coverage",
    "bower_components", "site-packages", ".gradle", ".cache", "pods",
    "fixtures", "testdata", "__snapshots__",
}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "cargo.lock", "pipfile.lock", "composer.lock", "go.sum", "gemfile.lock",
    "npm-shrinkwrap.json",
}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tif", ".tiff",
    ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".wav",
    ".ogg", ".webm", ".so", ".dll", ".dylib", ".exe", ".bin", ".class", ".pyc",
    ".wasm", ".sqlite", ".db", ".psd", ".svg",
}
DOC_EXTS = {".md", ".markdown", ".rst", ".txt", ".adoc", ".org"}
DATA_EXTS = {".json", ".csv", ".tsv", ".yaml", ".yml", ".toml"}
DOC_DIRS = {"docs", "doc", "documentation", "wiki", "guides", "man"}
KNOWLEDGE_DIRS = {
    "knowledge", "notes", "spec", "specs", "design", "rfcs", "rfc", "adr",
    "adrs", "decisions", "content", "data", "canon", "reference",
}
CONFIG_NAMES = {
    "package.json", "pyproject.toml", "setup.cfg", "setup.py", "pipfile",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "composer.json",
    "gemfile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "makefile", "tsconfig.json", "mkdocs.yml", "book.toml", "_config.yml",
    "netlify.toml", "vercel.json", ".env.example", ".editorconfig", "cname",
}
MANIFEST_PREFIXES = ("license", "licence", "copying", "notice", "security",
                     "citation", "codemeta", "codeowners", "funding")
PRIORITY = {"readme": 0, "manifest": 1, "config": 2, "doc": 3,
            "knowledge": 4, "extra": 5}


def classify(path, include=(), exclude=()):
    """Return (kind, reason). kind is None when the file is skipped.

    Reasons starting with "noise:" are only counted; other reasons are listed
    in the pack's "skipped" array.
    """
    if any(fnmatch.fnmatch(path, g) for g in exclude):
        return None, "excluded-by-glob"
    if any(fnmatch.fnmatch(path, g) for g in include):
        return "extra", "included-by-glob"

    parts = path.split("/")
    base = parts[-1]
    low = base.lower()
    dirs = [p.lower() for p in parts[:-1]]
    ext = posixpath.splitext(low)[1]

    for d in dirs:
        if d in SKIP_DIRS:
            return None, "noise:skip-dir"
    if dirs and dirs[0].startswith(".") and dirs[0] != ".github":
        return None, "noise:dot-dir"
    if low in LOCKFILES:
        return None, "noise:lockfile"
    if low.endswith((".min.js", ".min.css", ".map", ".bundle.js")):
        return None, "noise:generated"
    if ext in BINARY_EXTS:
        return None, "noise:binary"

    if low.startswith("readme"):
        return "readme", "readme"
    if any(low.startswith(p) for p in MANIFEST_PREFIXES) and len(parts) == 1:
        return "manifest", "manifest"
    if path.startswith(".github/workflows/") and ext in (".yml", ".yaml"):
        return "config", "workflow"
    if low in CONFIG_NAMES or re.fullmatch(r"requirements[\w.-]*\.txt", low):
        return "config", "config"

    in_doc_dir = any(d in DOC_DIRS for d in dirs)
    in_know_dir = any(d in KNOWLEDGE_DIRS for d in dirs)
    at_root = len(parts) == 1

    if ext in DOC_EXTS:
        if ext == ".txt" and not (at_root or in_doc_dir or in_know_dir):
            return None, "noise:code-or-other"
        if in_know_dir:
            return "knowledge", "knowledge-dir"
        return "doc", "doc-dir" if in_doc_dir else "prose"
    if ext in DATA_EXTS and in_know_dir:
        return "knowledge", "knowledge-data"
    return None, "noise:code-or-other"


def select_files(entries, include=(), exclude=(), max_file=256 * 1024,
                 max_total=8 * 1024 * 1024):
    """Pure function over git-tree entries -> (selected, skipped, noise_counts)."""
    selected, skipped, noise = [], [], Counter()
    for e in entries:
        if e.get("type") != "blob":
            continue
        kind, reason = classify(e["path"], include, exclude)
        if kind is None:
            if reason.startswith("noise:"):
                noise[reason[6:]] += 1
            else:
                skipped.append({"path": e["path"], "reason": reason})
            continue
        if e.get("size", 0) > max_file:
            skipped.append({"path": e["path"], "reason": "too-large",
                            "size": e.get("size", 0)})
            continue
        selected.append({"path": e["path"], "kind": kind,
                         "size": e.get("size", 0), "git_sha": e.get("sha")})
    selected.sort(key=lambda f: (PRIORITY[f["kind"]], f["path"]))
    kept, total = [], 0
    for f in selected:
        if total + f["size"] > max_total:
            skipped.append({"path": f["path"], "reason": "over-budget",
                            "size": f["size"]})
            continue
        total += f["size"]
        kept.append(f)
    return kept, skipped, noise


def pack_digest(files):
    """sha256 over sorted 'path<TAB>sha256' lines. The lane recomputes this."""
    lines = [f"{f['path']}\t{f['sha256']}" for f in sorted(files, key=lambda f: f["path"])]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# ------------------------------------------------------------- network -----

class PullError(Exception):
    pass


def http_get(url, token=None, retries=3, timeout=30):
    headers = {"User-Agent": "tru-github-pull/2.1"}
    if url.startswith(API):
        headers["Accept"] = "application/vnd.github+json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise PullError(f"404 not found (private or misspelled?): {url}") from e
            if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
                reset = e.headers.get("X-RateLimit-Reset", "?")
                raise PullError("GitHub API rate limit reached (resets at epoch "
                                f"{reset}). Set GITHUB_TOKEN and retry.") from e
            last = e
        except urllib.error.URLError as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise PullError(f"failed after {retries} tries: {url} ({last})")


def parse_spec(spec):
    s = spec.strip()
    ref = None
    if s.startswith("http"):
        u = urllib.parse.urlparse(s)
        parts = [p for p in u.path.split("/") if p]
        if u.netloc.lower() not in ("github.com", "www.github.com") or len(parts) < 2:
            raise ValueError(f"not a GitHub repo URL: {spec}")
        owner, repo = parts[0], parts[1]
        if len(parts) >= 4 and parts[2] == "tree":
            ref = "/".join(parts[3:])
    else:
        if "@" in s:
            s, ref = s.rsplit("@", 1)
        parts = s.strip("/").split("/")
        if len(parts) != 2:
            raise ValueError(f"expected owner/repo, got: {spec}")
        owner, repo = parts
    if repo.endswith(".git"):
        repo = repo[:-4]
    ok = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not (ok.match(owner) and ok.match(repo)):
        raise ValueError(f"bad owner/repo: {spec}")
    return owner, repo, ref or None


def decode_text(raw):
    if b"\x00" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def pull_repo(owner, repo, ref, args, token):
    meta = json.loads(http_get(f"{API}/repos/{owner}/{repo}", token))
    ref = ref or meta["default_branch"]
    commit = json.loads(http_get(
        f"{API}/repos/{owner}/{repo}/commits/{urllib.parse.quote(ref, safe='')}", token))
    commit_sha, tree_sha = commit["sha"], commit["commit"]["tree"]["sha"]
    tree = json.loads(http_get(
        f"{API}/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1", token))

    warnings = []
    if tree.get("truncated"):
        warnings.append("GitHub truncated the git tree; this pack is incomplete.")

    selected, skipped, noise = select_files(
        tree.get("tree", []), args.include, args.exclude,
        args.max_file_kb * 1024, int(args.max_total_mb * 1024 * 1024))

    print(f"  {owner}/{repo}@{commit_sha[:7]}: {len(selected)} selected, "
          f"{sum(noise.values())} noise, {len(skipped)} listed skips")
    if args.dry_run:
        for f in selected:
            print(f"    {f['kind']:<9} {f['size']:>8}  {f['path']}")
        return None

    def fetch(f):
        url = f"{RAW}/{owner}/{repo}/{commit_sha}/{urllib.parse.quote(f['path'])}"
        try:
            raw = http_get(url)
        except PullError as e:
            return None, {"path": f["path"], "reason": "fetch-failed", "detail": str(e)[:200]}
        text = decode_text(raw)
        if text is None:
            return None, {"path": f["path"], "reason": "not-text"}
        ext = posixpath.splitext(f["path"])[1].lstrip(".").lower()
        return {"path": f["path"], "kind": f["kind"], "size": len(raw),
                "git_sha": f["git_sha"], "sha256": hashlib.sha256(raw).hexdigest(),
                "lang": ext or posixpath.basename(f["path"]).lower(),
                "text": text}, None

    files = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for ok, bad in pool.map(fetch, selected):
            if ok:
                files.append(ok)
            else:
                skipped.append(bad)
    files.sort(key=lambda f: (PRIORITY[f["kind"]], f["path"]))

    lic = (meta.get("license") or {}).get("spdx_id")
    return {
        "schema": PACK_SCHEMA,
        "version": PACK_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": GENERATOR,
        "source": {
            "owner": owner, "repo": repo, "url": meta["html_url"],
            "ref": ref, "commit_sha": commit_sha, "tree_sha": tree_sha,
            "default_branch": meta["default_branch"],
            "description": meta.get("description"),
            "license": lic, "topics": meta.get("topics", []),
            "pushed_at": meta.get("pushed_at"), "archived": meta.get("archived"),
            "fork": meta.get("fork"),
        },
        "provenance": {
            "method": "github-rest-api+raw",
            "api_base": API, "raw_base": RAW,
            "authenticated": bool(token),
            "tree_truncated": bool(tree.get("truncated")),
            "limits": {"max_file_kb": args.max_file_kb,
                       "max_total_mb": args.max_total_mb,
                       "include": list(args.include), "exclude": list(args.exclude)},
        },
        "stats": {
            "files": len(files),
            "bytes": sum(f["size"] for f in files),
            "by_kind": dict(Counter(f["kind"] for f in files)),
            "noise_counts": dict(noise),
            "skipped_listed": len(skipped),
        },
        "pack_digest": pack_digest(files),
        "files": files,
        "skipped": skipped,
        "warnings": warnings,
    }


def write_pack(pack, out, single):
    s = pack["source"]
    if single and out.endswith(".json"):
        path = out
    else:
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, f"{s['owner']}--{s['repo']}.tru-github-pack.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, ensure_ascii=False, indent=1 if ARGS_PRETTY else None,
                  separators=None if ARGS_PRETTY else (",", ":"))
    os.replace(tmp, path)
    return path


ARGS_PRETTY = False


def main(argv=None):
    global ARGS_PRETTY
    ap = argparse.ArgumentParser(description="Pull public GitHub repos into TRU packs.")
    ap.add_argument("repos", nargs="+", help="owner/repo[@ref] or a github.com URL")
    ap.add_argument("--out", default="packs", help="output dir, or a .json file for one repo")
    ap.add_argument("--include", action="append", default=[], metavar="GLOB",
                    help="force-include paths matching GLOB (kind 'extra'); repeatable")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                    help="drop paths matching GLOB; repeatable")
    ap.add_argument("--max-file-kb", type=int, default=256)
    ap.add_argument("--max-total-mb", type=float, default=8.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--token-env", default="GITHUB_TOKEN")
    ap.add_argument("--dry-run", action="store_true", help="list what would be kept; write nothing")
    ap.add_argument("--pretty", action="store_true", help="indent JSON (bigger, diffable)")
    args = ap.parse_args(argv)
    ARGS_PRETTY = args.pretty
    token = os.environ.get(args.token_env) or None

    failures = 0
    for spec in args.repos:
        try:
            owner, repo, ref = parse_spec(spec)
            pack = pull_repo(owner, repo, ref, args, token)
            if pack:
                path = write_pack(pack, args.out, single=len(args.repos) == 1)
                print(f"  wrote {path} ({pack['stats']['files']} files, "
                      f"{pack['stats']['bytes'] // 1024} KB)")
                for w in pack["warnings"]:
                    print(f"  WARNING: {w}")
        except (PullError, ValueError, KeyError, json.JSONDecodeError) as e:
            failures += 1
            print(f"  FAILED {spec}: {e}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
