"""NextraAxisVM worker: one long-lived process started by the MCP bridge (bridge/server/index.js).

Protocol: one JSON object per line.
  in : {"id": 1, "tool": "query", "args": {...}}
  out: {"id": 1, "ok": true, "text": "...", "images": ["C:/.../x.png"]}
All COM work happens on the main thread (single-threaded apartment). A reader thread takes requests from stdin and
answers `status` itself, so the bridge can ask what AxisVM is doing while a long call (analysis, import) runs.
"""
import json
import os
import queue
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

PROTO = sys.stdout                    # the real stdout carries the protocol only
sys.stdout = sys.stderr               # any library print goes to stderr (the bridge logs it)

from nextra_axisvm import core        # noqa: E402

_lock = threading.Lock()


def send(obj):
    line = json.dumps(obj, ensure_ascii=False)
    with _lock:
        PROTO.write(line + "\n")
        PROTO.flush()


def reader(q):
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if msg.get("tool") == "__status":       # answered without COM, even while the main thread is busy
            try:
                text, imgs = core.status(msg.get("args") or {})
                send({"id": msg.get("id"), "ok": True, "text": text, "images": imgs})
            except Exception as e:
                send({"id": msg.get("id"), "ok": False, "text": "status failed: %s" % e, "images": []})
            continue
        q.put(msg)
    q.put(None)                                  # stdin closed: bridge is gone


def main():
    import comtypes
    comtypes.CoInitialize()
    q = queue.Queue()
    threading.Thread(target=reader, args=(q,), daemon=True).start()
    send({"id": 0, "ok": True, "text": "ready", "images": [], "pid": os.getpid()})
    while True:
        msg = q.get()
        if msg is None:
            break
        rid, tool, args = msg.get("id"), msg.get("tool"), msg.get("args") or {}
        core.BUSY.update(tool=tool, since=time.time())
        try:
            reply = core.dispatch(tool, args)
            send({"id": rid, "ok": reply.ok, "text": reply.text(), "images": reply.images})
        except Exception as e:                   # dispatch already formats NxError; this is a last resort
            send({"id": rid, "ok": False, "text": "internal error: %s\n%s" % (e, traceback.format_exc(limit=4)), "images": []})
        finally:
            core.BUSY.update(tool=None, since=None)


if __name__ == "__main__":
    main()
