import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PackagedAssetTests(unittest.TestCase):
    def test_copy_packaged_codex_skill_tree(self) -> None:
        from ai_company.packaged_assets import copy_packaged_tree

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "installed-skill"
            written = copy_packaged_tree(("codex_skill", "ai-company-workflow"), target)

            self.assertTrue((target / "SKILL.md").exists())
            self.assertTrue((target / "scripts" / "company-run.sh").exists())
            self.assertTrue(any(path.name == "company-run.sh" for path in written))


if __name__ == "__main__":
    unittest.main()
