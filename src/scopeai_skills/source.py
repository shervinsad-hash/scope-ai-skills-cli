"""Read-only, commit-pinned GitHub source; selected files only."""
import base64
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_REPO = "shervinsad-hash/scope-ai-knowledge"

class SourceError(RuntimeError):
    pass

def get_token():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        p = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None

class GitHubSource:
    def __init__(self, repository=DEFAULT_REPO, ref="main", token=None):
        parts = repository.split("/")
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        if len(parts) != 2 or not all(parts) or any(c not in chars for p in parts for c in p):
            raise ValueError("Repository must be owner/repo")
        self.repository, self.ref = repository, ref
        self.token = token if token is not None else get_token()

    def _get(self, suffix):
        url = f"https://api.github.com/repos/{self.repository}/{suffix}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "scopeai-skills-cli/0.1", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            message = exc.read(250).decode("utf-8", errors="replace")
            raise SourceError(f"GitHub HTTP {exc.code}: {message}; check authentication and repository access") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SourceError(f"GitHub request failed: {exc}") from exc

    def revision(self):
        return self._get("commits/" + urllib.parse.quote(self.ref, safe=""))["sha"]

    def tree(self, revision):
        obj = self._get(f"git/trees/{revision}?recursive=1")
        if obj.get("truncated"):
            raise SourceError("Truncated tree; refusing incomplete discovery")
        return {x["path"]: x["sha"] for x in obj["tree"] if x["type"] == "blob"}

    def read(self, sha):
        obj = self._get("git/blobs/" + urllib.parse.quote(sha, safe=""))
        if obj.get("encoding") != "base64":
            raise SourceError("Expected base64 Git blob")
        return base64.b64decode(obj["content"])

def discover(tree):
    skills = {}
    for path in sorted(tree):
        if path.startswith("skills/") and path.endswith("/SKILL.md"):
            name = path.split("/")[-2]
            if name in skills:
                raise SourceError(f"Ambiguous skill identifier: {name}")
            skills[name] = path
    return skills
