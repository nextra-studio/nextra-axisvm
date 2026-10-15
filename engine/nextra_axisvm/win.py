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


# ------------------------------------------------------------------ dialog inspection / capture / answer
def _children(hwnd):
    out = []

    def cb(c, _):
        n = user32.GetWindowTextLengthW(c)
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(c, b, n + 1)
        k = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(c, k, 128)
        out.append((c, k.value, b.value))
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return out


def dialog_details(pid):
    """[(hwnd, title, class, [button captions], [static texts])] of the modal windows of a process."""
    ws = windows(pid)
    modal = any(not en for _, _, _, en in ws)
    out = []
    for hwnd, title, cls, en in ws:
        if not en or not (modal or cls == "#32770"):
            continue
        kids = _children(hwnd)
        buttons = [t.replace("&", "") for _, k, t in kids if "button" in k.lower() and t.strip()]
        texts = [t for _, k, t in kids if ("static" in k.lower() or "label" in k.lower()) and t.strip()]
        out.append((hwnd, title or "(untitled)", cls, buttons, texts))
    return out


def capture(hwnd, path):
    """Screenshot of one window (PrintWindow, works when covered) -> PNG path."""
    from PIL import Image
    gdi32 = ctypes.WinDLL("gdi32")
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    try:
        user32.PrintWindow(hwnd, mdc, 2)

        class BI(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("a", ctypes.c_uint32), ("b", ctypes.c_int32), ("c", ctypes.c_int32), ("d", ctypes.c_uint32), ("e", ctypes.c_uint32)]

        bi = BI(ctypes.sizeof(BI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB").save(path)
        return path
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)


BM_CLICK = 0x00F5


def click(pid, caption):
    """Press the button with this caption (case-insensitive, '&' ignored) in AxisVM's modal dialog."""
    want = caption.replace("&", "").strip().lower()
    for hwnd, title, cls, buttons, _ in dialog_details(pid):
        for c, k, t in _children(hwnd):
            if "button" in k.lower() and t.replace("&", "").strip().lower() == want:
                user32.PostMessageW(c, BM_CLICK, 0, 0)
                return "pressed '%s' in '%s'" % (t.replace("&", ""), title)
    return None
