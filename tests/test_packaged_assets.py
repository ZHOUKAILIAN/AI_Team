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


if __name__ == "__main__":
    unittest.main()
