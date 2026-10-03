#!/usr/bin/env python3
"""Summarize public default-branch commits by their GitHub author identity."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
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
                    if authored.astimezone(timezone.utc).year == now.year:
                        totals["year"][actor].add(added, deleted)
    return totals, len(repos)


def render(totals, repo_count, now):
    lines = [
        START,
        "### human + agent",
        "",
        "Public, non-fork repositories · default branches · non-merge commits",
    ]
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
            f"<sub>Updated {now:%Y-%m-%d %H:%M} UTC · {repo_count} repositories. "
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
    totals, repo_count = collect(client, args.owner, agent, now)
    section = render(totals, repo_count, now)
    update_readme(args.readme, section)
    print(section)


if __name__ == "__main__":
    main()
