import unittest


class ReviewTests(unittest.TestCase):
    def test_review_includes_artifact_diff_and_improvement_proposals(self) -> None:
        from ai_company.review import build_session_review

        review = build_session_review(
            stage_artifacts={
                "Product": "scope: create, edit",
                "QA": "scope missing: delete",
            },
            findings=[
                {
                    "source_stage": "QA",
                    "target_stage": "Product",
                    "issue": "Delete flow missing",
                    "severity": "high",
                    "proposed_context_update": "Always expand user actions into CRUD coverage.",
                }
            ],
        )

        self.assertIn("Delete flow missing", review)
        self.assertIn("--- Product", review)
        self.assertIn("proposed_context_update", review)


if __name__ == "__main__":
    unittest.main()
