#!/usr/bin/env python3
"""Простейший MCP-клиент (CLI): подключиться к серверу, вызвать инструмент, выйти.

Показывает, что MCP — это обычный JSON-RPC поверх stdio: никакого волшебства.

Примеры:
    python tools/mcp_client.py list
    python tools/mcp_client.py call read_source '{"module": "split"}'
    python tools/mcp_client.py call run_tests '{"test_file": "results/runs/NAME/test_ordercalc.py"}'
    python tools/mcp_client.py call coverage '{"test_file": "results/runs/NAME/test_ordercalc.py"}'
"""

import json
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "levels" / "level4_mcp_multiagent" / "mcp_testserver.py"


def rpc(proc: subprocess.Popen, msg: dict) -> dict:
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP-сервер закрыл поток")
        resp = json.loads(line)
        if resp.get("id") == msg.get("id"):
            return resp


def main() -> int:
    cmd, arg = (sys.argv[1:3] + [""])[:2]
    proc = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                   "params": {"protocolVersion": "2024-11-05", "capabilities": {}}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        if cmd == "list":
            resp = rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            for t in resp["result"]["tools"]:
                print(f"- {t['name']}: {t['description'].splitlines()[0]}")
        elif cmd == "call":
            resp = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": sys.argv[2], "arguments": json.loads(sys.argv[3] or "{}")}})
            for c in resp["result"]["content"]:
                print(c["text"])
        else:
            print(__doc__)
            return 2
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
