# Profile contribution statistics

The `human + agent` section contains separate human and agent commit calendars,
refreshed by the existing profile workflow at minute 17 of every hour (UTC), or
through its manual trigger. Schedules and GitHub image caches can delay visible
updates; these are periodically generated images, not live JavaScript widgets.
The updater needs only Python's
standard library, Git, and the workflow's existing token; no new secrets or
third-party statistics service are required.

## Calendar display

- Each green square represents one UTC author date in the last **365 days**,
  including today. Weeks start on Sunday; alignment padding is blank, not zero
  activity. Leap days are included when within the rolling window.
- Both authors use the same intensity scale: 0, 1–3, 4–9, 10–19, and 20+ commits.
  The totals and text additions/deletions inside each card cover that same window.
- Desktop cards show the full year across one grid. Below 600px, a separate image
  wraps the same weeks into two bands for readable labels. Images adapt to the
  viewer's preferred light/dark color scheme without JavaScript or animation.
- The original year-to-date and all-time totals remain in an expandable section.
  These calendars count **commits**, not GitHub's broader contributions metric
  (which also includes issues, pull requests, and reviews). They do not alter the
  native GitHub contribution graph or commit authorship.
- Calendar images and README are committed together only after a successful scan.
  The two desktop and two mobile images live under `assets/`; no external hosting
  is required. SVG descriptions include accessible aggregate summaries. GitHub
  embeds SVGs as images, so individual-day tooltips are not promised in the README.

## Counting rules

- **Scope:** publicly visible, non-fork repositories owned by the profile owner.
  Archived repositories remain included. Private repositories are never scanned.
- **History:** commits reachable from each repository's default branch at the
  time it is scanned. Merge commits are excluded; a squash merge contributes its
  resulting commit, not the original branch's individual commits.
- **Identity:** GitHub's resolved commit **author** login, not committer, pusher,
  repository ownership, author display name, or co-author trailers. The owner is
  the human identity; the agent login defaults to `<owner>-agent[bot]` and can be
  overridden with `--agent`. Other authors and unresolved identities are excluded.
- **Deduplication:** each commit SHA is counted once across all eligible repositories.
- **Time:** year-to-date uses the author timestamp converted to UTC. Future-dated
  commits are excluded from both periods. The displayed timestamp is the start of
  the scan, not a claim of an atomic cross-repository snapshot.
- **Lines:** Git's text additions and deletions with rename detection. These include
  source, tests, documentation, configuration, lockfiles, and generated text.
  Binary files do not contribute lines; binary-only and empty commits still count
  as commits. `Lines changed = additions + deletions`, not net growth or current LOC.

The updater reads unfiltered commit history because the API's author filter can
omit bot-authored commits. Pagination is pinned to the first commit SHA. Public
bare clones supply full diffs without per-commit API requests or checking out or
executing repository code. Temporary clones are deleted when each scan finishes.
No private data, credentials, or cloned source is published.

At most four repositories are scanned concurrently. Transient HTTP failures,
timeouts, connection errors, and interrupted responses are retried up to three
attempts with short backoff; authentication and not-found errors fail immediately.

All repositories must finish successfully before the statistics section changes.
An API, clone, or diff failure leaves the previous published statistics intact and
fails the workflow instead of displaying a partial total. A later scheduled or
manual run retries the complete scan. The existing project-table sync and its
publishing identity remain unchanged; that automation's commits are not counted
as human or agent contributions.

## Local verification

```sh
python3 -m unittest discover -s tests -v
python3 scripts/profile_stats.py --owner <profile-owner>
```

Set `GH_TOKEN` to an already authorized read token for API rate limits. Never put
credentials in command arguments or committed files. The script updates only the
README block between the `human-agent-stats` markers, after complete collection.
