# TRU GitHub Lane

Pull public GitHub repos into portable packs, then inspect, search and verify them offline in a single HTML file.

- `tools/github_pull.py` builds a `tru-github-pack` (format 2.1.0) from a public repo.
- `lane/index.html` is the offline reader. No network, no dependencies, no build step.

A gap stays a gap: every file that was not kept is either counted or listed with a reason, and every kept file carries a hash.

## Quick start

```bash
python tools/github_pull.py owner/repo            # writes packs/owner--repo.tru-github-pack.json
python tools/github_pull.py owner/repo --dry-run  # show what would be kept, write nothing
```

Then open `lane/index.html` in a browser and load the pack (button or drag and drop). Packs are stored in the browser's IndexedDB, so they are still there next time.

Python 3.8+, standard library only. Set `GITHUB_TOKEN` to raise the GitHub API rate limit (60 requests/hour unauthenticated).

### Options

| Flag | Meaning |
| --- | --- |
| `owner/repo@ref` or a github.com URL | Repo to pull. `@ref` is a branch, tag or commit. Several repos allowed. |
| `--out DIR` | Output directory (default `packs`), or a `.json` path when pulling one repo. |
| `--include GLOB` | Force-include matching paths as kind `extra`. Repeatable. |
| `--exclude GLOB` | Drop matching paths. Repeatable. Wins over `--include`. |
| `--max-file-kb N` | Skip files larger than N KB (default 256). |
| `--max-total-mb N` | Total text budget (default 8). Lowest-priority files are dropped first. |
| `--dry-run` | Classify only. |
| `--pretty` | Indent the JSON. |

## What gets extracted

The puller resolves the ref to an exact commit, reads the git tree, and keeps only:

| Kind | Examples |
| --- | --- |
| `readme` | `README*` anywhere outside skipped directories |
| `manifest` | root `LICENSE`, `NOTICE`, `SECURITY`, `CITATION.cff`, `CODEOWNERS`, `codemeta.json` |
| `config` | `package.json`, `pyproject.toml`, `requirements*.txt`, `Cargo.toml`, `go.mod`, `Dockerfile`, `Makefile`, `tsconfig.json`, `mkdocs.yml`, `.github/workflows/*.yml`, and similar |
| `doc` | `.md .rst .adoc .org .txt` at the root, in `docs/`, `doc/`, `wiki/`, `guides/`, or elsewhere (`.txt` only at the root or in doc/knowledge dirs) |
| `knowledge` | prose in `notes/`, `knowledge/`, `spec(s)/`, `rfcs/`, `adr(s)/`, `design/`, `content/`, `canon/`, `reference/`, `data/`, plus `.json .csv .tsv .yaml .toml` data files inside those directories |
| `extra` | anything matched by `--include` |

Never kept: source code, `node_modules`, `vendor`, `dist`, `build`, lockfiles, minified or generated files, images and other binaries (SVG included), test fixtures, dot-directories other than `.github`. These are counted in `stats.noise_counts`, not listed.

Listed in `skipped` with a reason: `too-large`, `over-budget`, `not-text`, `fetch-failed`, `excluded-by-glob`.

If GitHub truncates a very large tree, the pack says so in `warnings` and `provenance.tree_truncated`.

## Pack format 2.1.0

See `schema/tru-github-pack.schema.json`. In short:

- `source`: owner, repo, url, ref, **commit_sha**, tree_sha, license, topics, pushed_at.
- `provenance`: how it was fetched, whether authenticated, the limits used.
- `files[]`: `path`, `kind`, `size`, `git_sha` (blob sha from GitHub), `sha256` (of the stored UTF-8 text), `lang`, `text`.
- `pack_digest`: sha256 of the sorted `path<TAB>sha256` lines joined with LF.
- `skipped[]`, `warnings[]`, `stats`.

Files are fetched from `raw.githubusercontent.com` at the resolved commit sha, never from a moving branch.

The lane's **Verify hashes** button recomputes every file hash and the pack digest in the browser and flags any mismatch. It needs `crypto.subtle`, which browsers expose on `https:` and `localhost`, and on `file:` in most. If yours does not, serve the folder locally with `python -m http.server`.

Compatibility: the lane reads any pack with a `files` array of `{path, text}` and falls back to a single `readme` string for older packs. Fields it does not find are simply not shown.

## The lane

- Load several packs at once; search runs across all of them (BM25-style ranking, path matches weighted up).
- File tree with kind filters, rendered Markdown or source view, and a Provenance panel with commit, limits, warnings and everything that was skipped.
- Markdown is escaped before rendering; links are shown but inert, so a pack can never make the page call out.
- Light and dark follow the system; the Theme button overrides.

## Repo layout

```
tru-github-lane/
  README.md
  LICENSE
  tools/github_pull.py
  lane/index.html
  schema/tru-github-pack.schema.json
  tests/test_pull.py
  packs/examples/        # commit small example packs here
  .gitignore             # ignores generated packs
```

Run the tests with `python -m unittest discover -s tests`.

## License

MIT
