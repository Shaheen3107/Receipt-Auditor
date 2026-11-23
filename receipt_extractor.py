"""Reads a receipt photo with a vision model and returns checked, structured data.

Pieces in this file:
  Item, Receipt      the form the AI's answer must fit (Pydantic checks it)
  image_to_data_url  turns a photo into text, because the API only accepts text
  ask_receipt        sends the photo, validates the reply, retries if it is invalid
  to_number          turns price text like "70000.00" or "1,591,600" into a whole number
"""
import ast
import base64
import io
import re
from typing import Optional

from pydantic import BaseModel, ValidationError

MODEL = "qwen/qwen3.8-27b"      # the vision model on Groq at the time of writing; check console.groq.com/docs/vision


class Item(BaseModel):
    name: str
    quantity: int
    price: int                  # the amount printed for that line (line total, not per unit)


class Receipt(BaseModel):
    store_name: Optional[str]
    date: Optional[str]
    items: list[Item]
    subtotal: Optional[int]
    total: Optional[int]        # Optional: the receipt may not show it, so None is allowed


PROMPT = """You read photos of receipts. Extract the data and reply with ONLY a JSON object with exactly these keys:

{
  "store_name": string or null,
  "date": string or null,
  "items": [{"name": string, "quantity": integer, "price": integer}],
  "subtotal": integer or null,
  "total": integer or null
}

Rules:
- Prices are whole numbers in rupiah. Dots and commas in prices are thousands separators: "45.000" and "45,000" both mean 45000.
- "price" is the amount printed on the receipt for that line (the line total), not the price per unit.
- "total" is the final amount to pay, after tax and service charge.
- If something is not on the receipt, use null. Never guess or invent a value.
- Do not add any text outside the JSON."""


def image_to_data_url(pil_image):
    """Photo -> JPEG bytes -> base64 text, labelled as an image (a 'data URL')."""
    buffer = io.BytesIO()
    pil_image.convert("RGB").save(buffer, format="JPEG", quality=85)
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def ask_receipt(client, pil_image, attempts=3):
    """Ask the model to read one receipt. Returns a Receipt, or None if every attempt was invalid."""
    data_url = image_to_data_url(pil_image)
    for attempt in range(attempts):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            response_format={"type": "json_object"},
            temperature=0,
        )
        text = response.choices[0].message.content
        try:
            return Receipt.model_validate_json(text)        # checks every field and type
        except ValidationError as problem:
            print(f"Attempt {attempt + 1}: answer did not match the form -> {problem.error_count()} problem(s)")
    return None


def to_number(value):
    """Price text -> whole number. Returns None for missing or ambiguous values.

    "1,591,600" -> 1591600     thousands separators are dropped
    "70000.00"  -> 70000       cents are dropped
    "Rp 116000" -> 116000      currency prefix is dropped
    a list with two different values -> None (we cannot tell which is right)
    """
    if isinstance(value, str) and value.strip().startswith("["):
        value = ast.literal_eval(value)             # text that looks like a list -> a real list
    if isinstance(value, list):
        numbers = {to_number(v) for v in value}
        return numbers.pop() if len(numbers) == 1 else None
    if not isinstance(value, str):
        return None
    text = re.sub(r"^Rp\.?\s*", "", value.strip()).rstrip(".,")
    text = re.sub(r"[.,]\d{1,2}$", "", text)        # drop cents: ".00", ",50"
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None
