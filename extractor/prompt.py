"""Single shared prompt used by all providers and both extraction modes."""

from extractor.models import Invoice

PROMPT_TEMPLATE = """Extract the invoice fields from the invoice text below.
Return JSON only, with exactly these four keys and no others:
- "invoice_number": string. Preserve every leading zero; never convert it to a number.
- "date": string in ISO YYYY-MM-DD format, or null if the date is missing or cannot be determined.
- "total_amount": JSON number or null. Include no currency symbol and no thousands separators.
- "currency": ISO 4217 three-letter uppercase currency code (for example EGP, USD, EUR), or null if not stated or ambiguous.
All four keys must always be present. Use null for missing values.
Normalize Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) to ASCII digits in extracted values.
For ambiguous currency words such as "ريال" or "دينار", return null unless the country/context identifies one specific ISO currency code.
Convert an unambiguous written date to YYYY-MM-DD. Do not invent missing information.
Invoice text:
<<<
{text}
>>>
"""


def build_prompt(text: str) -> str:
    return PROMPT_TEMPLATE.format(text=text)
