"""配置读写：存放于 %APPDATA%\\DesktopSwitcherPanel\\config.json。"""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "DesktopSwitcherPanel"

CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict = {
    "pos": None,            # [x, y]，None 表示首次启动自动贴右下角
    "opacity": 0.92,        # 面板不透明度
    "theme": "dark",        # dark | light
    "compact": False,       # 紧凑模式：只显示当前桌面
    "hotkeys": True,        # 是否启用全局热键
    "animate": False,       # 切换桌面时是否保留系统动画
    "autostart": False,     # 开机自启（写入 HKCU Run）
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            # 只接受已知键，避免配置被写坏后污染运行
            cfg.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except OSError:
        pass
