#!/usr/bin/env python3
"""Уровень L4: мультиагентный конвейер генерации тестов (аналитик -> писатель -> критик).

Каждая роль — отдельный вызов LLM со своей узкой задачей и своим промптом.
Критик единственный получает доступ к инструментам через MCP-сервер
(levels/level4_mcp_multiagent/mcp_testserver.py) — запускает тесты и покрытие,
правит файл итеративно. Итог конвейера обязан быть «зелёным».

Зачем мультиагентность: как в команде — аналитик думает о полноте плана,
писатель пишет, критик безжалостно проверяет. Каждый шаг дешевле и точнее,
чем один «супер-промпт», и каждый артефакт (план, тесты, лог правок)
остаётся в репозитории для ревью.

Запуск (нужен ключ, см. SETUP.md):
    export LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=...
    python multiagent_pipeline.py --out ../../results/runs/l4_multi_glm46
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "levels" / "level1_api"))
from direct_api import compose_prompt  # noqa: E402

HERE = Path(__file__).parent
SOURCE = compose_prompt()


def llm(base_url, api_key, model, system, user, temperature=0.2) -> tuple[str, dict]:
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={"model": model, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}],
              "temperature": temperature, "max_tokens": 8192},
        headers={"Authorization": f"Bearer {api_key}"}, timeout=600,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def mcp_tool(name: str, arguments: dict) -> str:
    """Вызов инструмента через настоящий MCP-сервер (subprocess, JSON-RPC stdio)."""
    proc = subprocess.Popen([sys.executable, "-m", "mcp_testserver"], cwd=HERE,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)
    try:
        def rpc(msg):
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
            while True:
                r = json.loads(proc.stdout.readline())
                if r.get("id") == msg["id"]:
                    return r
        rpc({"jsonrpc": "2.0", "id": 0, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {}}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        r = rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": name, "arguments": arguments}})
        return r["result"]["content"][0]["text"]
    finally:
        proc.terminate()


ANALYST_SYSTEM = """Ты — QA-аналитик. Твоя работа — НЕ писать код, а составить план тестирования. \
Для каждой публичной функции библиотеки перечисли: типовые случаи, граничные условия \
(пороги, нули, пустые входы, даты), невалидные входы и ожидаемое поведение. Указывай \
конкретные числа-примеры. Формат — markdown."""
WRITER_SYSTEM = """Ты — Python-инженер, пишешь тесты строго по плану аналитика. \
Один файл test_ordercalc.py, только pytest и стандартная библиотека, импорты \
`from ordercalc.<module> import ...`. Тесты обязаны проходить на эталонном коде. \
Ответ — только ```python-блок."""
CRITIC_SYSTEM = """Ты — критический ревьюер тестов. У тебя есть MCP-инструменты: \
run_tests и coverage (вызываю их за тебя по твоему запросу — попроси \
«RUN_TESTS» или «COVERAGE», указав путь к файлу). Твоя задача: запустить тесты, \
найти падения и дыры покрытия, исправить файл. Когда всё зелёное и покрытие высокое — \
верни финальный полный код файла одним ```python-блоком."""


def save_code(reply: str, path: Path) -> None:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.DOTALL)
    path.write_text((m.group(1) if m else reply).strip() + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/paas/v4"))
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "glm-4.6"))
    ap.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""))
    ap.add_argument("--critic-iters", type=int, default=3)
    args = ap.parse_args()
    if not args.api_key:
        print("Нет ключа: задайте LLM_API_KEY (см. SETUP.md)", file=sys.stderr)
        return 2

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
    t0 = time.time()

    def call(system, user, tag):
        content, usage = llm(args.base_url, args.api_key, args.model, system, user)
        usage_total["prompt_tokens"] += usage.get("prompt_tokens", 0)
        usage_total["completion_tokens"] += usage.get("completion_tokens", 0)
        (out / f"{tag}.txt").write_text(content)
        return content

    # 1) АНАЛИТИК: план тестирования из исходников
    plan = call(ANALYST_SYSTEM, f"Исходники библиотеки:\n\n{SOURCE}", "analyst")
    (out / "plan.md").write_text(plan)

    # 2) ПИСАТЕЛЬ: тесты строго по плану
    draft = call(WRITER_SYSTEM, f"План тестирования аналитика:\n\n{plan}\n\nИсходники:\n\n{SOURCE}", "writer")
    test_file = out / "test_ordercalc.py"
    save_code(draft, test_file)

    # 3) КРИТИК: итерации с MCP-инструментами
    history = (f"Текущий файл тестов: {test_file}\nПлан аналитика:\n{plan}\n\n"
               f"Начни с запуска тестов (RUN_TESTS). После каждого инструмента я верну тебе результат.")
    iters = 0
    while iters < args.critic_iters:
        iters += 1
        reply = call(CRITIC_SYSTEM, history, f"critic_iter{iters}")
        tool = "run_tests" if "RUN_TESTS" in reply else "coverage" if "COVERAGE" in reply else None
        if not tool:
            save_code(reply, test_file)
            break
        result = mcp_tool(tool, {"test_file": str(test_file)})
        history += f"\n\nКритик (итерация {iters}):\n{reply}\n\nРезультат инструмента {tool}:\n{result}"
        m = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.DOTALL)
        if m:
            test_file.write_text(m.group(1).strip() + "\n")
    else:
        save_code(call(CRITIC_SYSTEM, history + "\n\nЛимит итераций. Верни финальный код.", "critic_final"), test_file)

    meta = {"level": "L4", "approach": "mcp_multiagent", "model": args.model,
            "executor": "api", "prompt_tokens": usage_total["prompt_tokens"],
            "completion_tokens": usage_total["completion_tokens"],
            "wall_seconds": round(time.time() - t0, 1),
            "iterations": 2 + iters, "roles": ["analyst", "writer", "critic"]}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"OK: {test_file} (роли: аналитик+писатель+критик×{iters}, токены: {usage_total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
