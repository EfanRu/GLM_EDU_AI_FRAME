#!/usr/bin/env python3
"""MCP-сервер инструментов тестирования (уровень L4).

Ноль внешних зависимостей: протокол MCP — это JSON-RPC 2.0 поверх stdio
(одна JSON-строка = один запрос/ответ). Любой MCP-клиент (ZCode, Claude,
наш tools/mcp_client.py) получает доступ к инструментам:

  run_tests(test_file)  — запустить pytest-файл против эталонного ordercalc
  coverage(test_file)   — покрытие line/branch через coverage.py
  read_source(module)   — прочитать исходник модуля ordercalc
  bug_scan(test_file)   — (только для оценки/CI) прогон против 5 баг-вариантов

Зачем это надо: агент перестаёт «угадывать» результат — он вызывает инструменты
так же, как разработчик вызывает команды. MCP = стандартный способ подключать
инструменты к любой агентной среде.

Запуск (обычно его запускает клиент, а не вы):
    python mcp_testserver.py            # слушает stdin, пишет в stdout

Ручная проверка протокола:
    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python mcp_testserver.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo_project" / "ordercalc"
VARIANTS = ROOT / "demo_project" / "variants"

TOOLS = [
    {
        "name": "run_tests",
        "description": "Запустить pytest-файл против эталонной библиотеки ordercalc. "
                       "Возвращает вывод pytest (хвост до 2500 символов).",
        "inputSchema": {
            "type": "object",
            "properties": {"test_file": {"type": "string", "description": "путь к test_ordercalc.py"}},
            "required": ["test_file"],
        },
    },
    {
        "name": "coverage",
        "description": "Покрытие ordercalc (line и branch, %) при выполнении тест-файла.",
        "inputSchema": {
            "type": "object",
            "properties": {"test_file": {"type": "string"}},
            "required": ["test_file"],
        },
    },
    {
        "name": "read_source",
        "description": "Прочитать исходник модуля ordercalc: discounts | split | loyalty.",
        "inputSchema": {
            "type": "object",
            "properties": {"module": {"type": "string", "enum": ["discounts", "split", "loyalty"]}},
            "required": ["module"],
        },
    },
    {
        "name": "bug_scan",
        "description": "ОЦЕНКА/CI: прогон тестов против 5 посеянных баг-вариантов, "
                       "возвращает, какие баги пойманы. НЕ давать генерирующим агентам "
                       "во время эксперимента (см. CRITERIA.md).",
        "inputSchema": {
            "type": "object",
            "properties": {"test_file": {"type": "string"}},
            "required": ["test_file"],
        },
    },
]


def _sandbox(test_file: Path, module_override: Path | None = None) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="mcp_tests_"))
    shutil.copytree(DEMO, tmp / "ordercalc")
    if module_override is not None:
        shutil.copy(module_override, tmp / "ordercalc" / module_override.name)
    shutil.copy(test_file, tmp / "test_ordercalc.py")
    return tmp


def _pytest(tmp: Path, extra: list[str] | None = None, max_chars: int = 2500) -> str:
    cmd = [sys.executable, "-m", "pytest", "test_ordercalc.py", "-q", "--no-header", "--tb=short"]
    if extra:
        cmd = extra
    proc = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=180)
    out = (proc.stdout + proc.stderr).strip()
    return out[-max_chars:] if len(out) > max_chars else out


def tool_run_tests(args) -> str:
    tmp = _sandbox(Path(args["test_file"]))
    try:
        return _pytest(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def tool_coverage(args) -> str:
    tmp = _sandbox(Path(args["test_file"]))
    try:
        _pytest(tmp, extra=[sys.executable, "-m", "coverage", "run", "--source=ordercalc",
                            "--branch", "-m", "pytest", "test_ordercalc.py", "-q"])
        proc = subprocess.run([sys.executable, "-m", "coverage", "report", "-m"],
                              cwd=tmp, capture_output=True, text=True, timeout=60)
        return proc.stdout.strip()[-2500:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def tool_read_source(args) -> str:
    return (DEMO / f"{args['module']}.py").read_text()


def tool_bug_scan(args) -> str:
    test_file = Path(args["test_file"])
    results = {}
    for bug_dir in sorted(VARIANTS.glob("bug*")):
        override = next(bug_dir.glob("*.py"))
        tmp = _sandbox(test_file, module_override=override)
        try:
            out = _pytest(tmp, max_chars=200)
            results[bug_dir.name] = "CAUGHT" if "failed" in out else "missed"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    caught = sum(1 for v in results.values() if v == "CAUGHT")
    return json.dumps({"caught": caught, "total": len(results), "details": results}, ensure_ascii=False)


HANDLERS = {"run_tests": tool_run_tests, "coverage": tool_coverage,
            "read_source": tool_read_source, "bug_scan": tool_bug_scan}


def handle(msg: dict) -> dict | None:
    method, msg_id = msg.get("method"), msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ordercalc-test-tools", "version": "1.0.0"},
        }}
    if method == "notifications/initialized":
        return None  # уведомление — без ответа
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = msg["params"]["name"], msg["params"].get("arguments", {})
        try:
            text = HANDLERS[name](args)
            return {"jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}}
    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown method {method}"}}
    return None


def main() -> int:
    for line in sys.stdin:  # MCP over stdio: строка JSON -> строка JSON
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
