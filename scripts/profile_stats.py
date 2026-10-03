#!/usr/bin/env python3
"""Summarize public default-branch commits by their GitHub author identity."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


START = "<!-- human-agent-stats:start -->"
END = "<!-- human-agent-stats:end -->"
# Commit metadata can include long messages; smaller pages tolerate network proxies.
PAGE_SIZE = 25


class GitHub:
    def __init__(self, token):
        self.token = token

    def get(self, path, **params):
        url = f"https://api.github.com/{path}?{urlencode(params)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "profile-contribution-stats",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers=headers), timeout=60) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
                error.close()
                time.sleep(2**attempt)
            except (URLError, IncompleteRead, ConnectionError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)

    def pages(self, path, **params):
        page = 1
        while True:
            items = self.get(path, per_page=PAGE_SIZE, page=page, **params)
            yield from items
            if len(items) < PAGE_SIZE:
                return
            page += 1

    def commits(self, repo):
        """Pin pagination to one branch snapshot; bot author filters are unreliable."""
        path = f"repos/{repo['full_name']}/commits"
        try:
            first = self.get(
                path, sha=repo["default_branch"], per_page=PAGE_SIZE, page=1
            )
        except HTTPError as error:
            if error.code == 409:  # An empty repository has no commit history.
                error.close()
                return []
            raise
        if not first:
            return []
        result = list(first)
        page = 2
        while len(first) == PAGE_SIZE:
            first = self.get(path, sha=result[0]["sha"], per_page=PAGE_SIZE, page=page)
            result.extend(first)
            page += 1
        return result


@dataclass
class Totals:
    commits: int = 0
    additions: int = 0
    deletions: int = 0

    def add(self, additions, deletions):
        self.commits += 1
        self.additions += additions
        self.deletions += deletions

    def __add__(self, other):
        return Totals(
            self.commits + other.commits,
            self.additions + other.additions,
            self.deletions + other.deletions,
        )


def sum_numstat(output):
    """Parse NUL-separated numstat, including renames and unusual filenames."""
    records = iter(output.split(b"\0"))
    additions = deletions = 0
    for record in records:
        if not record:
            continue
        added, deleted, filename = record.split(b"\t", 2)
        if not filename:  # A rename has two additional NUL-separated paths.
            next(records)
            next(records)
        if added != b"-" and deleted != b"-":
            additions += int(added)
            deletions += int(deleted)
    return additions, deletions


def git(*args, cwd=None):
    # Public clones must not borrow local credentials or execute repository code.
    environment = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "0",
    }
    for variable in (
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
    ):
        environment.pop(variable, None)
    return subprocess.run(
        [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            f"core.hooksPath={os.devnull}",
            *args,
        ],
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        timeout=600,
    ).stdout


def commit_actor(commit, identities):
    if len(commit["parents"]) > 1:
        return None
    login = (commit.get("author") or {}).get("login", "").casefold()
    return identities.get(login)


def collect_repository(client, repo, identities, now):
    print(f"Scanning {repo['full_name']}", flush=True)
    commits = client.commits(repo)
    selected = []
    for commit in commits:
        actor = commit_actor(commit, identities)
        authored = datetime.fromisoformat(
            commit["commit"]["author"]["date"].replace("Z", "+00:00")
        )
        if actor and authored <= now:
            selected.append((commit, actor, authored))
    result = []
    if selected:
        with tempfile.TemporaryDirectory(prefix="profile-stats-") as directory:
            repository = Path(directory) / "history.git"
            git(
                "clone",
                "--bare",
                "--single-branch",
                "--no-tags",
                f"--branch={repo['default_branch']}",
                f"https://github.com/{repo['full_name']}.git",
                str(repository),
                cwd=directory,
            )
            # Retain the API snapshot even if the default branch moved during clone.
            snapshot = commits[0]["sha"]
            try:
                git("cat-file", "-e", f"{snapshot}^{{commit}}", cwd=repository)
            except subprocess.CalledProcessError:
                git("fetch", "origin", snapshot, cwd=repository)
            for commit, actor, authored in selected:
                output = git(
                    "show",
                    "--format=",
                    "--numstat",
                    "-z",
                    "--find-renames",
                    "--root",
                    "--no-ext-diff",
                    "--no-textconv",
                    commit["sha"],
                    cwd=repository,
                )
                added, deleted = sum_numstat(output)
                result.append((commit["sha"], actor, authored, added, deleted))
    print(f"Finished {repo['full_name']}: {len(result)} attributed commits", flush=True)
    return result


def collect(client, owner, agent, now):
    identities = {owner.casefold(): "Human", agent.casefold(): "Agent"}
    if len(identities) != 2:
        raise ValueError("Human and agent identities must be different")
    repos = sorted(
        (
            repo
            for repo in client.pages(f"users/{owner}/repos", type="owner")
            if not repo["private"]
            and not repo["fork"]
            and repo["owner"]["login"].casefold() == owner.casefold()
        ),
        key=lambda repo: repo["full_name"].casefold(),
    )
    totals = {
        period: {actor: Totals() for actor in identities.values()}
        for period in ("year", "all")
    }
    daily = {actor: {} for actor in identities.values()}
    seen = set()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(
            lambda repo: collect_repository(client, repo, identities, now), repos
        )
        for repository_result in results:
            for sha, actor, authored, added, deleted in repository_result:
                if sha not in seen:
                    seen.add(sha)
                    totals["all"][actor].add(added, deleted)
                    day = authored.astimezone(timezone.utc).date()
                    daily[actor].setdefault(day, Totals()).add(added, deleted)
                    if day.year == now.year:
                        totals["year"][actor].add(added, deleted)
    return totals, len(repos), daily


def calendar_days(today: date):
    """Exactly 365 days, with Sunday-aligned columns and blank padding."""
    start = today - timedelta(days=364)
    first_sunday = start - timedelta(days=(start.weekday() + 1) % 7)
    weeks = ((today - first_sunday).days // 7) + 1
    return start, first_sunday, weeks


def calendar_level(count):
    # Fixed thresholds make the two authors' colors comparable.
    return (
        0
        if count == 0
        else 1
        if count <= 3
        else 2
        if count <= 9
        else 3
        if count <= 19
        else 4
    )


def render_calendar(login, actor, days, today, *, compact=False):
    start, first_sunday, weeks = calendar_days(today)
    recent = {day: total for day, total in days.items() if start <= day <= today}
    total = sum(recent.values(), Totals())
    width, step, left = (450, 13, 50) if compact else (900, 15, 68)
    columns = 27 if compact else weeks
    bands = (weeks + columns - 1) // columns
    legend_y = 134 + (bands - 1) * 144 + 7 * step + 20
    height = legend_y + 32 + 84
    small, caption = (12.5, 14) if compact else (10, 12)
    name = escape(login)
    title = f"{name}: {total.commits:,} commits in the last 365 days"
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
        f'<title id="title">{title}</title>',
        f'<desc id="description">{start:%b %d, %Y} to {today:%b %d, %Y}, UTC. '
        f"{len(recent)} active days, {total.additions:,} lines added, {total.deletions:,} lines deleted. "
        "Public non-fork repositories, default branches, non-merge commits. "
        "Text changes include documentation and configuration. Darker green means more commits.</desc>",
        "<style>svg{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--border:#d1d9e0;"
        "--zero:#eff2f5;--one:#aceebb;--two:#4ac26b;--three:#2da44e;--four:#116329;"
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}'
        "@media(prefers-color-scheme:dark){svg{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;"
        "--border:#3d444d;--zero:#161b22;--one:#0e4429;--two:#006d32;--three:#26a641;--four:#39d353}}"
        "text{fill:var(--fg)}.muted{fill:var(--muted)}.level-0{fill:var(--zero)}"
        ".level-1{fill:var(--one)}.level-2{fill:var(--two)}.level-3{fill:var(--three)}"
        ".level-4{fill:var(--four)}.day{stroke:var(--border);stroke-width:.4}</style>",
        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="12" fill="var(--bg)" stroke="var(--border)"/>',
        f'<text x="24" y="38" font-size="22" font-weight="600">{name}</text>',
        f'<text x="{width - 24}" y="38" text-anchor="end" font-size="{caption}" class="muted">{escape(actor)}</text>',
        f'<text x="24" y="72" font-size="18" font-weight="600">{total.commits:,} commits in the last 365 days</text>',
        f'<text x="24" y="96" font-size="{caption}" class="muted">{start:%b %d, %Y} – {today:%b %d, %Y} · UTC</text>',
    ]
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    for band in range(bands):
        top = 134 + band * 144
        last_month_x = -100
        band_start = band * columns
        for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
            svg.append(
                f'<text x="{left - 10}" y="{top + row * step + 9}" text-anchor="end" font-size="{small}" class="muted">{label}</text>'
            )
        for week in range(band_start, min(weeks, band_start + columns)):
            x = left + (week - band_start) * step
            week_start = first_sunday + timedelta(weeks=week)
            visible = [
                week_start + timedelta(days=row)
                for row in range(7)
                if start <= week_start + timedelta(days=row) <= today
            ]
            month_day = next((day for day in visible if day.day == 1), None)
            if week == band_start and visible:
                month_day = visible[0]
            if month_day and x - last_month_x >= 30:
                svg.append(
                    f'<text x="{x}" y="{top - 12}" font-size="{small}" class="muted">{months[month_day.month - 1]}</text>'
                )
                last_month_x = x
            for row in range(7):
                day = week_start + timedelta(days=row)
                if not start <= day <= today:
                    continue
                count = days.get(day, Totals()).commits
                size = step - 3
                svg.append(
                    f'<rect class="day level-{calendar_level(count)}" x="{x}" y="{top + row * step}" '
                    f'width="{size}" height="{size}" rx="2" data-date="{day}" data-count="{count}">'
                    f"<title>{count} {'commit' if count == 1 else 'commits'} on {day:%b %d, %Y}</title></rect>"
                )
    svg.append(
        f'<text x="{width - 185}" y="{legend_y}" font-size="{small}" class="muted">Less</text>'
    )
    for level in range(5):
        svg.append(
            f'<rect class="day level-{level}" x="{width - 154 + level * 16}" y="{legend_y - 10}" width="11" height="11" rx="2"/>'
        )
    svg.append(
        f'<text x="{width - 65}" y="{legend_y}" font-size="{small}" class="muted">More</text>'
    )
    divider_y = height - 84
    svg.append(f'<path d="M24 {divider_y}H{width - 24}" stroke="var(--border)"/>')
    for index, (value, label) in enumerate(
        (
            (f"{len(recent):,}", "Active days"),
            (f"+{total.additions:,}", "Lines added"),
            (f"−{total.deletions:,}", "Lines deleted"),
        )
    ):
        x = 24 + index * ((width - 48) // 3)
        svg.append(
            f'<text x="{x}" y="{height - 48}" font-size="20" font-weight="600">{value}</text>'
        )
        svg.append(
            f'<text x="{x}" y="{height - 25}" font-size="{caption}" class="muted">{label}</text>'
        )
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def render(totals, repo_count, now):
    lines = [
        START,
        "### human + agent",
        "",
        "Public, non-fork repositories · default branches · non-merge commits",
    ]
    for actor in ("human", "agent"):
        lines.extend(
            [
                "",
                "<picture>",
                f'  <source media="(max-width: 600px)" srcset="assets/{actor}-calendar-mobile.svg">',
                f'  <img src="assets/{actor}-calendar.svg" alt="{actor.title()} commit calendar for the last 365 days, with active days and text additions/deletions" width="900">',
                "</picture>",
            ]
        )
    lines.extend(
        ["", "<details>", "<summary>Year-to-date and all-time totals</summary>"]
    )
    for period, title in (("year", f"{now.year} year to date"), ("all", "All time")):
        lines.extend(
            [
                "",
                f"**{title}**",
                "",
                "| Author | Commits | Lines added | Lines deleted | Lines changed |",
                "|:--|--:|--:|--:|--:|",
            ]
        )
        rows = {
            **totals[period],
            "Combined": totals[period]["Human"] + totals[period]["Agent"],
        }
        for actor, count in rows.items():
            lines.append(
                f"| {actor} | {count.commits:,} | +{count.additions:,} | −{count.deletions:,} "
                f"| {count.additions + count.deletions:,} |"
            )
    lines.extend(
        [
            "",
            "</details>",
            "",
            f"<sub>Updated {now:%Y-%m-%d %H:%M} UTC · {repo_count} repositories · Scheduled hourly (refresh/cache delays possible). "
            "GitHub author identity; unique commit SHAs; UTC author dates. "
            "Lines measure text churn (including docs/config), not current LOC; binaries excluded. "
            "Other automation accounts are not counted.</sub>",
            END,
        ]
    )
    return "\n".join(lines)


def update_readme(path, section):
    content = path.read_text()
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("README must contain exactly one statistics marker pair")
    start = content.index(START)
    end = content.index(END) + len(END)
    if end <= start:
        raise ValueError("Statistics markers are out of order")
    # All collection must succeed before publishing anything to the README.
    path.write_text(content[:start] + section + content[end:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--agent", help="Agent login; defaults to <owner>-agent[bot]")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    if not args.owner:
        parser.error("--owner or GITHUB_REPOSITORY_OWNER is required")
    agent = args.agent or f"{args.owner.lower()}-agent[bot]"
    client = GitHub(os.environ.get("GH_TOKEN"))
    # Fail closed on a typo or an unavailable identity instead of publishing zeroes.
    for login in (args.owner, agent):
        if client.get(f"users/{login}")["login"].casefold() != login.casefold():
            raise ValueError(f"Identity mismatch for {login}")
    now = datetime.now(timezone.utc)
    totals, repo_count, daily = collect(client, args.owner, agent, now)
    section = render(totals, repo_count, now)
    calendars = {}
    for actor, login in (("Human", args.owner), ("Agent", agent)):
        for compact in (False, True):
            filename = f"{actor.lower()}-calendar{'-mobile' if compact else ''}.svg"
            calendars[filename] = render_calendar(
                login, actor, daily[actor], now.date(), compact=compact
            )
    # Render everything successfully before changing any published artifacts.
    update_readme(args.readme, section)
    assets = args.readme.parent / "assets"
    assets.mkdir(exist_ok=True)
    for filename, content in calendars.items():
        (assets / filename).write_text(content, encoding="utf-8")
    print(section)


if __name__ == "__main__":
    main()
