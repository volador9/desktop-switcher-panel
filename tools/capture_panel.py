"""临时工具：截取面板所在区域，用于开发期验证外观。"""
import ctypes
import ctypes.wintypes as wt
import sys

from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wt.HWND


def find_panel() -> int:
    hwnd = user32.FindWindowW(None, "桌面切换面板")
    return int(hwnd or 0)


def rect_of(hwnd: int):
    r = wt.RECT()
    if not user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


def main() -> int:
    hwnd = find_panel()
    if not hwnd:
        print("未找到面板窗口")
        return 1
    box = rect_of(hwnd)
    print("面板句柄:", hwnd, "区域:", box)

    # 以面板为中心向外扩一圈，便于观察与壁纸的对比
    pad = 40
    l, t, r, b = box
    shot = ImageGrab.grab(bbox=(l - pad, t - pad, r + pad, b + pad))
    out = sys.argv[1] if len(sys.argv) > 1 else "panel_shot.png"
    shot.save(out)
    print("已保存:", out, shot.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
