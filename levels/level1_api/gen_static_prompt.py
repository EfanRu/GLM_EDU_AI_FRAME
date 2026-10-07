#!/usr/bin/env python3
"""Сохранить базовый промпт в статичный файл — для уровня L0 (чат) и документации.

    python gen_static_prompt.py   # -> prompts/task_full.txt
"""

from pathlib import Path

from direct_api import compose_prompt

out = Path(__file__).parent / "prompts" / "task_full.txt"
out.write_text(compose_prompt())
print(f"written: {out} ({len(compose_prompt())} chars)")
