import importlib.util
from datetime import date, datetime, timedelta, timezone
from http.client import IncompleteRead
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from xml.etree import ElementTree


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
            with (
                HTTPError("url", code, "error", {}, None) as error,
                patch.object(client, "get", side_effect=error),
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
                    totals, _, _ = stats.collect(
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
            totals, count, daily = stats.collect(client, "person", "helper[bot]", now)
        self.assertEqual(count, 2)
        self.assertEqual(totals["all"]["Human"], stats.Totals(1, 3, 2))
        self.assertEqual(totals["all"]["Agent"], stats.Totals(1, 3, 2))
        self.assertEqual(totals["year"]["Human"].commits, 1)
        self.assertEqual(totals["year"]["Agent"].commits, 0)
        self.assertEqual(daily["Human"], {date(2026, 2, 1): stats.Totals(1, 3, 2)})
        self.assertEqual(daily["Agent"], {date(2025, 1, 1): stats.Totals(1, 3, 2)})

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
            totals, _, daily = stats.collect(
                client,
                "person",
                "helper[bot]",
                datetime(2026, 10, 2, tzinfo=timezone.utc),
            )
        self.assertEqual(totals["year"]["Human"].commits, 1)
        self.assertEqual(daily["Human"], {date(2026, 1, 1): stats.Totals(1, 1, 0)})

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
        self.assertIn("human-calendar.svg", section)
        self.assertIn("agent-calendar-mobile.svg", section)
        self.assertIn("<details>", section)
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
                totals, _, _ = stats.collect(
                    client, "person", "helper[bot]", datetime.now(timezone.utc)
                )
            self.assertEqual(totals["all"]["Human"], stats.Totals(2, 2, 0))

    def test_calendar_has_exactly_365_days_including_leap_day_and_no_future_cells(self):
        for today in (date(2024, 3, 1), date(2026, 10, 3), date(2026, 10, 4)):
            for compact in (False, True):
                root = ElementTree.fromstring(
                    stats.render_calendar("person", "Human", {}, today, compact=compact)
                )
                cells = [
                    element for element in root.iter() if "data-date" in element.attrib
                ]
                expected = {
                    str(today - timedelta(days=offset)) for offset in range(365)
                }
                self.assertEqual({cell.attrib["data-date"] for cell in cells}, expected)
                self.assertEqual(len(cells), 365)
                self.assertTrue(all(cell.attrib["data-count"] == "0" for cell in cells))
                width, height = map(int, root.attrib["viewBox"].split()[2:])
                for cell in cells:
                    self.assertLess(
                        float(cell.attrib["x"]) + float(cell.attrib["width"]), width
                    )
                    self.assertLess(
                        float(cell.attrib["y"]) + float(cell.attrib["height"]), height
                    )

    def test_calendar_positions_weekdays_and_shared_color_thresholds(self):
        today = date(2026, 10, 3)  # Saturday
        days = {
            today: stats.Totals(20, 50, 10),
            today - timedelta(days=1): stats.Totals(1, 4, 2),
        }
        root = ElementTree.fromstring(
            stats.render_calendar("person", "Human", days, today)
        )
        cells = {
            element.attrib["data-date"]: element
            for element in root.iter()
            if "data-date" in element.attrib
        }
        self.assertEqual(cells[str(today)].attrib["class"], "day level-4")
        self.assertEqual(cells[str(today)].attrib["y"], str(134 + 6 * 15))
        self.assertEqual(
            cells[str(today - timedelta(days=1))].attrib["class"], "day level-1"
        )
        self.assertEqual(
            [stats.calendar_level(x) for x in (0, 1, 3, 4, 9, 10, 19, 20)],
            [0, 1, 1, 2, 2, 3, 3, 4],
        )

    def test_calendar_totals_match_visible_window_and_escape_text(self):
        today = date(2026, 10, 3)
        days = {
            today: stats.Totals(2, 15, 7),
            today - timedelta(days=364): stats.Totals(3, 20, 1),
            today - timedelta(days=365): stats.Totals(100, 100, 100),
            today + timedelta(days=1): stats.Totals(100, 100, 100),
        }
        content = stats.render_calendar('person <&> "test"', "Human", days, today)
        root = ElementTree.fromstring(content)
        text = " ".join(root.itertext())
        self.assertIn("5 commits in the last 365 days", text)
        self.assertIn("2 active days, 35 lines added, 8 lines deleted", text)
        self.assertIn('person <&> "test"', text)
        self.assertIn("prefers-color-scheme:dark", content)

    def test_main_generates_four_calendars_after_successful_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text(f"intro\n{stats.START}\nold\n{stats.END}\nprojects")
            today = datetime.now(timezone.utc).date()
            totals = {
                period: {
                    "Human": stats.Totals(2, 10, 5),
                    "Agent": stats.Totals(1, 6, 3),
                }
                for period in ("year", "all")
            }
            daily = {
                "Human": {today: totals["all"]["Human"]},
                "Agent": {today: totals["all"]["Agent"]},
            }
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "profile_stats.py",
                        "--owner",
                        "person",
                        "--agent",
                        "helper[bot]",
                        "--readme",
                        str(path),
                    ],
                ),
                patch.object(
                    stats.GitHub,
                    "get",
                    side_effect=[{"login": "person"}, {"login": "helper[bot]"}],
                ),
                patch.object(stats, "collect", return_value=(totals, 1, daily)),
                patch("builtins.print"),
            ):
                stats.main()
            self.assertEqual(
                {p.name for p in (Path(directory) / "assets").iterdir()},
                {
                    "human-calendar.svg",
                    "human-calendar-mobile.svg",
                    "agent-calendar.svg",
                    "agent-calendar-mobile.svg",
                },
            )
            self.assertIn("human-calendar.svg", path.read_text())
            for asset in (Path(directory) / "assets").iterdir():
                ElementTree.fromstring(asset.read_text())


if __name__ == "__main__":
    unittest.main()
