import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PackagedAssetTests(unittest.TestCase):
    def test_copy_packaged_role_assets(self) -> None:
        from agent_team.packaged_assets import copy_packaged_tree

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "installed-roles"
            written = copy_packaged_tree(("roles", "Dev"), target)

            self.assertTrue((target / "SKILL.md").exists())
            self.assertTrue(any(path.name == "SKILL.md" for path in written))

    def test_resolve_web_dist_prefers_explicit_path(self) -> None:
        from agent_team.web_assets import resolve_web_dist

        with TemporaryDirectory() as temp_dir:
            explicit = Path(temp_dir) / "dist"
            explicit.mkdir()

            self.assertEqual(resolve_web_dist(explicit), explicit)

    def test_copy_web_dist_copies_react_build(self) -> None:
        from agent_team.web_assets import copy_web_dist

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            (source / "assets").mkdir(parents=True)
            (source / "index.html").write_text("<div id='root'></div>")
            (source / "assets" / "app.js").write_text("console.log('ok')")

            written = copy_web_dist(source=source, destination=target)

            self.assertTrue((target / "index.html").exists())
            self.assertTrue((target / "assets" / "app.js").exists())
            self.assertTrue(any(path.name == "app.js" for path in written))


if __name__ == "__main__":
    unittest.main()
