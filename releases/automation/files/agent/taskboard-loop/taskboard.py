"""The deterministic half of the taskboard loop.

Hermes judges, this script gathers and writes. Every status read, status write,
comment and pull-request lookup the tick needs is one subcommand here, so the
model never composes GraphQL and never guesses which card is where.

Identity is the trap this exists to avoid: the owner's PAT posts the agent's and
Hermes' comments too, so author is not a discriminator. Every machine comment ends
with a `<!-- taskboard:... -->` marker and an owner answer is a comment without
one.

Usage:
  taskboard.py sync
  taskboard.py board             (every open issue on the board, with its status)
  taskboard.py ready
  taskboard.py issue <n>
  taskboard.py inbox <n>              (comments the session has not been given)
  taskboard.py status <n> <Status>
  taskboard.py finish <n>             (Done, only once the issue is closed)
  taskboard.py comment <n> [--owner] [--text <body>]
                                  (body on stdin by default; --owner relays the
                                   owner's words)
  taskboard.py start <n> <session>    (records the session on the issue)
  taskboard.py forwarded <n> <since> [--failed]
                                  (records the send and reacts 👀; --failed reacts 😕
                                   and leaves the marker so the next tick retries)
  taskboard.py waiting <n>           (posts one ⏳ note while the agent is busy)
  taskboard.py pr <repo> <branch>
  taskboard.py review <repo> <pr>
  taskboard.py notify <n> [--text <body>]  (posts one Slack line with the links)
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
SLACK_API = "https://slack.com/api/chat.postMessage"
MARKER = "<!-- taskboard:"
HELP_MARKER = "<!-- taskboard:help -->"
AGENT_MARKER = "<!-- taskboard:agent -->"
WAITING_MARKER = "<!-- taskboard:waiting -->"
SESSION_RE = re.compile(r"<!-- taskboard:session (\S+) -->")
FORWARDED_RE = re.compile(r"<!-- taskboard:forwarded (\S+) -->")
BRANCH_RE = re.compile(r"Branch `([^`]+)`")
CLAIM_REPO_RE = re.compile(r"Branch `[^`]+` in ([\w-]+(?:/[\w.-]+)?)")
MARKER_RE = re.compile(r"<!-- taskboard:[^>]*-->\s*", re.MULTILINE)
MAX_COMMENT_CHARS = 1500

ORG = os.environ.get("TASKBOARD_ORG", "datahub-local")
PROJECT = int(os.environ.get("TASKBOARD_PROJECT", "1"))
REPO = os.environ.get("TASKBOARD_REPO", "datahub-local/datahub-local")
OWNER = os.environ.get("TASKBOARD_OWNER", "alvsanand")

PROJECT_QUERY = """
query($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      id
      field(name: "Status") {
        ... on ProjectV2SingleSelectField {
          id
          options { id name }
        }
      }
      items(first: 100) {
        nodes {
          id
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            __typename
            ... on Issue {
              number
              title
              url
              state
              body
              labels(first: 10) { nodes { name } }
            }
            ... on PullRequest { number title url state }
          }
        }
      }
    }
  }
}
"""

ADD_ITEM = """
mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: { projectId: $project, contentId: $content }) {
    item { id }
  }
}
"""

SET_STATUS = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: $project
      itemId: $item
      fieldId: $field
      value: { singleSelectOptionId: $option }
    }
  ) { projectV2Item { id } }
}
"""


def credential(env: dict | None = None) -> str:
    """The installation token for this call.

    Hermes has no GitHub token in its environment: the App key sits in a sidecar
    that answers /token on loopback, so nothing in the process that runs the model
    can read it, and nothing caches a token past the hour it is good for.
    """
    environment = os.environ if env is None else env
    exported = environment.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if exported:
        return exported
    url = environment.get("MINTER_URL", "")
    if not url:
        raise SystemExit("ERROR: GITHUB_PERSONAL_ACCESS_TOKEN is not set and MINTER_URL is empty")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read())["token"]
    except (urllib.error.URLError, ValueError, KeyError) as exc:
        raise SystemExit(f"ERROR: could not mint a GitHub token: {exc}")


def server_key(origin: str) -> str:
    """OpenCode's route key for a server origin.

    The web app routes a session at /server/<serverKey>/session/<id>, and
    serverKey is the base64url encoding of `location.origin` without padding,
    not the origin or a hash of it. A link built from the session id alone opens
    the app root, and a hash makes the app fail while resolving the server.
    """
    return base64.urlsafe_b64encode(origin.encode()).decode().rstrip("=")


def session_url(session: str, origin: str | None = None) -> str:
    """The web link to a session, or "" when no origin is configured.

    The origin must match what the browser reports as `location.origin`; a
    different scheme or a trailing slash produces a key that resolves to nothing.
    """
    base = (
        origin if origin is not None else os.environ.get("TASKBOARD_OPENCODE_URL", "")
    ).rstrip("/")
    if not base or not session:
        return ""
    return f"{base}/server/{server_key(base)}/session/{session}"


class GitHub:
    def __init__(self, token: str):
        self.token = token
        self._project = None

    def _call(self, method: str, path: str, body: dict | None = None):
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        if data:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise SystemExit(f"ERROR: {method} {path} -> {exc.code} {detail}")

    def graphql(self, query: str, variables: dict) -> dict:
        payload = self._call("POST", "/graphql", {"query": query, "variables": variables})
        if payload.get("errors"):
            raise SystemExit(f"ERROR: graphql {payload['errors']}")
        return payload["data"]

    def invalidate(self) -> None:
        self._project = None

    def project(self) -> dict:
        if self._project is None:
            data = self.graphql(PROJECT_QUERY, {"org": ORG, "number": PROJECT})
            project = data["organization"]["projectV2"]
            self._project = {
                "id": project["id"],
                "field": project["field"]["id"],
                "options": {o["name"]: o["id"] for o in project["field"]["options"]},
                "items": project["items"]["nodes"],
            }
        return self._project

    def item(self, number: int) -> dict:
        for item in self.project()["items"]:
            content = item.get("content") or {}
            if content.get("number") == number and content.get("__typename") == "Issue":
                return item
        raise SystemExit(f"ERROR: issue #{number} is not on the board")

    def comments(self, number: int) -> list[dict]:
        raw = self._call("GET", f"/repos/{REPO}/issues/{number}/comments?per_page=100")
        return [
            {
                "id": c.get("id"),
                "repo": REPO,
                "author": (c.get("user") or {}).get("login", ""),
                "created_at": c.get("created_at", ""),
                "body": (c.get("body") or "")[:MAX_COMMENT_CHARS],
                "url": c.get("html_url", ""),
                "machine": MARKER in (c.get("body") or ""),
            }
            for c in raw
        ]

    def pull_comments(self, repo: str, number: int) -> list[dict]:
        """Every surface the owner can write on, shaped alike.

        A conversation comment and an inline review comment are different REST
        collections; reading only the second is how an owner reply on the pull
        request is lost. `path`/`line` stay empty on a conversation comment.
        """
        conversation = self._call(
            "GET", f"/repos/{repo}/issues/{number}/comments?per_page=100"
        )
        review = self._call("GET", f"/repos/{repo}/pulls/{number}/comments?per_page=100")
        return [
            {
                "id": c.get("id"),
                "repo": repo,
                "author": (c.get("user") or {}).get("login", ""),
                "created_at": c.get("created_at", ""),
                "body": (c.get("body") or "")[:MAX_COMMENT_CHARS],
                "url": c.get("html_url", ""),
                "machine": MARKER in (c.get("body") or ""),
                "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
            }
            for c in list(conversation) + list(review)
        ]


REPO_HEADING = re.compile(r"^##\s*Repo\s*$", re.IGNORECASE | re.MULTILINE)
BACKTICK = re.compile(r"`([^`]+)`")


def set_status(github: GitHub, number: int, wanted: str) -> dict:
    """Move one card, or report that it is already there. The only board write."""
    project = github.project()
    if wanted not in project["options"]:
        raise SystemExit(f"ERROR: unknown status {wanted}")
    item = github.item(number)
    content = item.get("content") or {}
    previous = (item.get("fieldValueByName") or {}).get("name")
    result = {
        "number": number,
        "title": content.get("title", ""),
        "url": content.get("url", ""),
        "status": wanted,
        "changed": previous != wanted,
    }
    if previous == wanted:
        return result
    github.graphql(
        SET_STATUS,
        {
            "project": project["id"],
            "item": item["id"],
            "field": project["field"],
            "option": project["options"][wanted],
        },
    )
    github.invalidate()
    result["previous"] = previous
    return result


def move_line(result: dict, session: str | None = None, origin: str | None = None) -> str:
    """The one Slack line a board write produces."""
    status = result["status"]
    previous = result.get("previous")
    change = f"{previous} → {status}" if previous else status
    line = f"#{result['number']} {change}: {result.get('title', '')}\n{result.get('url', '')}"
    link = session_url(session, origin) if session else ""
    if link:
        line += f"\nSession: {link}"
    return line


def slack(text: str, env: dict | None = None) -> bool:
    """Post one line as Hermes' own app.

    The token rides in an Authorization header, never argv. The call is allowed
    to fail without failing the board write that triggered it: the card has
    already moved, and a retry would move it twice.
    """
    environment = os.environ if env is None else env
    token = environment.get("SLACK_BOT_TOKEN", "")
    channel = environment.get("SLACK_HOME_CHANNEL", "")
    if not token or not channel:
        print(
            "WARNING: Slack is not configured (SLACK_BOT_TOKEN / SLACK_HOME_CHANNEL)",
            file=sys.stderr,
        )
        return False
    body = json.dumps({"channel": channel, "text": text}).encode()
    request = urllib.request.Request(SLACK_API, data=body, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            answer = json.loads(response.read() or b"{}")
    except (urllib.error.URLError, ValueError, OSError) as exc:
        print(f"WARNING: Slack post failed: {exc}", file=sys.stderr)
        return False
    if not answer.get("ok"):
        print(
            f"WARNING: Slack post failed: {answer.get('error', 'unknown error')}",
            file=sys.stderr,
        )
        return False
    return True


def notify_move(result: dict, session: str | None = None, post=slack) -> bool:
    """Announce a board write, and stay silent when the board did not change."""
    if not result.get("changed"):
        return False
    return post(move_line(result, session))


def strip_markers(body: str) -> str:
    return MARKER_RE.sub("", body).strip()


def start_body(session: str, newest: str, origin: str | None = None) -> str:
    """The claim comment, with the link the owner needs to watch the turn."""
    lines = [f"Started session `{session}`."]
    link = session_url(session, origin)
    if link:
        lines += ["", f"Session: {link}"]
    lines += [
        "",
        f"<!-- taskboard:session {session} -->",
        f"<!-- taskboard:forwarded {newest} -->",
    ]
    return "\n".join(lines)


def may_finish(state: str) -> bool:
    """Done belongs to a closed issue, or to the owner's own move.

    An open issue with merged pull requests referencing it is still being worked:
    the loop's umbrella issue proved that the hard way.
    """
    return (state or "").upper() == "CLOSED"


def repos_of(body: str) -> list[str]:
    """The repositories the issue names under its `## Repo` heading.

    The section is the contract the intake shape already states, and reading it
    here is what lets the tick start a task inside that repository's checkout
    instead of the workspace root, which is the difference between two parallel
    sessions and two writers in one tree.
    """
    match = REPO_HEADING.search(body or "")
    if not match:
        return []
    section = (body or "")[match.end() :]
    section = re.split(r"^##\s", section, maxsplit=1, flags=re.MULTILINE)[0]
    repos = []
    for token in BACKTICK.findall(section):
        name = token.strip().rstrip("/").split("/")[-1]
        if name and name not in repos:
            repos.append(name)
    return repos


def full_repo(name: str) -> str:
    """A repository slug with its organisation.

    Everything reads a repository the way the issue prose names it; the API path
    needs `<owner>/<repo>`, and a bare name is an owner that does not exist.
    """
    name = (name or "").strip().strip("/")
    if not name:
        return ""
    return name if "/" in name else f"{ORG}/{name}"


def repo_of(body: str, comments: list[dict]) -> str:
    """The repository the work is in, from the issue or the agent's claim.

    `## Repo` is the intake contract, but an older issue can lack it; the claim
    comment still names where the branch was pushed (`Branch `x` in <repo>`), and
    that is enough to find the pull request.
    """
    repos = repos_of(body)
    if len(repos) == 1:
        return full_repo(repos[0])
    if repos:
        return ""
    for comment in reversed(comments):
        match = CLAIM_REPO_RE.search(comment.get("body") or "")
        if match:
            return full_repo(match.group(1))
    return ""


def active_items(items: list[dict]) -> list[dict]:
    """Board items still being worked: an issue, agent-labelled, not Done.

    The tick has no memory between runs, so its work list has to come from the
    board. Without this the comment, question and pull-request steps have nothing
    to iterate and silently do nothing.
    """
    active = []
    for item in items:
        content = item.get("content") or {}
        if content.get("__typename") != "Issue":
            continue
        status = (item.get("fieldValueByName") or {}).get("name")
        labels = [n["name"] for n in (content.get("labels") or {}).get("nodes", [])]
        if status in (None, "Done") or "agent" not in labels:
            continue
        active.append(
            {
                "number": content["number"],
                "title": content["title"],
                "url": content["url"],
                "status": status,
                "state": content.get("state"),
            }
        )
    order = ["Backlog", "Ready", "In Progress", "Blocked", "Code Review", "Testing"]
    return sorted(active, key=lambda r: (order.index(r["status"]), r["number"]))


def comment_text(args: list[str], stdin_text: str) -> str:
    """The body for `comment`: `--text`, or stdin when it is absent.

    Cron mode refuses a heredoc as a dangerous command, so a tick has to pass the
    body on argv. The body is public once posted; only the token stays off argv.
    """
    if "--text" in args:
        index = args.index("--text")
        if index + 1 >= len(args):
            raise SystemExit("ERROR: --text needs a value")
        return args[index + 1].strip()
    return stdin_text.strip()


def comment_body(body: str, owner: bool = False) -> str:
    """What a comment posted by the tick carries.

    `--owner` is the relay path: the words are the owner's, and marking them would
    make `inbox` drop them, which is how an answer gets lost.
    """
    text = body.strip()
    if owner or MARKER in text:
        return text
    return f"{text}\n\n{AGENT_MARKER}"


def missing_on_board(issues: list[dict], items: list[dict]) -> list[dict]:
    """Open agent issues that never reached the board.

    The project's own automation adds sub-issues, and nothing adds a labelled
    issue, so a new taskboard issue stays invisible to the tick until something
    puts it on the board.
    """
    on_board = {
        (item.get("content") or {}).get("number")
        for item in items
        if (item.get("content") or {}).get("__typename") == "Issue"
    }
    return [
        {
            "number": i["number"],
            "node_id": i["node_id"],
            "title": i["title"],
            "url": i.get("html_url", ""),
        }
        for i in issues
        if i["number"] not in on_board
    ]


def pick_ready(items: list[dict]) -> list[dict]:
    """Board items that are Ready, labelled agent, and are issues."""
    ready = []
    for item in items:
        content = item.get("content") or {}
        if content.get("__typename") != "Issue":
            continue
        status = (item.get("fieldValueByName") or {}).get("name")
        labels = [n["name"] for n in (content.get("labels") or {}).get("nodes", [])]
        if status != "Ready" or "agent" not in labels:
            continue
        ready.append(
            {
                "number": content["number"],
                "title": content["title"],
                "url": content["url"],
                "labels": labels,
            }
        )
    return sorted(ready, key=lambda r: r["number"])


def last_forwarded(comments: list[dict]) -> str:
    """The newest comment timestamp already sent to the session."""
    found = ""
    for comment in comments:
        for match in FORWARDED_RE.finditer(comment["body"]):
            found = match.group(1)
    return found


def pending_comments(comments: list[dict]) -> list[dict]:
    """Human comments the session has not been given yet, oldest first.

    Forwarding is not the same as reading: the owner can write on the issue at any
    point, including while a pull request waits for review, and each of those is a
    message the agent has to receive exactly once.
    """
    since = last_forwarded(comments)
    return [
        comment
        for comment in comments
        if not comment["machine"] and comment["created_at"] > since
    ]


def last_branch(comments: list[dict]) -> str:
    found = ""
    for comment in comments:
        for match in BRANCH_RE.finditer(comment["body"]):
            found = match.group(1)
    return found


def pull_of(github, body: str, comments: list[dict]):
    """The pull request's repository and record, when the issue names where it opened."""
    repo = repo_of(body, comments)
    branch = last_branch(comments)
    if not (repo and branch):
        return None, None
    found = github._call(
        "GET", f"/repos/{repo}/pulls?state=all&head={repo.split('/')[0]}:{branch}"
    )
    if not found:
        return None, None
    return repo, found[0]


def pull_comments_for(github, body: str, comments: list[dict]) -> list[dict]:
    repo, pull = pull_of(github, body, comments)
    return github.pull_comments(repo, pull["number"]) if pull else []


def reaction_path(comment: dict) -> str:
    """The reactions endpoint for the collection the comment came from.

    GitHub splits issue/PR conversation comments from inline review comments;
    posting to the wrong collection is a 404, not a reaction on the same comment.
    """
    repo = comment.get("repo") or REPO
    ident = comment.get("id")
    if comment.get("path") or "#discussion_r" in (comment.get("url") or ""):
        return f"/repos/{repo}/pulls/comments/{ident}/reactions"
    return f"/repos/{repo}/issues/comments/{ident}/reactions"


def ack(github, comments: list[dict], failed: bool = False) -> int:
    """React 👀 to what the session received, 😕 to what the send could not deliver.

    A reaction is the only receipt GitHub offers; it is worth one call per
    comment, and a failed reaction must not fail the marker that prevents a
    duplicate send.
    """
    content = "confused" if failed else "eyes"
    acked = 0
    for comment in comments:
        if comment.get("id") is None:
            continue
        try:
            github._call("POST", reaction_path(comment), {"content": content})
        except SystemExit as exc:
            print(f"WARNING: reaction failed: {exc}", file=sys.stderr)
            continue
        acked += 1
    return acked


def waiting_surface(github, number: int, body: str, comments: list[dict]):
    """Where the ⏳ note belongs: the pull request if it exists, else the issue."""
    repo, pull = pull_of(github, body, comments)
    if pull:
        return repo, pull["number"]
    return REPO, number


def waiting(github, number: int, body: str, comments: list[dict]) -> str:
    """Post one ⏳ note while the agent is busy, and never a second one.

    GitHub has no hourglass reaction, so a queued comment says it in the thread.
    The marker makes the note machine-written: `inbox` never forwards it, and the
    next `forwarded` deletes it.
    """
    repo, target = waiting_surface(github, number, body, comments)
    path = f"/repos/{repo}/issues/{target}/comments?per_page=100"
    for comment in github._call("GET", path):
        if WAITING_MARKER in (comment.get("body") or ""):
            return comment.get("html_url", "")
    note = (
        "⏳ Waiting — the agent is finishing another turn. This comment is queued "
        f"and will be forwarded on the next tick.\n\n{WAITING_MARKER}"
    )
    created = github._call(
        "POST", f"/repos/{repo}/issues/{target}/comments", {"body": note}
    )
    return created.get("html_url", "")


def clear_waiting(github, number: int, body: str, comments: list[dict]) -> int:
    """Remove the ⏳ note once the comment is delivered, or the send failed."""
    repo, target = waiting_surface(github, number, body, comments)
    removed = 0
    for comment in github._call(
        "GET", f"/repos/{repo}/issues/{target}/comments?per_page=100"
    ):
        if WAITING_MARKER not in (comment.get("body") or ""):
            continue
        try:
            github._call("DELETE", f"/repos/{repo}/issues/comments/{comment['id']}")
        except SystemExit as exc:
            print(f"WARNING: waiting note not removed: {exc}", file=sys.stderr)
            continue
        removed += 1
    return removed


def merge_pending(
    issue_comments: list[dict], pull_comments: list[dict], since: str
) -> list[dict]:
    """One queue for a session, whatever surface the words arrived on.

    A conversation or review comment on the pull request is the owner writing to
    the agent just as much as a comment on the issue is; the agent should not have
    to learn the difference, and the tick should not have two bookkeeping paths.
    An id keeps a comment read from two collections out of the queue twice.
    """
    items = []
    seen = set()
    for comment in list(issue_comments) + list(pull_comments):
        if comment["machine"] or comment["created_at"] <= since:
            continue
        ident = comment.get("id")
        if ident is not None:
            if ident in seen:
                continue
            seen.add(ident)
        items.append(comment)
    return sorted(items, key=lambda c: c["created_at"])


def last_session(comments: list[dict]) -> str | None:
    found = None
    for comment in comments:
        for match in SESSION_RE.finditer(comment["body"]):
            found = match.group(1)
    return found


def help_state(comments: list[dict]) -> dict:
    """The newest help marker and the first human comment after it, if any."""
    marker_at = None
    marker_body = ""
    for comment in comments:
        if HELP_MARKER in comment["body"]:
            marker_at = comment["created_at"]
            marker_body = comment["body"]
    if marker_at is None:
        return {"asked": False, "answered": False, "question": ""}
    answer = None
    for comment in comments:
        if comment["created_at"] > marker_at and not comment["machine"]:
            answer = comment
            break
    return {
        "asked": True,
        "question": marker_body,
        "answered": answer is not None,
        "answer": answer,
    }


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    command, args = argv[0], argv[1:]
    github = GitHub(credential())

    if command == "board":
        print(json.dumps({"items": active_items(github.project()["items"])}, indent=2))
        return 0

    if command == "sync":
        issues = github._call("GET", f"/repos/{REPO}/issues?labels=agent&state=open&per_page=100")
        issues = [i for i in issues if "pull_request" not in i]
        project = github.project()
        missing = missing_on_board(issues, project["items"])
        added = []
        for issue in missing:
            created = github.graphql(
                ADD_ITEM, {"project": project["id"], "content": issue["node_id"]}
            )
            # A new item carries no Status until it is written; without this the
            # card sits outside every column.
            github.graphql(
                SET_STATUS,
                {
                    "project": project["id"],
                    "item": created["addProjectV2ItemById"]["item"]["id"],
                    "field": project["field"],
                    "option": project["options"]["Backlog"],
                },
            )
            notify_move(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "url": issue["url"],
                    "status": "Backlog",
                    "changed": True,
                }
            )
            added.append(issue["number"])
        github.invalidate()
        print(json.dumps({"added": added, "on_board": len(github.project()["items"])}))
        return 0

    if command == "ready":
        items = github.project()["items"]
        print(json.dumps({"ready": pick_ready(items)}, indent=2))
        return 0

    if command == "issue":
        number = int(args[0])
        item = github.item(number)
        content = item["content"]
        comments = github.comments(number)
        session = last_session(comments)
        print(
            json.dumps(
                {
                    "number": number,
                    "title": content["title"],
                    "url": content["url"],
                    "state": content["state"],
                    "status": (item.get("fieldValueByName") or {}).get("name"),
                    "labels": [n["name"] for n in content["labels"]["nodes"]],
                    "body": content.get("body", "")[:4000] if content.get("body") else None,
                    "repos": repos_of(content.get("body") or ""),
                    "session": session,
                    "session_url": session_url(session) or None,
                    "help": help_state(comments),
                    "comments": comments,
                },
                indent=2,
            )
        )
        return 0

    if command == "inbox":
        number = int(args[0])
        item = github.item(number)
        body = item["content"].get("body") or ""
        issue_comments = github.comments(number)
        branch = last_branch(issue_comments)
        since = last_forwarded(issue_comments)
        repo = repo_of(body, issue_comments)
        pull = None
        pull_comments = []
        if repo and branch:
            found = github._call(
                "GET", f"/repos/{repo}/pulls?state=all&head={repo.split('/')[0]}:{branch}"
            )
            if found:
                pull = found[0]
                pull_comments = github.pull_comments(repo, pull["number"])
        print(
            json.dumps(
                {
                    "number": number,
                    "repo": repo or None,
                    "branch": branch,
                    "since": since,
                    "pull": (
                        {"number": pull["number"], "url": pull["html_url"], "state": pull["state"]}
                        if pull
                        else None
                    ),
                    "items": merge_pending(issue_comments, pull_comments, since),
                },
                indent=2,
            )
        )
        return 0

    if command == "status":
        number = int(args[0])
        result = set_status(github, number, args[1])
        session = last_session(github.comments(number)) if result["changed"] else None
        result["notified"] = notify_move(result, session)
        print(json.dumps(result))
        return 0

    if command == "finish":
        number = int(args[0])
        state = ((github.item(number).get("content") or {}).get("state") or "").upper()
        if not may_finish(state):
            raise SystemExit(
                f"ERROR: issue #{number} is {state or 'unknown'}, not CLOSED; "
                "Done needs a closed issue, or the owner moving the card by hand"
            )
        result = set_status(github, number, "Done")
        session = last_session(github.comments(number)) if result["changed"] else None
        result["notified"] = notify_move(result, session)
        print(json.dumps(result))
        return 0

    if command == "notify":
        number = int(args[0])
        body = strip_markers(comment_text(args[1:], sys.stdin.read()))
        if not body:
            raise SystemExit("ERROR: notification body is empty")
        issue = github.item(number)["content"]
        session = last_session(github.comments(number))
        link = session_url(session) if session else ""
        text = f"{body}\n\n{issue['url']}"
        if link:
            text += f"\nSession: {link}"
        posted = slack(text)
        print(
            json.dumps(
                {
                    "number": number,
                    "posted": posted,
                    "url": issue["url"],
                    "session_url": link or None,
                }
            )
        )
        return 0

    if command == "comment":
        number = int(args[0])
        owner = "--owner" in args[1:]
        body = comment_text(args[1:], sys.stdin.read())
        if not body:
            raise SystemExit("ERROR: comment body is empty")
        body = comment_body(body, owner=owner)
        created = github._call("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": body})
        print(json.dumps({"number": number, "url": created.get("html_url", "")}))
        return 0

    if command == "start":
        number, session = int(args[0]), args[1]
        # The marker carries the newest comment so the tick does not replay the
        # issue's history into a session that already has the body.
        newest = max((c["created_at"] for c in github.comments(number)), default="")
        body = start_body(session, newest)
        created = github._call("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": body})
        print(json.dumps({"number": number, "session": session, "url": created.get("html_url", "")}))
        return 0

    if command == "forwarded":
        number, since = int(args[0]), args[1]
        failed = "--failed" in args[2:]
        body = github.item(number)["content"].get("body") or ""
        comments = github.comments(number)
        previous = last_forwarded(comments)
        pull_comments = pull_comments_for(github, body, comments)
        sent = [
            comment
            for comment in merge_pending(comments, pull_comments, previous)
            if comment["created_at"] <= since
        ]
        created = {}
        if not failed:
            marker = f"Forwarded to the session.\n\n<!-- taskboard:forwarded {since} -->"
            created = github._call(
                "POST", f"/repos/{REPO}/issues/{number}/comments", {"body": marker}
            )
        acked = ack(github, sent, failed=failed)
        cleared = clear_waiting(github, number, body, comments)
        print(
            json.dumps(
                {
                    "number": number,
                    "since": since,
                    "failed": failed,
                    "acked": acked,
                    "waiting_cleared": cleared,
                    "url": created.get("html_url", ""),
                }
            )
        )
        return 0

    if command == "waiting":
        number = int(args[0])
        body = github.item(number)["content"].get("body") or ""
        comments = github.comments(number)
        print(
            json.dumps(
                {
                    "number": number,
                    "url": waiting(github, number, body, comments),
                }
            )
        )
        return 0

    if command == "pr":
        repo, branch = full_repo(args[0]), args[1]
        query = f"/repos/{repo}/pulls?state=all&head={repo.split('/')[0]}:{branch}"
        pulls = github._call("GET", query)
        # A branch can carry an old merged pull request and a current one; the open
        # one is the state the tick acts on.
        pulls = sorted(pulls, key=lambda p: (p["state"] != "open", -p["number"]))
        print(
            json.dumps(
                {
                    "prs": [
                        {
                            "number": p["number"],
                            "url": p["html_url"],
                            "state": p["state"],
                            "merged": bool(p.get("merged_at")),
                            "draft": bool(p.get("draft")),
                            "title": p["title"],
                        }
                        for p in pulls
                    ]
                },
                indent=2,
            )
        )
        return 0

    if command == "review":
        repo, pull = full_repo(args[0]), int(args[1])
        github._call("POST", f"/repos/{repo}/pulls/{pull}/requested_reviewers", {"reviewers": [OWNER]})
        print(
            json.dumps(
                {
                    "repo": repo,
                    "pr": pull,
                    "url": f"https://github.com/{repo}/pull/{pull}",
                    "reviewer": OWNER,
                }
            )
        )
        return 0

    raise SystemExit(f"ERROR: unknown command {command}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
