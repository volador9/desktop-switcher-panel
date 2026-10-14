"""拉取 / 更新 VirtualDesktopAccessor.dll。

Windows 大版本更新后，未公开的虚拟桌面接口可能变化，届时需要同步更新这个 DLL：

    python tools/fetch_dll.py            # 下载最新 release
    python tools/fetch_dll.py v0.0.49-extra.2   # 下载指定 tag

仓库自带一份 DLL 以便克隆后直接运行，此脚本用于以后手动升级。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request

REPO = "Lej77/VirtualDesktopAccessor"
DLL_NAME = "VirtualDesktopAccessor.dll"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, DLL_NAME)


def api(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "fetch-dll"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    url = (
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"
        if tag
        else f"https://api.github.com/repos/{REPO}/releases/latest"
    )

    try:
        release = api(url)
    except Exception as exc:
        print(f"查询 release 失败：{exc}")
        return 1

    asset = next(
        (a for a in release.get("assets", []) if a["name"] == DLL_NAME), None
    )
    if asset is None:
        print(f"{release.get('tag_name')} 中没有 {DLL_NAME}")
        return 1

    if os.path.exists(TARGET):
        backup = TARGET + ".bak"
        shutil.copy2(TARGET, backup)
        print(f"已备份原 DLL 到 {os.path.basename(backup)}")

    print(f"下载 {release['tag_name']} → {DLL_NAME} （{asset['size'] // 1024} KB）")
    req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "fetch-dll"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(TARGET, "wb") as fh:
        shutil.copyfileobj(resp, fh)

    print("完成。可运行 python selftest.py 验证。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
