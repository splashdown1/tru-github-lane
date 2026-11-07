# Claude contribution to TRU

Contributed by: Claude (Anthropic), working with splashdown1. Single pack-level timestamp applies on publish.

## What we added

- `tools/tru_shelf.py`: shelf intake (propose, approve, reject, list, check). The shelf holds only items pinned to a full 40-hex commit SHA; each item records who contributed it, so the shelf is added to, not only taken from.
- `tools/tru_extract.py`: extraction beyond README.md (file tree, all markdown headings, license, manifests, Python docstrings, JS exports, TODO/FIXME), each record with repo, SHA, path and source hash. Emits pack v2.1.0 and merges into an existing pack.
- `tools/tru_lane.py`: builds a single-file offline HTML lane from a pack (search and kind filter, no network, no external assets).
- `docs/hg-torus-inertial-rig.md`: evidence tiers and a controlled test protocol for the liquid-metal torus experiment.

## Method notes

- Established means pinned. Branch names, tags and short SHAs are held as pending.
- Dedup is by repo + SHA + path; re-extracting the same SHA replaces its records.
- All tools are stdlib-only Python and run offline.

## Tested

Shelf: unpinned item refused, pinned item established, audit passes. Extract and lane: ran against a local directory, merge replaced rather than duplicated records. Not yet run against a live GitHub tarball (no network in this session).
