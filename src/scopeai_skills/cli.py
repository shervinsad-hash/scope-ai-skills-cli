"""Command-line interface."""
import argparse
import json
import sys
from pathlib import Path
from .source import DEFAULT_REPO, GitHubSource, discover
from .workspace import install, status, load_lock
from . import feedback

def parser():
    p = argparse.ArgumentParser(prog="scopeai")
    p.add_argument("--repo", default=DEFAULT_REPO, help="Authoritative GitHub owner/repo")
    p.add_argument("--ref", default="main", help="Source ref, defaults to main")
    modules = p.add_subparsers(dest="module", required=True)
    skills = modules.add_parser("skills")
    actions = skills.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    for action in ("install", "update"):
        cmd = actions.add_parser(action)
        cmd.add_argument("skill", nargs="?" if action == "update" else None)
        cmd.add_argument("--workspace", type=Path, default=Path.cwd())
        cmd.add_argument("--apply", action="store_true", help="Explicitly write changes (preview otherwise)")
    cmd = actions.add_parser("status")
    cmd.add_argument("--workspace", type=Path, default=Path.cwd())
    fb = actions.add_parser("feedback")
    tasks = fb.add_subparsers(dest="feedback_action", required=True)
    cmd = tasks.add_parser("capture")
    cmd.add_argument("--workspace", type=Path, default=Path.cwd())
    for option in ("skill", "project", "session", "objective", "expected", "observed", "improvement"):
        cmd.add_argument("--" + option, required=True)
    cmd.add_argument("--result", choices=feedback.RESULTS, required=True)
    cmd.add_argument("--category", choices=feedback.CATEGORIES, required=True)
    cmd.add_argument("--evidence", action="append", default=[])
    cmd = tasks.add_parser("validate")
    cmd.add_argument("--workspace", type=Path, default=Path.cwd())
    cmd = tasks.add_parser("propose")
    cmd.add_argument("--workspace", type=Path, default=Path.cwd())
    cmd.add_argument("--skill")
    cmd.add_argument("--output", type=Path, required=True)
    return p

def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == "list":
            source = GitHubSource(args.repo, args.ref)
            rev = source.revision()
            for name, path in discover(source.tree(rev)).items():
                print(f"{name}\t{path}\t{rev[:12]}")
        elif args.action == "status":
            print(json.dumps(status(args.workspace), indent=2))
        elif args.action in ("install", "update"):
            source = GitHubSource(args.repo, args.ref)
            if args.action == "install":
                names = [args.skill]
            else:
                names = [args.skill] if args.skill else list(load_lock(args.workspace)["skills"])
                if not names:
                    raise ValueError("Nothing installed")
            print(json.dumps([install(args.workspace, name, source, apply=args.apply) for name in names], indent=2))
            if not args.apply:
                print("Preview only. Use --apply to write files.")
        elif args.action == "feedback":
            if args.feedback_action == "capture":
                record = feedback.capture(args.workspace, **{key: getattr(args, key) for key in ("skill", "project", "session", "objective", "result", "category", "expected", "observed", "improvement", "evidence")})
                print("Feedback recorded:", record["id"])
            elif args.feedback_action == "validate":
                problems = feedback.validate(feedback.read(args.workspace))
                if problems:
                    raise ValueError("; ".join(problems))
                print("Feedback contract valid")
            elif args.feedback_action == "propose":
                count = feedback.propose(args.workspace, args.output, args.skill)
                print(f"Review proposal created: {args.output} ({count} finding(s))")
        return 0
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
