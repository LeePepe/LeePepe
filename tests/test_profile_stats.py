import importlib.util
from datetime import datetime, timezone
from http.client import IncompleteRead
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError


SPEC = importlib.util.spec_from_file_location(
    "profile_stats", Path(__file__).resolve().parents[1] / "scripts/profile_stats.py"
)
stats = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stats
SPEC.loader.exec_module(stats)


def commit(sha="a", author="person", date="2026-02-01T00:00:00Z", parents=1):
    return {
        "sha": sha,
        "author": {"login": author} if author else None,
        "parents": [{}] * parents,
        "commit": {"author": {"date": date}},
    }


def repo(name="project", **changes):
    return {
        "full_name": f"person/{name}",
        "owner": {"login": "person"},
        "private": False,
        "fork": False,
        "default_branch": "main",
        **changes,
    }


class StatsTests(unittest.TestCase):
    def test_incomplete_network_response_is_retried(self):
        client = stats.GitHub("")
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"login":"person"}'
        with (
            patch.object(
                stats, "urlopen", side_effect=[IncompleteRead(b"partial", 10), response]
            ) as request,
            patch.object(stats.time, "sleep"),
        ):
            self.assertEqual(client.get("users/person"), {"login": "person"})
        self.assertEqual(request.call_count, 2)

    def test_persistent_network_error_is_not_silently_ignored(self):
        client = stats.GitHub("")
        with (
            patch.object(
                stats, "urlopen", side_effect=TimeoutError("network timeout")
            ) as request,
            patch.object(stats.time, "sleep"),
        ):
            with self.assertRaises(TimeoutError):
                client.get("users/person")
        self.assertEqual(request.call_count, 3)

    def test_numstat_handles_binary_rename_tabs_and_newlines(self):
        # Separate literals prevent Python's octal escapes from absorbing digits.
        data = (
            b"3\t2\tcode.py\0-\t-\timage.png\0"
            + b"0\t0\t\0old.py\0new.py\0"
            + b"5\t1\todd\tname\n.py\0"
        )
        self.assertEqual(stats.sum_numstat(data), (8, 3))
        self.assertEqual(stats.sum_numstat(b""), (0, 0))

    def test_attribution_uses_author_not_committer_and_excludes_merges(self):
        identities = {"person": "Human", "helper[bot]": "Agent"}
        authored = commit(author="HELPER[bot]")
        authored["committer"] = {"login": "person"}
        self.assertEqual(stats.commit_actor(authored, identities), "Agent")
        self.assertIsNone(stats.commit_actor(commit(parents=2), identities))
        self.assertIsNone(stats.commit_actor(commit(author=None), identities))
        self.assertIsNone(
            stats.commit_actor(commit(author="unrelated[bot]"), identities)
        )

    def test_repository_pagination(self):
        client = stats.GitHub("")
        with patch.object(
            client, "get", side_effect=[list(range(stats.PAGE_SIZE)), [stats.PAGE_SIZE]]
        ) as get:
            self.assertEqual(
                len(list(client.pages("users/person/repos"))), stats.PAGE_SIZE + 1
            )
        self.assertEqual(get.call_args.kwargs["page"], 2)

    def test_commit_pagination_is_pinned_to_first_sha(self):
        client = stats.GitHub("")
        with patch.object(
            client,
            "get",
            side_effect=[[commit("snapshot")] * stats.PAGE_SIZE, [commit("last")]],
        ) as get:
            self.assertEqual(len(client.commits(repo())), stats.PAGE_SIZE + 1)
        self.assertEqual(get.call_args.kwargs["sha"], "snapshot")
        self.assertNotIn("author", get.call_args.kwargs)

    def test_only_empty_repository_errors_are_ignored(self):
        client = stats.GitHub("")
        for code in (409, 403, 404, 500):
            with patch.object(
                client, "get", side_effect=HTTPError("url", code, "error", {}, None)
            ):
                if code == 409:
                    self.assertEqual(client.commits(repo()), [])
                else:
                    with self.assertRaises(HTTPError):
                        client.commits(repo())

    def test_exact_commit_page_boundaries(self):
        client = stats.GitHub("")
        with patch.object(
            client,
            "get",
            side_effect=[
                [commit()] * stats.PAGE_SIZE,
                [commit()] * stats.PAGE_SIZE,
                [],
            ],
        ) as get:
            self.assertEqual(len(client.commits(repo())), stats.PAGE_SIZE * 2)
        self.assertEqual(get.call_args.kwargs["page"], 3)

    def test_missing_snapshot_is_fetched_and_failure_aborts(self):
        client = stats.GitHub("")
        missing = subprocess.CalledProcessError(1, "git cat-file")
        for fetch_result in (b"", subprocess.CalledProcessError(1, "git fetch")):
            with (
                patch.object(client, "pages", return_value=iter([repo()])),
                patch.object(client, "commits", return_value=[commit()]),
                patch.object(
                    stats,
                    "git",
                    side_effect=[b"", missing, fetch_result, b"1\t0\tfile\0"],
                ) as git,
            ):
                if isinstance(fetch_result, Exception):
                    with self.assertRaises(subprocess.CalledProcessError):
                        stats.collect(
                            client, "person", "helper[bot]", datetime.now(timezone.utc)
                        )
                else:
                    totals, _ = stats.collect(
                        client, "person", "helper[bot]", datetime.now(timezone.utc)
                    )
                    self.assertEqual(totals["all"]["Human"], stats.Totals(1, 1, 0))
            self.assertEqual(git.call_args_list[2].args, ("fetch", "origin", "a"))

    def test_main_failures_leave_readme_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            content = f"intro\n{stats.START}\nold\n{stats.END}\nprojects"
            path.write_text(content)
            arguments = [
                "profile_stats.py",
                "--owner",
                "person",
                "--agent",
                "helper[bot]",
                "--readme",
                str(path),
            ]
            for identity in ("person", "wrong-person"):
                with (
                    patch.object(sys, "argv", arguments),
                    patch.object(
                        stats.GitHub,
                        "get",
                        side_effect=[{"login": identity}, {"login": "helper[bot]"}],
                    ),
                    patch.object(
                        stats, "collect", side_effect=RuntimeError("collection failed")
                    ) as collect,
                ):
                    with self.assertRaises((ValueError, RuntimeError)):
                        stats.main()
                    if identity == "wrong-person":
                        collect.assert_not_called()
                self.assertEqual(path.read_text(), content)

    def test_collection_filters_repos_dates_authors_merges_and_duplicate_shas(self):
        client = stats.GitHub("")
        repositories = [
            repo(),
            repo("duplicate"),
            repo("fork", fork=True),
            repo("private", private=True),
            repo("foreign", owner={"login": "other"}),
        ]
        history = [
            commit("one"),
            commit("one"),
            commit("old", "helper[bot]", "2025-01-01T00:00:00Z"),
            commit("merge", parents=2),
            commit("unknown", author=None),
            commit("future", date="2027-01-01T00:00:00Z"),
        ]
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)
        with (
            patch.object(client, "pages", return_value=iter(repositories)),
            patch.object(client, "commits", return_value=history),
            patch.object(stats, "git", return_value=b"3\t2\tfile.py\0"),
        ):
            totals, count = stats.collect(client, "person", "helper[bot]", now)
        self.assertEqual(count, 2)
        self.assertEqual(totals["all"]["Human"], stats.Totals(1, 3, 2))
        self.assertEqual(totals["all"]["Agent"], stats.Totals(1, 3, 2))
        self.assertEqual(totals["year"]["Human"].commits, 1)
        self.assertEqual(totals["year"]["Agent"].commits, 0)

    def test_git_failure_stops_collection(self):
        client = stats.GitHub("")
        with (
            patch.object(client, "pages", return_value=iter([repo()])),
            patch.object(client, "commits", return_value=[commit()]),
            patch.object(
                stats, "git", side_effect=subprocess.CalledProcessError(1, "git")
            ),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                stats.collect(
                    client, "person", "helper[bot]", datetime.now(timezone.utc)
                )

    def test_year_uses_utc_not_original_offset(self):
        client = stats.GitHub("")
        with (
            patch.object(client, "pages", return_value=iter([repo()])),
            patch.object(
                client,
                "commits",
                return_value=[commit(date="2025-12-31T23:30:00-02:00")],
            ),
            patch.object(stats, "git", return_value=b"1\t0\tfile.py\0"),
        ):
            totals, _ = stats.collect(
                client,
                "person",
                "helper[bot]",
                datetime(2026, 10, 2, tzinfo=timezone.utc),
            )
        self.assertEqual(totals["year"]["Human"].commits, 1)

    def test_render_and_update_preserve_surrounding_readme(self):
        totals = {
            period: {
                "Human": stats.Totals(2, 100, 30),
                "Agent": stats.Totals(3, 200, 40),
            }
            for period in ("year", "all")
        }
        section = stats.render(totals, 4, datetime(2026, 10, 2, tzinfo=timezone.utc))
        self.assertIn("| Combined | 5 | +300 | −70 | 370 |", section)
        self.assertIn("including docs/config", section)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text(f"intro\n{stats.START}\nold\n{stats.END}\nprojects")
            stats.update_readme(path, section)
            self.assertEqual(path.read_text(), f"intro\n{section}\nprojects")
            stats.update_readme(path, section)
            self.assertEqual(path.read_text(), f"intro\n{section}\nprojects")

    def test_bad_markers_do_not_change_readme(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            for content in (
                "no markers",
                stats.END + stats.START,
                stats.START + stats.START + stats.END,
            ):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    stats.update_readme(path, "new")
                self.assertEqual(path.read_text(), content)

    def test_real_git_root_binary_and_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(*args):
                return stats.git(*args, cwd=root)

            run("init", "--quiet", "--initial-branch=main")
            run("config", "user.name", "Test")
            run("config", "user.email", "test@example.invalid")
            (root / "file.py").write_text("one\ntwo\n")
            (root / "image.bin").write_bytes(b"\0\1\2")
            run("add", ".")
            run("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "root")
            first_sha = run("rev-parse", "HEAD").decode().strip()
            options = (
                "show",
                "--format=",
                "--numstat",
                "-z",
                "--find-renames",
                "--root",
            )
            self.assertEqual(stats.sum_numstat(run(*options, "HEAD")), (2, 0))
            run("mv", "file.py", "renamed.py")
            run("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "rename")
            self.assertEqual(stats.sum_numstat(run(*options, "HEAD")), (0, 0))
            last_sha = run("rev-parse", "HEAD").decode().strip()
            real_git = stats.git

            def local_clone(*args, **kwargs):
                if args[0] == "clone":
                    args = (*args[:-2], str(root), args[-1])
                return real_git(*args, **kwargs)

            client = stats.GitHub("")
            with (
                patch.object(client, "pages", return_value=iter([repo()])),
                patch.object(
                    client,
                    "commits",
                    return_value=[commit(last_sha), commit(first_sha, parents=0)],
                ),
                patch.object(stats, "git", side_effect=local_clone),
            ):
                totals, _ = stats.collect(
                    client, "person", "helper[bot]", datetime.now(timezone.utc)
                )
            self.assertEqual(totals["all"]["Human"], stats.Totals(2, 2, 0))


if __name__ == "__main__":
    unittest.main()
