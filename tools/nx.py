"""Talk to the NextraAxisVM MCP bridge like an AI client does (stdio JSON-RPC), for manual tests and the regression suite.

  python tools/nx.py query '{"scope":"instances"}'
  python tools/nx.py edit '{"ops":"beam 0,0,0 6,0,0 sec=IPE 300 mat=S 235"}' query '{}'
Several tool/args pairs run in one session (binding and checkpoints persist). Images are reported by size.
"""
import base64
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Client:
    def __init__(self, server=None, env=None):
        server = server or os.path.join(ROOT, "bridge", "server", "index.js")
        self.p = subprocess.Popen(["node", server], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env={**os.environ, **(env or {})}, text=True, encoding="utf-8", bufsize=1)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "nx", "version": "0"}})

    def rpc(self, method, params):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params}) + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("bridge closed")
            msg = json.loads(line)
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]

    def call(self, tool, args=None):
        res = self.rpc("tools/call", {"name": tool, "arguments": args or {}})
        text = "\n".join(c["text"] for c in res["content"] if c["type"] == "text")
        imgs = [base64.b64decode(c["data"]) for c in res["content"] if c["type"] == "image"]
        return text, imgs, bool(res.get("isError"))

    def close(self):
        self.p.stdin.close()
        self.p.wait(10)


if __name__ == "__main__":
    c = Client()
    tools = c.rpc("tools/list", {})["tools"]
    if len(sys.argv) < 2:
        print("tools:", ", ".join(t["name"] for t in tools), "· schema chars:", len(json.dumps(tools)))
    it = iter(sys.argv[1:])
    for tool in it:
        args = json.loads(next(it, "{}"))
        text, imgs, err = c.call(tool, args)
        print(">>> %s %s%s\n%s%s" % (tool, json.dumps(args)[:150], " [ERROR]" if err else "", text,
                                    "".join("\n[image %d bytes]" % len(i) for i in imgs)))
    c.close()
