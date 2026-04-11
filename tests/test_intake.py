import unittest


class IntakeTests(unittest.TestCase):
    def test_extracts_structured_acceptance_contract_for_figma_review(self) -> None:
        from ai_company.intake import parse_intake_message

        intake = parse_intake_message(
            (
                "执行这个需求：请使用 figma-restoration-review 处理这个页面。"
                "验收标准：1. page-root 递归检查所有可见子节点；"
                "2. 所有 geometry 偏差 <= 0.5px；"
                "3. 输出 deviation checklist。"
            )
        )

        self.assertEqual(intake.request, "请使用 figma-restoration-review 处理这个页面。验收标准：1. page-root 递归检查所有可见子节点；2. 所有 geometry 偏差 <= 0.5px；3. 输出 deviation checklist。")
        self.assertEqual(intake.contract.review_method, "figma-restoration-review")
        self.assertEqual(intake.contract.boundary, "page_root")
        self.assertTrue(intake.contract.recursive)
        self.assertEqual(intake.contract.tolerance_px, 0.5)
        self.assertEqual(
            intake.contract.required_dimensions,
            ["Structure", "Geometry", "Style", "Content", "State"],
        )
        self.assertIn("review_completion.json", intake.contract.required_artifacts)
        self.assertIn("runtime_screenshot", intake.contract.required_evidence)
        self.assertEqual(intake.contract.native_node_policy, "miniprogram")
        self.assertFalse(intake.contract.allow_host_environment_changes)
        self.assertEqual(len(intake.contract.acceptance_criteria), 3)

    def test_extracts_request_from_chinese_trigger(self) -> None:
        from ai_company.intake import extract_request_from_message

        request = extract_request_from_message("执行这个需求：做一个任务管理器")

        self.assertEqual(request, "做一个任务管理器")

    def test_extracts_request_from_workflow_trigger(self) -> None:
        from ai_company.intake import extract_request_from_message

        request = extract_request_from_message("按 AI Company 流程跑这个需求：支持 QA 反向纠偏")

        self.assertEqual(request, "支持 QA 反向纠偏")

    def test_extracts_request_from_english_trigger(self) -> None:
        from ai_company.intake import extract_request_from_message

        request = extract_request_from_message(
            "Run this requirement through the AI Company workflow: add audit trails"
        )

        self.assertEqual(request, "add audit trails")

    def test_returns_original_message_when_no_trigger_matches(self) -> None:
        from ai_company.intake import extract_request_from_message

        request = extract_request_from_message("做一个可追溯的 agent 流程")

        self.assertEqual(request, "做一个可追溯的 agent 流程")

    def test_explicit_host_environment_permission_is_detected(self) -> None:
        from ai_company.intake import parse_intake_message

        intake = parse_intake_message(
            "执行这个需求：做视觉验收。允许重启微信开发者工具并修改本机配置用于验收。"
        )

        self.assertTrue(intake.contract.allow_host_environment_changes)


if __name__ == "__main__":
    unittest.main()
