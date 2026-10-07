#!/usr/bin/env python3
"""Агрегация всех прогонов: results.json + TABLES.md + графики в results/charts/.

    python evaluation/aggregate.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from prices import cost_usd  # noqa: E402

RUNS = [
    # (run_id, метка для графиков, уровень, время оператора — экспертная оценка)
    ("ref", "REF человек", "REF", "~2–3 ч ручной работы"),
    ("l0_chat", "L0 чат", "L0", "~10–15 мин, 3–5 кругов руками"),
    ("l1_api_glm53", "L1 API 5.3", "L1", "1 команда"),
    ("l1_api_glm53_flash", "L1 API Flash", "L1", "1 команда"),
    ("l2_mini", "L2 мини-харнесс", "L2", "1 команда"),
    ("l3_top", "L3 топ-харнесс", "L3", "1 промпт агенту"),
    ("l4_multi", "L4 MCP+мультиагент", "L4", "1 команда"),
]
COLORS = {"ref": "#888888", "l0_chat": "#d62728", "l1_api_glm53": "#1f77b4",
          "l1_api_glm53_flash": "#9ecae1", "l2_mini": "#ff7f0e",
          "l3_top": "#2ca02c", "l4_multi": "#9467bd"}


def load_rows():
    rows = []
    for run_id, label, level, op_time in RUNS:
        f = ROOT / "results" / "runs" / run_id / "evaluation.json"
        if not f.exists():
            print(f"! пропуск {run_id}: нет evaluation.json")
            continue
        ev = json.loads(f.read_text())
        meta = ev.get("meta", {})
        rows.append({
            "run": run_id, "label": label, "level": level, "op_time": op_time,
            "model": meta.get("model", "—"), "executor": meta.get("executor", "—"),
            "iterations": meta.get("iterations"),
            "q1": ev.get("q1_collectable"), "q2": ev.get("q2_passed_pct"),
            "q2_passed": ev.get("q2_passed"), "q2_total": ev.get("q2_total"),
            "q3": ev.get("q3_line_pct"), "q4": ev.get("q4_branch_pct"),
            "q5": ev.get("q5_detection_pct"), "q5_caught": ev.get("q5_bugs_caught"),
            "e1": ev.get("e1_in_tokens"), "e2": ev.get("e2_out_tokens"),
            "e4": ev.get("e4_wall_seconds"), "v1": ev.get("v1_test_funcs"),
            "v2": ev.get("v2_asserts"), "token_source": ev.get("token_source"),
        })
    return rows


def score(rows):
    """Score из CRITERIA.md: 0.3*Q5 + 0.2*Q3 + 0.1*Q4 + 0.2*Q2 + 0.2*экономика."""
    tokens = [(r["e1"] or 0) + (r["e2"] or 0) for r in rows]
    tmin, tmax = min(tokens), max(tokens)
    for r, t in zip(rows, tokens):
        econ = 1.0 if tmax == tmin else 1 - (t - tmin) / (tmax - tmin)
        r["score"] = round(0.3 * (r["q5"] or 0) + 0.2 * (r["q3"] or 0)
                           + 0.1 * (r["q4"] or 0) + 0.2 * (r["q2"] or 0) + 0.2 * econ * 100, 1)
        r["e_total"] = t
        r["cost_ref_usd"] = cost_usd(r["run"], r["e1"] or 0, r["e2"] or 0)
    return rows


def write_json_and_tables(rows):
    (ROOT / "results" / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))

    def fmt(r, k):
        v = r.get(k)
        return "—" if v is None else v

    lines = [
        "# Сводные таблицы эксперимента",
        "",
        "Все метрики по CRITERIA.md; оценка автоматически из evaluation.json. ",
        "Прогоны `executor: session-subagent` выполнены моделью сессии через субагентов ZCode ",
        "(без внешнего API-ключа): входные/выходные токены посчитаны по протоколу ",
        "(tiktoken по точным промптам и ответам), внутренние размышления агентов не учитываются.",
        "",
        "## Главная таблица: подходы",
        "",
        "| Подход | Модель | Итераций | Тестов | Прошло | Покрытие line | Покрытие branch | Баги пойманы | Токены в/всего | Время | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['model']} | {fmt(r,'iterations')} | {fmt(r,'v1')} "
            f"| {r.get('q2_passed','—')}/{r.get('q2_total','—')} ({fmt(r,'q2')}%) "
            f"| {fmt(r,'q3')}% | {fmt(r,'q4')}% | {fmt(r,'q5_caught')}/5 ({fmt(r,'q5')}%) "
            f"| {fmt(r,'e1')}/{fmt(r,'e_total')} | {fmt(r,'e4')} c | {fmt(r,'score')} |")
    lines += [
        "",
        "## Экономика и трудозатраты оператора",
        "",
        "| Подход | Входные токены | Выходные токены | Всего | Расчётная стоимость* | Время генерации | Время оператора (оценка) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cost = "—" if r["cost_ref_usd"] is None else f"${r['cost_ref_usd']:.4f}"
        lines.append(f"| {r['label']} | {fmt(r,'e1')} | {fmt(r,'e2')} | {fmt(r,'e_total')} "
                     f"| {cost} | {fmt(r,'e4')} c | {r['op_time']} |")
    lines += [
        "",
        "\\* Расчётная стоимость — сколько стоили бы те же токены по публичному прайсу ",
        "(evaluation/prices.py, дата 2026-10-06). Прогоны сессии оплачиваются подпиской.",
        "",
        "## Ось «модели» (уровень L1, одинаковый промпт)",
        "",
        "| Модель | Прошло | Покрытие line/branch | Баги | Токены в→всего | Время |",
        "|---|---|---|---|---|---|",
    ]
    model_rows = [r for r in rows if r["run"] in ("l1_api_glm53_flash", "l1_api_glm53")]
    for r in model_rows:
        lines.append(f"| {r['model']} | {fmt(r,'q2')}% | {fmt(r,'q3')}% / {fmt(r,'q4')}% "
                     f"| {fmt(r,'q5_caught')}/5 | {fmt(r,'e1')}→{fmt(r,'e_total')} | {fmt(r,'e4')} c |")
    lines += [
        "| локальная qwen2.5-coder:7b (Ollama) | — | — | — | — | — |",
        "",
        "Локальный тир не прогонялся (нет установленной Ollama на машине эксперимента). ",
        "Запустить: см. SETUP.md раздел 3, затем `direct_api.py --base-url http://localhost:11434/v1`.",
    ]
    (ROOT / "results" / "TABLES.md").write_text("\n".join(lines) + "\n")


def charts(rows):
    ch = ROOT / "results" / "charts"
    ch.mkdir(parents=True, exist_ok=True)
    labels = [r["label"] for r in rows]
    x = list(range(len(rows)))

    # 1. Качество по подходам
    fig, ax = plt.subplots(figsize=(12.5, 5.5))
    w = 0.2
    metrics = [("q2", "Прошли на эталоне, %"), ("q3", "Покрытие строк, %"),
               ("q4", "Покрытие веток, %"), ("q5", "Баги пойманы, %")]
    for k, (key, name) in enumerate(metrics):
        vals = [r.get(key) or 0 for r in rows]
        pos = [xi + (k - 1.5) * w for xi in x]
        bars = ax.bar(pos, vals, w * 0.92, label=name,
                      color=["#8c564b", "#1f77b4", "#9ecae1", "#2ca02c"][k])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:g}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 118); ax.set_ylabel("%"); ax.legend(ncol=4, fontsize=9, loc="upper center")
    ax.set_title("Качество сгенерированных тестов по подходам (задача: автотесты ordercalc)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(ch / "01_quality.png", dpi=150); plt.close(fig)

    # 2. Токены
    fig, ax = plt.subplots(figsize=(10.5, 5))
    e1 = [r["e1"] or 0 for r in rows]; e2 = [r["e2"] or 0 for r in rows]
    ax.bar(labels, e1, label="входные (промпты/контекст)", color="#1f77b4")
    ax.bar(labels, e2, bottom=e1, label="выходные (сгенерированное)", color="#ff7f0e")
    for i, r in enumerate(rows):
        ax.text(i, (r["e1"] or 0) + (r["e2"] or 0) + 250, f"{(r['e1'] or 0)+(r['e2'] or 0):,}",
                ha="center", fontsize=9)
    ax.set_ylabel("токены"); ax.legend(); ax.grid(axis="y", alpha=0.3)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax.set_title("Расход токенов по подходам (протокол: промпты + артефакты)")
    fig.tight_layout(); fig.savefig(ch / "02_tokens.png", dpi=150); plt.close(fig)

    # 3. Интегральный Score против бюджета токенов (подписи-выноски в отдельной колонке)
    fig, ax = plt.subplots(figsize=(11, 6.5))
    import math
    # кластеры точек ближе 10% по токенам слегка разносятся по вертикали (сноска внизу)
    dodged = {}
    by_total = sorted(rows, key=lambda r: r["e_total"])
    cluster = [by_total[0]]
    for r in by_total[1:]:
        if math.isclose(r["e_total"], cluster[-1]["e_total"], rel_tol=0.10):
            cluster.append(r)
        else:
            if len(cluster) > 1:
                for i, cr in enumerate(sorted(cluster, key=lambda r: r["e_total"])):
                    dodged[cr["run"]] = (i - (len(cluster) - 1) / 2) * 1.3
            cluster = [r]
    if len(cluster) > 1:
        for i, cr in enumerate(sorted(cluster, key=lambda r: r["e_total"])):
            dodged[cr["run"]] = (i - (len(cluster) - 1) / 2) * 1.3

    ordered = sorted(rows, key=lambda r: (r["score"], r["e_total"]))
    label_ys = [78 + i * (100 - 78) / max(len(ordered) - 1, 1) for i in range(len(ordered))]
    for r, ly in zip(ordered, label_ys):
        total = r["e_total"]
        y = r["score"] + dodged.get(r["run"], 0)
        ax.scatter(total, y, s=170, color=COLORS.get(r["run"], "#333"),
                   alpha=0.9, edgecolors="k", zorder=3)
        ax.annotate(f"{r['label']} — {r['q5_caught']}/5 багов, ветки {r['q4']:.0f}% ({total:,} ток., Score {r['score']})",
                    xy=(total, y), xytext=(42000, ly), fontsize=8.5,
                    va="center",
                    arrowprops=dict(arrowstyle="-", color="#666", lw=0.8,
                                    connectionstyle="arc3,rad=0.08"))
    ax.set_xlabel("Всего токенов (вход + выход), лог. шкала")
    ax.set_ylabel("Интегральный Score (CRITERIA.md)")
    ax.set_title("Качество против бюджета: Score = качество + экономия токенов")
    ax.grid(alpha=0.3); ax.set_xscale("log")
    ax.set_xlim(1500, 130000); ax.set_ylim(74, 103)
    if dodged:
        ax.text(0.01, 0.012, "* точки кластера ~10–11k токенов разнесены по вертикали "
                             "для читаемости; реальные Score: 94.1–94.5",
                transform=ax.transAxes, fontsize=7.5, color="#555")
    fig.tight_layout(); fig.savefig(ch / "03_quality_vs_cost.png", dpi=150); plt.close(fig)

    # 4. Время и итерации
    present = [(r, i) for i, r in enumerate(rows) if r.get("e4")]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([r["label"] for r, _ in present], [r["e4"] for r, _ in present], color="#2ca02c")
    for i, (r, _) in enumerate(present):
        ax.text(i, r["e4"] + 4, f"{r['e4']:.0f} c", ha="center", fontsize=9)
        if r.get("iterations"):
            ax.text(i, 8, f"итераций: {r['iterations']}", ha="center", fontsize=8, color="white")
    ax.set_ylabel("wall-clock, сек"); ax.grid(axis="y", alpha=0.3)
    ax.set_title("Время генерации (внутри белым — число итераций цикла)")
    fig.tight_layout(); fig.savefig(ch / "04_time.png", dpi=150); plt.close(fig)

    # 5. Модели
    if len(model_rows := [r for r in rows if r["run"].startswith("l1_api")]) >= 1:
        fig, ax = plt.subplots(figsize=(8.5, 5))
        ml = [r["label"] for r in model_rows]
        for k, (key, name) in enumerate([("q2", "Прошли, %"), ("q3", "Строки, %"),
                                         ("q4", "Ветки, %"), ("q5", "Баги, %")]):
            vals = [r.get(key) or 0 for r in model_rows]
            pos = [i + (k - 1.5) * 0.2 for i in range(len(ml))]
            bars = ax.bar(pos, vals, 0.18, label=name)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}", ha="center", fontsize=8)
        ax.set_xticks(range(len(ml))); ax.set_xticklabels(ml)
        ax.set_ylim(0, 115); ax.legend(ncol=4, fontsize=8); ax.grid(axis="y", alpha=0.3)
        ax.set_title("Сравнение моделей на одинаковом промпте (L1)\n(локальный тир qwen2.5-coder:7b — запустите по SETUP.md)")
        fig.tight_layout(); fig.savefig(ch / "05_models.png", dpi=150); plt.close(fig)

    print("графики:", *sorted(p.name for p in ch.glob("*.png")), sep="\n  ")


def main():
    rows = score(load_rows())
    write_json_and_tables(rows)
    charts(rows)
    for r in rows:
        print(f"{r['label']:<22} score={r['score']:<5} bugs={r['q5_caught']}/5 "
              f"cov={r['q3']}/{r['q4']}% tokens={r['e_total']} t={r['e4']}s")


if __name__ == "__main__":
    main()
