import unittest


class IntakeTests(unittest.TestCase):
    def test_extract_request_only_strips_outer_whitespace(self) -> None:
        from agent_team.intake import extract_request_from_message

        request = extract_request_from_message("\n  修复登录按钮样式  \t")

        self.assertEqual(request, "修复登录按钮样式")

    def test_does_not_strip_natural_language_trigger_prefixes(self) -> None:
        from agent_team.intake import extract_request_from_message

        request = extract_request_from_message("执行这个需求：做一个任务管理器")

        self.assertEqual(request, "执行这个需求：做一个任务管理器")

    def test_parse_intake_preserves_raw_message_and_normalized_request(self) -> None:
        from agent_team.intake import parse_intake_message

        raw_message = "\n  Run this requirement through the Agent Team workflow: add audit trails  "

        intake = parse_intake_message(raw_message)

        self.assertEqual(
            intake.request,
            "Run this requirement through the Agent Team workflow: add audit trails",
        )
        self.assertEqual(intake.raw_message, raw_message)

    def test_figma_review_text_does_not_implicitly_create_acceptance_contract(self) -> None:
        from agent_team.intake import parse_intake_message

        intake = parse_intake_message(
            (
                "在当前 worktree 完成 Figma 1:1 还原。"
                "验收时必须重新完整读取 Figma 节点 2411:6162、2455:12852，"
                "输出 deviation checklist。"
            )
        )

        self.assertFalse(intake.contract.has_constraints())
        self.assertEqual(intake.contract.review_method, "")
        self.assertEqual(intake.contract.required_artifacts, [])
        self.assertEqual(intake.contract.required_evidence, [])

    def test_host_environment_text_does_not_implicitly_create_acceptance_contract(self) -> None:
        from agent_team.intake import parse_intake_message

        intake = parse_intake_message("做视觉验收。允许重启微信开发者工具并修改本机配置用于验收。")

        self.assertFalse(intake.contract.has_constraints())
        self.assertTrue(intake.contract.allow_host_environment_changes)


if __name__ == "__main__":
    unittest.main()
