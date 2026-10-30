#!/usr/bin/env python3
"""檢查本機是否符合所屬角色的環境需求。三台機器都可執行，只用標準函式庫。

    python3 scripts/env_check.py            # 角色讀 DSN_ROLE
    python3 scripts/env_check.py --role onboard
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.provenance import git_state  # noqa: E402

EXPECT_ARCH = {"onboard": "aarch64", "vlm": "x86_64", "backend": "x86_64"}


def sh(*cmd: str) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def torch_info() -> dict:
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "error": type(exc).__name__}
    info = {"installed": True, "version": torch.__version__, "cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available()}
    if info["cuda_available"]:
        info["device"] = torch.cuda.get_device_name(0)
        info["capability"] = ".".join(map(str, torch.cuda.get_device_capability(0)))
        info["arch_list"] = torch.cuda.get_arch_list()
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default=os.environ.get("DSN_ROLE"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    tegra = Path("/etc/nv_tegra_release")
    report = {
        "role": args.role,
        "host": platform.node(),
        "arch": platform.machine(),
        "os": sh("lsb_release", "-ds") or platform.platform(),
        "wsl": "microsoft" in platform.release().lower(),
        "jetson_l4t": tegra.read_text().splitlines()[0] if tegra.exists() else None,
        "python": platform.python_version(),
        "git": sh("git", "--version"),
        "ros_distro": os.environ.get("ROS_DISTRO"),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
        "docker": bool(shutil.which("docker")),
        "nvidia_smi": sh("nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"),
        "torch": torch_info(),
        **git_state(),
    }

    problems = []
    want = EXPECT_ARCH.get(args.role or "")
    if want and report["arch"] != want:
        problems.append(f"角色 {args.role} 預期 {want}，實際 {report['arch']}")
    if args.role == "onboard" and not report["jetson_l4t"]:
        problems.append("找不到 /etc/nv_tegra_release，這台不像 Jetson")
    t = report["torch"]
    if t.get("installed") and args.role in ("vlm", "backend"):
        if not t.get("cuda_available"):
            problems.append("torch 無法使用 CUDA（可能裝到 CPU 版）")
        elif t.get("capability", "").startswith("12") and not any("120" in a for a in t.get("arch_list", [])):
            problems.append("GPU 為 Blackwell（sm_120），但此 torch 未編譯 sm_120，請改裝支援的 CUDA 版本")
    if args.role == "onboard" and t.get("installed") and not t.get("cuda_available"):
        problems.append("Jetson 上 torch 無法用 CUDA：請改用 JetPack 對應的 NVIDIA wheel")
    if report["wsl"] and str(Path.cwd()).startswith("/mnt/"):
        problems.append("WSL 下 repo 位於 /mnt/*，請移到 Linux 家目錄")
    if report["git_dirty"]:
        problems.append("工作區有未提交修改")
    report["problems"] = problems

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for k, v in report.items():
            if k != "problems":
                print(f"{k:14} {v}")
        print("\n" + ("✓ 沒有發現問題" if not problems else "✗ 問題：\n  - " + "\n  - ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
