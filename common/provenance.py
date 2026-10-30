"""每份實驗輸出都要附上的出處紀錄。

回答「這個結果是哪一版程式、哪台機器、哪組設定、哪份標定、哪個模型版本跑出來的」。
在 Docker 映像內沒有 .git 時，改讀 build 時寫入的環境變數 DSN_GIT_COMMIT / DSN_GIT_DESCRIBE。

用法：
    from common.provenance import provenance
    report["provenance"] = provenance(extra={"calibration": "stereo_imx477_2026-11-02.yaml",
                                             "vlm_revision": "<HF revision hash>"})
"""
from __future__ import annotations

import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                             capture_output=True, text=True, timeout=5, check=True)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def git_state() -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD")
    if commit is None:  # 例如 Docker 映像內
        commit = os.environ.get("DSN_GIT_COMMIT")
        describe = os.environ.get("DSN_GIT_DESCRIBE")
        return {"git_commit": commit, "git_describe": describe,
                "git_dirty": None, "git_source": "env" if commit else "unavailable"}
    porcelain = _git("status", "--porcelain", "--untracked-files=normal") or ""
    return {
        "git_commit": commit,
        "git_describe": _git("describe", "--always", "--tags", "--dirty"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(porcelain),
        "git_source": "repo",
    }


def provenance(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "role": os.environ.get("DSN_ROLE"),
        "arch": platform.machine(),
        "python": platform.python_version(),
        **git_state(),
    }
    if extra:
        info.update(extra)
    return info


def require_clean() -> None:
    """正式實驗呼叫：工作區不乾淨就拒絕執行，避免產生無法追溯的結果。"""
    state = git_state()
    if state["git_dirty"]:
        raise RuntimeError(
            f"工作區有未提交修改（{state['git_describe']}）。請先 commit，或改用 --allow-dirty 做非正式測試。")


if __name__ == "__main__":
    import json
    print(json.dumps(provenance(), ensure_ascii=False, indent=2))
