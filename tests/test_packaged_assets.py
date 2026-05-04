import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PackagedAssetTests(unittest.TestCase):
    def test_copy_packaged_role_asset_tree(self) -> None:
        from agent_team.packaged_assets import copy_packaged_tree

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "product-role"
            written = copy_packaged_tree(("roles", "Product"), target)

            self.assertTrue((target / "SKILL.md").exists())
            self.assertTrue((target / "context.md").exists())
            self.assertTrue((target / "memory.md").exists())
            self.assertTrue(any(path.name == "context.md" for path in written))

    def test_ops_role_assets_are_removed(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        self.assertFalse((repo_root / "Ops").exists())
        self.assertFalse((repo_root / "agent_team" / "assets" / "roles" / "Ops").exists())


if __name__ == "__main__":
    unittest.main()
