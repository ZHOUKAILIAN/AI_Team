import unittest
from pathlib import Path


class PolicyTests(unittest.TestCase):
    def test_default_acceptance_policy_requires_visual_evidence_for_page_root_parity(self) -> None:
        from agent_team.acceptance_policy import load_acceptance_policy

        policy = load_acceptance_policy()
        profile = policy["evidence_profiles"]["page_root_visual_parity"]

        self.assertEqual(
            profile["required_evidence"],
            ["runtime_screenshot", "overlay_diff", "page_root_recursive_audit"],
        )
        self.assertIn("0.5px", profile["completion_signal"])

    def test_default_acceptance_policy_excludes_wechat_native_capsule_from_business_diff(self) -> None:
        from agent_team.acceptance_policy import load_acceptance_policy

        policy = load_acceptance_policy()
        exclusion = policy["native_node_exclusions"][0]

        self.assertEqual(exclusion["platform"], "miniprogram")
        self.assertEqual(exclusion["node_type"], "wechat_native_capsule")
        self.assertEqual(exclusion["rule"], "exclude_from_business_diff")
        self.assertEqual(exclusion["verification_focus"], "safe_area_avoidance")


if __name__ == "__main__":
    unittest.main()
