import unittest


class IntakeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
