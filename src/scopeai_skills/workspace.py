"""Install selected skills and declared dependencies, not entire linked-document graphs."""
import hashlib
import json
import posixpath
import re
from importlib.resources import files as resource_files
from pathlib import Path, PurePosixPath
from .source import SourceError, discover

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
DECLARATION = "skill_dependencies.json"

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

def manifest_rules(skill, manifest=None):
    """Use the packaged manifest, or an explicit manifest in offline tests."""
    if manifest is None:
        manifest = json.loads(resource_files("scopeai_skills").joinpath(DECLARATION).read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != "1.0":
        raise SourceError("Unsupported skill dependency manifest")
    rules = manifest.get("skills", {}).get(skill)
    if rules is None:
        # Unknown skills are safely discoverable but have no inferred dependencies.
        return {"required": [], "optional": [], "references": []}, True
    for field in ("required", "optional", "references"):
        if not isinstance(rules.get(field, []), list) or any(not isinstance(p, str) for p in rules.get(field, [])):
            raise SourceError(f"Invalid {field} dependency declaration for {skill}")
    return rules, False

def safe_path(path):
    if not path or path.startswith("/") or "\\" in path or ".." in PurePosixPath(path).parts:
        raise SourceError(f"Unsafe dependency path: {path}")
    if str(PurePosixPath(path)) != path:
        raise SourceError(f"Noncanonical dependency path: {path}")
    return path

def linked_references(path, content):
    """Inspect only top-level skill links for diagnostics, never recursively install them."""
    found = set()
    for url in LINK_RE.findall(content.decode("utf-8", errors="replace")):
        target = url.split("#", 1)[0].split("?", 1)[0].strip()
        if not target or ":" in target or target.startswith(("/", "#")):
            continue
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        if resolved.startswith("../") or resolved == "..":
            found.add(("unsafe", resolved))
        elif resolved.endswith((".md", ".yaml", ".yml")):
            found.add(("reference", resolved))
    return found

def collect(source, skill, revision, tree, manifest=None):
    paths = discover(tree)
    if skill not in paths:
        raise SourceError(f"Unknown skill '{skill}'. Available: {', '.join(paths)}")
    rules, undeclared = manifest_rules(skill, manifest)
    entry = safe_path(paths[skill])
    files = {entry: source.read(tree[entry])}
    warnings = []
    if undeclared:
        warnings.append(f"No dependency declaration for {skill}; installing SKILL.md only")
    for kind in ("required", "optional", "references"):
        for name in rules.get(kind, []):
            name = safe_path(name)
            if name not in tree:
                if kind == "required":
                    raise SourceError(f"Missing required dependency for {skill}: {name}")
                warnings.append(f"Missing {kind} dependency: {name}")
                continue
            if kind != "references":
                files[name] = source.read(tree[name])
    # Linked Markdown documents are references, not dependency declarations.
    # Do not recurse: a broken link three documents away must not block a skill.
    for kind, name in sorted(linked_references(entry, files[entry])):
        if kind == "unsafe":
            warnings.append(f"Unsafe reference link (not followed): {name}")
        elif name not in tree:
            warnings.append(f"Broken reference link (not required): {name}")
    return files, entry, sorted(set(warnings))

def prepare(workspace, skill, source, revision=None, manifest=None):
    lock = load_lock(workspace)
    if lock["repository"] not in (None, source.repository):
        raise SourceError("Workspace points to a different source repository")
    rev = revision or source.revision()
    tree = source.tree(rev)
    files, entry, warnings = collect(source, skill, rev, tree, manifest)
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
    return rev, files, entry, warnings

def install(workspace, skill, source, apply=False, revision=None, manifest=None):
    rev, files, entry, warnings = prepare(workspace, skill, source, revision, manifest)
    result = {"skill": skill, "revision": rev, "files": sorted(files), "warnings": warnings, "applied": False}
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
