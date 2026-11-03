# TRU Shelf Intake

`tools/tru_shelf.py` (stdlib only).

## Files

```
tools/tru_shelf.py
tools/tru_propose.py
tests/test_tru_shelf.py
SHELF.md
shelf/
  staging/          # candidate packs (not yet on the shelf)
  packs/            # approved packs (immutable once written)
  manifest.jsonl    # hash-chained append-only index
```

## Flow

```bash
python tools/tru_shelf.py propose  path/to/x.tru-github-pack.json   # checks, then stages
python tools/tru_shelf.py list                                      # what is waiting
python tools/tru_shelf.py approve  owner__repo@abc1234 --by you     # re-checks, then adds to shelf
python tools/tru_shelf.py reject   owner__repo@abc1234 --reason "..."
python tools/tru_shelf.py check                                     # offline audit of the whole shelf
```

Staging never touches the shelf. Only `approve` does, and it re-runs every check first.

## What “established” means (all must pass)

1. Source commit is a full 40-hex SHA that exists in the source repo (no branches, no “latest”).
2. That commit is reachable from the repo’s default branch.
3. Every file `sha256` and the `pack_digest` recompute exactly.
4. Commit is at least 7 days old (`--min-age-days`).
5. Not already on the shelf. Entries are added, never edited.

If GitHub can’t be reached, the pack is rejected (fails closed).

Use `--offline` only for local testing of hash logic; it still requires a full 40-hex SHA shape.

## Tier

`intact+provenance`. It means the bytes are unchanged and the source is pinned.  
It does **not** mean the content is true.

## Audit

`shelf/manifest.jsonl` is hash-chained: each entry holds the hash of the one before it, and the hash of its shelf pack file.  
`check` reports edited entries, changed or missing pack files, and orphan packs.  
Deleting entries from the end of the file is only visible through git history.

## Auth

Set `GITHUB_TOKEN` (read-only is enough) to avoid GitHub’s anonymous rate limit.

## Tests

```bash
python -m unittest discover -s tests
```

## Proposer (the missing front link)

`tools/tru_propose.py` runs `github_pull.py` then `tru_shelf.py propose`:

```bash
python tools/tru_propose.py owner/repo
python tools/tru_propose.py owner/repo@v1.2
GITHUB_TOKEN=... python tools/tru_propose.py owner/repo --min-age-days 7
```

This is the autonomous intake path. Staging still never touches the shelf;
`approve` remains a separate deliberate step.
