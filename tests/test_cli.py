"""Unit tests: offline fake source, no application code executed."""
import tempfile
import unittest
from pathlib import Path

from scopeai_skills.source import discover, SourceError
from scopeai_skills.workspace import install, load_lock, status
from scopeai_skills import feedback


class FakeSource:
    repository = "example/knowledge"
    def __init__(self):
        self.files = {
            "skills/engineering/implementation-work-package/SKILL.md": b"# Skill\n[contract](../../contracts/work.yaml)\n",
            "skills/delivery/implementation-planning/SKILL.md": b"# Plan\n[contract](../../contracts/work.yaml)\n",
            "skills/contracts/work.yaml": b"version: 1\n",
        }
        self.commit = "a" * 40

    def revision(self):
        return self.commit

    def tree(self, revision):
        return {path: path for path in self.files}

    def read(self, sha):
        return self.files[sha]


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        self.source = FakeSource()

    def test_discovery(self):
        self.assertEqual(set(discover(self.source.tree("any"))),
                         {"implementation-work-package", "implementation-planning"})

    def test_preview_then_install(self):
        proposed = install(self.workspace, "implementation-work-package", self.source)
        self.assertFalse(proposed["applied"])
        self.assertEqual(len(proposed["files"]), 2)
        self.assertFalse((self.workspace / ".scopeai").exists())
        install(self.workspace, "implementation-work-package", self.source, apply=True)
        self.assertEqual(status(self.workspace)[0]["integrity"], "ok")
        self.assertEqual(len(load_lock(self.workspace)["skills"]["implementation-work-package"]["files"]), 2)

    def test_append_feedback_and_prepare_proposal(self):
        install(self.workspace, "implementation-work-package", self.source, apply=True)
        rec = feedback.capture(self.workspace, skill="implementation-work-package", project="Example",
                               session="s1", objective="Prepare work", result="partial",
                               category="completeness", expected="Rollback guidance",
                               observed="Missing rollback", improvement="Add rollback",
                               evidence=["WP-01"])
        self.assertEqual(rec["skill_revision"], "a" * 40)
        self.assertFalse(feedback.validate(feedback.read(self.workspace)))
        output = self.workspace / "proposal.md"
        self.assertEqual(feedback.propose(self.workspace, output), 1)
        self.assertIn("Add rollback", output.read_text())

    def test_local_edit_blocks_update(self):
        install(self.workspace, "implementation-work-package", self.source, apply=True)
        file = self.workspace / ".scopeai/knowledge/skills/contracts/work.yaml"
        file.write_text("locally changed")
        self.assertEqual(status(self.workspace)[0]["integrity"], "modified")
        with self.assertRaises(SourceError):
            install(self.workspace, "implementation-work-package", self.source, apply=True)

    def test_missing_reference_fails(self):
        del self.source.files["skills/contracts/work.yaml"]
        with self.assertRaises(SourceError):
            install(self.workspace, "implementation-work-package", self.source)

    def test_shared_dependency_conflict_fails(self):
        install(self.workspace, "implementation-work-package", self.source, apply=True)
        self.source.files["skills/contracts/work.yaml"] = b"version: 2\n"
        self.source.commit = "b" * 40
        with self.assertRaises(SourceError):
            install(self.workspace, "implementation-planning", self.source, apply=True)

    def test_two_skills_share_unchanged_contract(self):
        install(self.workspace, "implementation-work-package", self.source, apply=True)
        install(self.workspace, "implementation-planning", self.source, apply=True)
        self.assertEqual(len(status(self.workspace)), 2)

    def test_invalid_feedback(self):
        self.assertTrue(feedback.validate({"contract_version": "1.0", "records": [{"id": "bad"}]}))


if __name__ == "__main__":
    unittest.main()
