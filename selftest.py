"""临时自检脚本：验证 VirtualDesktopAccessor.dll 在本机可用。"""
import ctypes
import os
import sys

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VirtualDesktopAccessor.dll")

if not os.path.exists(DLL):
    sys.exit(f"找不到 DLL: {DLL}")

try:
    vda = ctypes.CDLL(DLL)
except OSError as e:
    sys.exit(f"加载 DLL 失败: {e}")

# 只声明需要用到的导出函数
vda.GetDesktopCount.restype = ctypes.c_int
vda.GetCurrentDesktopNumber.restype = ctypes.c_int
vda.GetDesktopName.restype = ctypes.c_int
vda.GoToDesktopNumber.argtypes = [ctypes.c_int]
vda.GoToDesktopNumber.restype = ctypes.c_int


def get_name(index: int) -> str:
    buf = ctypes.create_string_buffer(256)
    ok = vda.GetDesktopName(index, buf, ctypes.sizeof(buf))
    if ok < 0:
        return ""
    return buf.value.decode("utf-8", "replace")


count = vda.GetDesktopCount()
cur = vda.GetCurrentDesktopNumber()

print(f"桌面总数 = {count}")
print(f"当前桌面 = {cur}  (0 基索引)")
for i in range(count):
    marker = " <== 当前" if i == cur else ""
    print(f"  [{i}] {get_name(i) or '(未命名)'}{marker}")

# 切到自身属于无副作用的写操作，用来确认写接口也通
r = vda.GoToDesktopNumber(cur)
print(f"GoToDesktopNumber({cur}) 返回 = {r}  (期望 0)")

print("RESULT: DLL 可用" if count > 0 and cur >= 0 else "RESULT: 异常，接口返回值不合法")
