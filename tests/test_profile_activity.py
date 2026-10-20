from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_activity as activity


NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def repository(name="one", **changes):
    return {"name": name, "full_name": f"person/{name}", "owner": {"login": "person"},
            "private": False, "fork": False, "default_branch": "main", "archived": False, **changes}


def commit(number=1, author="person", date="2026-10-20T00:00:00Z", parents=1):
    return dict(sha=f"{number:040x}", author={"login": author} if author else None,
                parents=[{}] * parents,
                commit={"author": {"date": date}, "message": "<script> & a change\nDetails"})


def pr(number=1, author="person", date="2026-10-20T00:00:00Z", state="open", merged=None):
    return dict(number=number, user={"login": author}, created_at=date, state=state,
                merged_at=merged, title="<img onerror='attack'> & a PR")


class Client(activity.GitHub):
    """Exercise real pagination with a deterministic public API boundary."""
    def __init__(self, repos=None, commits=None, prs=None, fail=None):
        super().__init__(None)
        self.repos = [repository()] if repos is None else repos
        self.history = commits or {}
        self.prs = prs or {}
        self.fail = fail
        self.calls = []

    def get(self, path, **params):
        self.calls.append((path, params))
        if self.fail and self.fail(path, params):
            raise TimeoutError("incomplete collection")
        if path in ("users/person", "users/helper%5Bbot%5D"):
            return {"login": "person" if path == "users/person" else "helper[bot]"}
        if path == "users/person/repos":
            items = self.repos
        elif path.endswith("/commits"):
            items = self.history.get(path.split("/")[2], [])
        elif path.endswith("/pulls"):
            items = self.prs.get(path.split("/")[2], [])
        else:
            raise AssertionError(path)
        start = (params["page"] - 1) * params["per_page"]
        return deepcopy(items[start:start + params["per_page"]])


def scan(client):
    with patch.object(activity, "git", return_value=b"3\t2\tfile.py\0"):
        return activity.collect(client, "person", "helper[bot]", NOW)


class ActivityTests(unittest.TestCase):
    def test_scope_excludes_private_forks_and_foreign_but_keeps_archives(self):
        repos = [repository(), repository("archive", archived=True)]
        for name, change in (("private", {"private": True}), ("fork", {"fork": True}),
                             ("foreign", {"owner": {"login": "someone"}})):
            item = repository(name)
            item.update(change)
            repos.append(item)
        client = Client(repos=repos)
        data = scan(client)
        self.assertEqual([r["name"] for r in data["repositories"]], ["archive", "one"])
        paths = [p for p, _ in client.calls]
        self.assertFalse(any(name in p for p in paths for name in ("private/", "fork/", "foreign/")))
        self.assertTrue(data["repositories"][0]["archived"])

    def test_full_repo_and_pr_pagination_and_pinned_commit_history(self):
        repos = [repository(f"r{i}") for i in range(26)]
        client = Client(repos, {"r0": [commit(i + 1) for i in range(51)]},
                        {"r0": [pr(i + 1) for i in range(51)]})
        data = scan(client)
        self.assertEqual(len(data["repositories"]), 26)
        self.assertEqual(len(data["records"]), 102)
        self.assertTrue(any(p == "users/person/repos" and q["page"] == 2 for p, q in client.calls))
        later = [q for p, q in client.calls if p.endswith("r0/commits") and q["page"] > 1]
        self.assertEqual([q["page"] for q in later], [2, 3])
        self.assertTrue(all(q["sha"] == commit()["sha"] for q in later))
        self.assertTrue(all(q["state"] == "all" and q["sort"] == "created" for p, q in client.calls if p.endswith("/pulls")))

    def test_author_identity_not_committer_merges_unknown_or_bot_names(self):
        commits = [commit(1), commit(2, "HELPER[bot]"), commit(3, "other"),
                   commit(4, None), commit(5, parents=2), commit(6, "logins")]
        commits[2]["committer"] = {"login": "person"}
        data = scan(Client(commits={"one": commits}))
        self.assertEqual([r["actor"] for r in data["records"]], ["human", "agent"])

    def test_utc_boundaries_future_and_window_dates(self):
        commits = [commit(1, date="2026-10-20T00:30:00+02:00"),
                   commit(2, date="2026-10-20T12:00:01Z"),
                   commit(3, date="2025-12-31T23:30:00-02:00"),
                   commit(4, date="2026-10-14T00:00:00Z"),
                   commit(5, date="2026-10-13T23:59:59Z")]
        data = scan(Client(commits={"one": commits}))
        records = {r["id"]: r for r in data["records"]}
        self.assertEqual(records[commit(1)["sha"]]["date"], "2026-10-19")
        self.assertNotIn(commit(2)["sha"], records)
        self.assertEqual(records[commit(3)["sha"]]["date"], "2026-01-01")
        self.assertEqual(len(activity.recent(data, 7)), 2)

    def test_shared_sha_is_one_global_record_and_retains_all_repo_memberships(self):
        data = scan(Client([repository("one"), repository("two")],
                           {"one": [commit()], "two": [commit()]}))
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["repositories"], ["one", "two"])
        self.assertIn("| Combined | 1 | +3 | −2 | 5 |", activity.totals_table(data))

    def test_pr_cohorts_use_creation_date_and_current_state(self):
        prs = [pr(1, date="2026-10-19T23:30:00-02:00", state="closed", merged="2026-10-20T03:00:00Z"),
               pr(2, author="helper[bot]", state="closed"), pr(3),
               pr(4, date="2026-09-01T00:00:00Z", state="closed", merged="2026-10-20T00:00:00Z"),
               pr(5, date="2026-10-20T12:01:00Z"), pr(6, author="other")]
        data = scan(Client(prs={"one": prs}))
        self.assertEqual(len(activity.recent(data, 7, "pr")), 3)
        self.assertEqual(sorted(r["state"] for r in activity.recent(data, 7, "pr")), ["closed", "merged", "open"])
        self.assertIn("| 2026-10-20 | 0 | 0 | 2 | 1 | 1 | 1 | 1 |", activity.render_daily(data))

    def test_later_page_failure_is_not_a_partial_success(self):
        client = Client(prs={"one": [pr(i + 1) for i in range(26)]},
                        fail=lambda p, q: p.endswith("/pulls") and q.get("page") == 2)
        with self.assertRaises(TimeoutError):
            scan(client)

    def test_duplicate_pagination_fails_closed(self):
        for client in (Client(repos=[repository(), repository()]),
                       Client(commits={"one": [commit(), commit()]}),
                       Client(prs={"one": [pr(), pr()]})):
            with self.subTest(client=client), self.assertRaises(ValueError):
                scan(client)

    def test_identity_mismatch_fails_before_scan(self):
        client = Client()
        with patch.object(client, "get", return_value={"login": "wrong"}), self.assertRaises(ValueError):
            scan(client)

    def test_empty_data_renders_zero_full_daily_table_and_same_generation(self):
        data = scan(Client(repos=[]))
        bundle = activity.outputs(data, activity.START + activity.END)
        self.assertEqual(len(activity.render_daily(data).splitlines()), 373)
        self.assertIn("**Last 7 days:** 0 commits, 0 PRs", bundle["README.md"])
        for content in bundle.values():
            self.assertIn(data["snapshot"]["id"][:12], content)
        for key in ("assets/profile-activity.svg", "assets/profile-activity-mobile.svg"):
            self.assertEqual(len(ElementTree.fromstring(bundle[key]).findall("{http://www.w3.org/2000/svg}rect")), 366)

    def test_external_titles_are_data_not_markup_or_markdown(self):
        data = scan(Client(commits={"one": [commit()]}, prs={"one": [pr()]}))
        bundle = activity.outputs(data, activity.START + activity.END)
        self.assertNotIn("<script>", bundle["README.md"])
        self.assertNotIn("<img onerror", bundle["assets/activity-daily.md"])
        self.assertIn("<script>", json.loads(bundle["site/data.json"])["records"][0]["title"])
        self.assertNotIn("Details", data["records"][0]["title"])
        self.assertEqual(data["records"][0]["url"], "https://github.com/person/one/commit/" + commit()["sha"])

    def test_invalid_readme_markers_refuse_replacement(self):
        for text in ("missing", activity.END + activity.START, activity.START * 2 + activity.END):
            with self.assertRaises(ValueError):
                activity.replace_section(text, "new")

    def test_collection_and_render_failure_preserve_previous_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = scan(Client(repos=[]))
            initial = activity.outputs(data, "Before\n" + activity.START + activity.END + "\nAfter")
            activity.publish(root, initial)
            argv = ["profile_activity.py", "--owner", "person", "--root", directory]
            for failure in ("collect", "render_svg"):
                with self.subTest(failure=failure), patch.object(sys, "argv", argv), patch.object(activity, "collect", return_value=data) as collector:
                    if failure == "collect":
                        collector.side_effect = TimeoutError("partial")
                    with patch.object(activity, "render_svg", side_effect=ValueError("render failure")):
                        with self.assertRaises((TimeoutError, ValueError)):
                            activity.main()
                    self.assertEqual({p: (root / p).read_text() for p in initial}, initial)

    def test_write_failure_rolls_back_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = {"README.md": "old readme", "assets/image.svg": "old image", "site/data.json": "old data"}
            activity.publish(root, initial)
            real_replace = os.replace
            calls = 0
            def replace(source, dest):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("disk failure")
                return real_replace(source, dest)
            with patch.object(activity.os, "replace", side_effect=replace), self.assertRaises(OSError):
                activity.publish(root, {p: "new" for p in initial})
            self.assertEqual({p: (root / p).read_text() for p in initial}, initial)
            self.assertFalse(list((root / "site").glob(".profile-build-*")))


if __name__ == "__main__":
    unittest.main()
