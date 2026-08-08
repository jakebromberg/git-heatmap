"""Tests for git-heatmap.

Fixture repositories are built programmatically with backdated commits, so there
is no committed binary git data. Run with:

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

# The executable is `git-heatmap` (hyphen, no .py extension). spec_from_file_location
# cannot infer a loader for an unrecognised suffix, so name the loader explicitly.
_MODULE_PATH = Path(__file__).resolve().parent.parent / "git-heatmap"
_loader = SourceFileLoader("git_heatmap", str(_MODULE_PATH))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
gh = importlib.util.module_from_spec(_spec)
sys.modules["git_heatmap"] = gh
_loader.exec_module(gh)


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` with identity pinned so tests don't read global config."""
    proc = subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=Test Author",
            "-c", "user.email=test@example.com",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def commit(repo: Path, date: str, message: str, author: str | None = None) -> None:
    """Create one empty commit stamped at `date` (YYYY-MM-DD)."""
    args = ["commit", "--allow-empty", "-q", "-m", message]
    if author:
        args += ["--author", author]
    env_date = f"{date}T12:00:00"
    proc = subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=Test Author",
            "-c", "user.email=test@example.com",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_DATE": env_date, "GIT_COMMITTER_DATE": env_date},
    )
    assert proc.returncode == 0


class FixtureRepoTestCase(unittest.TestCase):
    """Base class providing a small repo with a known commit shape."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls._tmp.name) / "fixture"
        cls.repo.mkdir()
        git(cls.repo, "init", "-q", "-b", "main")
        # 2 commits on one day, 1 on another, 3 on a third; one by a second author.
        commit(cls.repo, "2024-01-08", "a1")
        commit(cls.repo, "2024-01-08", "a2")
        commit(cls.repo, "2024-01-09", "b1")
        commit(cls.repo, "2024-03-15", "c1")
        commit(cls.repo, "2024-03-15", "c2")
        commit(cls.repo, "2024-03-15", "c3", author="Other Dev <other@example.com>")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def parse(self, *argv: str):
        return gh.build_parser().parse_args([str(self.repo), *argv])


class TestCollectCounts(FixtureRepoTestCase):
    def test_counts_commits_per_day(self):
        counts = gh.collect_counts(self.repo, self.parse())
        self.assertEqual(
            dict(counts), {"2024-01-08": 2, "2024-01-09": 1, "2024-03-15": 3}
        )

    def test_total_matches_git_log(self):
        counts = gh.collect_counts(self.repo, self.parse())
        expected = len(git(self.repo, "log", "--pretty=%H").strip().splitlines())
        self.assertEqual(sum(counts.values()), expected)

    def test_author_filter(self):
        counts = gh.collect_counts(self.repo, self.parse("--author", "Other Dev"))
        self.assertEqual(dict(counts), {"2024-03-15": 1})

    def test_since_filter(self):
        counts = gh.collect_counts(self.repo, self.parse("--since", "2024-02-01"))
        self.assertEqual(dict(counts), {"2024-03-15": 3})

    def test_until_filter(self):
        counts = gh.collect_counts(self.repo, self.parse("--until", "2024-01-31"))
        self.assertEqual(dict(counts), {"2024-01-08": 2, "2024-01-09": 1})

    def test_committer_dates_available(self):
        counts = gh.collect_counts(self.repo, self.parse("--date", "committer"))
        self.assertEqual(sum(counts.values()), 6)

    def test_no_commits_returns_empty(self):
        counts = gh.collect_counts(self.repo, self.parse("--author", "Nobody At All"))
        self.assertEqual(dict(counts), {})


class TestAuthorSummary(FixtureRepoTestCase):
    def test_reports_multiple_authors(self):
        self.assertEqual(gh.author_summary(self.repo, self.parse()), "all authors (2)")

    def test_echoes_explicit_author_filter(self):
        summary = gh.author_summary(self.repo, self.parse("--author", "Other Dev"))
        self.assertEqual(summary, "Other Dev")


class TestRepoLabel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "myproject"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        self._tmp.cleanup()

    def test_falls_back_to_directory_name_without_remote(self):
        self.assertEqual(gh.repo_label(self.repo), "myproject")

    def test_parses_ssh_remote(self):
        git(self.repo, "remote", "add", "origin", "git@github.com:WXYC/wxyc-ios-64.git")
        self.assertEqual(gh.repo_label(self.repo), "WXYC/wxyc-ios-64")

    def test_parses_https_remote(self):
        git(self.repo, "remote", "add", "origin", "https://github.com/WXYC/dj-site.git")
        self.assertEqual(gh.repo_label(self.repo), "WXYC/dj-site")

    def test_parses_remote_without_git_suffix(self):
        git(self.repo, "remote", "add", "origin", "https://github.com/WXYC/wiki")
        self.assertEqual(gh.repo_label(self.repo), "WXYC/wiki")


class TestResolveRepo(unittest.TestCase):
    def test_rejects_missing_path(self):
        with self.assertRaises(gh.GitHeatmapError):
            gh.resolve_repo(Path("/nonexistent/path/for/tests"))

    def test_rejects_non_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gh.GitHeatmapError):
                gh.resolve_repo(Path(tmp))

    def test_resolves_from_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            (repo / "nested" / "deep").mkdir(parents=True)
            git(repo, "init", "-q", "-b", "main")
            self.assertEqual(
                gh.resolve_repo(repo / "nested" / "deep").resolve(), repo.resolve()
            )


class TestRender(unittest.TestCase):
    def test_embeds_data_and_meta_as_valid_json(self):
        counts = {"2024-01-08": 2, "2024-01-09": 1}
        meta = {
            "repo": "acme/thing", "scope": "acme/thing — all authors",
            "title": "t", "today": "2024-06-01",
            "dateKind": "author", "generator": "git-heatmap test",
        }
        html = gh.render_html(counts, meta)

        for placeholder in ("__DATA_JSON__", "__META_JSON__", "__TITLE__"):
            self.assertNotIn(placeholder, html)

        data_line = next(l for l in html.splitlines() if l.startswith("const DATA ="))
        parsed = json.loads(data_line[len("const DATA ="):].strip().rstrip(";"))
        self.assertEqual(parsed, counts)

        meta_line = next(l for l in html.splitlines() if l.startswith("const META ="))
        self.assertEqual(
            json.loads(meta_line[len("const META ="):].strip().rstrip(";")), meta
        )

    def test_is_self_contained(self):
        """No external fetches: the page must work offline from file://."""
        html = gh.render_html({"2024-01-08": 1}, {
            "repo": "r", "scope": "s", "title": "t", "today": "2024-06-01",
            "dateKind": "author", "generator": "g",
        })
        for forbidden in ("http://", "https://", "<script src", "<link rel=\"stylesheet\""):
            self.assertNotIn(forbidden, html)

    def test_escapes_html_in_title(self):
        html = gh.render_html({"2024-01-08": 1}, {
            "repo": "r", "scope": "s", "title": '<script>x</script>',
            "today": "2024-06-01", "dateKind": "author", "generator": "g",
        })
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)
        self.assertNotIn("<title><script>", html)


class TestEscapeHtml(unittest.TestCase):
    def test_escapes_the_dangerous_five(self):
        self.assertEqual(
            gh.escape_html('<a href="x">&</a>'),
            "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;",
        )

    def test_ampersand_escaped_first(self):
        """&lt; must not become &amp;lt; -- ordering matters."""
        self.assertEqual(gh.escape_html("<"), "&lt;")


class TestMain(FixtureRepoTestCase):
    def setUp(self):
        # main() logs to stderr by design; silence it so error-path tests don't
        # print ERROR lines that read like failures.
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_json_mode_writes_counts(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = gh.main([str(self.repo), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(buf.getvalue()),
            {"2024-01-08": 2, "2024-01-09": 1, "2024-03-15": 3},
        )

    def test_writes_html_to_requested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "page.html"
            code = gh.main([str(self.repo), "-o", str(out), "--no-open"])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertIn("<!doctype html>", out.read_text())

    def test_exit_2_when_no_commits_match(self):
        code = gh.main([str(self.repo), "--author", "Nobody", "--no-open"])
        self.assertEqual(code, 2)

    def test_exit_1_for_non_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gh.main([tmp, "--no-open"]), 1)


if __name__ == "__main__":
    unittest.main()
