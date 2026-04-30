import unittest


class IntakeTests(unittest.TestCase):
    def test_extracts_structured_acceptance_contract_for_figma_review(self) -> None:
        from agent_team.intake import parse_intake_message

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

    def test_infers_figma_review_contract_from_generic_figma_1to1_request(self) -> None:
        from agent_team.intake import parse_intake_message

        intake = parse_intake_message(
            (
                "执行这个需求：在当前 worktree 完成 Figma 1:1 还原。"
                "验收时必须重新完整读取 Figma 节点 2411:6162、2455:12852，"
                "不允许只依赖开发阶段读取结果，并输出 deviation checklist。"
            )
        )

        self.assertEqual(intake.contract.review_method, "figma-restoration-review")
        self.assertEqual(intake.contract.boundary, "page_root")
        self.assertTrue(intake.contract.recursive)
        self.assertIn("deviation_checklist.md", intake.contract.required_artifacts)
        self.assertIn("review_completion.json", intake.contract.required_artifacts)
        self.assertIn("runtime_screenshot", intake.contract.required_evidence)
        self.assertIn("overlay_diff", intake.contract.required_evidence)
        self.assertIn("page_root_recursive_audit", intake.contract.required_evidence)

    def test_plain_figma_reference_does_not_force_review_contract(self) -> None:
        from agent_team.intake import parse_intake_message

        intake = parse_intake_message(
            "执行这个需求：根据 Figma 设计实现一个活动报名按钮，保持现有业务交互不变。"
        )

        self.assertEqual(intake.contract.review_method, "")
        self.assertEqual(intake.contract.required_artifacts, [])
        self.assertEqual(intake.contract.required_evidence, [])

    def test_figma_node_restoration_request_triggers_visual_review_contract(self) -> None:
        from agent_team.intake import parse_intake_message

        intake = parse_intake_message(
            (
                "用 Agent Team 修改：1. 运动统计周维度中，本周和上周不要显示时间段，只显示本周和上周。"
                "2. 还原 Figma 我的页统计相关节点 2411:3042、2411:3049、2411:3080，修正当前样式。"
            )
        )

        self.assertEqual(intake.contract.review_method, "figma-restoration-review")
        self.assertEqual(intake.contract.boundary, "page_root")
        self.assertTrue(intake.contract.recursive)
        self.assertIn("deviation_checklist.md", intake.contract.required_artifacts)
        self.assertIn("review_completion.json", intake.contract.required_artifacts)
        self.assertIn("runtime_screenshot", intake.contract.required_evidence)
        self.assertIn("overlay_diff", intake.contract.required_evidence)
        self.assertIn("page_root_recursive_audit", intake.contract.required_evidence)

    def test_extracts_request_from_chinese_trigger(self) -> None:
        from agent_team.intake import extract_request_from_message

        request = extract_request_from_message("执行这个需求：做一个任务管理器")

        self.assertEqual(request, "做一个任务管理器")

    def test_extracts_request_from_workflow_trigger(self) -> None:
        from agent_team.intake import extract_request_from_message

        request = extract_request_from_message("按 Agent Team 流程跑这个需求：支持 QA 反向纠偏")

        self.assertEqual(request, "支持 QA 反向纠偏")

    def test_extracts_request_from_english_trigger(self) -> None:
        from agent_team.intake import extract_request_from_message

        request = extract_request_from_message(
            "Run this requirement through the Agent Team workflow: add audit trails"
        )

        self.assertEqual(request, "add audit trails")

    def test_returns_original_message_when_no_trigger_matches(self) -> None:
        from agent_team.intake import extract_request_from_message

        request = extract_request_from_message("做一个可追溯的 agent 流程")

        self.assertEqual(request, "做一个可追溯的 agent 流程")

    def test_explicit_host_environment_permission_is_detected(self) -> None:
        from agent_team.intake import parse_intake_message

        intake = parse_intake_message(
            "执行这个需求：做视觉验收。允许重启微信开发者工具并修改本机配置用于验收。"
        )

        self.assertTrue(intake.contract.allow_host_environment_changes)


if __name__ == "__main__":
    unittest.main()
