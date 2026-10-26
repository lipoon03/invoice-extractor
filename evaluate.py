from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from config import GEMINI_MODEL, GEMINI_THINKING_LEVEL, OLLAMA_MODELS, OLLAMA_TIMEOUT_SECONDS, GEMINI_TIMEOUT_SECONDS
from extractor.extract import extract
from extractor.models import Invoice
from extractor.providers import GeminiProvider, OllamaProvider

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "test_set.jsonl"
RESULTS_DIR = ROOT / "results"
LOG_PATH = RESULTS_DIR / "documents.jsonl"
CSV_PATH = RESULTS_DIR / "summary.csv"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_cases():
    with DATA_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canonical(obj: Any) -> dict:
    if isinstance(obj, Invoice):
        return obj.model_dump(mode="json")
    return Invoice.model_validate(obj).model_dump(mode="json")


def main():
    parser = argparse.ArgumentParser(description="Evaluate invoice extraction providers serially.")
    parser.add_argument("--providers", default="ollama,gemini", help="Comma-separated: ollama,gemini")
    parser.add_argument("--ollama-models", default=",".join(OLLAMA_MODELS))
    parser.add_argument("--gemini-model", default=GEMINI_MODEL)
    parser.add_argument("--modes", default="prompt_only,schema_enforced")
    parser.add_argument("--limit", type=int, default=0, help="Optional document limit (0 means all 30)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    if args.limit:
        cases = cases[:args.limit]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    provider_specs = []
    if "ollama" in [p.strip().lower() for p in args.providers.split(",")]:
        provider_specs.extend(("ollama", m.strip()) for m in args.ollama_models.split(",") if m.strip())
    if "gemini" in [p.strip().lower() for p in args.providers.split(",")]:
        provider_specs.append(("gemini", args.gemini_model))

    rows = []
    with LOG_PATH.open("w", encoding="utf-8") as log_file:
        for provider_kind, model_name in provider_specs:
            try:
                provider = (
                    OllamaProvider(model_name, timeout_seconds=OLLAMA_TIMEOUT_SECONDS)
                    if provider_kind == "ollama"
                    else GeminiProvider(model_name, thinking_level=GEMINI_THINKING_LEVEL, timeout_seconds=GEMINI_TIMEOUT_SECONDS)
                )
            except Exception as exc:
                logging.error("Cannot initialize %s/%s: %s", provider_kind, model_name, exc)
                continue

            for mode in modes:
                if mode not in ("prompt_only", "schema_enforced"):
                    raise ValueError(f"Unsupported mode: {mode}")
                durations, exact_matches, valid_count = [], 0, 0
                for case in cases:
                    started = time.perf_counter()
                    valid = False
                    exact = False
                    err = None
                    output = None
                    total_tokens = thinking_tokens = None
                    try:
                        result = extract(case["text"], provider, mode)
                        durations.append(result.seconds)
                        valid = True
                        valid_count += 1
                        exact = canonical(result.invoice) == canonical(case["expected"])
                        exact_matches += int(exact)
                        output = result.invoice.model_dump(mode="json")
                        total_tokens, thinking_tokens = result.total_tokens, result.thinking_tokens
                    except Exception as exc:
                        err = f"{type(exc).__name__}: {exc}"
                        durations.append(time.perf_counter() - started)
                    log_row = {
                        "document_id": case["id"], "model": model_name, "provider": provider_kind,
                        "mode": mode, "seconds": round(durations[-1], 4), "valid": valid,
                        "exact_match": exact, "total_tokens": total_tokens,
                        "thinking_tokens": thinking_tokens, "error": err, "output": output,
                    }
                    log_file.write(json.dumps(log_row, ensure_ascii=False) + "\n")
                    log_file.flush()
                    logging.info("%s %s %s seconds=%.3f valid=%s exact_match=%s",
                                 model_name, mode, case["id"], durations[-1], valid, exact)
                n = len(cases)
                rows.append({
                    "provider": provider_kind, "model": model_name, "mode": mode, "documents": n,
                    "exact_match_accuracy": round(exact_matches / n, 4) if n else 0,
                    "schema_valid_rate": round(valid_count / n, 4) if n else 0,
                    "median_seconds_per_document": round(statistics.median(durations), 4) if durations else None,
                    "total_tokens": None, "thinking_tokens": None,
                })

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "provider", "model", "mode", "documents", "exact_match_accuracy",
            "schema_valid_rate", "median_seconds_per_document", "total_tokens", "thinking_tokens"
        ])
        writer.writeheader()
        writer.writerows(rows)
    print("\nResults summary")
    print("-" * 100)
    print(f"{'Provider':<10} {'Model':<24} {'Mode':<18} {'Exact':>8} {'Valid':>8} {'Median(s)':>12}")
    for r in rows:
        print(f"{r['provider']:<10} {r['model']:<24.24} {r['mode']:<18} "
              f"{r['exact_match_accuracy']:>7.1%} {r['schema_valid_rate']:>7.1%} "
              f"{str(r['median_seconds_per_document']):>12}")
    print(f"\nPer-document log: {LOG_PATH}")
    print(f"Summary CSV:      {CSV_PATH}")


if __name__ == "__main__":
    main()
