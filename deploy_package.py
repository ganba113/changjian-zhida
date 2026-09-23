#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包部署包：把 backend + dist + deploy 打包为 changjian-zhida-deploy.zip

用法：python deploy_package.py
产物：<workspace>/changjian-zhida-deploy.zip，内结构 changjian-zhida/{backend,dist,deploy}/
排除：chat.db（数据）、.env（配置）、__pycache__、*.pyc
"""
import os
import zipfile

WS = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(WS, "changjian-zhida-deploy.zip")

BACKEND_SRC = os.path.join(WS, "backend")
DIST_SRC = os.path.join(WS, "frontend", "changjian-zhida", "dist")
DEPLOY_SRC = os.path.join(WS, "deploy")

EXCLUDE_DIRS = {"__pycache__", ".git"}


def should_skip(f: str) -> bool:
    """排除数据库文件（含 WAL/SHM）、.env 配置、字节码缓存。"""
    if f == ".env" or f.endswith(".pyc"):
        return True
    # chat.db / chat.db-wal / chat.db-shm 等 SQLite 数据文件
    if f.startswith("chat.db"):
        return True
    return False


def add_tree(zf, src, arc_prefix):
    if not os.path.isdir(src):
        print(f"  !! 目录不存在，跳过: {src}")
        return
    count = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if should_skip(f):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src)
            arc = os.path.join(arc_prefix, rel).replace("\\", "/")
            zf.write(full, arc)
            count += 1
    print(f"  {arc_prefix}/  {count} 个文件")


def main():
    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)
    print(f"打包部署包 -> {ZIP_PATH}")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        add_tree(zf, BACKEND_SRC, "changjian-zhida/backend")
        add_tree(zf, DIST_SRC, "changjian-zhida/dist")
        add_tree(zf, DEPLOY_SRC, "changjian-zhida/deploy")
    size = os.path.getsize(ZIP_PATH) / 1024 / 1024
    print(f"\n完成：{ZIP_PATH}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
