"""Versioned, append-only session feedback ledger and review-only proposal."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .workspace import load_lock, root

CATEGORIES = ("completeness", "correctness", "clarity", "security", "cost", "performance", "usability", "other")
RESULTS = ("success", "partial", "failure", "not-tested")

def feedback_file(workspace):
    return root(workspace) / "feedback" / "skill-feedback.json"

def read(workspace):
    path = feedback_file(workspace)
    if not path.exists():
        return {"contract_version": "1.0", "records": []}
    return json.loads(path.read_text(encoding="utf-8"))

def validate(obj):
    if not isinstance(obj, dict) or obj.get("contract_version") != "1.0" or not isinstance(obj.get("records"), list):
        return ["Expected contract_version 1.0 and a records array"]
    issues = []
    seen = set()
    required = ("id", "recorded_at", "skill_id", "skill_revision", "project", "session_id", "objective", "result", "category", "expected", "observed", "improvement")
    for index, rec in enumerate(obj["records"]):
        if not isinstance(rec, dict):
            issues.append(f"Record {index} not an object")
            continue
        for field in required:
            if not isinstance(rec.get(field), str) or not rec[field].strip():
                issues.append(f"Record {index}: missing {field}")
        if rec.get("result") not in RESULTS:
            issues.append(f"Record {index}: unsupported result")
        if rec.get("category") not in CATEGORIES:
            issues.append(f"Record {index}: unsupported category")
        if not isinstance(rec.get("evidence_refs"), list) or any(not isinstance(x, str) for x in rec.get("evidence_refs", [])):
            issues.append(f"Record {index}: evidence_refs must be string list")
        if rec.get("id") in seen:
            issues.append(f"Record {index}: duplicate ID")
        seen.add(rec.get("id"))
        try:
            datetime.fromisoformat(rec.get("recorded_at", ""))
        except (TypeError, ValueError):
            issues.append(f"Record {index}: invalid recorded_at")
    return issues

def capture(workspace, **fields):
    lock = load_lock(workspace)
    skill = fields.pop("skill")
    if skill not in lock["skills"]:
        raise ValueError(f"Skill '{skill}' not installed")
    obj = read(workspace)
    rec = {
        "id": str(uuid.uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "skill_id": skill,
        "skill_revision": lock["skills"][skill]["revision"],
        "project": fields["project"],
        "session_id": fields["session"],
        "objective": fields["objective"],
        "result": fields["result"],
        "category": fields["category"],
        "expected": fields["expected"],
        "observed": fields["observed"],
        "evidence_refs": fields.get("evidence", []),
        "improvement": fields["improvement"],
        "review_status": "proposed"
    }
    obj["records"].append(rec)
    issues = validate(obj)
    if issues:
        raise ValueError("; ".join(issues))
    path = feedback_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec

def propose(workspace, output, skill=None):
    obj = read(workspace)
    problems = validate(obj)
    if problems:
        raise ValueError("; ".join(problems))
    records = [r for r in obj["records"] if not skill or r["skill_id"] == skill]
    if not records:
        raise ValueError("No matching feedback")
    lines = ["# Scope AI Skill Improvement Proposal", "", "Review only: no central skills are changed.", ""]
    for rec in records:
        lines += [f"## {rec['skill_id']} — {rec['id']}", "",
                  f"- Revision: `{rec['skill_revision']}`", f"- Project: {rec['project']}",
                  f"- Session: {rec['session_id']}", f"- Outcome: {rec['result']}",
                  f"- Objective: {rec['objective']}", f"- Expected: {rec['expected']}",
                  f"- Observed: {rec['observed']}", f"- Category: {rec['category']}",
                  f"- Proposed improvement: {rec['improvement']}", "- Evidence:"]
        lines += [f"  - {ref}" for ref in rec["evidence_refs"]] or ["  - Not supplied (unverified)"]
        lines.append("")
    dest = Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines), encoding="utf-8")
    return len(records)
