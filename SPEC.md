# Invoice Extractor - SPEC

## 1. Problem
LLMs return free-form text; we need reliable structured extraction. 
The goal is to extract four specific fields from an unstructured invoice text and return them as a valid, parseable JSON object, strictly adhering to the defined schema.

## 2. Input
- **Document type:** Plain text invoice (Arabic or English).
- **Source:** Text extracted from a PDF/image (via OCR) or manually typed.
- **Example:** "فاتورة رقم 1042 بتاريخ 2026-10-01، المبلغ الإجمالي 3500 جنيه."
- **Note:** The system does not process PDFs or images directly at this stage; the input is text only.

## 3. Output schema

| field | type | rule |
| --- | --- | --- |
| invoice_number | string | keep leading zeros, never convert to number |
| date | string or null | ISO format YYYY-MM-DD, null if not in the document |
| total_amount | number or null | no currency symbol, no thousands separator |
| currency | string or null | ISO code like EGP, null if ambiguous or not stated |

All four keys must always be present. Missing values are null.

## 4. Rules
- **Output:** JSON only, no additional text or explanation.
- **Thinking mode:** Must be disabled (`think=false`) to ensure speed and reduce cost.
- **Schema enforcement:** The schema is enforced programmatically using JSON Schema + Pydantic for validation.
- **Determinism:** Set `temperature=0` to ensure consistency across repeated runs.
- **Field rules:** As defined in the schema table (leading zeros, ISO date format, amount as number, ISO currency code).

## 5. Success criteria
- **Test set:** 30 synthetic invoices (Arabic and English), including hard cases (leading zeros, missing dates, ambiguous currencies).
- **Correctness:** An invoice is correct only if all four fields match the expected values **exactly**.
- **Target:** At least 90% of documents correct (27 out of 30).
- **Schema validity:** 100% of outputs pass Pydantic validation.
- **Speed:** Under 10 seconds per document.

## 6. Model comparison

| model | think | total duration | eval rate (tok/s) | key names | types ok |
| --- | --- | --- | --- | --- | --- |
| llama3 | false | 3.41s | 11.06 | ✅ Correct | ❌ invoice_number was a number (1042) |
| qwen3-8b | false | 5.24s | 9.60 | ❌ Arabic keys | ❌ total_amount was text + currency ("3500 جنيه") |
| qwen3.5:9b | false | 5.40s | 8.33 | ❌ camelCase (invoiceNumber) | ❌ total_amount was text ("3500") |
| Gemini 3.5 Flash | N/A | 16.45s | TBD | ✅ Correct | ✅ Correct (EGP extracted) |

## 7. Preliminary notes

### Schema Violations (Critical)
- **llama3:** Fastest model (3.41s) but the first to violate the schema. It returned `invoice_number` as a number (`1042`) instead of a string, which breaks the leading-zeros rule (e.g., `"001042"` would become `1042`).
- **qwen3-8b:** Returned keys in Arabic (`"رقم الفاتورة"`, `"التاريخ"`) instead of English, and returned `total_amount` as a string including the currency (`"3500 جنيه"`) instead of a pure number.
- **qwen3.5:9b:** Used camelCase keys (`invoiceNumber`, `totalAmount`) instead of the required snake_case, and returned `total_amount` as a string (`"3500"`).
- **All local models (llama3, qwen3-8b, qwen3.5:9b):** Completely ignored the `currency` field, despite the word "جنيه" (EGP) being present in the input text. This **suggests** that prompt-only approaches may be insufficient for strict schema adherence with small local models. However, this is based on a single sample and has not yet been tested with programmatic schema enforcement. Notably, Gemini complied with the same prompt-only approach, which indicates the limitation is model-dependent rather than universal.

### Stability & Consistency
- **qwen3.5:9b:** Changed its key format between runs (camelCase vs. snake_case), indicating unstable schema adherence. This makes it unreliable for production without programmatic enforcement.

### Performance vs. Correctness
- **Speed alone is not a criterion:** llama3 is the fastest (3.41s) but the least compliant with the schema. It cannot be considered the best model before testing on a wider set of documents (30+ invoices) and enforcing the schema programmatically.
- **Gemini 3.5 Flash:** The only model that fully complied with the spec (correct keys, correct types, and extracted `EGP`). However, its total duration (16.45s) exceeds the 10-second success criterion. This may be due to network latency or model load, and should be re-tested with `gemini-3.5-flash-lite`.

### Next Steps
- **Current tests were prompt-only.** All models will be re-tested with **programmatic schema enforcement** (JSON Schema + Pydantic) and `temperature=0` to isolate model capability from prompt engineering.
- **Test set expansion:** Move from a single sample to 30 synthetic invoices (Arabic and English) including hard cases (leading zeros, missing dates, ambiguous currencies).
- **Gemini model selection:** Re-run Gemini with `gemini-3.5-flash-lite` to check if it meets the 10-second speed criterion.