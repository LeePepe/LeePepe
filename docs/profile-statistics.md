# Profile activity notebook

The profile README contains a generated snapshot, readable 7/30-day commit and
PR counts, year-to-date/all-time text-churn totals and a link to the interactive
[activity notebook](https://leepepe.github.io/LeePepe/). GitHub README images cannot
run JavaScript: per-day hover/focus, click/touch details and filters live on Pages.
The complete [365-day table](../assets/activity-daily.md) works without JavaScript.

## Counting rules

- Scope is owner-owned, publicly visible, non-fork repositories, including archives.
  Private repositories are never scanned. Browser code has no API token.
- Human means GitHub-resolved commit **author** LeePepe; Agent means
  leepepe-agent[bot]. Committer, pusher, display names and co-author trailers do
  not determine attribution. Other authors, unresolved identities and automation
  are excluded. PR authors use the same resolved GitHub logins.
- Commits are reachable from each repository's default branch at its pinned head.
  Merge commits are excluded. A squash merge contributes its resulting commit.
  Each SHA counts once globally; its membership in every eligible repository is
  retained, so repository filters may overlap and must not be summed together.
- Commit periods use the author timestamp converted to UTC. PR periods use UTC
  **creation dates**. Future timestamps are excluded from all totals. The 365-day
  window includes the snapshot date; weeks start Sunday, with blank alignment.
- PRs opened is the size of the creation-date cohort. Merged, open and closed
  unmerged are that cohort's **current states**, not merge events in that period.
  Every PR page is scanned with `state=all`, sorted by creation time.
- Lines are Git text additions/deletions with rename detection, including docs,
  tests, config, lockfiles and generated text. Binaries contribute no lines.
  Empty/binary-only commits still count. Churn is additions + deletions, not
  current LOC or net growth. YTD starts January 1 UTC; all time has no lower bound.

## Reading the page

Author, repository, commit/PR and 7/30/365-day controls jointly update all numbers,
calendar, trend chart and daily details. Last-7/30 cards are limited to the selected
range. The longer-view table always shows YTD/all-time commits for the selected
actor and repository. Green intensity thresholds are 0, 1–3, 4–9, 10–19 and 20+;
both authors use the same scale. Words distinguish Human and Agent as well as color.

Hover or focus a cell for a tooltip; click/tap or Enter/Space selects persistent
details with actual GitHub record links. Arrow keys browse dates; Home/End jump
to the ends. On mobile the year scrolls inside its panel; recent views use larger
touch cells. The daily list scrolls inside its panel when long. System/manual
light/dark themes and reduced motion are supported. Empty data is shown as zero;
a failed load offers the last successful daily table.

## One generation and hourly publication

`scripts/profile_activity.py` is the production entry point. It reuses HTTP,
public bare-clone and numstat helpers from the retained legacy
`scripts/profile_stats.py`; the legacy command is no longer run by automation.
Python's standard library and Git are the only collector dependencies. No cloned
code is checked out or executed. At most four public repositories scan concurrently.

Repository and PR lists are fully paginated. Commit pagination is pinned to the
first SHA, avoiding branch movement between pages. All repositories, PRs and diffs
must finish successfully before rendering; all outputs render before any files
are replaced. Staged writes roll back on replacement failure. API/auth/clone/diff,
malformed or duplicate pagination and rendering failures fail the workflow and
leave the last published generation intact. No partial totals are published.

The canonical `site/data.json` contains only public metadata and records. It drives
the README block, desktop/mobile SVGs, full daily table and interactive page.
Generated files carry one generation ID and scan-start timestamp. This is a set
of per-repository pinned scans, not an atomic cross-repository GitHub snapshot;
completion time and each repository head are recorded in the data.

`Update README` runs at minute 17 each hour UTC, on manual dispatch, or main source
changes. The old whole-project-table sync has been removed; curated copy outside
the statistics markers stays unchanged. One bot commit publishes the complete
bundle. A failed/non-fast-forward push stops deployment. Workflow-level concurrency
serializes collection through deployment, preventing older runs from overtaking.
Generated paths are ignored for push triggers, preventing update loops.

The updater explicitly calls `deploy-pages.yml` with the exact generated commit.
This is necessary because GITHUB_TOKEN bot pushes with `[skip ci]` do not trigger
ordinary push deploys. The reusable deploy validates generation agreement, uploads
only `site/` and publishes the same-repository project Pages site at `/LeePepe/`.
No user-site repository is modified. Schedules, scan duration, GitHub Pages and
image caches can delay visible updates; the page shows its actual snapshot time
and labels snapshots older than three hours as delayed.

## Local verification

```sh
python3 -m unittest discover -s tests -v
python3 scripts/profile_activity.py --owner LeePepe
python3 -m http.server 8787 --directory site
```

Supply an already authorized read credential only through `GH_TOKEN` in the
environment. Never put tokens in arguments, browser code, logs or committed files.
The script uses no earlier diagnostic report. A real run replaces only the README
statistics block, the two activity SVGs, daily table and public JSON after success.
