#!/usr/bin/env python3
"""Оценка одного прогона или всех прогонов по критериям CRITERIA.md.

Метрики: Q1 запускаемость, Q2 прохождение на эталоне, Q3/Q4 покрытие
(line/branch), Q5 чувствительность к 5 посеянным багам, V1/V2 объём тестов,
E1/E2 токены (точно из API-usage или tiktoken-оценкой), стоимость.

    python evaluation/evaluate.py results/runs/l1_api_glm46   # один прогон
    python evaluation/evaluate.py --all                       # все прогоны
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo_project" / "ordercalc"
VARIANTS = sorted((ROOT / "demo_project" / "variants").glob("bug*"))

try:  # точный подсчёт токенов, если tiktoken доступен
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
    TOKEN_METHOD = "tiktoken/cl100k_base"
except ImportError:  # запасная оценка
    def count_tokens(text: str) -> int:
        return len(text) // 4
    TOKEN_METHOD = "chars/4 (tiktoken недоступен)"


def sandbox(test_file: Path, override: Path | None = None) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="eval_"))
    shutil.copytree(DEMO, tmp / "ordercalc")
    if override is not None:
        shutil.copy(override, tmp / "ordercalc" / override.name)
    shutil.copy(test_file, tmp / "test_ordercalc.py")
    return tmp


def pytest_run(tmp: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "test_ordercalc.py", "-q", "--no-header", *args],
        cwd=tmp, capture_output=True, text=True, timeout=180,
    )


def parse_summary(output: str) -> tuple[int, int]:
    """(passed, total) из вывода pytest -q."""
    m = re.search(r"(\d+) passed", output)
    passed = int(m.group(1)) if m else 0
    total = passed
    m_failed = re.search(r"(\d+) failed", output)
    m_error = re.search(r"(\d+) error", output)
    if m_failed:
        total += int(m_failed.group(1))
    if m_error:
        total += int(m_error.group(1))
    return passed, total


def failing_test_ids(output: str) -> set:
    return set(re.findall(r"^FAILED (\S+)", output, re.M)) | set(re.findall(r"^ERROR (\S+)", output, re.M))


def evaluate_run(run_dir: Path) -> dict:
    meta = {}
    meta_file = run_dir / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
    test_file = run_dir / "test_ordercalc.py"
    result = {"run": run_dir.name, "meta": meta, "token_method": TOKEN_METHOD}

    if not test_file.exists():
        result["error"] = "test_ordercalc.py отсутствует (прогон не выполнялся — см. SETUP.md)"
        result.update({"q1_collectable": 0, "q2_passed_pct": 0, "q3_line_pct": 0, "q4_branch_pct": 0,
                       "q5_bugs_caught": 0, "q5_total_bugs": len(VARIANTS), "v1_test_funcs": 0, "v2_asserts": 0})
        (run_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    src = test_file.read_text()
    result["v1_test_funcs"] = len(re.findall(r"^\s*def test_", src, re.M))
    result["v2_asserts"] = len(re.findall(r"^\s*assert |pytest\.raises", src, re.M))

    # Q1: собирается ли вообще
    tmp = sandbox(test_file)
    try:
        collect = pytest_run(tmp, "--collect-only")
        result["q1_collectable"] = int("error" not in collect.stdout.lower() and collect.returncode in (0, 1) or "passed" in collect.stdout or "::" in collect.stdout)
        run = pytest_run(tmp)
        passed, total = parse_summary(run.stdout + run.stderr)
        result["q2_passed"] = passed
        result["q2_total"] = total
        result["q2_passed_pct"] = round(100 * passed / total, 1) if total else 0.0
        result["pytest_clean_tail"] = (run.stdout + run.stderr).strip()[-400:]

        # Q3/Q4: покрытие (line по statements, branch по branch-колонкам отчёта)
        subprocess.run([sys.executable, "-m", "coverage", "run", "--source=ordercalc", "--branch",
                        "-m", "pytest", "test_ordercalc.py", "-q"], cwd=tmp, capture_output=True, text=True, timeout=180)
        cov2 = subprocess.run([sys.executable, "-m", "coverage", "report", "-m"], cwd=tmp,
                              capture_output=True, text=True)
        line_pct = branch_pct = 0.0
        for line in cov2.stdout.splitlines():
            if line.startswith("TOTAL"):
                # TOTAL   St  Mi  Br  BMi  %
                cols = line.split()
                stmts, missed = int(cols[1]), int(cols[2])
                line_pct = round(100 * (stmts - missed) / stmts, 1) if stmts else 0.0
                br, br_missed = int(cols[3]), int(cols[4])
                branch_pct = round(100 * (br - br_missed) / br, 1) if br else 0.0
                result["q_combined_pct"] = float(cols[-1].rstrip("%"))
        result["q3_line_pct"] = line_pct
        result["q4_branch_pct"] = branch_pct
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Q5: чувствительность к багам.
    # Баг «пойман», только если на варианте упал тест, ПРОХОДИВШИЙ на эталоне —
    # постоянно падающие (ошибочные) тесты не засчитываются как детект.
    tmp = sandbox(test_file)
    try:
        clean_fails = failing_test_ids(pytest_run(tmp).stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    caught = {}
    for bug_dir in VARIANTS:
        override = next(bug_dir.glob("*.py"))
        tmp = sandbox(test_file, override)
        try:
            run = pytest_run(tmp)
            variant_fails = failing_test_ids(run.stdout)
            caught[bug_dir.name] = bool(variant_fails - clean_fails)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    result["q5_bugs"] = caught
    result["q5_bugs_caught"] = sum(1 for v in caught.values() if v)
    result["q5_total_bugs"] = len(VARIANTS)
    result["q5_detection_pct"] = round(100 * result["q5_bugs_caught"] / len(VARIANTS), 1)

    # E1/E2: токены — точно из API или tiktoken-оценкой по файлам прогона
    if meta.get("prompt_tokens") is not None:
        result["e1_in_tokens"] = meta["prompt_tokens"]
        result["e2_out_tokens"] = meta["completion_tokens"]
        result["token_source"] = "api_usage"
    else:
        in_txt = "".join(p.read_text() for p in sorted(run_dir.glob("prompt_parts/*.txt")))
        out_txt = "".join(p.read_text() for p in sorted(run_dir.glob("response_parts/*.txt")))
        out_txt += src
        result["e1_in_tokens"] = count_tokens(in_txt)
        result["e2_out_tokens"] = count_tokens(out_txt)
        result["token_source"] = TOKEN_METHOD
    result["e4_wall_seconds"] = meta.get("wall_seconds")

    (run_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    runs_root = ROOT / "results" / "runs"
    if args.all:
        dirs = sorted(d for d in runs_root.iterdir() if d.is_dir())
    else:
        dirs = [Path(args.run_dir).resolve()]
    for d in dirs:
        r = evaluate_run(d)
        summary = (f"{r['run']}: collect={r.get('q1_collectable')} pass={r.get('q2_passed_pct')}% "
                   f"line={r.get('q3_line_pct')}% branch={r.get('q4_branch_pct')}% "
                   f"bugs={r.get('q5_bugs_caught')}/{r.get('q5_total_bugs')} "
                   f"in={r.get('e1_in_tokens')} out={r.get('e2_out_tokens')}")
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
