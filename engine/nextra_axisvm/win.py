"""Small Win32 helpers through ctypes (no COM): process liveness, AxisVM processes, dialog windows."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def alive(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return ctypes.get_last_error() == 5          # access denied: exists (other user / elevated)
    try:
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def exe_path(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def axisvm_pids():
    """All running AxisVM executables (with or without the add-on)."""
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower().startswith("axisvm"):
                out.append(int(e.th32ProcessID))
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def windows(pid):
    """Visible top-level windows of a process: [(hwnd, title, class, enabled)]."""
    res = []

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            t = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, t, n + 1)
            c = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, c, 256)
            res.append((hwnd, t.value, c.value, bool(user32.IsWindowEnabled(hwnd))))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return res


def dialogs(pid):
    """Modal windows: while a modal dialog is up, Windows disables the owner (AxisVM's main window); the enabled
    visible windows are the dialog(s). Standard dialog boxes (#32770) are always reported."""
    ws = windows(pid)
    modal = any(not en for _, _, _, en in ws)
    return [(t or "(untitled)", c) for _, t, c, en in ws if en and (modal or c == "#32770")]
