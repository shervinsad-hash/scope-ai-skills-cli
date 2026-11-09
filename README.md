# Scope AI Skills CLI

A **project-independent** tool to discover, install, track and improve reusable Scope AI skills. The central skill definitions stay in `shervinsad-hash/scope-ai-knowledge` (private); this repository holds the CLI only.

## Install

Requires Python 3.10+ and GitHub read permission for the central repository.

```powershell
python -m pip install -e .
gh auth login
```

The GitHub API is accessed read-only. Authentication uses `GH_TOKEN`, `GITHUB_TOKEN`, or `gh auth token`. Credentials are not written to the workspace.

## Use in any project

```powershell
scopeai skills list
scopeai skills install implementation-work-package --workspace C:\Projects\AnyProject
scopeai skills install implementation-work-package --workspace C:\Projects\AnyProject --apply
scopeai skills status --workspace C:\Projects\AnyProject
scopeai skills update --workspace C:\Projects\AnyProject
scopeai skills update --workspace C:\Projects\AnyProject --apply
```

The CLI retrieves the selected skill and its transitively linked local Markdown/YAML documents, not the entire knowledge repository or application code. Installation is pinned to a Git commit, keeping original relative paths under `<workspace>/.scopeai/knowledge/`. The `<workspace>/.scopeai/skills.lock.json` lock records source revisions and file hashes.

Installation/update defaults to preview. `--apply` is required to write files. Unmanaged, locally modified or incompatible shared dependencies are never silently overwritten. This initial version does not auto-register skills with VS Code agents; direct them to the installed `SKILL.md`.

## Session-end feedback

`contracts/skill-feedback.schema.json` is the versioned feedback contract. The built-in validator validates required fields, types and enumerations; it is not a complete JSON Schema engine.

```powershell
scopeai skills feedback capture --workspace C:\Projects\AnyProject `
  --skill implementation-work-package --project Example --session session-001 `
  --objective "Prepare a bounded implementation package" --result partial `
  --category completeness --expected "Handoff includes rollback" `
  --observed "Rollback missing" --improvement "Add rollback instructions" `
  --evidence "work-packages/WP-01.md"

scopeai skills feedback validate --workspace C:\Projects\AnyProject

scopeai skills feedback propose --workspace C:\Projects\AnyProject `
  --output C:\Reviews\skills-feedback.md
```

Capture appends to `<workspace>/.scopeai/feedback/skill-feedback.json` using the validated contract, preserving earlier findings. The CLI does **not** automatically read coding-agent transcripts. Provide the observed behavior explicitly. Avoid secrets and confidential client information in feedback.

Proposal output is a review-only Markdown document; it does not modify or submit changes to the central skills library. Improved skills require a separately approved PR to `scope-ai-knowledge`, followed by an explicit project update.

## Developer checks

```powershell
python -m unittest discover -s tests -v
```

## Limitations

- No automated skill authoring, central repository writes, PR creation or agent execution.
- Workspace skill revision is pinned by commit; qualification remains manual-pilot-only unless separately established.
- A shared dependency version conflict must be resolved manually in this MVP.
- For multi-skill updates, review all packages and versions before using `--apply`.
