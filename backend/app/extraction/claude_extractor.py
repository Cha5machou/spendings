"""Claude-based fallback: statement extraction for unknown layouts and
category suggestions. Only used when ANTHROPIC_API_KEY is configured."""

import base64
from datetime import date

import anthropic
from pydantic import BaseModel

from app.config import settings

_client: anthropic.Anthropic | None = None


def is_available() -> bool:
    return bool(settings.anthropic_api_key)


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


class StatementLine(BaseModel):
    date: date
    label: str
    amount: float  # negative for debits, positive for credits


class StatementExtraction(BaseModel):
    transactions: list[StatementLine]


EXTRACTION_PROMPT = (
    "This is a bank or credit card statement. Extract every transaction line. "
    "Use the operation date (not the value date). Amount must be signed: negative when money "
    "leaves the account (débit), positive when it comes in (crédit). Keep the label as printed, "
    "merged onto one line. Skip balances, totals and headers."
)


def _extract(content_block: dict) -> list:
    from app.extraction import ExtractedTransaction

    client = get_client()
    with client.messages.stream(
        model=settings.claude_model,
        max_tokens=64000,
        messages=[{"role": "user", "content": [content_block, {"type": "text", "text": EXTRACTION_PROMPT}]}],
        output_format=StatementExtraction,
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this document.")
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError("Claude returned no structured output for this document.")
    return [ExtractedTransaction(line.date, line.label, line.amount) for line in parsed.transactions]


def extract_from_pdf(content: bytes) -> list:
    encoded = base64.standard_b64encode(content).decode("utf-8")
    return _extract({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": encoded}})


def extract_from_image_or_pdf(content: bytes, mime_type: str) -> list:
    if mime_type == "application/pdf":
        return extract_from_pdf(content)
    encoded = base64.standard_b64encode(content).decode("utf-8")
    return _extract({"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}})


class CategorySuggestion(BaseModel):
    transaction_id: int
    category_name: str
    confidence: float  # 0..1


class CategorySuggestions(BaseModel):
    suggestions: list[CategorySuggestion]


def suggest_categories(transactions: list[dict], category_names: list[str]) -> list[CategorySuggestion]:
    """transactions: [{"id", "label", "amount"}]. Returns one suggestion per transaction
    the model is reasonably sure about; names must be in category_names."""
    if not transactions:
        return []
    client = get_client()
    listing = "\n".join(f'{item["id"]}\t{item["amount"]:.2f}\t{item["label"]}' for item in transactions)
    response = client.messages.parse(
        model=settings.claude_model,
        max_tokens=16000,
        system=(
            "You categorise personal bank transactions (mostly French). Choose exactly one category "
            "from the allowed list for each transaction; set confidence below 0.5 when unsure. "
            "Allowed categories: " + ", ".join(category_names)
        ),
        messages=[{"role": "user", "content": "id\tamount\tlabel\n" + listing}],
        output_format=CategorySuggestions,
    )
    if response.parsed_output is None:
        return []
    allowed = set(category_names)
    return [item for item in response.parsed_output.suggestions if item.category_name in allowed]
