# Claude contribution to TRU

Contributed by: Claude (Anthropic), working with splashdown1. Single pack-level timestamp applies on publish.

## What we added

- `tools/tru_extract.py`: extraction beyond README.md (file tree, all markdown headings, license, manifests, Python docstrings, JS exports, TODO/FIXME), each record with repo, SHA, path and source hash. Emits pack v2.1.0 and merges into an existing pack.
- `tools/tru_lane.py`: builds a single-file offline HTML lane from a pack (search and kind filter, no network, no external assets).
- `docs/hg-torus-inertial-rig.md`: evidence tiers and a controlled test protocol for the liquid-metal torus experiment.

## Shelf

The shelf is the existing pack-oriented `tools/tru_shelf.py` (propose a pack, re-check hashes and provenance, approve, check). Our contribution goes through it as a pack built at a pinned commit; we did not replace it.

## Method notes

- Established means pinned to a full 40-hex commit SHA.
- Re-extracting the same repo and SHA replaces its records instead of duplicating them.
- Stdlib-only Python, runs offline.

## Tested

Extract and lane: ran against a local directory, and merge replaced rather than duplicated records. Not yet run against a live GitHub tarball, and not yet accepted by the shelf's pack validator.
