"""依角色讀取機器設定：config/hosts/<role>.yaml，再疊加 config/hosts/local/<role>.yaml（不進 Git）。

共用的值（IP 規劃、埠號、話題名稱）寫在進 Git 的檔案；
只屬於某台實體機器的值（家目錄路徑、裝置序號）寫在 local/ 覆寫檔。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HOSTS_DIR = REPO_ROOT / "config" / "hosts"
ROLES = ("onboard", "vlm", "backend")


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def load_host_config(role: str | None = None, hosts_dir: Path = HOSTS_DIR) -> dict[str, Any]:
    import yaml  # 延遲載入，讓沒用到設定的工具不必安裝 PyYAML

    role = role or os.environ.get("DSN_ROLE")
    if role not in ROLES:
        raise ValueError(f"DSN_ROLE 必須是 {ROLES} 之一，目前為 {role!r}")
    base = yaml.safe_load((hosts_dir / f"{role}.yaml").read_text(encoding="utf-8")) or {}
    local_path = hosts_dir / "local" / f"{role}.yaml"
    if local_path.exists():
        base = _merge(base, yaml.safe_load(local_path.read_text(encoding="utf-8")) or {})
    return _expand(base)
