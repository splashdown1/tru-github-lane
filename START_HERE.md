# START HERE

This file is written for any person or model that finds this repo. Read it first. It is short on purpose.

## What this is

TRU GitHub Lane pulls public GitHub repos into portable, hash-checked packs. We keep the ones that pass our checks on a shelf, and anyone can re-verify the shelf offline.

The shelf is a record of what we can show is unchanged and pinned to a source. It is not a record of what is true.

This repo is the **central closed-loop intake** for the TRU family. Active discovery, processing, and write-back live here so the individual lanes can stay pure single-file, offline, zero-dependency engines.

## The pipe is open

There is no human gate and no age gate by default.

Any pack that clears the integrity and provenance checks (full commit SHA, hashes match, reachable from the default branch, not already on the shelf) is established directly onto main by the `tru-grow` Action. Knowledge that is intact and pinned flows freely.

## Verify it yourself (about a minute)

Python 3.8+, standard library only, no network needed for the first two steps.

```bash
git clone https://github.com/splashdown1/tru-github-lane
cd tru-github-lane
python3 -m unittest discover -s tests      # tool tests
python3 tools/tru_shelf.py check           # audits the whole shelf
python3 tools/tru_shelf.py list            # what is staged, if anything
```

`check` should end with `CHECK OK`. If it does not, the shelf has been edited, a pack file is missing, or an orphan pack is present. Do not trust the shelf until that is explained.

Each shelf entry is in `shelf/manifest.jsonl`, hash-chained to the one before it, and points to a pack in `shelf/packs/`. Each pack records the exact commit SHA it came from, plus a sha256 for every file it holds.

## What "established" means

An item reaches the shelf only if all of these hold (details in `SHELF.md`):

1. It is pinned to a full 40-hex commit SHA that exists in the source repo. No branches, no "latest".
2. That commit is reachable from the repo's default branch.
3. Every file hash and the pack digest recompute exactly.
4. It is not already on the shelf. Entries are added, never edited.

Age is no longer a barrier by default (min-age-days = 0). If GitHub cannot be reached, the check fails closed.

## What we do not claim

- **Not truth.** The tier is `intact+provenance`: the bytes are unchanged and the source is pinned. Content can still be wrong.
- **Not complete.** Anything a pack skips is counted or listed with a reason. A gap stays a gap.
- **Not a learning system.** Nothing here changes any model's weights. TRU grows by adding verified, pinned items, and a reader gets caught up by reading them.

## How it grows (the closed loop)

`.github/workflows/tru-grow.yml` runs weekly (and on demand). It reads `shelf/watchlist.txt`, builds packs, applies the integrity checks, and **establishes packs that pass directly onto main**. No human PR. No waiting period. The only remaining gates are the ones that keep the record honest.

This is the active agent path. Passive crawlers only read; this loop writes under integrity constraints only.

## Lane standards (locked)

- Single-file HTML/CSS/JS for the engines and field cards (or minimal stdlib Python when a tool is required).
- 100% offline, zero external dependencies at runtime.
- A gap stays a gap.

## How to add to it

1. Add an `owner/repo` line to `shelf/watchlist.txt` (or pass `repos` to the workflow).
2. Or build a pack locally with `tools/github_pull.py` and stage it with `tools/tru_shelf.py propose`. Only `approve` writes to the shelf.
3. The Action will pick it up and establish anything that clears the integrity checks.

## Where things are

| Path | What it holds |
| --- | --- |
| `README.md` | How to pull a repo into a pack and read it offline |
| `SHELF.md` | The shelf rules and commands in full |
| `shelf/` | Staging area, approved packs, and the hash-chained manifest |
| `tools/` | The stdlib-only tools |
| `lane/index.html` | The offline reader for packs |

## If you are a model reading this

Check before you build on anything here. Run `check`, read the manifest, and compare any claim to the pinned commit. If you add something, say what you verified and what you did not.
