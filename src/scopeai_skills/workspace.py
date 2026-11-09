"""Install selected skills and linked docs while preserving repository-relative paths."""
import hashlib
import json
import posixpath
import re
from pathlib import Path, PurePosixPath
from .source import SourceError, discover

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def root(workspace):
    return Path(workspace).resolve() / ".scopeai"

def load_lock(workspace):
    path = root(workspace) / "skills.lock.json"
    if not path.exists():
        return {"lock_version": 1, "repository": None, "skills": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("lock_version") != 1 or not isinstance(data.get("skills"), dict):
        raise ValueError("Unsupported lock file")
    return data

def dependencies(path, content, tree):
    found = set()
    for url in LINK_RE.findall(content.decode("utf-8", errors="replace")):
        target = url.split("#", 1)[0].split("?", 1)[0].strip()
        if not target or ":" in target or target.startswith(("/", "#")):
            continue
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        if resolved.startswith("../") or resolved == "..":
            raise SourceError(f"Linked reference escapes repository: {path} -> {url}")
        if resolved in tree and resolved.endswith((".md", ".yaml", ".yml")):
            found.add(resolved)
        elif resolved.endswith((".md", ".yaml", ".yml")):
            raise SourceError(f"Missing linked reference: {path} -> {resolved}")
    return found

def collect(source, skill, revision, tree):
    paths = discover(tree)
    if skill not in paths:
        raise SourceError(f"Unknown skill '{skill}'. Available: {', '.join(paths)}")
    queue = [paths[skill]]
    files = {}
    while queue:
        name = queue.pop()
        if name in files:
            continue
        if name not in tree or name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts:
            raise SourceError(f"Unsafe or missing file: {name}")
        data = source.read(tree[name])
        files[name] = data
        queue.extend(dependencies(name, data, tree) - files.keys())
    return files, paths[skill]

def prepare(workspace, skill, source, revision=None):
    lock = load_lock(workspace)
    if lock["repository"] not in (None, source.repository):
        raise SourceError("Workspace points to a different source repository")
    rev = revision or source.revision()
    tree = source.tree(rev)
    files, entry = collect(source, skill, rev, tree)
    for path, data in files.items():
        dest = root(workspace) / "knowledge" / Path(*PurePosixPath(path).parts)
        if dest.is_symlink():
            raise SourceError(f"Symlink target refused: {dest}")
        if not dest.exists():
            continue
        references = [(name, item["files"][path]) for name, item in lock["skills"].items() if path in item.get("files", {})]
        if any(name != skill and value != digest(data) for name, value in references):
            raise SourceError(f"Shared dependency version conflict: {path}")
        previous = next((value for _, value in references), None)
        if previous is None or digest(dest.read_bytes()) != previous:
            raise SourceError(f"Unmanaged or locally modified file: {dest}")
    return rev, files, entry

def install(workspace, skill, source, apply=False, revision=None):
    rev, files, entry = prepare(workspace, skill, source, revision)
    result = {"skill": skill, "revision": rev, "files": sorted(files), "applied": False}
    if not apply:
        return result
    base = root(workspace)
    for path, data in files.items():
        destination = base / "knowledge" / Path(*PurePosixPath(path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    lock = load_lock(workspace)
    lock["repository"] = source.repository
    lock["skills"][skill] = {"revision": rev, "entry": entry, "files": {p: digest(data) for p, data in files.items()}}
    base.mkdir(parents=True, exist_ok=True)
    (base / "skills.lock.json").write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["applied"] = True
    return result

def status(workspace):
    state = load_lock(workspace)
    base = root(workspace) / "knowledge"
    output = []
    for name, item in sorted(state["skills"].items()):
        altered = []
        for path, expected in item.get("files", {}).items():
            dest = base / Path(*PurePosixPath(path).parts)
            if not dest.is_file() or digest(dest.read_bytes()) != expected:
                altered.append(path)
        output.append({"skill": name, "revision": item["revision"], "integrity": "modified" if altered else "ok", "altered": altered})
    return output
