#!/usr/bin/env python3
"""Уровень L1: прямой вызов LLM API, без харнесса и инструментов.

Один HTTP-запрос -> один ответ -> сохраняем тест-файл и точные цифры токенов
(из поля `usage` ответа). Работает с любым OpenAI-совместимым провайдером
(Z.AI, OpenAI, OpenRouter, Ollama...) — меняются только переменные окружения.

Запуск:
    export LLM_API_KEY=... LLM_BASE_URL=https://api.z.ai/api/paas/v4 LLM_MODEL=glm-4.6
    python direct_api.py --out ../../results/runs/l1_api_glm46
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo_project" / "ordercalc"

TASK_PREAMBLE = """Ты — senior Python-инженер. Ниже — полный код учебной библиотеки `ordercalc`.

Задача: напиши исчерпывающий набор автотестов на pytest для этой библиотеки.

Требования:
- ровно один файл `test_ordercalc.py`;
- только pytest и стандартная библиотека Python;
- импорты вида `from ordercalc.discounts import ...` (пакет ordercalc лежит рядом с тестом);
- тесты обязаны проходить на приведённом коде;
- покрой все публичные функции: типовые значения, граничные условия (пороги, нули,
  пустые списки, даты/високосные годы), валидацию входов (pytest.raises);
- используй параметризацию;
- ответ: ТОЛЬКО код файла, без пояснений и без markdown-ограждений.

Код библиотеки:
"""


def compose_prompt(demo_dir: Path = DEMO) -> str:
    """Собрать базовый промпт: преамбула + полный исходник всех модулей.

    Один и тот же промпт используется на всех уровнях (правило честного сравнения
    из CRITERIA.md) — меняется только обвязка вокруг модели.
    """
    parts = [TASK_PREAMBLE]
    for name in sorted(p.name for p in demo_dir.glob("*.py") if p.name != "__init__.py"):
        parts.append(f"=== ordercalc/{name} ===\n{demo_dir.joinpath(name).read_text()}\n")
    return "".join(parts)


def extract_code(text: str) -> str:
    """Вытащить python-код, если модель всё-таки обернула в ```...```."""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="каталог прогона, напр. ../../results/runs/l1_api_glm")
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/paas/v4"))
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "glm-4.6"))
    ap.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""))
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=8192)
    args = ap.parse_args()

    if not args.api_key:
        print("Нет ключа: задайте LLM_API_KEY или --api-key (см. SETUP.md, раздел 2)", file=sys.stderr)
        return 2

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    prompt = compose_prompt()
    (out / "prompt.txt").write_text(prompt)

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}

    t0 = time.time()
    resp = requests.post(
        f"{args.base_url.rstrip('/')}/chat/completions",
        json=payload, headers=headers, timeout=600,
    )
    elapsed = time.time() - t0
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})  # prompt_tokens / completion_tokens — точные цифры от API
    code = extract_code(content)
    (out / "test_ordercalc.py").write_text(code + "\n")
    (out / "response_raw.txt").write_text(content)
    meta = {
        "level": "L1",
        "approach": "direct_api",
        "model": args.model,
        "base_url": args.base_url,
        "executor": "api",
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "wall_seconds": round(elapsed, 1),
        "iterations": 1,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"OK: {out}/test_ordercalc.py  ({usage.get('prompt_tokens')} in / "
          f"{usage.get('completion_tokens')} out tokens, {elapsed:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
