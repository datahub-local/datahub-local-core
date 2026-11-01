"""The three decisions the tick makes from board and comment data.

Everything else in taskboard.py is transport. These are the functions that could
silently pick the wrong issue or answer the wrong person, so they are pinned.
"""

import importlib.util
import pathlib

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
