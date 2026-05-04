import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


def visual_review_contract(*, allow_host_environment_changes: bool = True):
    from agent_team.models import AcceptanceContract

    return AcceptanceContract(
        review_method="figma-restoration-review",
        boundary="page_root",
        recursive=True,
        tolerance_px=0.5,
        required_dimensions=["Structure", "Geometry", "Style", "Content", "State"],
        required_artifacts=["deviation_checklist.md", "review_completion.json"],
        required_evidence=["runtime_screenshot", "overlay_diff", "page_root_recursive_audit"],
        native_node_policy="miniprogram",
        allow_host_environment_changes=allow_host_environment_changes,
        read_only_review=True,
        acceptance_criteria=["递归检查所有可见子节点", "偏差 <= 0.5px"],
    )


class OrchestratorTests(unittest.TestCase):
    def test_review_completion_gate_blocks_visual_review_without_required_artifacts(self) -> None:
        from agent_team.models import StageOutput
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        class ReviewBackend:
            supports_rework_routing = True

            def run_stage(self, *, stage, request, role, stage_artifacts, findings):
                if stage == "Product":
                    return StageOutput(
                        stage="Product",
                        artifact_name="prd.md",
                        artifact_content="# Product PRD\n\n## Acceptance Criteria\n- Use figma-restoration-review.\n",
                        journal="# Product Journal\n",
                    )
                if stage == "Dev":
                    return StageOutput(
                        stage="Dev",
                        artifact_name="implementation.md",
                        artifact_content="# Implementation\n\n## QA Regression Checklist\n- Run visual audit.\n",
                        journal="# Dev Journal\n",
                    )
                if stage == "QA":
                    return StageOutput(
                        stage="QA",
                        artifact_name="qa_report.md",
                        artifact_content="# QA Report\n\n## Decision\npassed\n",
                        journal="# QA Journal\n",
                    )
                if stage == "Acceptance":
                    return StageOutput(
                        stage="Acceptance",
                        artifact_name="acceptance_report.md",
                        artifact_content="# Acceptance Report\n\n## Recommendation\nrecommended_go\n",
                        journal="# Acceptance Journal\n",
                        acceptance_status="recommended_go",
                    )
                raise AssertionError(f"unexpected stage: {stage}")

        repo_root = Path(__file__).resolve().parents[1]
        request = "使用 figma-restoration-review 做 page-root 视觉验收。"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=ReviewBackend(),
            ).run(request=request, contract=visual_review_contract())

            review = (state_root / result.session_id / "review.md").read_text()
            summary = (state_root / result.session_id / "workflow_summary.md").read_text()

            self.assertEqual(result.acceptance_status, "blocked")
            self.assertIn("review_completion_gate", review)
            self.assertIn("criteria_covered", (state_root / result.session_id / "review_completion.json").read_text())
            self.assertIn("blocked_reason: Review completion gate is incomplete", summary)

    def test_review_completion_gate_passes_when_acceptance_outputs_required_artifacts(self) -> None:
        from agent_team.models import StageOutput
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        class ReviewBackend:
            supports_rework_routing = True

            def run_stage(self, *, stage, request, role, stage_artifacts, findings):
                if stage == "Product":
                    return StageOutput(
                        stage="Product",
                        artifact_name="prd.md",
                        artifact_content="# Product PRD\n\n## Acceptance Criteria\n- Use figma-restoration-review.\n",
                        journal="# Product Journal\n",
                    )
                if stage == "Dev":
                    return StageOutput(
                        stage="Dev",
                        artifact_name="implementation.md",
                        artifact_content="# Implementation\n\n## QA Regression Checklist\n- Run visual audit.\n",
                        journal="# Dev Journal\n",
                    )
                if stage == "QA":
                    return StageOutput(
                        stage="QA",
                        artifact_name="qa_report.md",
                        artifact_content="# QA Report\n\n## Decision\npassed\n",
                        journal="# QA Journal\n",
                    )
                if stage == "Acceptance":
                    return StageOutput(
                        stage="Acceptance",
                        artifact_name="acceptance_report.md",
                        artifact_content="# Acceptance Report\n\n## Recommendation\nrecommended_go\n",
                        journal="# Acceptance Journal\n",
                        acceptance_status="recommended_go",
                        supplemental_artifacts={
                            "deviation_checklist.md": "# Deviation Checklist\n\n- No unresolved deviations.\n",
                            "review_completion.json": (
                                "{\n"
                                '  "review_method": "figma-restoration-review",\n'
                                '  "completed": true,\n'
                                '  "criteria_covered": [\n'
                                '    "递归检查所有可见子节点",\n'
                                '    "偏差 <= 0.5px"\n'
                                "  ],\n"
                                '  "dimensions_evaluated": ["Structure", "Geometry", "Style", "Content", "State"],\n'
                                '  "evidence_provided": ["runtime_screenshot", "overlay_diff", "page_root_recursive_audit"],\n'
                                '  "produced_artifacts": ["deviation_checklist.md", "review_completion.json"],\n'
                                '  "unresolved_items": []\n'
                                "}"
                            ),
                        },
                    )
                raise AssertionError(f"unexpected stage: {stage}")

        repo_root = Path(__file__).resolve().parents[1]
        request = "使用 figma-restoration-review 做 page-root 视觉验收。"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=ReviewBackend(),
            ).run(request=request, contract=visual_review_contract())

            self.assertEqual(result.acceptance_status, "recommended_go")

    def test_orchestrator_records_stage_events_for_panel_timeline(self) -> None:
        from agent_team.models import StageOutput
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        class TimelineBackend:
            supports_rework_routing = True

            def run_stage(self, *, stage, request, role, stage_artifacts, findings):
                if stage == "Product":
                    return StageOutput(stage="Product", artifact_name="prd.md", artifact_content="prd", journal="j")
                if stage == "Dev":
                    return StageOutput(stage="Dev", artifact_name="implementation.md", artifact_content="impl", journal="j")
                if stage == "QA":
                    return StageOutput(stage="QA", artifact_name="qa_report.md", artifact_content="qa", journal="j")
                if stage == "Acceptance":
                    return StageOutput(
                        stage="Acceptance",
                        artifact_name="acceptance_report.md",
                        artifact_content="accept",
                        journal="j",
                        acceptance_status="recommended_go",
                    )
                raise AssertionError(f"unexpected stage: {stage}")

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=TimelineBackend(),
            ).run(request="ship a visible timeline")

            events_path = state_root / result.session_id / "events.jsonl"
            events = [json.loads(line) for line in events_path.read_text().splitlines()]

            event_kinds = [event["kind"] for event in events]
            self.assertIn("stage_started", event_kinds)
            self.assertIn("stage_completed", event_kinds)
            self.assertEqual(events[-1]["kind"], "workflow_waiting_human_decision")

    def test_explicit_visual_review_contract_triggers_review_completion_gate(self) -> None:
        from agent_team.models import StageOutput
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        class ReviewBackend:
            supports_rework_routing = True

            def run_stage(self, *, stage, request, role, stage_artifacts, findings):
                if stage == "Product":
                    return StageOutput(
                        stage="Product",
                        artifact_name="prd.md",
                        artifact_content="# Product PRD\n\n## Acceptance Criteria\n- Freshly reread Figma nodes.\n",
                        journal="# Product Journal\n",
                    )
                if stage == "Dev":
                    return StageOutput(
                        stage="Dev",
                        artifact_name="implementation.md",
                        artifact_content="# Implementation\n\n## QA Regression Checklist\n- Run visual audit.\n",
                        journal="# Dev Journal\n",
                    )
                if stage == "QA":
                    return StageOutput(
                        stage="QA",
                        artifact_name="qa_report.md",
                        artifact_content="# QA Report\n\n## Decision\npassed\n",
                        journal="# QA Journal\n",
                    )
                if stage == "Acceptance":
                    return StageOutput(
                        stage="Acceptance",
                        artifact_name="acceptance_report.md",
                        artifact_content="# Acceptance Report\n\n## Recommendation\nrecommended_go\n",
                        journal="# Acceptance Journal\n",
                        acceptance_status="recommended_go",
                    )
                raise AssertionError(f"unexpected stage: {stage}")

        repo_root = Path(__file__).resolve().parents[1]
        request = (
            "在当前 worktree 完成 Figma 1:1 还原。"
            "验收时必须重新完整读取 Figma 节点 2411:6162、2455:12852，"
            "不允许只依赖开发阶段读取结果。"
        )

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=ReviewBackend(),
            ).run(request=request, contract=visual_review_contract())

            review = (state_root / result.session_id / "review.md").read_text()

            self.assertEqual(result.acceptance_status, "blocked")
            self.assertIn("review_completion_gate", review)

    def test_environment_gate_blocks_host_config_changes_without_explicit_approval(self) -> None:
        from agent_team.models import AcceptanceContract, StageOutput
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        class ReviewBackend:
            supports_rework_routing = True

            def run_stage(self, *, stage, request, role, stage_artifacts, findings):
                if stage == "Product":
                    return StageOutput(stage="Product", artifact_name="prd.md", artifact_content="prd", journal="j")
                if stage == "Dev":
                    return StageOutput(stage="Dev", artifact_name="implementation.md", artifact_content="impl", journal="j")
                if stage == "QA":
                    return StageOutput(stage="QA", artifact_name="qa_report.md", artifact_content="passed", journal="j")
                if stage == "Acceptance":
                    return StageOutput(
                        stage="Acceptance",
                        artifact_name="acceptance_report.md",
                        artifact_content=(
                            "# Acceptance Report\n\n"
                            "## Recommendation\nblocked\n\n"
                            "Need to restart WeChat DevTools and modify local config before the audit can continue.\n"
                        ),
                        journal="# Acceptance Journal\n",
                        acceptance_status="blocked",
                    )
                raise AssertionError(f"unexpected stage: {stage}")

        repo_root = Path(__file__).resolve().parents[1]
        request = "做一个视觉验收，不允许改本机环境。"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=ReviewBackend(),
            ).run(
                request=request,
                contract=AcceptanceContract(allow_host_environment_changes=False),
            )

            review = (state_root / result.session_id / "review.md").read_text()
            summary = (state_root / result.session_id / "workflow_summary.md").read_text()

            self.assertEqual(result.acceptance_status, "blocked")
            self.assertIn("host_environment_change", review)
            self.assertIn("explicit user approval", summary)

    def test_acceptance_findings_route_back_to_dev_until_acceptance_passes(self) -> None:
        from agent_team.models import Finding, StageOutput
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        class SequencedBackend:
            supports_rework_routing = True

            def __init__(self) -> None:
                self.acceptance_round = 0

            def run_stage(self, *, stage, request, role, stage_artifacts, findings):
                if stage == "Product":
                    return StageOutput(
                        stage="Product",
                        artifact_name="prd.md",
                        artifact_content="# Product PRD\n\n## Acceptance Criteria\n- Match the page-root visual audit.\n",
                        journal="# Product Journal\n",
                    )
                if stage == "Dev":
                    return StageOutput(
                        stage="Dev",
                        artifact_name="implementation.md",
                        artifact_content="# Implementation\n\n## QA Regression Checklist\n- Re-run the visual audit.\n",
                        journal="# Dev Journal\n",
                    )
                if stage == "QA":
                    return StageOutput(
                        stage="QA",
                        artifact_name="qa_report.md",
                        artifact_content="# QA Report\n\n## Decision\npassed\n",
                        journal="# QA Journal\n",
                    )
                if stage == "Acceptance":
                    self.acceptance_round += 1
                    if self.acceptance_round == 1:
                        return StageOutput(
                            stage="Acceptance",
                            artifact_name="acceptance_report.md",
                            artifact_content=(
                                "# Acceptance Report\n\n"
                                "## Recommendation\nrecommended_no_go\n\n"
                                "because page-root parity still lacks runtime overlay evidence.\n"
                            ),
                            journal="# Acceptance Journal\n",
                            findings=[
                                Finding(
                                    source_stage="Acceptance",
                                    target_stage="Dev",
                                    issue="Page-root parity still lacks runtime overlay evidence.",
                                    severity="high",
                                    lesson="Do not close visual parity from code review alone.",
                                    proposed_context_update="Require runtime visual evidence before closing page-root parity work.",
                                    proposed_skill_update="Route page-root parity failures back to Dev until runtime visual evidence is attached.",
                                    evidence="acceptance_report",
                                )
                            ],
                            acceptance_status="recommended_no_go",
                        )
                    return StageOutput(
                        stage="Acceptance",
                        artifact_name="acceptance_report.md",
                        artifact_content="# Acceptance Report\n\n## Recommendation\nrecommended_go\n",
                        journal="# Acceptance Journal\n",
                        acceptance_status="recommended_go",
                    )
                raise AssertionError(f"unexpected stage: {stage}")

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=SequencedBackend(),
            ).run(request="Close the page-root parity gaps")

            session_payload = (state_root / result.session_id / "session.json").read_text()
            self.assertEqual(result.acceptance_status, "recommended_go")
            self.assertEqual(
                [record.stage for record in result.stage_records],
                ["Product", "Dev", "QA", "Acceptance", "Dev", "QA", "Acceptance"],
            )
            self.assertIn('"round_index": 2', session_payload)

    def test_downstream_findings_create_learning_records(self) -> None:
        from agent_team.backend import StaticBackend
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can create a task",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA found missing delete flow",
                acceptance_report="Rejected because delete flow missing",
                findings=[
                    {
                        "source_stage": "QA",
                        "target_stage": "Product",
                        "issue": "Delete flow missing from PRD",
                        "severity": "high",
                        "lesson": "Enumerate CRUD scope explicitly.",
                        "proposed_context_update": "Always expand user actions into CRUD coverage.",
                    }
                ],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a task manager")

            learned_memory = (state_root / "memory" / "Product" / "lessons.md").read_text()

            self.assertEqual(result.acceptance_status, "recommended_no_go")
            self.assertIn("Enumerate CRUD scope explicitly.", learned_memory)
            self.assertTrue((state_root / result.session_id / "review.md").exists())

    def test_workflow_summary_reflects_progress_and_final_status(self) -> None:
        from agent_team.backend import StaticBackend
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can create a task",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA found missing delete flow",
                acceptance_report="Rejected because delete flow missing",
                findings=[
                    {
                        "source_stage": "QA",
                        "target_stage": "Product",
                        "issue": "Delete flow missing from PRD",
                        "severity": "high",
                        "lesson": "Enumerate CRUD scope explicitly.",
                        "proposed_context_update": "Always expand user actions into CRUD coverage.",
                    }
                ],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a task manager")

            summary_path = state_root / result.session_id / "workflow_summary.md"
            summary = summary_path.read_text()

            self.assertIn("- runtime_mode: deterministic_demo", summary)
            self.assertIn("- current_state: WaitForHumanDecision", summary)
            self.assertIn("- current_stage: Acceptance", summary)
            self.assertIn("- prd_status: drafted", summary)
            self.assertIn("- dev_status: completed", summary)
            self.assertIn("- qa_status: blocked", summary)
            self.assertIn("- acceptance_status: recommended_no_go", summary)

    def test_review_includes_workflow_status_from_orchestrator_run(self) -> None:
        from agent_team.backend import StaticBackend
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can create a task",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA found missing delete flow",
                acceptance_report="Rejected because delete flow missing",
                findings=[
                    {
                        "source_stage": "QA",
                        "target_stage": "Product",
                        "issue": "Delete flow missing from PRD",
                        "severity": "high",
                    }
                ],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a task manager")

            review_path = state_root / result.session_id / "review.md"
            review = review_path.read_text()

            self.assertIn("## Workflow Status", review)
            self.assertIn("runtime_mode: deterministic_demo", review)
            self.assertIn("current_state: WaitForHumanDecision", review)
            self.assertIn("current_stage: Acceptance", review)
            self.assertIn("prd_status: drafted", review)
            self.assertIn("dev_status: completed", review)
            self.assertIn("qa_status: blocked", review)
            self.assertIn("acceptance_status: recommended_no_go", review)
            self.assertIn("human_decision: pending", review)
            self.assertIn("qa_round: 1", review)

    def test_acceptance_failure_creates_rework_learning_for_dev(self) -> None:
        from agent_team.backend import StaticBackend
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can submit a form",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA passed after rerun",
                acceptance_report="recommended_no_go because the empty-state UX is missing",
                findings=[],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a form flow")

            learned_memory = (state_root / "memory" / "Dev" / "lessons.md").read_text()

            self.assertEqual(result.acceptance_status, "recommended_no_go")
            self.assertIn("Acceptance", learned_memory)
            self.assertIn("empty-state UX", learned_memory)

    def test_qa_findings_increment_rework_round(self) -> None:
        from agent_team.backend import StaticBackend
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can create a task",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA found retry-state regression",
                acceptance_report="blocked",
                findings=[
                    {
                        "source_stage": "QA",
                        "target_stage": "Dev",
                        "issue": "Retry-state regression",
                        "severity": "high",
                        "lesson": "Preserve retry states during rework.",
                    }
                ],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a task manager")

            review = (state_root / result.session_id / "review.md").read_text()
            self.assertIn("qa_round: 1", review)

    def test_visual_acceptance_findings_require_runtime_visual_evidence(self) -> None:
        from agent_team.backend import StaticBackend
        from agent_team.orchestrator import WorkflowOrchestrator
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users need page-root parity",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA passed after command rerun",
                acceptance_report=(
                    "recommended_no_go because page-root figma parity lacks <=0.5px "
                    "runtime screenshot and overlay diff evidence"
                ),
                findings=[],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Restore page-root parity")

            review = (state_root / result.session_id / "review.md").read_text()
            self.assertIn("required_evidence: runtime_screenshot, overlay_diff, page_root_recursive_audit", review)
            self.assertIn("completion_signal:", review)


if __name__ == "__main__":
    unittest.main()
