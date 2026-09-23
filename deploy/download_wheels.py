#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载项目全部离线依赖（aarch64 wheel），用于换电脑 / 重建开发环境

用法（有网环境，Windows / Linux 均可，Python 3.8+）：
    python deploy/download_wheels.py

产出：backend/wheels/ 下全部 wheel（主依赖 + OCR 依赖，共约 45 个）

说明：
- 目标平台：openEuler aarch64（鲲鹏 ARM）+ Python 3.9
- 镜像默认阿里云（支持 --platform 跨平台下载；清华镜像不支持，会报 "from versions: none"）
- 主依赖用完整解析（pip 自动拉传递依赖，requirements.txt 已锁版本）
- OCR 依赖用 --no-deps（rapidocr 声明依赖 opencv-python，本项目用 headless 替代，
  二者是不同包名 pip 无法自动替代，完整解析会报错）
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(os.path.dirname(HERE), "backend")
WHEELS_DIR = os.path.join(BACKEND_DIR, "wheels")

INDEX_URL = os.environ.get("PIP_INDEX_URL", "https://mirrors.aliyun.com/pypi/simple/")

BASE_CMD = [
    sys.executable, "-m", "pip", "download",
    "--platform", "manylinux_2_17_aarch64",
    "--python-version", "39",
    "--only-binary=:all:",
    "-d", WHEELS_DIR,
    "-i", INDEX_URL,
]


def run(cmd):
    print("  $ " + " ".join(cmd) + "\n")
    return subprocess.run(cmd).returncode


def main():
    os.makedirs(WHEELS_DIR, exist_ok=True)
    print("=" * 62)
    print(" 下载全部离线依赖（aarch64 / Python 3.9）")
    print(f" 目标目录: {WHEELS_DIR}")
    print(f" 镜像:     {INDEX_URL}")
    print("=" * 62)

    print("\n[1/2] 主依赖（完整解析，pip 自动拉传递依赖）")
    rc = run(BASE_CMD + ["-r", os.path.join(BACKEND_DIR, "requirements.txt")])
    if rc != 0:
        print("\n!! 主依赖下载失败。可换镜像重试：")
        print("   PIP_INDEX_URL=https://pypi.org/simple python deploy/download_wheels.py")
        sys.exit(rc)

    print("\n[2/2] OCR 依赖（--no-deps，避免 opencv-python 冲突）")
    rc = run(BASE_CMD + ["--no-deps", "-r", os.path.join(BACKEND_DIR, "requirements-ocr.txt")])
    if rc != 0:
        print("\n!! OCR 依赖下载失败。")
        sys.exit(rc)

    whls = sorted(f for f in os.listdir(WHEELS_DIR) if f.endswith(".whl"))
    print(f"\n完成，共 {len(whls)} 个 wheel：")
    for fn in whls:
        size = os.path.getsize(os.path.join(WHEELS_DIR, fn)) / 1024 / 1024
        print(f"  {fn}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
