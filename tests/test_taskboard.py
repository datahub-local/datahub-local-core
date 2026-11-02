"""The three decisions the tick makes from board and comment data.

Everything else in taskboard.py is transport. These are the functions that could
silently pick the wrong issue or answer the wrong person, so they are pinned.
"""

import importlib.util
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "releases/automation/files/agent/taskboard-loop/taskboard.py"
)
spec = importlib.util.spec_from_file_location("taskboard", SCRIPT)
taskboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(taskboard)


def item(number, status, labels, kind="Issue", title="t"):
    return {
        "id": f"item-{number}",
        "fieldValueByName": {"name": status} if status else None,
        "content": {
            "__typename": kind,
            "number": number,
            "title": title,
            "url": f"https://example/{number}",
            "labels": {"nodes": [{"name": name} for name in labels]},
        },
    }


def test_pick_ready_keeps_ready_agent_issues_only():
    items = [
        item(3, "Ready", ["agent", "docs"]),
        item(1, "Ready", ["agent"]),
        item(2, "Ready", ["docs"]),
        item(4, "In Progress", ["agent"]),
        item(5, "Backlog", ["agent"]),
        item(6, "Ready", ["agent"], kind="PullRequest"),
        item(7, None, ["agent"]),
    ]
    assert [r["number"] for r in taskboard.pick_ready(items)] == [1, 3]


def test_pick_ready_is_empty_when_nothing_is_ready():
    assert taskboard.pick_ready([item(1, "Backlog", ["agent"])]) == []


def comment(body, created_at="2026-11-01T10:00:00Z"):
    return {
        "author": "alvsanand",
        "created_at": created_at,
        "body": body,
        "url": "",
        "machine": taskboard.MARKER in body,
    }


def test_last_session_wins_over_earlier_ones():
    comments = [
        comment("Started session `abc`.\n\n<!-- taskboard:session abc -->"),
        comment("Started session `def`.\n\n<!-- taskboard:session def -->"),
    ]
    assert taskboard.last_session(comments) == "def"


def test_last_session_is_none_without_a_marker():
    assert taskboard.last_session([comment("Claimed. Branch feat/1-x")]) is None


def test_help_state_is_unanswered_when_only_machine_comments_follow():
    comments = [
        comment("<!-- taskboard:help -->\nWhich repository?", "2026-11-01T10:00:00Z"),
        comment("Started session `abc`.\n\n<!-- taskboard:session abc -->", "2026-11-01T10:05:00Z"),
    ]
    state = taskboard.help_state(comments)
    assert state["asked"] is True
    assert state["answered"] is False


def test_help_state_takes_the_first_owner_comment_after_the_marker():
    comments = [
        comment("older chatter", "2026-11-01T09:00:00Z"),
        comment("<!-- taskboard:help -->\nWhich repository?", "2026-11-01T10:00:00Z"),
        comment("datahub-local, please", "2026-11-01T11:00:00Z"),
        comment("and don't touch secrets", "2026-11-01T12:00:00Z"),
    ]
    state = taskboard.help_state(comments)
    assert state["answered"] is True
    assert state["answer"]["body"] == "datahub-local, please"


def test_help_state_ignores_a_comment_posted_before_the_question():
    comments = [
        comment("do it", "2026-11-01T09:00:00Z"),
        comment("<!-- taskboard:help -->\nWhich repository?", "2026-11-01T10:00:00Z"),
    ]
    assert taskboard.help_state(comments)["answered"] is False


def test_help_state_without_a_marker_asks_nothing():
    assert taskboard.help_state([comment("hello")])["asked"] is False


def test_missing_on_board_finds_labelled_issues_never_added():
    issues = [
        {"number": 117, "node_id": "I_117", "title": "new"},
        {"number": 116, "node_id": "I_116", "title": "on board"},
    ]
    items = [item(116, "Ready", ["agent"])]
    assert [i["number"] for i in taskboard.missing_on_board(issues, items)] == [117]


def test_missing_on_board_is_empty_when_every_issue_is_there():
    issues = [{"number": 116, "node_id": "I_116", "title": "t"}]
    assert taskboard.missing_on_board(issues, [item(116, "Ready", ["agent"])]) == []


def test_repos_of_reads_the_named_repositories():
    body = "## What\ntext\n\n## Repo\n\n`datahub-local`\n"
    assert taskboard.repos_of(body) == ["datahub-local"]


def test_repos_of_keeps_several_and_drops_the_org():
    body = "## Repo\n`datahub-local/` `datahub-local-core`, `datahub-local`\n"
    assert taskboard.repos_of(body) == ["datahub-local", "datahub-local-core"]


def test_repos_of_returns_nothing_for_an_issue_without_the_section():
    assert taskboard.repos_of("## What\nno repo line here, only `code`\n") == []


def comment_with_id(body, created_at, ident=1):
    c = comment(body, created_at)
    c["id"] = ident
    return c


def test_pending_comments_are_every_human_comment_without_a_forwarder_marker():
    comments = [
        comment_with_id("do it", "2026-11-01T09:00:00Z"),
        comment_with_id("Started session `abc`.\n\n<!-- taskboard:session abc -->", "2026-11-01T09:01:00Z"),
    ]
    assert [c["body"] for c in taskboard.pending_comments(comments)] == ["do it"]


def test_pending_comments_start_after_the_newest_forwarded_marker():
    comments = [
        comment_with_id("old", "2026-11-01T09:00:00Z"),
        comment_with_id("Forwarded.\n\n<!-- taskboard:forwarded 2026-11-01T09:30:00Z -->", "2026-11-01T09:31:00Z"),
        comment_with_id("new", "2026-11-01T10:00:00Z"),
        comment_with_id("Claimed.\n\n<!-- taskboard:agent -->", "2026-11-01T10:05:00Z"),
    ]
    assert [c["body"] for c in taskboard.pending_comments(comments)] == ["new"]


def test_pending_comments_never_include_a_machine_comment():
    comments = [
        comment_with_id("Forwarded.\n\n<!-- taskboard:forwarded 2026-11-01T09:30:00Z -->", "2026-11-01T09:31:00Z", 1),
        comment_with_id("**The agent needs a decision**\n<!-- taskboard:help -->", "2026-11-01T10:00:00Z", 2),
    ]
    assert taskboard.pending_comments(comments) == []


def test_merge_pending_orders_issue_and_review_comments_together():
    issue_comments = [comment_with_id("issue note", "2026-11-01T10:05:00Z", 1)]
    review = [
        {
            "id": 2,
            "author": "alvsanand",
            "created_at": "2026-11-01T10:00:00Z",
            "body": "rename this",
            "url": "",
            "machine": False,
            "path": "src/a.py",
            "line": 12,
        }
    ]
    merged = taskboard.merge_pending(issue_comments, review, "2026-11-01T09:00:00Z")
    assert [c["body"] for c in merged] == ["rename this", "issue note"]


def test_merge_pending_drops_a_review_comment_already_forwarded():
    review = [
        {
            "id": 2,
            "author": "alvsanand",
            "created_at": "2026-11-01T09:00:00Z",
            "body": "old",
            "url": "",
            "machine": False,
            "path": None,
            "line": None,
        }
    ]
    assert taskboard.merge_pending([], review, "2026-11-01T10:00:00Z") == []


def test_last_branch_reads_the_claim_comment():
    comments = [
        comment_with_id("Claimed. Branch `feat/116-org-profile-readme` in datahub-local.", "2026-11-01T09:00:00Z")
    ]
    assert taskboard.last_branch(comments) == "feat/116-org-profile-readme"


def test_comment_body_marks_a_machine_comment():
    assert taskboard.comment_body("Claimed.").endswith(taskboard.AGENT_MARKER)


def test_comment_body_keeps_an_owner_relay_unmarked():
    body = taskboard.comment_body("use the other repository", owner=True)
    assert body == "use the other repository"
    assert taskboard.MARKER not in body


def test_comment_body_does_not_double_mark():
    body = taskboard.comment_body("Already.\n\n<!-- taskboard:help -->")
    assert body.count("<!-- taskboard:") == 1


def test_active_items_lists_every_open_issue_ordered_by_work_state():
    items = [
        item(9, "Testing", ["agent"]),
        item(4, "Backlog", ["agent"]),
        item(2, "In Progress", ["agent"]),
        item(7, "Done", ["agent"]),
        item(5, "Blocked", ["agent"]),
        item(6, "In Progress", ["docs"]),
        item(3, "Ready", ["agent"]),
    ]
    assert [r["number"] for r in taskboard.active_items(items)] == [4, 3, 2, 5, 9]


class _Minter(BaseHTTPRequestHandler):
    """A one-shot stand-in for the sidecar that answers /token on loopback."""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's name
        body = json.dumps({"token": "ghs_from_minter"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_an_exported_token_wins_over_the_minter():
    assert taskboard.credential({"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_exported"}) == "ghp_exported"


def test_the_helper_mints_when_the_environment_has_no_token():
    server = HTTPServer(("127.0.0.1", 0), _Minter)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/token"
        assert taskboard.credential({"MINTER_URL": url}) == "ghs_from_minter"
    finally:
        server.shutdown()


def test_no_token_and_no_minter_fails_loudly():
    try:
        taskboard.credential({})
    except SystemExit as exc:
        assert "MINTER_URL is empty" in str(exc)
        return
    raise AssertionError("credential() accepted an environment with no token source")


def test_comment_text_takes_the_body_from_argv_because_cron_blocks_a_heredoc():
    """A heredoc is refused as dangerous in cron, so `comment` needs --text."""
    assert taskboard.comment_text(["--text", "the body"], "") == "the body"


def test_comment_text_falls_back_to_stdin():
    assert taskboard.comment_text([], "the body\n") == "the body"


def test_comment_text_refuses_a_missing_value():
    try:
        taskboard.comment_text(["--text"], "")
    except SystemExit as exc:
        assert "--text needs a value" in str(exc)
        return
    raise AssertionError("comment_text() accepted --text without a body")


def test_done_needs_a_closed_issue():
    """#117 was moved to Done while open because three merged PRs mentioned it."""
    assert taskboard.may_finish("CLOSED")
    assert not taskboard.may_finish("OPEN")
    assert not taskboard.may_finish("")
