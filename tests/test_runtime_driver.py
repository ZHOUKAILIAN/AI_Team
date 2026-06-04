import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


def product_definition_request(
    root: Path,
    *,
    state_store=None,
    session_id: str = "session",
    executor_env_config_path: Path | None = None,
):
    from agent_team.execution_context import StageExecutionContext
    from agent_team.models import StageContract
    from agent_team.runtime_driver import StageExecutionRequest

    return StageExecutionRequest(
        repo_root=root,
        state_store=state_store,
        session_id=session_id,
        run_id="product-definition-run-1",
        contract=StageContract(
            session_id=session_id,
            stage="ProductDefinition",
            goal="Write an L1 delta.",
            contract_id="contract",
            required_outputs=["product-definition-delta.md"],
        ),
        context=StageExecutionContext(
            session_id=session_id,
            stage="ProductDefinition",
            round_index=1,
            context_id="context",
            contract_id="contract",
            original_request_summary="写个js文件，并打印hello world",
            approved_product_definition_summary="",
            acceptance_matrix=[],
            constraints=[],
            required_outputs=["product-definition-delta.md"],
            required_evidence=[],
            relevant_artifacts=[],
        ),
        contract_path=root / "contract.json",
        context_path=root / "context.json",
        result_path=root / "result.json",
        output_schema_path=root / "schema.json",
        prompt_path=root / "prompt.md",
        executor_env_config_path=executor_env_config_path,
    )


def write_product_definition_result(output_path: Path, *, summary: str = "ProductDefinition completed.") -> None:
    output_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "artifact_content": "# Product Definition Delta\n",
                "journal": "",
                "findings": [],
                "evidence": [],
                "suggested_next_owner": "",
                "summary": summary,
                "acceptance_status": "",
                "blocked_reason": "",
            }
        )
    )


class RuntimeDriverSchemaTests(unittest.TestCase):
    def test_stage_result_schema_is_strict_for_codex_structured_output(self) -> None:
        from agent_team.runtime_driver import _stage_result_schema

        def assert_strict_objects(schema: dict[str, object], path: str) -> None:
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                required = schema.get("required", [])
                self.assertEqual(schema.get("additionalProperties"), False, path)
                self.assertEqual(set(required), set(properties), path)
                for name in required:
                    self.assertIn(name, properties, f"{path}: {name} in required but not properties")
                for _name, child in properties.items():
                    if isinstance(child, dict):
                        assert_strict_objects(child, f"{path}.{_name}")
            if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
                assert_strict_objects(schema["items"], f"{path}[]")

        assert_strict_objects(_stage_result_schema(), "$")


    def test_stage_result_schema_uses_contract_required_evidence_keys(self) -> None:
        from agent_team.models import StageContract
        from agent_team.runtime_driver import _stage_result_schema

        schema = _stage_result_schema(
            StageContract(
                session_id="session",
                stage="Implementation",
                goal="Implement",
                evidence_requirements=["self_code_review", "self_verification"],
            )
        )
        evidence_by_name = schema["properties"]["evidence_by_name"]

        self.assertEqual(evidence_by_name["required"], ["self_code_review", "self_verification"])
        self.assertEqual(set(evidence_by_name["properties"]), {"self_code_review", "self_verification"})
        self.assertFalse(evidence_by_name["additionalProperties"])
        self.assertNotIn("self_verification_check", evidence_by_name["properties"])

    def test_route_artifact_instructions_name_verification_contract_fields(self) -> None:
        from agent_team.runtime_driver import _stage_artifact_format_instructions

        instructions = _stage_artifact_format_instructions("Route")

        self.assertIn("required_evidence", instructions)
        self.assertIn("private_config_required", instructions)
        self.assertIn("fixture_preconditions", instructions)
        self.assertIn("verification_reason", instructions)

    def test_stage_output_schema_file_is_contract_specific(self) -> None:
        from agent_team.models import StageContract
        from agent_team.runtime_driver import _stage_result_schema

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            contract = StageContract(
                session_id="session",
                stage="Implementation",
                goal="Implement",
                evidence_requirements=["self_verification"],
            )
            schema_path.write_text(json.dumps(_stage_result_schema(contract), indent=2))
            payload = json.loads(schema_path.read_text())

        self.assertEqual(payload["properties"]["evidence_by_name"]["required"], ["self_verification"])
        self.assertIn("self_verification", payload["properties"]["evidence_by_name"]["properties"])

    def test_stage_result_schema_excludes_runtime_control_fields(self) -> None:
        from agent_team.runtime_driver import _stage_result_schema
        from agent_team.stage_payload import FORBIDDEN_STAGE_PAYLOAD_FIELDS

        properties = _stage_result_schema()["properties"]

        for field in FORBIDDEN_STAGE_PAYLOAD_FIELDS:
            self.assertNotIn(field, properties)
        self.assertNotIn("supplemental_artifacts", properties)

    def test_verification_stage_result_schema_allows_partial_needs_verification_semantics(self) -> None:
        from agent_team.runtime_driver import _stage_result_schema
        from agent_team.stage_policies import default_policy_registry

        contract = default_policy_registry().build_contract(
            session_id="session",
            stage="Verification",
            contract_id="contract-verification",
            input_artifacts={},
        )
        schema = _stage_result_schema(contract)

        self.assertIn("partial", schema["properties"]["status"]["enum"])
        self.assertIn("needs_verification", schema["properties"]["status"]["enum"])
        self.assertIn("verification_conclusion", schema["properties"])
        self.assertIn("release_recommendation", schema["properties"])
        self.assertIn("gate_decision", schema["properties"])
        self.assertIn("needs_verification", schema["properties"]["verification_conclusion"]["enum"])
        self.assertIn("needs_verification", schema["properties"]["release_recommendation"]["enum"])
        self.assertIn("proceed", schema["properties"]["gate_decision"]["enum"])

    def test_codex_prompt_instructs_product_definition_l1_boundaries(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import Finding, StageContract
        from agent_team.runtime_driver import StageExecutionRequest, _build_codex_prompt

        request = StageExecutionRequest(
            repo_root=Path("/repo"),
            state_store=None,
            session_id="session",
            run_id="product-definition-run-1",
            contract=StageContract(
                session_id="session",
                stage="ProductDefinition",
                goal="Write L1 delta",
                contract_id="contract",
                required_outputs=["product-definition-delta.md"],
            ),
            context=StageExecutionContext(
                session_id="session",
                stage="ProductDefinition",
                round_index=1,
                context_id="context",
                contract_id="contract",
                original_request_summary="本期 PRD 里包含稳定产品对象和实现细节",
                approved_product_definition_summary="",
                acceptance_matrix=[],
                constraints=[],
                required_outputs=["product-definition-delta.md"],
                required_evidence=[],
                relevant_artifacts=[],
                actionable_findings=[
                    Finding(
                        source_stage="ProductDefinition",
                        target_stage="ProductDefinition",
                        issue="确认哪些内容真正进入 L1",
                    )
                ],
            ),
            contract_path=Path("/tmp/contract.json"),
            context_path=Path("/tmp/context.json"),
            result_path=Path("/tmp/result.json"),
            output_schema_path=Path("/tmp/schema.json"),
        )

        prompt = _build_codex_prompt(request)

        self.assertIn("Write product-definition-delta.md content in Simplified Chinese", prompt)
        self.assertIn("Return only JSON stage payload", prompt)
        self.assertIn("Human-readable content must be Simplified Chinese", prompt)
        self.assertNotIn("Write every human-readable artifact", prompt)
        self.assertIn("<alignment_updates>", prompt)
        self.assertIn("corrected artifact feeds later stages", prompt)
        self.assertNotIn("<human_revision_requests>", prompt)
        self.assertIn("Keep the document in artifact_content", prompt)
        self.assertIn("Use evidence_by_name for contract evidence", prompt)
        self.assertIn("product-definition-delta.md", prompt)
        self.assertIn("If unclear or missing an L1 product decision", prompt)
        self.assertIn("return status `blocked`", prompt)
        self.assertIn("`## 理解复述`", prompt)
        self.assertIn("Then separate `## L1 候选` from `## 非 L1 内容`", prompt)
        self.assertIn("Do not write implementation plans", prompt)
        self.assertIn("确认哪些内容真正进入 L1", prompt)
        self.assertNotIn("Non-Goals", prompt)

    def test_codex_prompt_instructs_technical_design_tables_and_flowcharts(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import StageExecutionRequest, _build_codex_prompt

        request = StageExecutionRequest(
            repo_root=Path("/repo"),
            state_store=None,
            session_id="session",
            run_id="technical-design-run-1",
            contract=StageContract(
                session_id="session",
                stage="TechnicalDesign",
                goal="Write technical design",
                contract_id="contract",
                required_outputs=["technical-design.md"],
            ),
            context=StageExecutionContext(
                session_id="session",
                stage="TechnicalDesign",
                round_index=1,
                context_id="context",
                contract_id="contract",
                original_request_summary="写个js文件，并打印hello world",
                approved_product_definition_summary="# Product Definition Delta",
                acceptance_matrix=[],
                constraints=[],
                required_outputs=["technical-design.md"],
                required_evidence=[],
                relevant_artifacts=[],
            ),
            contract_path=Path("/tmp/contract.json"),
            context_path=Path("/tmp/context.json"),
            result_path=Path("/tmp/result.json"),
            output_schema_path=Path("/tmp/schema.json"),
        )

        prompt = _build_codex_prompt(request)

        self.assertIn("technical-design.md", prompt)
        self.assertIn("Simplified Chinese", prompt)
        self.assertIn("Do not edit source code", prompt)
        self.assertIn("If a material design choice is unresolved", prompt)
        self.assertIn("focused questions in artifact_content", prompt)
        self.assertIn("return status `blocked`", prompt)
        self.assertIn("`## 方案理解复述`", prompt)
        self.assertIn("verification plan, risks, and rollback", prompt)

    def test_codex_prompt_instructs_implementation_to_follow_approved_technical_design(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import StageExecutionRequest, _build_codex_prompt

        request = StageExecutionRequest(
            repo_root=Path("/repo"),
            state_store=None,
            session_id="session",
            run_id="implementation-run-1",
            contract=StageContract(
                session_id="session",
                stage="Implementation",
                goal="Implement",
                contract_id="contract",
                required_outputs=["implementation.md"],
            ),
            context=StageExecutionContext(
                session_id="session",
                stage="Implementation",
                round_index=1,
                context_id="context",
                contract_id="contract",
                original_request_summary="写个js文件，并打印hello world",
                approved_product_definition_summary="# Product Definition Delta",
                acceptance_matrix=[],
                constraints=[],
                required_outputs=["implementation.md"],
                required_evidence=[],
                relevant_artifacts=[],
                approved_technical_design_content="# 技术设计\n\n- 按已确认技术设计创建 hello.js。\n",
            ),
            contract_path=Path("/tmp/contract.json"),
            context_path=Path("/tmp/context.json"),
            result_path=Path("/tmp/result.json"),
            output_schema_path=Path("/tmp/schema.json"),
        )

        prompt = _build_codex_prompt(request)

        self.assertIn("approved technical design", prompt)
        self.assertIn("implementation source of truth", prompt)
        self.assertIn("too ambiguous to implement safely", prompt)
        self.assertIn("server-side changes", prompt)
        self.assertIn("frontend mini-program changes", prompt)
        self.assertIn("implementation.md in Simplified Chinese", prompt)
        self.assertIn("按已确认技术设计创建 hello.js", prompt)

    def test_codex_prompt_includes_enabled_skills(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import StageExecutionRequest, _build_codex_prompt
        from agent_team.skill_registry import Skill

        request = StageExecutionRequest(
            repo_root=Path("/repo"),
            state_store=None,
            session_id="session",
            run_id="implementation-run-1",
            contract=StageContract(
                session_id="session",
                stage="Implementation",
                goal="Implement",
                contract_id="contract",
                required_outputs=["implementation.md"],
            ),
            context=StageExecutionContext(
                session_id="session",
                stage="Implementation",
                round_index=1,
                context_id="context",
                contract_id="contract",
                original_request_summary="写个js文件，并打印hello world",
                approved_product_definition_summary="# Product Definition Delta",
                acceptance_matrix=[],
                constraints=[],
                required_outputs=["implementation.md"],
                required_evidence=[],
                relevant_artifacts=[],
                approved_technical_design_content="# 技术设计\n\n- 创建 hello.js。\n",
            ),
            contract_path=Path("/tmp/contract.json"),
            context_path=Path("/tmp/context.json"),
            result_path=Path("/tmp/result.json"),
            output_schema_path=Path("/tmp/schema.json"),
            skill_asset_root=Path(
                "/repo/.agent-team/_runtime/sessions/session/roles/implementation/attempt-001/execution-contexts/skills/.agent-team/skills"
            ),
            skills=[
                Skill(
                    name="plan",
                    description="Plan the implementation",
                    content="# Plan\n\nDo the plan.",
                    source="builtin",
                    path=Path("/skills/plan/SKILL.md"),
                    source_ref="https://example.com/skills/plan",
                    stages=("Implementation",),
                    delivery="sandbox",
                )
            ],
        )

        prompt = _build_codex_prompt(request)

        self.assertIn("<enabled_skills>", prompt)
        self.assertIn('<skill name="plan">', prompt)
        self.assertIn("<source_type>builtin</source_type>", prompt)
        self.assertIn("<source_ref>https://example.com/skills/plan</source_ref>", prompt)
        self.assertIn(
            "<asset_root>/repo/.agent-team/_runtime/sessions/session/roles/implementation/attempt-001/execution-contexts/skills/.agent-team/skills/plan/</asset_root>",
            prompt,
        )
        self.assertIn("Do the plan", prompt)

    def test_dry_run_product_definition_artifact_records_l1_and_non_l1(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from dataclasses import replace

        from agent_team.models import Finding
        from agent_team.runtime_driver import _dry_run_artifact_content, _dry_run_supplemental_artifacts

        context = StageExecutionContext(
            session_id="session",
            stage="ProductDefinition",
            round_index=1,
            context_id="context",
            contract_id="contract",
            original_request_summary="写个js文件，并打印hello world",
            approved_product_definition_summary="",
            acceptance_matrix=[],
            constraints=[],
            required_outputs=["product-definition-delta.md"],
            required_evidence=[],
            relevant_artifacts=[],
            actionable_findings=[
                Finding(
                    source_stage="ProductDefinition",
                    target_stage="ProductDefinition",
                    issue="在桌面生成文件",
                )
            ],
        )

        artifact = _dry_run_artifact_content("ProductDefinition", context)

        self.assertIn("# Product Definition Delta", artifact)
        self.assertIn("理解复述", artifact)
        self.assertIn("阶段对齐更新", artifact)
        self.assertIn("正式产品定义 delta", artifact)
        self.assertIn("在桌面生成文件", artifact)
        self.assertIn("非 L1 内容", artifact)
        self.assertNotIn("Non-Goals", artifact)
        self.assertEqual(_dry_run_supplemental_artifacts("ProductDefinition", context), {})


    def test_dry_run_executor_marks_result_non_authoritative(self) -> None:
        from agent_team.runtime_driver import DryRunStageExecutor

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = product_definition_request(root)
            result = DryRunStageExecutor().execute(request)

        self.assertTrue(result.dry_run)
        self.assertFalse(result.authoritative)
        self.assertEqual(result.executor_status, "synthetic")
        self.assertEqual(result.result_parse_status, "synthetic")

    def test_provider_smoke_metadata_is_recorded_without_running_check_by_default(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            state_root = root / "state"
            result = run_requirement(
                repo_root=root,
                state_root=state_root,
                message="记录 provider metadata",
                options=RuntimeDriverOptions(executor="dry-run", max_stage_runs=0),
            )
            from agent_team.state import StateStore

            summary = StateStore(state_root).load_workflow_summary(result.session_id)

        self.assertEqual(summary.provider_model_metadata["executor"], "dry-run")
        self.assertEqual(summary.provider_model_metadata["model"], "gpt-5.4")
        self.assertFalse(summary.provider_model_metadata["smoke_check_enabled"])

    def test_codex_capability_check_skips_unsupported_prompt_protection_flags(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = product_definition_request(root)
            request.output_schema_path.write_text("{}")
            with patch("agent_team.runtime_driver._codex_exec_capabilities", lambda: {"--json", "-o", "--skip-git-repo-check"}):
                command = CodexExecStageExecutor(RuntimeDriverOptions())._build_codex_command(
                    request,
                    prompt="reply",
                    output_path=root / "result.json",
                    resume_id="",
                )

        self.assertNotIn("--ignore-rules", command)
        self.assertNotIn("plugins", command)
        self.assertNotIn("--output-schema", command)
        self.assertIn("--json", command)
        self.assertEqual(request.executor_metadata["codex_exec_capabilities"]["skipped_flags"], [
            "--cd",
            "--sandbox",
            "--output-schema",
            "--ignore-rules",
            "--ephemeral",
        ])



    def test_codex_exec_resume_skips_output_schema(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = product_definition_request(root)
            request.output_schema_path.write_text("{}")
            with patch("agent_team.runtime_driver._codex_exec_capabilities", lambda: {"--json", "-o", "--output-schema"}):
                command = CodexExecStageExecutor(RuntimeDriverOptions())._build_codex_command(
                    request,
                    prompt="reply",
                    output_path=root / "result.json",
                    resume_id="resume-123",
                )

        self.assertIn("resume", command)
        self.assertNotIn("--output-schema", command)
        self.assertNotIn("-o", command)
        self.assertIn("resume --output-schema", request.executor_metadata["codex_exec_capabilities"]["skipped_flags"])
        self.assertIn("resume output file", request.executor_metadata["codex_exec_capabilities"]["skipped_flags"])

    def test_codex_exec_does_not_disable_plugins_by_default(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = product_definition_request(root)
            request.output_schema_path.write_text("{}")
            with patch("agent_team.runtime_driver._codex_exec_capabilities", lambda: {"--json", "-o", "--disable"}):
                command = CodexExecStageExecutor(RuntimeDriverOptions())._build_codex_command(
                    request,
                    prompt="reply",
                    output_path=root / "result.json",
                    resume_id="",
                )

        self.assertNotIn("--disable", command)
        self.assertNotIn("plugins", command)

    def test_codex_exec_stage_executor_skips_git_repo_check(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions, StageExecutionRequest

        commands = []

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            commands.append(command)
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "artifact_content": "# Product Definition Delta\n",
                        "journal": "",
                        "findings": [],
                        "evidence": [],
                        "suggested_next_owner": "",
                        "summary": "ProductDefinition completed.",
                        "acceptance_status": "",
                        "blocked_reason": "",
                    }
                )
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = StageExecutionRequest(
                repo_root=root,
                state_store=None,
                session_id="session",
                run_id="product-definition-run-1",
                contract=StageContract(
                    session_id="session",
                    stage="ProductDefinition",
                    goal="Write an L1 delta.",
                    contract_id="contract",
                    required_outputs=["product-definition-delta.md"],
                ),
                context=StageExecutionContext(
                    session_id="session",
                    stage="ProductDefinition",
                    round_index=1,
                    context_id="context",
                    contract_id="contract",
                    original_request_summary="写个js文件，并打印hello world",
                    approved_product_definition_summary="",
                    acceptance_matrix=[],
                    constraints=[],
                    required_outputs=["product-definition-delta.md"],
                    required_evidence=[],
                    relevant_artifacts=[],
                ),
                contract_path=root / "contract.json",
                context_path=root / "context.json",
                result_path=root / "result.json",
                output_schema_path=root / "schema.json",
                prompt_path=root / "prompt.md",
            )

            with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                envelope = CodexExecStageExecutor(RuntimeDriverOptions(codex_ephemeral=False)).execute(request)

        self.assertEqual(len(commands), 1)
        self.assertIn("--skip-git-repo-check", commands[0])
        self.assertEqual(envelope.session_id, "session")
        self.assertEqual(envelope.stage, "ProductDefinition")
        self.assertEqual(envelope.contract_id, "contract")
        self.assertEqual(envelope.artifact_name, "product-definition-delta.md")

    def test_codex_exec_stage_executor_uses_executor_env_config(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions, StageExecutionRequest

        captured_env = {}

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            captured_env.update(env or {})
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "artifact_content": "# Product Definition Delta\n",
                        "journal": "",
                        "findings": [],
                        "evidence": [],
                        "suggested_next_owner": "",
                        "summary": "ProductDefinition completed.",
                        "acceptance_status": "",
                        "blocked_reason": "",
                    }
                )
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            config_path = root / "executor-env.json"
            config_path.write_text(
                json.dumps(
                    {
                        "inherit": ["PATH", "OPENAI_API_KEY"],
                        "set": {"AGENT_TEAM_ALLOWED": "yes"},
                    }
                )
            )
            request = StageExecutionRequest(
                repo_root=root,
                state_store=None,
                session_id="session",
                run_id="product-definition-run-1",
                contract=StageContract(
                    session_id="session",
                    stage="ProductDefinition",
                    goal="Write an L1 delta.",
                    contract_id="contract",
                    required_outputs=["product-definition-delta.md"],
                ),
                context=StageExecutionContext(
                    session_id="session",
                    stage="ProductDefinition",
                    round_index=1,
                    context_id="context",
                    contract_id="contract",
                    original_request_summary="写个js文件，并打印hello world",
                    approved_product_definition_summary="",
                    acceptance_matrix=[],
                    constraints=[],
                    required_outputs=["product-definition-delta.md"],
                    required_evidence=[],
                    relevant_artifacts=[],
                ),
                contract_path=root / "contract.json",
                context_path=root / "context.json",
                result_path=root / "result.json",
                output_schema_path=root / "schema.json",
                prompt_path=root / "prompt.md",
                executor_env_config_path=config_path,
            )

            with patch.dict(
                "os.environ",
                {"PATH": "/bin", "OPENAI_API_KEY": "openai-secret", "DATABASE_URL": "postgres://secret"},
                clear=True,
            ):
                with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                    envelope = CodexExecStageExecutor(RuntimeDriverOptions()).execute(request)

        self.assertEqual(envelope.session_id, "session")
        self.assertEqual(captured_env["PATH"], "/bin")
        self.assertEqual(captured_env["OPENAI_API_KEY"], "openai-secret")
        self.assertEqual(captured_env["AGENT_TEAM_ALLOWED"], "yes")
        self.assertIn("CODEX_HOME", captured_env)
        self.assertNotIn("DATABASE_URL", captured_env)


    def test_codex_exec_recovers_result_from_jsonl_stdout_when_output_file_missing(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions

        commands = []

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None, start_new_session=None):
            commands.append(command)
            message = json.dumps({
                "status": "completed",
                "artifact_content": "# Product Definition Delta\n",
                "journal": "",
                "findings": [],
                "evidence": [],
                "suggested_next_owner": "",
                "summary": "stdout recovered",
                "acceptance_status": "",
                "blocked_reason": "",
            })
            stdout = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": message}}) + "\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = product_definition_request(root)
            with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                envelope = CodexExecStageExecutor(RuntimeDriverOptions()).execute(request)
            result_exists = request.result_path.exists()

        self.assertTrue(commands)
        self.assertEqual(envelope.summary, "stdout recovered")
        self.assertTrue(result_exists)

    def test_codex_exec_stage_executor_persists_resume_id_from_json_stream(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions
        from agent_team.state import StateStore

        conversation_id = "019e3d5f-2b95-7e90-9f55-62a892a01234"
        captured_env = {}
        commands = []

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            commands.append(command)
            captured_env.update(env or {})
            write_product_definition_result(Path(command[command.index("-o") + 1]))
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"type": "session_meta", "payload": {"id": conversation_id}}) + "\n",
                stderr="",
            )

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root / "state")
            session = store.create_session("demo")
            source_home = root / "source-codex"
            source_home.mkdir()
            request = product_definition_request(root, state_store=store, session_id=session.session_id)

            with patch("agent_team.runtime_driver.default_codex_home", lambda: source_home):
                with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                    envelope = CodexExecStageExecutor(RuntimeDriverOptions(codex_ephemeral=False)).execute(request)

            saved = store.load_codex_exec_state(session.session_id)
            codex_home = store.codex_home_path(session.session_id)

        self.assertEqual(envelope.status, "completed")
        self.assertEqual(saved["conversation_id"], conversation_id)
        self.assertEqual(captured_env["CODEX_HOME"], str(codex_home))
        self.assertNotIn("--ephemeral", commands[0])
        self.assertIn("--json", commands[0])
        self.assertEqual(request.executor_metadata["codex_exec"]["conversation_id"], conversation_id)
        self.assertEqual(request.executor_metadata["codex_exec"]["mode"], "new")

    def test_codex_exec_stage_executor_uses_persistent_session_codex_home(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions
        from agent_team.state import StateStore

        captured_env = {}

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            captured_env.update(env or {})
            write_product_definition_result(Path(command[command.index("-o") + 1]))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root / "state")
            session = store.create_session("demo")
            source_home = root / "source-codex"
            source_home.mkdir()
            (source_home / "auth.json").write_text('{"token": "secret"}')
            (source_home / "config.toml").write_text('model = "gpt-5.4"\n[mcp_servers.test]\ncommand = "secret"\n')
            request = product_definition_request(root, state_store=store, session_id=session.session_id)

            with patch("agent_team.runtime_driver.default_codex_home", lambda: source_home):
                with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                    CodexExecStageExecutor(RuntimeDriverOptions(codex_ephemeral=False)).execute(request)

            codex_home = store.codex_home_path(session.session_id)
            auth_exists = (codex_home / "auth.json").exists()
            config_text = (codex_home / "config.toml").read_text()

        self.assertEqual(captured_env["CODEX_HOME"], str(codex_home))
        self.assertTrue(auth_exists)
        self.assertIn('model = "gpt-5.4"', config_text)
        self.assertNotIn("mcp_servers", config_text)

    def test_codex_exec_stage_executor_resumes_recorded_session(self) -> None:
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions
        from agent_team.state import StateStore

        resume_id = "019e3d5f-2b95-7e90-9f55-62a892a01234"
        commands = []

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            commands.append(command)
            message = json.dumps({
                "status": "completed",
                "artifact_content": "# Product Definition Delta\n",
                "journal": "",
                "findings": [],
                "evidence": [],
                "suggested_next_owner": "",
                "summary": "resumed",
                "acceptance_status": "",
                "blocked_reason": "",
            })
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"type": "session_meta", "payload": {"id": resume_id}}) + "\n" + json.dumps({"type": "agent_message", "payload": {"message": message}}) + "\n",
                stderr="",
            )

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root / "state")
            session = store.create_session("demo")
            store.save_codex_exec_state(session.session_id, {"conversation_id": resume_id})
            source_home = root / "source-codex"
            source_home.mkdir()
            request = product_definition_request(root, state_store=store, session_id=session.session_id)

            with patch("agent_team.runtime_driver.default_codex_home", lambda: source_home):
                with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                    envelope = CodexExecStageExecutor(RuntimeDriverOptions(codex_ephemeral=False)).execute(request)

        self.assertEqual(envelope.summary, "resumed")
        self.assertEqual(commands[0][:3], ["codex", "exec", "resume"])
        self.assertIn(resume_id, commands[0])
        self.assertIn("--json", commands[0])
        self.assertNotIn("--output-schema", commands[0])
        self.assertNotIn("-o", commands[0])
        self.assertIn("resume --output-schema", request.executor_metadata["codex_exec_capabilities"]["skipped_flags"])
        self.assertIn("resume output file", request.executor_metadata["codex_exec_capabilities"]["skipped_flags"])
        self.assertNotIn("--cd", commands[0])
        self.assertNotIn("--sandbox", commands[0])
        self.assertNotIn("--ephemeral", commands[0])
        self.assertEqual(request.executor_metadata["codex_exec"]["resume_id"], resume_id)
        self.assertEqual(request.executor_metadata["codex_exec"]["mode"], "resume")

    def test_codex_session_id_extraction_supports_session_meta_events(self) -> None:
        from agent_team.runtime_driver import _extract_codex_session_id

        stream = "\n".join(
            [
                json.dumps({"type": "agent_message", "payload": {"message": "ready"}}),
                json.dumps({"type": "session_meta", "payload": {"id": "019e3d5f-2b95-7e90-9f55-62a892a01234"}}),
                json.dumps({"type": "agent_message", "payload": {"id": "message-id-should-not-win"}}),
            ]
        )

        self.assertEqual(_extract_codex_session_id(stream), "019e3d5f-2b95-7e90-9f55-62a892a01234")
    def test_codex_exec_repairs_output_protocol_error_once(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions, StageExecutionRequest
        from agent_team.state import StateStore

        commands = []

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            commands.append(command)
            output_path = Path(command[command.index("-o") + 1])
            if len(commands) == 1:
                output_path.write_text(
                    json.dumps(
                        {
                            "stage": "ProductDefinition",
                            "status": "completed",
                            "artifact_content": "# Product Definition Delta\n",
                            "journal": "",
                            "findings": [],
                            "evidence": [],
                            "suggested_next_owner": "",
                            "summary": "bad envelope",
                            "acceptance_status": "",
                            "blocked_reason": "",
                        }
                    )
                )
            else:
                output_path.write_text(
                    json.dumps(
                        {
                            "status": "completed",
                            "artifact_content": "# Product Definition Delta\n",
                            "journal": "",
                            "findings": [],
                            "evidence": [],
                            "suggested_next_owner": "",
                            "summary": "repaired envelope",
                            "acceptance_status": "",
                            "blocked_reason": "",
                        }
                    )
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root / "state")
            session = store.create_session("demo")
            request = StageExecutionRequest(
                repo_root=root,
                state_store=store,
                session_id=session.session_id,
                run_id="product-definition-run-1",
                contract=StageContract(
                    session_id=session.session_id,
                    stage="ProductDefinition",
                    goal="Write an L1 delta.",
                    contract_id="contract",
                    required_outputs=["product-definition-delta.md"],
                ),
                context=StageExecutionContext(
                    session_id=session.session_id,
                    stage="ProductDefinition",
                    round_index=1,
                    context_id="context",
                    contract_id="contract",
                    original_request_summary="写个js文件，并打印hello world",
                    approved_product_definition_summary="",
                    acceptance_matrix=[],
                    constraints=[],
                    required_outputs=["product-definition-delta.md"],
                    required_evidence=[],
                    relevant_artifacts=[],
                ),
                contract_path=root / "contract.json",
                context_path=root / "context.json",
                result_path=root / "result.json",
                output_schema_path=root / "schema.json",
                prompt_path=root / "prompt.md",
                stdout_path=root / "stdout.txt",
                stderr_path=root / "stderr.txt",
            )

            with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                envelope = CodexExecStageExecutor(RuntimeDriverOptions()).execute(request)
            stats = store.load_workflow_summary(session.session_id).model_output_format_stats

        self.assertEqual(len(commands), 2)
        self.assertIn("<agent_team_output_repair", commands[1][-1])
        self.assertIn("runtime-controlled fields", commands[1][-1])
        self.assertEqual(envelope.status, "completed")
        self.assertEqual(envelope.summary, "repaired envelope")
        self.assertEqual(envelope.stage, "ProductDefinition")
        self.assertEqual(stats["runtime_controlled_field_count"], 1)
        self.assertEqual(stats["invalid_json_count"], 1)
        self.assertEqual(stats["repair_attempt_count"], 1)
        self.assertEqual(stats["repair_success_count"], 1)

    def test_codex_exec_repairs_output_protocol_error_twice_before_blocking_user(self) -> None:
        from agent_team.execution_context import StageExecutionContext
        from agent_team.models import StageContract
        from agent_team.runtime_driver import CodexExecStageExecutor, RuntimeDriverOptions, StageExecutionRequest

        commands = []

        def fake_run(command, *, cwd, capture_output, text, timeout, check, env=None, stdin=None):
            commands.append(command)
            output_path = Path(command[command.index("-o") + 1])
            if len(commands) < 3:
                output_path.write_text(
                    json.dumps(
                        {
                            "stage": "ProductDefinition",
                            "status": "completed",
                            "artifact_content": "# Product Definition Delta\n",
                            "journal": "",
                            "findings": [],
                            "evidence": [],
                            "summary": "still bad",
                        }
                    )
                )
            else:
                output_path.write_text(
                    json.dumps(
                        {
                            "status": "completed",
                            "artifact_content": "# Product Definition Delta\n",
                            "journal": "",
                            "findings": [],
                            "evidence": [],
                            "suggested_next_owner": "",
                            "summary": "repaired on second attempt",
                            "acceptance_status": "",
                            "blocked_reason": "",
                        }
                    )
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            request = StageExecutionRequest(
                repo_root=root,
                state_store=None,
                session_id="session",
                run_id="product-definition-run-1",
                contract=StageContract(
                    session_id="session",
                    stage="ProductDefinition",
                    goal="Write an L1 delta.",
                    contract_id="contract",
                    required_outputs=["product-definition-delta.md"],
                ),
                context=StageExecutionContext(
                    session_id="session",
                    stage="ProductDefinition",
                    round_index=1,
                    context_id="context",
                    contract_id="contract",
                    original_request_summary="写个js文件，并打印hello world",
                    approved_product_definition_summary="",
                    acceptance_matrix=[],
                    constraints=[],
                    required_outputs=["product-definition-delta.md"],
                    required_evidence=[],
                    relevant_artifacts=[],
                ),
                contract_path=root / "contract.json",
                context_path=root / "context.json",
                result_path=root / "result.json",
                output_schema_path=root / "schema.json",
                prompt_path=root / "prompt.md",
                stdout_path=root / "stdout.txt",
                stderr_path=root / "stderr.txt",
            )

            with patch("agent_team.runtime_driver.subprocess.run", fake_run):
                envelope = CodexExecStageExecutor(RuntimeDriverOptions()).execute(request)

        self.assertEqual(len(commands), 3)
        self.assertIn("result-repair-1.json", str(commands[1]))
        self.assertIn("result-repair-2.json", str(commands[2]))
        self.assertEqual(envelope.status, "completed")
        self.assertEqual(envelope.summary, "repaired on second attempt")

    def test_stage_payload_parser_rejects_runtime_control_fields(self) -> None:
        from agent_team.runtime_driver import _stage_result_from_json_text

        request = SimpleNamespace(
            session_id="runtime-session",
            contract=SimpleNamespace(stage="ProductDefinition", contract_id="runtime-contract"),
        )
        result = _stage_result_from_json_text(
            request=request,
            value=json.dumps(
                {
                    "stage": "ProductDefinition",
                    "status": "completed",
                    "artifact_content": "# Product Definition Delta\n",
                    "journal": "",
                    "findings": [],
                    "evidence": [],
                    "suggested_next_owner": "",
                    "summary": "done",
                    "acceptance_status": "",
                    "blocked_reason": "",
                }
            ),
            source="stdout",
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("runtime-controlled field(s): stage", result.blocked_reason)

    def test_stage_run_streams_accept_timeout_bytes(self) -> None:
        from agent_team.runtime_driver import _write_stage_run_streams

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            request = SimpleNamespace(
                result_path=Path(temp_dir) / "stage_runs" / "route-run-1_result.json",
                run_id="route-run-1",
            )
            _write_stage_run_streams(request, stdout=b"partial stdout", stderr=b"partial stderr")

            stdout = (Path(temp_dir) / "stage_runs" / "route-run-1_stdout.txt").read_text()
            stderr = (Path(temp_dir) / "stage_runs" / "route-run-1_stderr.txt").read_text()

        self.assertEqual(stdout, "partial stdout")
        self.assertEqual(stderr, "partial stderr")


class RuntimeDriverTraceTests(unittest.TestCase):
    def test_dry_run_records_non_skippable_stage_trace(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--message",
                    "执行这个需求：验证 runtime trace 不允许跳过链路步骤",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            session_id = dict(
                line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line
            )["session_id"]
            stage_result_path = (
                Path(temp_dir)
                / "_runtime"
                / "sessions"
                / session_id
                / "roles"
                / "product-definition"
                / "attempt-001"
                / "stage-results"
                / "product-definition-stage-result.json"
            )
            stage_result = json.loads(stage_result_path.read_text())

        self.assertEqual(
            [step["step"] for step in stage_result["steps"]],
            [
                "contract_built",
                "execution_context_built",
                "stage_run_acquired",
                "executor_started",
                "executor_completed",
                "worktree_changes_detected",
                "result_submitted",
                "gate_evaluated",
                "state_advanced",
            ],
        )
        self.assertTrue(all(step["status"] == "ok" for step in stage_result["steps"]))
        self.assertTrue(all("elapsed_seconds" in step for step in stage_result["steps"]))
        self.assertTrue(all("since_previous_seconds" in step for step in stage_result["steps"]))
        self.assertIn("stage_result", stage_result)
        self.assertNotIn("artifact_content", stage_result["stage_result"])
        self.assertNotIn("supplemental_artifacts", stage_result["stage_result"])
        self.assertIn("artifact_path", stage_result["stage_result"])
        self.assertFalse(
            (
                Path(temp_dir)
                / "_runtime"
                / "sessions"
                / session_id
                / "roles"
                / "product-definition"
                / "attempt-001"
                / "stage-results"
                / "product-definition-run-state.json"
            ).exists()
        )
        self.assertFalse(
            (
                Path(temp_dir)
                / "_runtime"
                / "sessions"
                / session_id
                / "roles"
                / "product-definition"
                / "attempt-001"
                / "stage-results"
                / "product-definition-runtime-trace.json"
            ).exists()
        )
        self.assertFalse(
            (
                Path(temp_dir)
                / "_runtime"
                / "sessions"
                / session_id
                / "roles"
                / "product-definition"
                / "attempt-001"
                / "execution-contexts"
                / "product-definition-agent-prompt-bundle.md"
            ).exists()
        )

    def test_runtime_trace_validator_blocks_missing_required_steps(self) -> None:
        from agent_team.runtime_driver import REQUIRED_PASS_TRACE_STEPS, _validate_runtime_trace

        trace = [{"step": step, "status": "ok"} for step in REQUIRED_PASS_TRACE_STEPS[:-1]]
        result = _validate_runtime_trace(trace, required_steps=REQUIRED_PASS_TRACE_STEPS)

        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("state_advanced", result.reason)

    def test_command_executor_timeout_blocks_without_leaving_active_run(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            state_root = root / "state"
            repo_root.mkdir()
            worker_path = root / "slow_worker.py"
            worker_path.write_text("import time\ntime.sleep(30)\n")

            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="验证 timeout",
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                    command_timeout_seconds=1,
                    max_stage_runs=1,
                ),
            )
            store = StateStore(state_root)
            run = store.latest_stage_run(result.session_id, stage="Route")
            session_id = run.session_id if run is not None else result.session_id

            self.assertIsNotNone(run)
            self.assertEqual(run.state if run else "", "BLOCKED")
            active_runs = [item for item in store.stage_runs(session_id) if item.state == "RUNNING"]
            self.assertEqual(active_runs, [])
            self.assertIn("exit code 124", run.blocked_reason if run else "")

    def test_executor_nonzero_completed_result_blocks_as_conflict(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            state_root = root / "state"
            repo_root.mkdir()
            worker_path = root / "stage_worker.py"
            worker_path.write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "stage = os.environ['AGENT_TEAM_STAGE']\n"
                "payload = {\n"
                "  'status': 'completed',\n"
                "  'artifact_content': '# Stage\\n',\n"
                "  'journal': '',\n"
                "  'findings': [],\n"
                "  'evidence': [],\n"
                "  'suggested_next_owner': '',\n"
                "  'summary': stage + ' completed despite executor failure',\n"
                "  'acceptance_status': '',\n"
                "  'blocked_reason': '',\n"
                "}\n"
                "Path(os.environ['AGENT_TEAM_RESULT_BUNDLE']).write_text(json.dumps(payload))\n"
                "sys.exit(2)\n"
            )

            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="执行这个需求：验证 executor/result 冲突",
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                    max_stage_runs=1,
                ),
            )
            run = StateStore(state_root).latest_stage_run(result.session_id, stage="Route")

        self.assertIsNotNone(run)
        self.assertEqual(run.state if run is not None else "", "BLOCKED")
        self.assertIn("executor_result_conflict", run.gate_result.reason if run and run.gate_result else "")
        self.assertEqual(result.status.lower(), "blocked")


    def test_route_transition_error_blocks_without_crashing(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            state_root = root / "state"
            repo_root.mkdir()
            worker_path = root / "bad_route_worker.py"
            worker_path.write_text(
                "import json, os\n"
                "from pathlib import Path\n"
                "payload = {\n"
                "  'status': 'completed',\n"
                "  'artifact_content': '{\"affected_layers\":[\"L1\"], BAD',\n"
                "  'journal': '',\n"
                "  'findings': [],\n"
                "  'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed'}],\n"
                "  'suggested_next_owner': '',\n"
                "  'summary': 'route completed',\n"
                "  'acceptance_status': '',\n"
                "  'blocked_reason': '',\n"
                "}\n"
                "Path(os.environ['AGENT_TEAM_RESULT_BUNDLE']).write_text(json.dumps(payload))\n"
            )

            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="执行这个需求：坏 route json",
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                    max_stage_runs=1,
                ),
            )
            store = StateStore(state_root)
            run = store.latest_stage_run(result.session_id, stage="Route")
            summary = store.load_workflow_summary(result.session_id)

        self.assertEqual(result.status.lower(), "blocked")
        self.assertIsNotNone(run)
        self.assertEqual(run.state if run is not None else "", "BLOCKED")
        self.assertIn("State transition failed", run.blocked_reason if run is not None else "")
        self.assertIn("Expecting", run.blocked_reason if run is not None else "")
        self.assertIn("State transition failed", summary.blocked_reason)

    def test_rework_feedback_is_injected_into_next_attempt_prompt_and_trace(self) -> None:
        from dataclasses import replace

        from agent_team.models import Finding
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            state_root = root / "state"
            repo_root.mkdir()
            store = StateStore(state_root)
            session = store.create_session("验证返工反馈进入下一轮 prompt", runtime_mode="runtime_driver")
            summary = store.load_workflow_summary(session.session_id)
            store.save_workflow_summary(session, replace(summary, current_state="Route", current_stage="Route"))
            store.record_feedback(
                session.session_id,
                Finding(
                    source_stage="Verification",
                    target_stage="Route",
                    issue="必须使用 exact self_verification，不要再输出 self_verification_check。",
                    severity="high",
                    required_evidence=["self_verification"],
                    completion_signal="evidence_by_name.self_verification is present",
                ),
            )
            worker_path = root / "stage_worker.py"
            worker_path.write_text(
                "import json, os\n"
                "from pathlib import Path\n"
                "payload = {\n"
                "  'status': 'completed',\n"
                "  'artifact_content': '{\\\"affected_layers\\\":[\\\"L1\\\"],\\\"required_stages\\\":[]}',\n"
                "  'journal': '',\n"
                "  'findings': [],\n"
                "  'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed'}],\n"
                "  'suggested_next_owner': '',\n"
                "  'summary': 'route completed',\n"
                "  'acceptance_status': '',\n"
                "  'blocked_reason': '',\n"
                "}\n"
                "Path(os.environ['AGENT_TEAM_RESULT_BUNDLE']).write_text(json.dumps(payload))\n"
            )

            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                session_id=session.session_id,
                message="继续",
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                    max_stage_runs=1,
                    trace_prompts=True,
                ),
            )
            store = StateStore(state_root)
            run = store.latest_stage_run(result.session_id, stage="Route")
            context_path = store.latest_execution_context_path(result.session_id, "Route")

            self.assertIsNotNone(run)
            self.assertIsNotNone(context_path)
            prompt_bundle = (
                Path(run.artifact_paths.get("prompt_bundle", ""))
                if run is not None
                else Path("missing")
            )
            if not prompt_bundle.exists():
                self.fail(f"prompt bundle missing: {prompt_bundle}; artifacts={run.artifact_paths if run else {}}")
            prompt_text = prompt_bundle.read_text()
            self.assertIn("必须使用 exact self_verification", prompt_text)
            self.assertIn("self_verification_check", prompt_text)
            self.assertTrue(any(
                step.get("step") == "executor_started"
                and step.get("details", {}).get("attempt") == 1
                and step.get("details", {}).get("actionable_feedback_count") == 1
                for step in (run.steps if run is not None else [])
            ))

    def test_command_stage_records_worktree_changes(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            state_root = root / "state"
            repo_root.mkdir()
            subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True, check=True)
            (repo_root / "existing.txt").write_text("clean baseline\n")
            subprocess.run(["git", "add", "existing.txt"], cwd=repo_root, capture_output=True, text=True, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Agent Team Test",
                    "-c",
                    "user.email=agent-team@example.invalid",
                    "commit",
                    "-m",
                    "init",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            (repo_root / "existing.txt").write_text("dirty before stage\n")
            worker_path = root / "stage_worker.py"
            worker_path.write_text(
                "import json, os\n"
                "from pathlib import Path\n"
                "stage = os.environ['AGENT_TEAM_STAGE']\n"
                "repo = Path(os.environ['AGENT_TEAM_REPO_ROOT'])\n"
                "if stage == 'ProductDefinition':\n"
                "    (repo / 'existing.txt').write_text('dirty after stage\\n')\n"
                "    (repo / 'created.txt').write_text('created by stage\\n')\n"
                "payloads = {\n"
                "  'Route': {'status': 'completed', 'artifact_content': '{\"affected_layers\":[\"L1\"]}', 'journal': '', 'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed'}], 'summary': 'route'},\n"
                "  'ProductDefinition': {'status': 'completed', 'artifact_content': '# Product Definition Delta\\n', 'journal': '', 'evidence': [{'name': 'l1_classification', 'kind': 'artifact', 'summary': 'l1'}], 'summary': 'l1'},\n"
                "}\n"
                "payload = payloads[stage]\n"
                "payload.setdefault('findings', [])\n"
                "payload.setdefault('suggested_next_owner', '')\n"
                "payload.setdefault('acceptance_status', '')\n"
                "payload.setdefault('blocked_reason', '')\n"
                "Path(os.environ['AGENT_TEAM_RESULT_BUNDLE']).write_text(json.dumps(payload))\n"
            )

            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="执行这个需求：验证工作树改动记录",
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                ),
            )
            run = StateStore(state_root).latest_stage_run(result.session_id, stage="ProductDefinition")

        self.assertIsNotNone(run)
        steps = run.steps if run is not None else []
        details = next(step["details"] for step in steps if step["step"] == "worktree_changes_detected")
        self.assertTrue(details["available"])
        self.assertEqual(details["before_dirty_count"], 1)
        self.assertEqual(details["after_dirty_count"], 2)
        self.assertEqual(set(details["changed_file_paths"]), {"created.txt", "existing.txt"})
        by_path = {item["path"]: item for item in details["changed_files"]}
        self.assertEqual(by_path["created.txt"]["change_type"], "new_dirty_file")
        self.assertEqual(by_path["existing.txt"]["change_type"], "content_changed")
        self.assertTrue(by_path["existing.txt"]["preexisting_dirty"])


class RuntimeDriverInteractiveFlowTests(unittest.TestCase):
    def test_interactive_dry_run_stops_at_technical_design_approval_after_product_definition_go(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.stage_machine import StageMachine
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            product_definition_result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="执行这个需求：写个js文件，并打印hello world",
                options=RuntimeDriverOptions(executor="dry-run", interactive=True),
            )
            store = StateStore(state_root)
            session = store.load_session(product_definition_result.session_id)
            summary = store.load_workflow_summary(product_definition_result.session_id)
            store.save_workflow_summary(session, StageMachine().apply_human_decision(summary=summary, decision="go"))
            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                session_id=product_definition_result.session_id,
                options=RuntimeDriverOptions(executor="dry-run", interactive=True),
            )

            self.assertEqual(result.status, "waiting_human")
            self.assertEqual(result.current_state, "WaitForTechnicalDesignApproval")
            self.assertEqual(result.current_stage, "TechnicalDesign")
            self.assertEqual(result.stage_run_count, 2)
            session_dir = Path(temp_dir) / result.session_id
            self.assertTrue((session_dir / "product-definition-delta.md").exists())
            self.assertTrue((session_dir / "project-landing-delta.md").exists())
            self.assertTrue((session_dir / "technical-design.md").exists())

    def test_auto_advance_intermediate_stops_at_final_session_handoff_gate(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.stage_machine import StageMachine
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            product_definition_result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="执行这个需求：写个js文件，并打印hello world",
                options=RuntimeDriverOptions(executor="dry-run", interactive=True),
            )
            store = StateStore(state_root)
            session = store.load_session(product_definition_result.session_id)
            summary = store.load_workflow_summary(product_definition_result.session_id)
            store.save_workflow_summary(session, StageMachine().apply_human_decision(summary=summary, decision="go"))
            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                session_id=product_definition_result.session_id,
                options=RuntimeDriverOptions(
                    executor="dry-run",
                    interactive=True,
                    auto_advance_intermediate=True,
                ),
            )

            self.assertEqual(result.status, "waiting_human")
            self.assertEqual(result.current_state, "WaitForTechnicalDesignApproval")
            self.assertEqual(result.current_stage, "TechnicalDesign")
            self.assertEqual(result.stage_run_count, 2)
            summary = store.load_workflow_summary(product_definition_result.session_id)
            store.save_workflow_summary(session, StageMachine().apply_human_decision(summary=summary, decision="go"))

            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                session_id=product_definition_result.session_id,
                options=RuntimeDriverOptions(
                    executor="dry-run",
                    interactive=True,
                    auto_advance_intermediate=True,
                ),
            )

            self.assertEqual(result.status, "waiting_human")
            self.assertEqual(result.current_state, "WaitForHumanDecision")
            self.assertEqual(result.current_stage, "SessionHandoff")
            self.assertEqual(result.stage_run_count, 5)
            session_dir = Path(temp_dir) / result.session_id
            self.assertTrue((session_dir / "product-definition-delta.md").exists())
            self.assertTrue((session_dir / "project-landing-delta.md").exists())
            self.assertTrue((session_dir / "technical-design.md").exists())
            self.assertTrue((session_dir / "implementation.md").exists())
            self.assertTrue((session_dir / "verification-report.md").exists())
            self.assertTrue((session_dir / "governance-review.md").exists())
            self.assertTrue((session_dir / "acceptance-report.md").exists())
            self.assertTrue((session_dir / "session-handoff.md").exists())

    def test_interactive_driver_blocks_invalid_stage_identity_without_traceback(self) -> None:
        from agent_team.runtime_driver import RuntimeDriverOptions, run_requirement
        from agent_team.stage_machine import StageMachine
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            worker_path = Path(temp_dir) / "bad_stage_worker.py"
            worker_path.write_text(
                "import json, os\n"
                "stage = os.environ['AGENT_TEAM_STAGE']\n"
                "contract = json.loads(open(os.environ['AGENT_TEAM_CONTRACT_PATH']).read())\n"
                "payloads = {\n"
                "  'Route': {'status': 'completed', 'artifact_content': '{\"affected_layers\":[\"L1\",\"L2\",\"L3\"],\"required_stages\":[\"ProductDefinition\",\"ProjectRuntime\",\"TechnicalDesign\"]}', 'journal': '', 'findings': [], 'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed'}], 'summary': 'route'},\n"
                "  'ProductDefinition': {'status': 'completed', 'artifact_content': '# Product Definition Delta\\n', 'journal': '', 'findings': [], 'evidence': [{'name': 'l1_classification', 'kind': 'artifact', 'summary': 'l1'}], 'summary': 'l1'},\n"
                "  'ProjectRuntime': {'status': 'completed', 'artifact_content': '# Project Landing Delta\\n', 'journal': '', 'findings': [], 'evidence': [{'name': 'project_landing_review', 'kind': 'report', 'summary': 'l3'}], 'summary': 'l3'},\n"
                "  'TechnicalDesign': {'status': 'completed', 'artifact_content': '# Technical Design\\n', 'journal': '', 'findings': [], 'evidence': [{'name': 'technical_design_plan', 'kind': 'report', 'summary': 'design'}], 'summary': 'design', 'stage': 'Route'},\n"
                "}\n"
                "payload = payloads[stage]\n"
                "payload.setdefault('suggested_next_owner', '')\n"
                "payload.setdefault('acceptance_status', '')\n"
                "payload.setdefault('blocked_reason', '')\n"
                "open(os.environ['AGENT_TEAM_RESULT_BUNDLE'], 'w').write(json.dumps(payload))\n"
            )

            state_root = Path(temp_dir)
            product_definition_result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                message="执行这个需求：写个js文件，并打印hello world",
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                    interactive=True,
                ),
            )
            store = StateStore(state_root)
            session = store.load_session(product_definition_result.session_id)
            summary = store.load_workflow_summary(product_definition_result.session_id)
            store.save_workflow_summary(session, StageMachine().apply_human_decision(summary=summary, decision="go"))
            result = run_requirement(
                repo_root=repo_root,
                state_root=state_root,
                session_id=product_definition_result.session_id,
                options=RuntimeDriverOptions(
                    executor="command",
                    executor_command=f"{sys.executable} {worker_path}",
                    interactive=True,
                ),
            )
            summary = store.load_workflow_summary(result.session_id)
            run = store.latest_stage_run(result.session_id, stage="TechnicalDesign")

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.current_state, "TechnicalDesign")
            self.assertIn("Invalid stage payload JSON", result.gate_reason)
            self.assertIn("runtime-controlled field(s): stage", result.gate_reason)
            self.assertEqual(summary.blocked_reason, result.gate_reason)
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(run.state, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
