#!/usr/bin/env python3
"""tru_extract.py - deeper extraction than README.md, with provenance.

Reads a local checkout (--dir) or, when network exists, a repo tarball pinned
to a commit SHA (--repo owner/name --sha <40hex>). Emits a tru-github-pack
v2.1.0 entry set; merges into an existing pack if --merge is given.
One pack-level timestamp covers everything. Stdlib only.

Extracts: file tree, README + all markdown headings, LICENSE id, manifests
(package.json, pyproject.toml, requirements*.txt, setup.py, Cargo.toml, go.mod),
Python module/class/function docstrings, JS/TS exported names, TODO/FIXME notes.
Every record carries repo, sha, path, sha256 of the file it came from.
"""
import argparse, ast, hashlib, io, json, os, re, sys, tarfile, urllib.request
from datetime import datetime, timezone

SCHEMA, VERSION = "tru-github-pack", "2.1.0"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
MAX_FILE = 1_000_000
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MANIFESTS = {"package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "Pipfile"}

def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def sha256(b): return hashlib.sha256(b).hexdigest()

def read_tar(repo, sha):
    url = f"https://codeload.github.com/{repo}/tar.gz/{sha}"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        for m in t.getmembers():
            if not m.isfile() or m.size > MAX_FILE: continue
            rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
            if any(p in SKIP_DIRS for p in rel.split("/")): continue
            files[rel] = t.extractfile(m).read()
    return files

def read_dir(d):
    files = {}
    for root, dirs, names in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            p = os.path.join(root, n)
            if os.path.getsize(p) > MAX_FILE: continue
            with open(p, "rb") as f:
                files[os.path.relpath(p, d).replace(os.sep, "/")] = f.read()
    return files

def text(b): return b.decode("utf-8", errors="replace")

def py_items(src):
    out = []
    try: tree = ast.parse(src)
    except SyntaxError: return out
    d = ast.get_docstring(tree)
    if d: out.append(("module", "", d))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(n)
            if d: out.append((type(n).__name__.replace("Def", "").lower(), n.name, d))
    return out

def extract(files, repo, sha):
    recs = []
    def add(kind, path, name, content, raw):
        recs.append({"kind": kind, "repo": repo, "sha": sha, "path": path, "name": name,
                     "content": content[:4000], "source_sha256": sha256(raw)})
    recs.append({"kind": "tree", "repo": repo, "sha": sha, "path": "", "name": "file tree",
                 "content": "\n".join(sorted(files)), "source_sha256": sha256("\n".join(sorted(files)).encode())})
    for path, raw in sorted(files.items()):
        base, low = os.path.basename(path), path.lower()
        if base in MANIFESTS or re.match(r"requirements.*\.txt$", base):
            add("manifest", path, base, text(raw), raw)
        elif base.upper().startswith(("LICENSE", "COPYING")):
            first = text(raw).strip().splitlines()[:1]
            add("license", path, base, first[0] if first else "", raw)
        elif low.endswith((".md", ".markdown")):
            t = text(raw)
            heads = [l.strip() for l in t.splitlines() if re.match(r"#{1,6}\s", l)]
            add("readme" if base.lower().startswith("readme") else "markdown", path, base,
                "\n".join(heads) + "\n\n" + t[:2500], raw)
        elif low.endswith(".py"):
            t = text(raw)
            for k, n, d in py_items(t): add("py-" + k, path, n or base, d, raw)
        elif low.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs")):
            t = text(raw)
            names = re.findall(r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z0-9_$]+)", t)
            if names: add("js-exports", path, base, ", ".join(names), raw)
        if low.endswith((".py", ".js", ".ts", ".md", ".sh", ".go", ".rs")):
            notes = [l.strip() for l in text(raw).splitlines() if re.search(r"\b(TODO|FIXME)\b", l)]
            if notes: add("todo", path, base, "\n".join(notes[:20]), raw)
    return recs

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--sha", required=True, help="full 40-hex commit SHA (provenance requires a pin)")
    p.add_argument("--dir", help="local checkout at that SHA (offline)")
    p.add_argument("--merge", help="existing pack JSON to extend")
    p.add_argument("-o", "--out", default="tru-github-pack.json")
    a = p.parse_args()
    if not SHA_RE.match(a.sha.lower()):
        sys.exit("--sha must be a full 40-hex commit SHA")
    sha = a.sha.lower()
    files = read_dir(a.dir) if a.dir else read_tar(a.repo, sha)
    recs = extract(files, a.repo, sha)
    pack = {"schema": SCHEMA, "version": VERSION, "timestamp": now(), "records": []}
    if a.merge and os.path.exists(a.merge):
        old = json.load(open(a.merge, encoding="utf-8"))
        pack["records"] = [r for r in old.get("records", old.get("repos", [])) if isinstance(r, dict) and "kind" in r
                           and not (r.get("repo") == a.repo and r.get("sha") == sha)]
        pack["merged_from"] = {"version": old.get("version"), "timestamp": old.get("timestamp")}
    pack["records"] += recs
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, ensure_ascii=False); f.write("\n")
    kinds = {}
    for r in recs: kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"{len(recs)} records -> {a.out}  {kinds}")

if __name__ == "__main__":
    main()
