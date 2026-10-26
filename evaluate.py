from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any

from config import GEMINI_MODEL, GEMINI_THINKING_LEVEL, OLLAMA_MODELS, OLLAMA_TIMEOUT_SECONDS, GEMINI_TIMEOUT_SECONDS
from extractor.extract import extract
from extractor.models import Invoice
from extractor.providers import GeminiProvider, OllamaProvider

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
FIELD_NAMES = ("invoice_number", "date", "total_amount", "currency")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_cases(dataset: str) -> list[dict[str, Any]]:
    data_path = DATA_DIR / f"{dataset}.jsonl"
    if not data_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {data_path}")
    with data_path.open(encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]
    for line_no, case in enumerate(cases, start=1):
        if not all(key in case for key in ("id", "text", "expected")):
            raise ValueError(f"{data_path.name}:{line_no} must contain id, text, expected")
        Invoice.model_validate(case["expected"])
    return cases


def canonical(obj: Any) -> dict:
    if isinstance(obj, Invoice):
        return obj.model_dump(mode="json")
    return Invoice.model_validate(obj).model_dump(mode="json")


def field_errors(expected: dict, actual: dict | None, exception: str | None = None) -> list[str]:
    if exception:
        return [f"extraction_error: {exception}"]
    if actual is None:
        return ["extraction_error: no output"]
    return [f"{field}: expected={expected.get(field)!r}, actual={actual.get(field)!r}"
            for field in FIELD_NAMES if expected.get(field) != actual.get(field)]


def percentile95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank percentile: simple and reproducible for small test sets.
    return round(ordered[max(0, __import__("math").ceil(0.95 * len(ordered)) - 1)], 4)


def main():
    parser = argparse.ArgumentParser(description="Evaluate invoice extraction providers serially.")
    parser.add_argument("--providers", default="ollama", help="Comma-separated: ollama,gemini (default: ollama)")
    parser.add_argument("--ollama-models", default=",".join(OLLAMA_MODELS))
    parser.add_argument("--gemini-model", default=GEMINI_MODEL)
    parser.add_argument("--modes", default="prompt_only,schema_enforced")
    parser.add_argument("--dataset", choices=("test_set", "hard_set"), default="test_set",
                        help="Dataset name under data/ (test_set or hard_set)")
    parser.add_argument("--limit", type=int, default=0, help="Optional document limit (0 means all documents)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases(args.dataset)
    if args.limit:
        cases = cases[:args.limit]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    provider_names = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    provider_specs = []
    if "ollama" in provider_names:
        provider_specs.extend(("ollama", m.strip()) for m in args.ollama_models.split(",") if m.strip())
    if "gemini" in provider_names:
        provider_specs.append(("gemini", args.gemini_model))
    unknown = set(provider_names) - {"ollama", "gemini"}
    if unknown:
        parser.error(f"Unsupported provider(s): {', '.join(sorted(unknown))}")

    log_path = RESULTS_DIR / f"documents_{args.dataset}.jsonl"
    csv_path = RESULTS_DIR / f"summary_{args.dataset}.csv"
    rows = []
    with log_path.open("w", encoding="utf-8") as log_file:
        for provider_kind, model_name in provider_specs:
            try:
                provider = (
                    OllamaProvider(model_name, timeout_seconds=OLLAMA_TIMEOUT_SECONDS)
                    if provider_kind == "ollama"
                    else GeminiProvider(model_name, thinking_level=GEMINI_THINKING_LEVEL,
                                        timeout_seconds=GEMINI_TIMEOUT_SECONDS)
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                logging.warning("تعذر تهيئة %s/%s: %s", provider_kind, model_name, message)
                rows.append({"provider": provider_kind, "model": model_name, "mode": "all",
                             "documents": len(cases), "error_count": len(cases),
                             "initialization_error": message})
                continue

            for mode in modes:
                if mode not in ("prompt_only", "schema_enforced"):
                    raise ValueError(f"Unsupported mode: {mode}")
                durations: list[float] = []
                valid_count = exact_matches = error_count = 0
                field_correct = {field: 0 for field in FIELD_NAMES}
                for case in cases:
                    started = time.perf_counter()
                    valid = exact = False
                    error_message = None
                    output = None
                    total_tokens = thinking_tokens = None
                    try:
                        result = extract(case["text"], provider, mode)
                        elapsed = result.seconds
                        valid = True
                        valid_count += 1
                        output = result.invoice.model_dump(mode="json")
                        total_tokens, thinking_tokens = result.total_tokens, result.thinking_tokens
                        expected = canonical(case["expected"])
                        actual = canonical(result.invoice)
                        exact = actual == expected
                        exact_matches += int(exact)
                        for field in FIELD_NAMES:
                            field_correct[field] += int(actual[field] == expected[field])
                    except Exception as exc:
                        elapsed = time.perf_counter() - started
                        error_message = f"{type(exc).__name__}: {exc}"
                        logging.warning("تحذير: فشل استخراج %s باستخدام %s/%s (%s): %s",
                                        case["id"], model_name, mode, type(exc).__name__, exc)
                    durations.append(elapsed)
                    errors = field_errors(case["expected"], output, error_message)
                    if errors:
                        error_count += 1
                        logging.warning("تحذير: %s | %s", case["id"], " ; ".join(errors))
                    log_row = {
                        "document_id": case["id"], "dataset": args.dataset,
                        "model": model_name, "provider": provider_kind, "mode": mode,
                        "seconds": round(elapsed, 4), "valid": valid, "exact_match": exact,
                        "total_tokens": total_tokens, "thinking_tokens": thinking_tokens,
                        "errors": errors, "output": output,
                    }
                    log_file.write(json.dumps(log_row, ensure_ascii=False) + "\n")
                    log_file.flush()
                    logging.info("%s %s %s seconds=%.3f valid=%s exact_match=%s errors=%d",
                                 model_name, mode, case["id"], elapsed, valid, exact, len(errors))

                n = len(cases)
                row = {
                    "dataset": args.dataset, "provider": provider_kind, "model": model_name,
                    "mode": mode, "documents": n,
                    "exact_match_accuracy": round(exact_matches / n, 4) if n else 0,
                    "schema_valid_rate": round(valid_count / n, 4) if n else 0,
                    "p95_seconds_per_document": percentile95(durations),
                    "median_seconds_per_document": round(statistics.median(durations), 4) if durations else None,
                    "error_count": error_count,
                    "invoice_number_accuracy": round(field_correct["invoice_number"] / n, 4) if n else 0,
                    "date_accuracy": round(field_correct["date"] / n, 4) if n else 0,
                    "total_amount_accuracy": round(field_correct["total_amount"] / n, 4) if n else 0,
                    "currency_accuracy": round(field_correct["currency"] / n, 4) if n else 0,
                    "total_tokens": None, "thinking_tokens": None,
                }
                # exact_match_accuracy is derived from field-level correctness for all four fields.
                row["exact_match_accuracy"] = round(exact_matches / n, 4) if n else 0
                rows.append(row)

    columns = ["dataset", "provider", "model", "mode", "documents", "exact_match_accuracy",
               "schema_valid_rate", "p95_seconds_per_document", "median_seconds_per_document",
               "error_count", "invoice_number_accuracy", "date_accuracy", "total_amount_accuracy",
               "currency_accuracy", "total_tokens", "thinking_tokens", "initialization_error"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nEvaluation summary — dataset: {args.dataset} ({len(cases)} documents)")
    print("-" * 125)
    print(f"{'Model':<24} {'Mode':<17} {'Exact':>8} {'Valid':>8} {'p95(s)':>9} {'Errors':>8} "
          f"{'Inv#':>7} {'Date':>7} {'Amount':>8} {'Currency':>9}")
    for r in rows:
        if "exact_match_accuracy" not in r:
            print(f"{r['model']:<24.24} {r['mode']:<17} {'INIT ERROR':>8} {'—':>8} {'—':>9} {r['error_count']:>8}")
            continue
        p95 = r["p95_seconds_per_document"]
        print(f"{r['model']:<24.24} {r['mode']:<17} {r['exact_match_accuracy']:>7.1%} "
              f"{r['schema_valid_rate']:>7.1%} {str(p95):>9} {r['error_count']:>8} "
              f"{r['invoice_number_accuracy']:>6.1%} {r['date_accuracy']:>6.1%} "
              f"{r['total_amount_accuracy']:>7.1%} {r['currency_accuracy']:>8.1%}")
    print(f"\nPer-document log: {log_path}")
    print(f"Summary CSV:      {csv_path}")


if __name__ == "__main__":
    main()
