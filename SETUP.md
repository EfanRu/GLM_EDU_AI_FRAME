# SETUP: с нуля до воспроизводимого эксперимента

Проект рассчитан на «чистую машину»: ничего (кроме Python 3.10+) заранее не предполагается.
Ниже — каждый ресурс: **что нужно, где взять, зачем**.

## 0. Что понадобится

| Ресурс | Обязательно? | Зачем |
|---|---|---|
| Python 3.10+ | да | весь проект: генерация, оценка, графики |
| venv + 5 пакетов | да | тесты/покрытие/графики/подсчёт токенов |
| Ключ LLM API (любой OpenAI-совместимый) | для L1–L2, L4 | реальные прогоны генерации |
| Ollama + 1–2 локальные модели | для оси «модели» (локальный тир) | сравнение малых/локальных моделей |
| ZCode / Claude Code / другой агент-харнесс | для L3 | демонстрация топового харнесса |

Без ключей и ollama проект тоже работает: уровни L0 и REF выполняются «руками»,
L1–L4 дают скрипты и инструкции, а демо-результаты в `results/` получены через
субагентов сессионной модели (помечено `executor: session-subagent`).

## 1. Python-окружение

```bash
cd ai_dev_ladder
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pytest coverage matplotlib tiktoken requests
```

Зачем каждый пакет:

| Пакет | Зачем |
|---|---|
| `pytest` | запуск сгенерированных тестов (метрики Q1, Q2) |
| `coverage` | метрики покрытия Q3/Q4 (line/branch) |
| `matplotlib` | графики для отчёта и презентации |
| `tiktoken` | точный подсчёт токенов промптов/ответов (E1/E2) |
| `requests` | HTTP-вызовы LLM API в `direct_api.py` и `mini_agent.py` |

Проверка: `python -c "import pytest, coverage, matplotlib, tiktoken, requests"`.

## 2. Ключ LLM API — где взять

Все скрипты проекта говорят по **OpenAI-совместимому протоколу** (`/v1/chat/completions`),
поэтому подходит любой из провайдеров ниже. Кладём в переменные окружения или `.env`
(файл `.env` уже в `.gitignore` — не коммитим ключи!).

| Провайдер | Где взять ключ | Что даёт | Base URL |
|---|---|---|---|
| **Z.AI** | <https://z.ai> → API-ключ в консоли (open.bigmodel.cn для Китая) | GLM-4.6 / GLM-4.5-Air / GLM-4.6-Flash — дешёвые, хороши для кода; отдельный Coding Plan для агентных сценариев | `https://api.z.ai/api/paas/v4` |
| **OpenRouter** | <https://openrouter.ai/keys> | агрегатор: один ключ → сотни моделей, удобно для сравнения моделей одним скриптом | `https://openrouter.ai/api/v1` |
| **OpenAI** | <https://platform.openai.com/api-keys> | GPT-класс: сильные, дороже | `https://api.openai.com/v1` |
| **Anthropic** | <https://console.anthropic.com> | Claude-класс (протокол свой — для L1/L2 скриптов используйте OpenRouter-прокси или их SDK) | — |
| **Ollama (локально)** | ключ не нужен | малые/средние модели на вашей машине | `http://localhost:11434/v1` |

```bash
export LLM_API_KEY="sk-..."        # ваш ключ
export LLM_BASE_URL="https://api.z.ai/api/paas/v4"
export LLM_MODEL="glm-4.6"
```

Почему протокол один: это и есть урок уровня L1 — «прямой API» у всех провайдеров
почти одинаков, меняются base URL, модель и деньги.

## 3. Локальные модели (Ollama) — ось «простые/локальные модели»

**Зачем:** сравнить, что даёт модель, которую можно поднять у себя (дёшево, приватно,
офлайн), против средних и топовых облачных.

Установка (Linux/macOS):

```bash
curl -fsSL https://ollama.com/install.sh | sh     # поставит и сервис, и CLI
# macOS: brew install ollama && ollama serve
# Windows: https://ollama.com/download
```

Модели для эксперимента (подбираются под вашу RAM/VRAM):

| Модель | Размер | Нужно RAM/VRAM | Тир |
|---|---|---|---|
| `qwen2.5-coder:1.5b` | ~1 ГБ | 4 ГБ | малый |
| `qwen2.5-coder:7b` | ~4.7 ГБ | 8 ГБ | средний локальный |
| `llama3.1:8b` | ~4.9 ГБ | 8 ГБ | средний локальный (не кодовый) |
| `qwen2.5-coder:14b` | ~9 ГБ | 16 ГБ | сильный локальный |

```bash
ollama pull qwen2.5-coder:7b
export LLM_BASE_URL="http://localhost:11434/v1"   # ollama говорит по OpenAI-протоколу
export LLM_API_KEY="ollama"                        # любой непустой
export LLM_MODEL="qwen2.5-coder:7b"
```

Альтернативы Ollama: **LM Studio** (GUI + локальный OpenAI-совместимый сервер),
**llama.cpp** (максимальный контроль). Для ноутбука без GPU — модели до 7b в Q4.

## 4. Топовый харнесс (уровень L3)

Это любой CLI/IDE-агент, который сам читает и правит файлы, запускает команды,
итеративно исправляет себя: **ZCode**, Claude Code, Codex CLI, Cursor и т.п.
Достаточно установить любой из них и открыть папку проекта. Скриптов не нужно —
задача уровня в том и состоит, что харнесс всё делает сам.

## 5. Полный прогон эксперимента

```bash
source .venv/bin/activate

# оценка любой сгенерированной папки с тестами:
python evaluation/evaluate.py results/runs/<имя_прогона>

# агрегация всех прогонов в таблицы/графики/отчёт:
python evaluation/aggregate.py
```

Прогоны создаются уровнями:
- L0: чат — сохраните ответ чата в `results/runs/l0_chat/test_ordercalc.py` (инструкция в `levels/level0_chat/README.md`);
- L1: `python levels/level1_api/direct_api.py --out results/runs/l1_api_glm46`;
- L2: `python levels/level2_simple_harness/mini_agent.py --out results/runs/l2_mini_glm46`;
- L3: попросите ваш агент-харнесс: «прочитай demo_project и напиши pytest-сьют в results/runs/l3_top/test_ordercalc.py, добейся зелёных тестов и высокого покрытия»;
- L4: MCP-сервер + конвейер — `levels/level4_mcp_multiagent/README.md`.
