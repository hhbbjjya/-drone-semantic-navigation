import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import provenance as prov
from common.config import load_host_config, ROLES


class ProvenanceTests(unittest.TestCase):
    def test_has_required_fields(self):
        info = prov.provenance(extra={"calibration": "x.yaml"})
        for key in ("time_utc", "host", "arch", "git_commit", "git_source", "calibration"):
            self.assertIn(key, info)

    def test_env_fallback_when_no_git(self):
        with mock.patch.object(prov, "_git", return_value=None), \
             mock.patch.dict(os.environ, {"DSN_GIT_COMMIT": "abc123", "DSN_GIT_DESCRIBE": "v2.1"}):
            state = prov.git_state()
        self.assertEqual(state["git_commit"], "abc123")
        self.assertEqual(state["git_source"], "env")
        self.assertIsNone(state["git_dirty"])

    def test_require_clean_rejects_dirty(self):
        with mock.patch.object(prov, "git_state", return_value={"git_dirty": True, "git_describe": "x-dirty"}):
            with self.assertRaises(RuntimeError):
                prov.require_clean()


class HostConfigTests(unittest.TestCase):
    def test_every_role_file_loads(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML 未安裝")
        for role in ROLES:
            cfg = load_host_config(role)
            self.assertEqual(cfg["role"], role)

    def test_local_override_merges(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML 未安裝")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "local").mkdir()
            (d / "vlm.yaml").write_text("role: vlm\npaths: {data: a, models: b}\n")
            (d / "local" / "vlm.yaml").write_text("paths: {data: c}\n")
            cfg = load_host_config("vlm", hosts_dir=d)
        self.assertEqual(cfg["paths"], {"data": "c", "models": "b"})

    def test_rejects_unknown_role(self):
        with self.assertRaises(ValueError):
            load_host_config("ugv")


if __name__ == "__main__":
    unittest.main()
