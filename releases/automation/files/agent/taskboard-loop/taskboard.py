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
  taskboard.py ready
  taskboard.py issue <n>
  taskboard.py inbox <n>              (comments the session has not been given)
  taskboard.py status <n> <Status>
  taskboard.py comment <n>            (body on stdin)
  taskboard.py start <n> <session>    (records the session on the issue)
  taskboard.py forwarded <n> <since>  (records that comments up to <since> were sent)
  taskboard.py pr <repo> <branch>
  taskboard.py review <repo> <pr>
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
MARKER = "<!-- taskboard:"
HELP_MARKER = "<!-- taskboard:help -->"
AGENT_MARKER = "<!-- taskboard:agent -->"
SESSION_RE = re.compile(r"<!-- taskboard:session (\S+) -->")
FORWARDED_RE = re.compile(r"<!-- taskboard:forwarded (\S+) -->")
BRANCH_RE = re.compile(r"Branch `([^`]+)`")
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
                "author": (c.get("user") or {}).get("login", ""),
                "created_at": c.get("created_at", ""),
                "body": (c.get("body") or "")[:MAX_COMMENT_CHARS],
                "url": c.get("html_url", ""),
                "machine": MARKER in (c.get("body") or ""),
            }
            for c in raw
        ]


REPO_HEADING = re.compile(r"^##\s*Repo\s*$", re.IGNORECASE | re.MULTILINE)
BACKTICK = re.compile(r"`([^`]+)`")


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
        {"number": i["number"], "node_id": i["node_id"], "title": i["title"]}
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


def merge_pending(
    issue_comments: list[dict], review_comments: list[dict], since: str
) -> list[dict]:
    """One queue for a session, whatever surface the words arrived on.

    A review comment on the pull request is the owner writing to the agent just as
    much as a comment on the issue is; the agent should not have to learn the
    difference, and the tick should not have two bookkeeping paths.
    """
    items = [
        comment
        for comment in list(issue_comments) + list(review_comments)
        if not comment["machine"] and comment["created_at"] > since
    ]
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
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: GITHUB_PERSONAL_ACCESS_TOKEN is not set")
    if not argv:
        raise SystemExit(__doc__)
    command, args = argv[0], argv[1:]
    github = GitHub(token)

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
                    "session": last_session(comments),
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
        repos = repos_of(body)
        branch = last_branch(issue_comments)
        since = last_forwarded(issue_comments)
        repo = f"{ORG}/{repos[0]}" if len(repos) == 1 else None
        pull = None
        review_comments = []
        if repo and branch:
            found = github._call(
                "GET", f"/repos/{repo}/pulls?state=all&head={repo.split('/')[0]}:{branch}"
            )
            if found:
                pull = found[0]
                review_comments = [
                    {
                        "id": c.get("id"),
                        "author": (c.get("user") or {}).get("login", ""),
                        "created_at": c.get("created_at", ""),
                        "body": (c.get("body") or "")[:MAX_COMMENT_CHARS],
                        "url": c.get("html_url", ""),
                        "machine": MARKER in (c.get("body") or ""),
                        "path": c.get("path"),
                        "line": c.get("line") or c.get("original_line"),
                    }
                    for c in github._call(
                        "GET", f"/repos/{repo}/pulls/{found[0]['number']}/comments?per_page=100"
                    )
                ]
        print(
            json.dumps(
                {
                    "number": number,
                    "repo": repo,
                    "branch": branch,
                    "since": since,
                    "pull": (
                        {"number": pull["number"], "url": pull["html_url"], "state": pull["state"]}
                        if pull
                        else None
                    ),
                    "items": merge_pending(issue_comments, review_comments, since),
                },
                indent=2,
            )
        )
        return 0

    if command == "status":
        number, wanted = int(args[0]), args[1]
        project = github.project()
        if wanted not in project["options"]:
            raise SystemExit(f"ERROR: unknown status {wanted}")
        item = github.item(number)
        previous = (item.get("fieldValueByName") or {}).get("name")
        if previous == wanted:
            print(json.dumps({"number": number, "status": wanted, "changed": False}))
            return 0
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
        print(json.dumps({"number": number, "previous": previous, "status": wanted, "changed": True}))
        return 0

    if command == "comment":
        number = int(args[0])
        body = sys.stdin.read().strip()
        if not body:
            raise SystemExit("ERROR: comment body is empty")
        if MARKER not in body:
            body = f"{body}\n\n{AGENT_MARKER}"
        created = github._call("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": body})
        print(json.dumps({"number": number, "url": created.get("html_url", "")}))
        return 0

    if command == "start":
        number, session = int(args[0]), args[1]
        # The marker carries the newest comment so the tick does not replay the
        # issue's history into a session that already has the body.
        newest = max((c["created_at"] for c in github.comments(number)), default="")
        body = (
            f"Started session `{session}`.\n\n"
            f"<!-- taskboard:session {session} -->\n"
            f"<!-- taskboard:forwarded {newest} -->"
        )
        created = github._call("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": body})
        print(json.dumps({"number": number, "session": session, "url": created.get("html_url", "")}))
        return 0

    if command == "forwarded":
        number, since = int(args[0]), args[1]
        body = f"Forwarded to the session.\n\n<!-- taskboard:forwarded {since} -->"
        created = github._call("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": body})
        print(json.dumps({"number": number, "since": since, "url": created.get("html_url", "")}))
        return 0

    if command == "pr":
        repo, branch = args[0], args[1]
        query = f"/repos/{repo}/pulls?state=all&head={repo.split('/')[0]}:{branch}"
        pulls = github._call("GET", query)
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
        repo, pull = args[0], int(args[1])
        github._call("POST", f"/repos/{repo}/pulls/{pull}/requested_reviewers", {"reviewers": [OWNER]})
        print(json.dumps({"repo": repo, "pr": pull, "reviewer": OWNER}))
        return 0

    raise SystemExit(f"ERROR: unknown command {command}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
