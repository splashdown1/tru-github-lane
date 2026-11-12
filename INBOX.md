# TRU Open Inbox

The knowledge pipe is open.

## Two ways knowledge enters

1. **Watchlist (proactive)**  
   Sources listed in `shelf/watchlist.txt` are scanned by `tru-grow`. This is for known, recurring sources.

2. **Inbox (open to any agent)**  
   Any agent, crawler, or human can drop a valid pack into `shelf/inbox/` and the same automated path will process it.

There is no requirement to be pre-listed on the watchlist. The only requirements are the integrity checks that keep the record honest.

## How an external agent feeds knowledge

1. Build a pack with `tools/github_pull.py` (or any tool that produces a valid `.tru-github-pack.json` matching the schema).
2. Place the file in `shelf/inbox/` (via pull request, direct push if you have write access, or any other means that lands the file there).
3. The `tru-grow` workflow triggers on push to `shelf/inbox/**` (and also on schedule / manual / `repository_dispatch` type `tru-intake`).
4. The pack is proposed, checked (full SHA, hashes, reachability), and if clean is **established directly on main**. No age gate. No human gate.
5. Successfully processed inbox files are cleared so the pipe stays open and clean.

## What still must pass

- Full 40-hex commit SHA (no floating branch names)
- Every file hash and the pack digest recompute exactly
- Commit is reachable from the source repo’s default branch
- Pack is not already on the shelf

If those hold, the knowledge is established. The pipe is as wide as the integrity of the data.

## repository_dispatch (programmatic)

Agents that can call the GitHub API can also fire:

```
POST /repos/splashdown1/tru-github-lane/dispatches
{
  "event_type": "tru-intake"
}
```

This runs the same grow job (which will process whatever is currently in the inbox and the watchlist).

## Summary

Watchlist = curated recurring sources.  
Inbox = open entrance for anything that arrives as a valid pack.  
Both feed the identical automated establish path.  
No human gate. No age gate. Only integrity.
