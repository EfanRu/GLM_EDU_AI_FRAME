#!/usr/bin/env python3
"""Уровень L2: «простой харнесс» — свой мини-агентный цикл ~200 строк.

Отличия от L1: у модели появляется ИНСТРУМЕНТ (запуск тестов) и цикл обратной
связи — она видит падения pytest и исправляет файл. Отличия от топового харнесса
(L3): один инструмент, нет доступа к файловой системе, жёсткий лимит итераций,
никакого контекст-менеджмента.

Протокол диалога (универсальный для любых OpenAI-совместимых API, включая Ollama):
- модель отвечает строкой RUN_TESTS -> харнесс сохраняет последний ```python-блок
  и запускает pytest, возвращая вывод;
- модель отвечает ```python-блоком без RUN_TESTS -> это финальная версия.

Запуск:
    export LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=...
    python mini_agent.py --out ../../results/runs/l2_mini_glm46
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo_project" / "ordercalc"
sys.path.insert(0, str(ROOT / "levels" / "level1_api"))
from direct_api import compose_prompt, extract_code  # noqa: E402

SYSTEM_PROMPT = """Ты — агент-тестировщик Python. Твоя задача — написать файл test_ordercalc.py \
(pytest) для библиотеки ordercalc, код которой тебе пришлёт пользователь.

У тебя есть ОДИН инструмент: запуск тестов. Чтобы воспользоваться им, ответь \
ровно строкой RUN_TESTS — оператор сохранит твой последний ```python-блок в \
test_ordercalc.py, запустит pytest и пришлёт тебе вывод. Проанализировав падения, \
исправь тесты и снова запроси запуск, либо выдай финальную версию.

Финальный ответ: только ```python-блок с полным кодом файла, без пояснений.
Тесты не должны падать на эталонном коде библиотеки."""


def run_pytest(test_file: Path, max_chars: int = 2200) -> str:
    """Инструмент харнесса: собрать песочницу (ordercalc + тест) и запустить pytest."""
    tmp = Path(tempfile.mkdtemp(prefix="mini_agent_"))
    try:
        shutil.copytree(DEMO, tmp / "ordercalc")
        shutil.copy(test_file, tmp / "test_ordercalc.py")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "test_ordercalc.py", "-q", "--no-header", "--tb=short"],
            cwd=tmp, capture_output=True, text=True, timeout=120,
        )
        out = (proc.stdout + proc.stderr).strip()
        return out[-max_chars:] if len(out) > max_chars else out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def chat(base_url, api_key, model, messages, temperature=0.2):
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": 8192},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/paas/v4"))
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "glm-4.6"))
    ap.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""))
    ap.add_argument("--max-tool-calls", type=int, default=3, help="лимит итераций цикла")
    args = ap.parse_args()

    if not args.api_key:
        print("Нет ключа: задайте LLM_API_KEY или --api-key (см. SETUP.md)", file=sys.stderr)
        return 2

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    test_file = out / "test_ordercalc.py"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": compose_prompt() + "\n\nНачинай: выдай первую версию тестов."},
    ]

    log, tool_calls, usage_total = [], 0, {"prompt_tokens": 0, "completion_tokens": 0}
    t0 = time.time()
    reply = ""

    while True:
        data = chat(args.base_url, args.api_key, args.model, messages)
        reply = data["choices"][0]["message"]["content"]
        u = data.get("usage", {})
        usage_total["prompt_tokens"] += u.get("prompt_tokens", 0)
        usage_total["completion_tokens"] += u.get("completion_tokens", 0)
        messages.append({"role": "assistant", "content": reply})

        if "RUN_TESTS" in reply and tool_calls < args.max_tool_calls:
            tool_calls += 1
            block = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.DOTALL)
            if block:
                test_file.write_text(block.group(1).strip() + "\n")
            result = run_pytest(test_file)
            log.append({"iter": tool_calls, "pytest_tail": result[-400:]})
            messages.append({"role": "user", "content": f"Результат pytest (окружение: пакет ordercalc лежит рядом с тестом):\n\n{result}\n\n"
                                                         "Исправь тесты и снова RUN_TESTS, либо выдай финальную версию кода."})
            continue

        block = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.DOTALL)
        test_file.write_text((block.group(1) if block else reply).strip() + "\n")
        break

    meta = {
        "level": "L2",
        "approach": "mini_harness",
        "model": args.model,
        "base_url": args.base_url,
        "executor": "api",
        "prompt_tokens": usage_total["prompt_tokens"],
        "completion_tokens": usage_total["completion_tokens"],
        "wall_seconds": round(time.time() - t0, 1),
        "iterations": tool_calls + 1,
        "tool_calls_log": log,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"OK: {test_file}  (итераций: {tool_calls + 1}, токены: {usage_total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
