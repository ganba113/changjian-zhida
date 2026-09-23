#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR 离线依赖下载脚本（在有网络的机器上运行一次，产出 wheel 到 backend/wheels/）

用法（Windows / Linux 均可，需 Python 3.8+）：
    python deploy/download_ocr.py

说明：
- 目标平台：openEuler aarch64（鲲鹏 ARM）+ Python 3.9
- 采用 RapidOCR（onnxruntime 后端），模型内置于 rapidocr_onnxruntime 包，无需单独下载模型
- onnxruntime / numpy 已在 backend/wheels/ 中，本脚本不重复下载
- 版本锁定原因（务必保留，否则离线部署会失败）：
    opencv-python-headless==4.9.0.80   # 4.10+/5.x 依赖 numpy 2.x，与本项目 numpy 1.24.4 冲突
    shapely==2.0.5                     # rapidocr 要求 !=2.0.4；2.1.x 要求 Python>=3.10（服务器是 3.9.9）
    pyclipper==1.3.0.post5             # 最新 1.4.0 未提供 aarch64 wheel
    Pillow==10.4.0                     # 12.x 无 cp39 wheel
- 必须带 --python-version 39：rapidocr_onnxruntime 的 Requires-Python <3.13，
  在本机较新 Python 上不加该参数会被 pip 忽略
- 镜像默认阿里云（支持 --platform 跨平台下载；清华镜像不支持，官方 PyPI 国内慢）
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(os.path.dirname(HERE), "backend")
WHEELS_DIR = os.path.join(BACKEND_DIR, "wheels")

# 默认阿里云镜像：已验证支持 --platform 跨平台下载 aarch64 wheel
# （清华镜像的 simple index 不支持 --platform 跨平台下载，会报 "from versions: none"；
#   官方 PyPI 支持但国内下载慢）
INDEX_URL = os.environ.get("PIP_INDEX_URL", "https://mirrors.aliyun.com/pypi/simple/")

# 纯 Python（any wheel）：无需 --platform
ANY_PACKAGES = [
    ("rapidocr_onnxruntime==1.4.4", "OCR 核心（onnxruntime 后端，内置模型）"),
    ("six==1.16.0", "兼容层"),
    ("tqdm==4.66.5", "进度条"),
]

# 含二进制扩展（需 aarch64 wheel）：需 --platform
BIN_PACKAGES = [
    ("opencv-python-headless==4.9.0.80", "图像解码/预处理"),
    ("pyclipper==1.3.0.post5", "DB 检测框后处理"),
    ("shapely==2.0.5", "几何计算"),
    ("PyYAML==6.0.1", "配置解析"),
    ("Pillow==10.4.0", "图像读取"),
    ("PyMuPDF==1.26.0", "PDF 文本提取与扫描页渲染"),
]


def run_download(specs, platform=None):
    cmd = [sys.executable, "-m", "pip", "download", *specs]
    cmd += ["--python-version", "39"]
    if platform:
        cmd += ["--platform", platform]
    cmd += ["--only-binary=:all:", "--no-deps", "-d", WHEELS_DIR, "-i", INDEX_URL]
    print("  $ " + " ".join(cmd) + "\n")
    return subprocess.run(cmd).returncode


def main():
    os.makedirs(WHEELS_DIR, exist_ok=True)
    print("=" * 62)
    print(" 下载 OCR 离线依赖（aarch64 / Python 3.9）")
    print(f" 目标目录: {WHEELS_DIR}")
    print(f" 镜像:     {INDEX_URL}")
    print("=" * 62)

    print("\n[1/2] 纯 Python 包：")
    for spec, desc in ANY_PACKAGES:
        print(f"  - {spec:42s} {desc}")
    rc = run_download([p for p, _ in ANY_PACKAGES])
    if rc != 0:
        print("\n!! 纯 Python 包下载失败。")
        sys.exit(rc)

    print("\n[2/2] aarch64 二进制包：")
    for spec, desc in BIN_PACKAGES:
        print(f"  - {spec:42s} {desc}")
    rc = run_download([p for p, _ in BIN_PACKAGES], platform="manylinux_2_17_aarch64")
    if rc != 0:
        print("\n!! aarch64 二进制包下载失败。可重试，或换镜像：")
        print("   PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple python deploy/download_ocr.py")
        sys.exit(rc)

    print("\n已下载 wheel：")
    for fn in sorted(os.listdir(WHEELS_DIR)):
        if fn.endswith(".whl"):
            size = os.path.getsize(os.path.join(WHEELS_DIR, fn)) / 1024 / 1024
            print(f"  {fn}  ({size:.1f} MB)")
    print("\n完成。将 backend/wheels/ 一并打包进部署包，服务器 install.sh 会自动离线安装。")


if __name__ == "__main__":
    main()
