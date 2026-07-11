import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowConfigTest(unittest.TestCase):
    def test_daily_workflow_tests_before_production_and_serializes_runs(self):
        workflow = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:", workflow)
        self.assertIn("group: daily-english", workflow)
        self.assertIn("pip install -r requirements.txt", workflow)
        self.assertNotIn("pip install openai || true", workflow)
        test_position = workflow.index("python -m unittest discover -v")
        production_position = workflow.index("python daily.py --source ai")
        self.assertLess(test_position, production_position)
        self.assertIn("python -m compileall -q *.py scf/index.py", workflow)
        self.assertIn("git add articles docs state", workflow)
        self.assertNotIn("git pull --rebase origin main 2>/dev/null || true", workflow)

    def test_dependencies_are_exactly_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        packages = [line for line in requirements if line and not line.startswith("#")]
        self.assertIn("openai==2.45.0", packages)
        self.assertIn("anthropic==0.116.0", packages)
        self.assertTrue(all("==" in line for line in packages))

    def test_local_secrets_and_scf_packages_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for marker in ("secret.env", "secret.txt", "__pycache__/", "*.pyc", "scf/*.zip"):
            self.assertIn(marker, ignored)

    def test_deployment_docs_cover_auth_throttling_rotation_and_recovery(self):
        docs = ((ROOT / "SCF_DEPLOY.md").read_text(encoding="utf-8") + "\n" +
                (ROOT / "README.md").read_text(encoding="utf-8"))
        for marker in (
            "APP_ACCESS_KEY",
            "ALLOW_ORIGIN",
            "API 网关",
            "轮换",
            "state/",
            "飞书推送失败",
            "浏览器内置语音",
        ):
            self.assertIn(marker, docs)


if __name__ == "__main__":
    unittest.main()
