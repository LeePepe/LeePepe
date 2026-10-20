#!/usr/bin/env python3
"""Build one public activity snapshot for the profile, daily table and Pages."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote

from profile_stats import END, START, GitHub, calendar_level, commit_actor, git, sum_numstat


SCHEMA_VERSION = 1
OWNER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}\Z")
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("GitHub timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def title(value):
    # Preserve readable external text, never HTML or multiline Markdown.
    subject = str(value or "Untitled change").splitlines()[0]
    return " ".join(subject.split())[:240] or "Untitled change"


def public_repositories(client, owner):
    if not OWNER_PATTERN.fullmatch(owner):
        raise ValueError("Invalid GitHub owner")
    result = {}
    for repo in client.pages(f"users/{owner}/repos", type="owner"):
        if repo["private"] or repo["fork"] or repo["owner"]["login"].casefold() != owner.casefold():
            continue
        name = repo["name"]
        if not REPO_PATTERN.fullmatch(name):
            raise ValueError("Invalid public repository name")
        canonical = f"{owner}/{name}"
        if repo["full_name"].casefold() != canonical.casefold():
            raise ValueError("Repository owner/name mismatch")
        if name.casefold() in result:
            raise ValueError("Duplicate repository across pagination; retry complete snapshot")
        result[name.casefold()] = {**repo, "full_name": canonical}
    return sorted(result.values(), key=lambda repo: repo["name"].casefold())


def collect_repository(client, repo, identities, logins, now):
    """Read a pinned default branch and every PR page; nothing is published here."""
    print(f"Scanning {repo['full_name']}", flush=True)
    commits = client.commits(repo)
    seen_commits = set()
    selected = []
    for commit in commits:
        if not SHA_PATTERN.fullmatch(commit["sha"]) or commit["sha"] in seen_commits:
            raise ValueError("Invalid or repeated commit SHA")
        seen_commits.add(commit["sha"])
        actor = commit_actor(commit, identities)
        if actor not in ("human", "agent"):
            continue
        authored = utc(commit["commit"]["author"]["date"])
        if authored <= now:
            if not SHA_PATTERN.fullmatch(commit["sha"]):
                raise ValueError("Invalid commit SHA")
            selected.append((commit, actor, authored))
    records = []
    snapshot = commits[0]["sha"] if commits else None
    if selected:
        with tempfile.TemporaryDirectory(prefix="public-profile-history-") as directory:
            repository = Path(directory) / "history.git"
            git("clone", "--bare", "--single-branch", "--no-tags", f"--branch={repo['default_branch']}",
                f"https://github.com/{repo['full_name']}.git", str(repository), cwd=directory)
            try:
                git("cat-file", "-e", f"{snapshot}^{{commit}}", cwd=repository)
            except subprocess.CalledProcessError:
                git("fetch", "origin", snapshot, cwd=repository)
            for commit, actor, authored in selected:
                output = git("show", "--format=", "--numstat", "-z", "--find-renames", "--root",
                             "--no-ext-diff", "--no-textconv", commit["sha"], cwd=repository)
                additions, deletions = sum_numstat(output)
                records.append({"id": commit["sha"], "type": "commit", "date": authored.date().isoformat(),
                                "authored_at": timestamp(authored), "actor": actor,
                                "author_login": logins[actor], "repository": repo["name"],
                                "repositories": [repo["name"]], "title": title(commit["commit"].get("message")),
                                "url": f"https://github.com/{repo['full_name']}/commit/{commit['sha']}",
                                "additions": additions, "deletions": deletions})
    seen_prs = set()
    # No early date exit: all creation-date cohorts and all pages are collected.
    for pr in client.pages(f"repos/{repo['full_name']}/pulls", state="all", sort="created", direction="asc"):
        number = pr["number"]
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise ValueError("Invalid PR number")
        if number in seen_prs:
            raise ValueError("Duplicate PR across pagination; retry complete snapshot")
        seen_prs.add(number)
        login = (pr.get("user") or {}).get("login", "").casefold()
        actor = identities.get(login)
        if actor not in ("human", "agent"):
            continue
        created = utc(pr["created_at"])
        if created > now:
            continue
        state = "merged" if pr.get("merged_at") else pr["state"]
        if state not in ("merged", "open", "closed"):
            raise ValueError("Unknown PR state")
        records.append({"id": f"{repo['full_name']}#{number}", "number": number, "type": "pr",
                        "date": created.date().isoformat(), "created_at": timestamp(created),
                        "actor": actor, "author_login": logins[actor],
                        "repository": repo["name"], "repositories": [repo["name"]],
                        "title": title(pr.get("title")), "state": state,
                        "url": f"https://github.com/{repo['full_name']}/pull/{number}"})
    metadata = {"name": repo["name"], "url": f"https://github.com/{repo['full_name']}", "visibility": "public",
                "fork": False, "archived": bool(repo.get("archived")), "default_branch": repo["default_branch"],
                "snapshot_sha": snapshot}
    print(f"Finished {repo['full_name']}: {len(selected)} commits, {len(seen_prs)} PRs", flush=True)
    return metadata, records


def collect(client, owner, agent, now):
    now = now.astimezone(timezone.utc)
    if owner.casefold() == agent.casefold():
        raise ValueError("Human and agent identities must differ")
    identities = {owner.casefold(): "human", agent.casefold(): "agent"}
    logins = {"human": owner, "agent": agent}
    for login in (owner, agent):
        if client.get(f"users/{quote(login, safe='')}")["login"].casefold() != login.casefold():
            raise ValueError(f"Identity mismatch for {login}")
    repositories = public_repositories(client, owner)
    metadata, unique = [], {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(lambda repo: collect_repository(client, repo, identities, logins, now), repositories)
        for repo, records in results:
            metadata.append(repo)
            for record in records:
                key = (record["type"], record["id"])
                if key not in unique:
                    unique[key] = record
                elif record["type"] == "commit":
                    original = unique[key]
                    for field in ("actor", "date", "authored_at", "additions", "deletions"):
                        if original[field] != record[field]:
                            raise ValueError("Inconsistent duplicate commit metadata")
                    original["repositories"] = sorted(set(original["repositories"] + record["repositories"]), key=str.casefold)
                else:
                    raise ValueError("Duplicate PR identity")
    data = {"schema_version": SCHEMA_VERSION, "data_kind": "public_snapshot", "owner": owner,
            "snapshot": {"date": now.date().isoformat(), "generated_at": timestamp(now),
                         "completed_at": timestamp(datetime.now(timezone.utc))},
            "actors": logins, "scope": {"visibility": "public", "non_fork": True,
                "include_archives": True, "commits": "Non-merge default-branch commits; globally unique SHA; UTC author date",
                "pull_requests": "UTC creation-date cohorts; current merged/open/closed-unmerged state",
                "other_authors": "Excluded", "future_dates": "Excluded"},
            "repositories": metadata,
            "records": sorted(unique.values(), key=lambda r: (r["date"], r["type"], r["id"]))}
    data["snapshot"]["id"] = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return data


def recent(data, days, metric="commit", actor=None):
    end = utc(data["snapshot"]["generated_at"]).date()
    start = (end - timedelta(days=days - 1)).isoformat()
    return [r for r in data["records"] if r["type"] == metric and start <= r["date"] <= str(end)
            and (actor is None or r["actor"] == actor)]


def totals_table(data):
    year = data["snapshot"]["date"][:4]
    result = []
    for start, label in ((year + "-01-01", f"{year} year to date"), ("0000-01-01", "All time")):
        result.extend([f"**{label}**", "", "| Author | Commits | Lines added | Lines deleted | Lines changed |",
                       "|:--|--:|--:|--:|--:|"])
        for actor, actor_label in (("human", "Human"), ("agent", "Agent"), (None, "Combined")):
            records = [r for r in data["records"] if r["type"] == "commit" and r["date"] >= start
                       and (actor is None or r["actor"] == actor)]
            added, deleted = sum(r["additions"] for r in records), sum(r["deletions"] for r in records)
            result.append(f"| {actor_label} | {len(records):,} | +{added:,} | −{deleted:,} | {added + deleted:,} |")
        result.append("")
    return "\n".join(result)


def render_readme(data):
    n7, n30 = len(recent(data, 7)), len(recent(data, 30))
    p7, p30 = len(recent(data, 7, "pr")), len(recent(data, 30, "pr"))
    human, agent = len(recent(data, 365, actor="human")), len(recent(data, 365, actor="agent"))
    owner = quote(data["owner"], safe="")
    page = f"https://{data['owner'].lower()}.github.io/{owner}/"
    return f'''{START}
## Activity notebook

Human and agent activity, side by side. **[Explore days, repositories & pull requests ↗]({page})**

<a href="{page}">
<picture>
  <source media="(max-width: 600px)" srcset="assets/profile-activity-mobile.svg">
  <img src="assets/profile-activity.svg" width="1000" alt="Public activity: {n7} commits and {p7} PRs opened in 7 days; {n30} commits and {p30} PRs opened in 30 days. Open the activity notebook for daily details.">
</picture>
</a>

**Last 7 days:** {n7:,} commits, {p7:,} PRs opened · **Last 30 days:** {n30:,} commits, {p30:,} PRs opened<br>
**365 days:** {human:,} human + {agent:,} agent commits<br>
<sub>Updated {data['snapshot']['generated_at'].replace('T', ' ').replace('Z', ' UTC')} · {len(data['repositories'])} public repositories · Snapshot {data['snapshot']['id'][:12]} · Refreshed hourly; scan and image-cache delays are possible.</sub>

<details>
<summary>Counting notes & year-to-date / all-time totals</summary>

{totals_table(data)}
Owner-owned public, non-fork repositories, including archives. Human = {escape(data['actors']['human'])}; Agent = {escape(data['actors']['agent'])}. Other authors and automation are excluded. Unique non-merge default-branch commits use UTC author dates; PRs use UTC creation dates. Merged/open/closed-unmerged figures describe the PR creation-date cohort's current states, not period merge events. Future dates are excluded.

Lines measure text churn (including docs/config), not current LOC; binaries are excluded. [Daily totals](assets/activity-daily.md) · [Counting rules](docs/profile-statistics.md) · [Public dataset](site/data.json)

</details>
{END}'''


def replace_section(content, section):
    if content.count(START) != 1 or content.count(END) != 1 or content.index(START) >= content.index(END):
        raise ValueError("README must contain one ordered statistics marker pair")
    return content[:content.index(START)] + section + content[content.index(END) + len(END):]


def render_daily(data):
    days = {}
    for record in recent(data, 365) + recent(data, 365, "pr"):
        counter = days.setdefault(record["date"], Counter())
        counter[record["type"] + "_" + record["actor"]] += 1
        if record["type"] == "pr":
            counter[record["state"]] += 1
    lines = ["# Public daily activity", "", f"Snapshot: {data['snapshot']['generated_at']} · Generation {data['snapshot']['id']} · [Interactive notebook](https://{data['owner'].lower()}.github.io/{data['owner']}/)", "",
             "UTC commit author dates / PR creation dates. PR states are current states of each creation-date cohort, not merge events on that day. Commits are globally deduplicated; a repository filter can include shared SHAs, but the all-repository total counts them once.", "",
             "| UTC date | Human commits | Agent commits | Human PRs opened | Agent PRs opened | Merged | Open | Closed unmerged |",
             "|:--|--:|--:|--:|--:|--:|--:|--:|"]
    end = utc(data["snapshot"]["generated_at"]).date()
    for i in range(365):
        day = (end - timedelta(days=i)).isoformat()
        c = days.get(day, Counter())
        lines.append(f"| {day} | {c['commit_human']} | {c['commit_agent']} | {c['pr_human']} | {c['pr_agent']} | {c['merged']} | {c['open']} | {c['closed']} |")
    return "\n".join(lines) + "\n"


def render_svg(data, mobile=False):
    """First-party snapshot image; true per-day interaction lives on Pages."""
    width, height = (600, 580) if mobile else (1000, 380)
    end = utc(data["snapshot"]["generated_at"]).date()
    start = end - timedelta(days=364)
    n7, n30, p7, p30 = len(recent(data, 7)), len(recent(data, 30)), len(recent(data, 7, "pr")), len(recent(data, 30, "pr"))
    human, agent = len(recent(data, 365, actor="human")), len(recent(data, 365, actor="agent"))
    daily = Counter(r["date"] for r in recent(data, 365))
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           f'<title id="title">Public activity notebook</title><desc id="desc">{human + agent:,} unique non-merge default-branch commits in 365 days. {n7} commits and {p7} PRs opened in 7 days. {n30} commits and {p30} PRs opened in 30 days. Human {human}; agent {agent}. Public repositories only; UTC dates.</desc>',
           '<style>svg{--bg:#f5f5f0;--text:#242822;--muted:#62685e;--line:#dcded6;--zero:#e9ece4;--one:#c8d9c0;--two:#9dbb91;--three:#6b9666;--four:#3b6d42}@media(prefers-color-scheme:dark){svg{--bg:#171b18;--text:#edf1e9;--muted:#abb4a5;--line:#3d463b;--zero:#30382f;--one:#3d543a;--two:#587850;--three:#7b9c70;--four:#b2cf9f}}text{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:var(--text)}.meta{fill:var(--muted)}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:1px}.l0{fill:var(--zero)}.l1{fill:var(--one)}.l2{fill:var(--two)}.l3{fill:var(--three)}.l4{fill:var(--four)}</style>',
           f'<rect x=".5" y=".5" width="{width-1}" height="{height-1}" rx="12" fill="var(--bg)" stroke="var(--line)"/>',
           '<text x="32" y="38" class="meta mono" font-size="11">THE WORK, OVER TIME</text>',
           f'<text x="{width-32}" y="38" class="meta mono" text-anchor="end" font-size="10">PUBLIC SNAPSHOT</text>']
    for index, (value, label) in enumerate(((n7, "commits · last 7 days"), (n30, "commits · last 30 days"), (p30, "PRs opened · last 30 days"))):
        x = (32, width // 2 if mobile else 400, 32 if mobile else 700)[index]
        y = 90 + (82 if mobile and index == 2 else 0)
        svg.extend([f'<text x="{x}" y="{y}" font-size="38" font-weight="600">{value:,}</text>',
                    f'<text x="{x}" y="{y+24}" class="meta" font-size="13">{label}</text>'])
    svg.append(f'<text x="32" y="132" class="meta" font-size="11">{p7} PRs opened · last 7 days</text>')
    grid_y = 240 if mobile else 185
    svg.extend([f'<path d="M32 {grid_y-40} H{width-32}" stroke="var(--line)"/>',
                f'<text x="32" y="{grid_y-18}" font-size="13" font-weight="600">{human+agent:,} commits · 365 days</text>',
                f'<text x="{width-32}" y="{grid_y-18}" class="meta" font-size="11" text-anchor="end">{human:,} human / {agent:,} agent</text>'])
    leading = (start.weekday() + 1) % 7
    cell, gap, columns = (14, 5, 27) if mobile else (13, 4, 54)
    for i in range(365):
        day = start + timedelta(days=i)
        week, weekday = divmod(leading+i, 7)
        band, col = divmod(week, columns)
        x, y = 32 + col * (cell+gap), grid_y + band*150 + weekday*(cell+gap)
        count = daily[str(day)]
        svg.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" class="l{calendar_level(count)}" data-date="{day}" data-count="{count}"/>')
        if day.day == 1:
            svg.append(f'<text x="{x}" y="{grid_y+band*150-5}" class="meta" font-size="9">{day:%b}</text>')
    svg.append(f'<text x="32" y="{height-32}" class="meta" font-size="11">{end:%d %b %Y} · UTC · 0 / 1–3 / 4–9 / 10–19 / 20+ commits</text>')
    svg.append(f'<text x="{width-32}" y="{height-12}" class="meta" font-size="11" text-anchor="end">{data["snapshot"]["id"][:12]} · Explore daily details ↗</text></svg>')
    return "".join(svg)


def outputs(data, readme):
    """Render the whole bundle before any published file changes."""
    return {"README.md": replace_section(readme, render_readme(data)),
            "assets/profile-activity.svg": render_svg(data),
            "assets/profile-activity-mobile.svg": render_svg(data, True),
            "assets/activity-daily.md": render_daily(data),
            "site/data.json": json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"}


def publish(root, bundle):
    """Atomic individual files, rollback on write failure; Git publishes one bundle."""
    root = Path(root)
    (root / "site").mkdir(exist_ok=True)
    original = {}
    with tempfile.TemporaryDirectory(prefix=".profile-build-", dir=root / "site") as directory:
        stage = Path(directory)
        for index, (relative, content) in enumerate(bundle.items()):
            destination = root / relative
            original[relative] = destination.read_bytes() if destination.exists() else None
            (stage / f"new-{index}").write_text(content, encoding="utf-8")
            if original[relative] is not None:
                (stage / f"old-{index}").write_bytes(original[relative])
        written = []
        try:
            for index, relative in enumerate(bundle):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / f"new-{index}", destination)
                written.append((index, relative))
        except BaseException:
            for index, relative in reversed(written):
                destination = root / relative
                if original[relative] is None:
                    destination.unlink()
                else:
                    os.replace(stage / f"old-{index}", destination)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--agent")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if not args.owner:
        parser.error("--owner or GITHUB_REPOSITORY_OWNER is required")
    now = datetime.now(timezone.utc)
    data = collect(GitHub(os.environ.get("GH_TOKEN")), args.owner, args.agent or f"{args.owner.lower()}-agent[bot]", now)
    bundle = outputs(data, (args.root / "README.md").read_text())
    publish(args.root, bundle)
    print(json.dumps({"snapshot": data["snapshot"], "public_repositories": len(data["repositories"]),
                      "commits365": len(recent(data, 365)), "prs365": len(recent(data, 365, "pr"))}))


if __name__ == "__main__":
    main()
