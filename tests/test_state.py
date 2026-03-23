import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StateTests(unittest.TestCase):
    def test_state_store_initializes_session_and_artifacts(self) -> None:
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("demo")

            self.assertTrue((Path(temp_dir) / "sessions" / session.session_id / "session.json").exists())
            self.assertTrue((Path(temp_dir) / "artifacts" / session.session_id).exists())

    def test_state_store_creates_unique_session_ids_for_same_request(self) -> None:
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            first = store.create_session("repeatable request")
            second = store.create_session("repeatable request")

            self.assertNotEqual(first.session_id, second.session_id)

    def test_apply_learning_ignores_unknown_target_stage(self) -> None:
        from ai_company.models import Finding
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            store.apply_learning(
                Finding(
                    source_stage="QA",
                    target_stage="../../outside",
                    issue="malicious target",
                    lesson="ignore invalid targets",
                )
            )

            self.assertFalse((root / "memory" / ".." / ".." / "outside").exists())

    def test_load_role_profiles_reads_context_and_memory(self) -> None:
        from ai_company.roles import load_role_profiles

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            roles = load_role_profiles(repo_root=repo_root, state_root=state_root)

            self.assertIn("Product", roles)
            self.assertIn("Dev", roles)
            self.assertIn("Product Manager Onboarding Manual", roles["Product"].effective_context_text)
            self.assertIn("Initialized memory system", roles["Product"].effective_memory_text)


if __name__ == "__main__":
    unittest.main()
