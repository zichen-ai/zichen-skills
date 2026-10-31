"""Synthetic infrastructure tests; never load the maintainer's installed Skills."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zichen-publish-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "work"
        self.root.mkdir()
        self.remote = self.base / "remote.git"
        release.git(self.base, "init", "--bare", str(self.remote))
        release.git(self.root, "init", "--initial-branch=main")
        release.git(self.root, "config", "user.name", "Infrastructure Test")
        release.git(self.root, "config", "user.email", "test@example.invalid")
        release.git(self.root, "config", "core.autocrlf", "false")
        release.git(self.root, "remote", "add", "origin", self.remote.as_posix())
        self.write("README.md", "# Synthetic publication fixture\n")
        self.write("LICENSE", "Synthetic test fixture.\n")
        self.write(".gitignore", ".local/\n")
        self.write("catalog.json", '{"schema_version":1,"skills":[]}\n')
        self.target_patch = patch.object(release, "configured_remote", return_value="https://github.com/example/fixture.git")
        self.target_patch.start()
        self.addCleanup(self.target_patch.stop)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def plan(self):
        return release.create_plan(self.root, sorted(release.changes(self.root)), "Publish synthetic fixture")

    def approved(self):
        self.plan()
        release.approve(self.root, "Synthetic test approval")

    def test_normal_publication_repeat_and_deletion(self):
        self.approved()
        first = release.publish(self.root)
        self.assertEqual(first["commit"], release.remote_head(self.root))
        self.assertEqual(first["commit"], release.publish(self.root)["commit"])
        self.write("docs/guide.md", "# Public guide\n")
        self.approved()
        release.publish(self.root)
        (self.root / "docs/guide.md").unlink()
        self.approved()
        release.publish(self.root)
        self.assertEqual(release.changes(self.root), set())
        self.assertEqual(release.git(self.root, "rev-list", "--count", "HEAD").stdout.strip(), "3")

    def test_unapproved_and_changed_after_approval_are_blocked(self):
        self.plan()
        with self.assertRaisesRegex(release.Stop, "not approved"):
            release.publish(self.root)
        release.approve(self.root, "Synthetic approval")
        self.write("README.md", "# Changed after review\n")
        with self.assertRaisesRegex(release.Stop, "changed after review"):
            release.publish(self.root)
        self.assertIsNone(release.head(self.root))
        self.assertIsNone(release.remote_head(self.root))

    def test_private_paths_secrets_and_orphans_are_blocked(self):
        for name in ["../outside.md", ".local/private.md", "skills/fixture/.env", "docs/../../escape.md"]:
            with self.subTest(name=name), self.assertRaises(release.Stop):
                release.safe_path(self.root, name)
        for text in ["ghp_" + "X" * 32, "C:" + "/" + "Users" + "/someone/private.txt"]:
            self.write("docs/unsafe.md", text)
            with self.assertRaisesRegex(release.Stop, "Possible"):
                release.check_repo(self.root)
        (self.root / "docs/unsafe.md").unlink()
        self.write("skills/orphan/SKILL.md", "unregistered fixture")
        with self.assertRaisesRegex(release.Stop, "Unregistered"):
            release.check_repo(self.root)

    def test_extra_changes_staging_and_remote_target_are_blocked(self):
        self.approved()
        self.write("docs/unreviewed.md", "Unreviewed public file")
        with self.assertRaisesRegex(release.Stop, "outside plan"):
            release.publish(self.root)
        (self.root / "docs/unreviewed.md").unlink()
        release.git(self.root, "add", "--", "README.md")
        with self.assertRaisesRegex(release.Stop, "staged changes"):
            release.publish(self.root)
        release.git(self.root, "rm", "--cached", "--", "README.md")
        with patch.object(release, "configured_remote", return_value="https://github.com/example/wrong.git"):
            with self.assertRaisesRegex(release.Stop, "target changed"):
                release.publish(self.root)
        with patch.object(release, "remote_head", return_value="a" * 40):
            with self.assertRaisesRegex(release.Stop, "Remote changed"):
                release.publish(self.root)
        self.assertIsNone(release.head(self.root))

    def test_push_failure_retries_the_same_commit(self):
        self.approved()
        original = release.git

        def fail_push(root, *args, **kwargs):
            if args and args[0] == "push":
                raise release.Stop("Synthetic network failure")
            return original(root, *args, **kwargs)

        with patch.object(release, "git", side_effect=fail_push):
            with self.assertRaisesRegex(release.Stop, "network failure"):
                release.publish(self.root)
        committed = release.head(self.root)
        self.assertIsNotNone(committed)
        self.assertIsNone(release.remote_head(self.root))
        self.assertEqual(release.publish(self.root)["commit"], committed)
        self.assertEqual(release.git(self.root, "rev-list", "--count", "HEAD").stdout.strip(), "1")

    def test_deleted_remote_branch_requires_review(self):
        self.approved()
        first = release.publish(self.root)
        self.write("docs/guide.md", "# Reviewed update\n")
        self.approved()
        with patch.object(release, "remote_head", return_value=None):
            with self.assertRaisesRegex(release.Stop, "Remote changed"):
                release.publish(self.root)
        self.assertEqual(release.head(self.root), first["commit"])

    def test_catalog_registered_package_and_missing_resource(self):
        entry = {"name": "fixture", "path": "skills/fixture", "version": "0.1.0",
                 "summary": "Synthetic infrastructure fixture", "license": "Synthetic test only",
                 "validation": {"level": "held-out-regression", "summary": "Synthetic parser test, not a real Skill evaluation"}}
        self.write("catalog.json", json.dumps({"schema_version": 1, "skills": [entry]}))
        self.write("skills/fixture/SKILL.md", "---\nname: fixture\ndescription: Synthetic parser fixture\n---\nRead [guide](references/guide.md).\n")
        self.write("skills/fixture/README.md", "\n".join("## " + s + "\nSynthetic test." for s in ["用途", "输入", "输出", "使用示例", "依赖", "边界", "验证", "许可"]))
        self.write("skills/fixture/LICENSE", "Synthetic test only.")
        with self.assertRaisesRegex(release.Stop, "Missing/outside"):
            release.check_repo(self.root)
        self.write("skills/fixture/references/guide.md", "Synthetic reference.")
        self.assertEqual(release.check_repo(self.root)["skills"], 1)
        entry["validation"]["level"] = "structure"
        self.write("catalog.json", json.dumps({"schema_version": 1, "skills": [entry]}))
        with self.assertRaisesRegex(release.Stop, "held-out/regression"):
            release.check_repo(self.root)


if __name__ == "__main__":
    unittest.main()
