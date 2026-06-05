import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PackagedAssetTests(unittest.TestCase):
    def test_copy_packaged_role_asset_tree(self) -> None:
        from agent_team.packaged_assets import copy_packaged_tree

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "product-definition-role"
            written = copy_packaged_tree(("roles", "ProductDefinition"), target)

            self.assertTrue((target / "contract.md").exists())
            self.assertTrue((target / "context.md").exists())
            self.assertTrue(any(path.name == "context.md" for path in written))

    def test_ops_role_assets_are_removed(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        self.assertFalse((repo_root / "Ops").exists())
        self.assertFalse((repo_root / "agent_team" / "assets" / "roles" / "Ops").exists())

    def test_role_contracts_document_backend_verification_and_partial_statuses(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        roles_dir = repo_root / "agent_team" / "assets" / "roles"

        route_contract = (roles_dir / "Route" / "contract.md").read_text()
        verification_contract = (roles_dir / "Verification" / "contract.md").read_text()
        governance_contract = (roles_dir / "GovernanceReview" / "contract.md").read_text()
        acceptance_contract = (roles_dir / "Acceptance" / "contract.md").read_text()

        self.assertIn("verification_profile", route_contract)
        self.assertIn("backend_api_db", route_contract)
        self.assertIn("verification_conclusion: needs_verification", verification_contract)
        self.assertIn("backend_api_db", verification_contract)
        self.assertIn("still needs verification", governance_contract)
        self.assertIn("needs_verification", acceptance_contract)


if __name__ == "__main__":
    unittest.main()
