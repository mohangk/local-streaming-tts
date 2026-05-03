from __future__ import annotations

import base64

import httpx

from tts_app.ocr_providers.base import OCROptions, OCRProviderError


QWEN_OCR_ENDPOINT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_OCR_PROMPT = (
    "Preserve only visible text content from this image without extra descriptions, "
    "formatting, or commentary. Preserve visible Chinese text and visible pinyin exactly "
    "as shown. Do not infer missing text, do not generate missing pinyin, and do not "
    "transliterate Chinese characters into pinyin."
)


class QwenOCRProvider:
    name = "qwen-ocr"

    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        if not self.api_key:
            raise OCRProviderError("API key is required for qwen ocr provider")

        image_data = base64.b64encode(image).decode("ascii")
        payload = {
            "model": options.model or self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                        },
                        {"type": "text", "text": QWEN_OCR_PROMPT},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(QWEN_OCR_ENDPOINT, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise OCRProviderError(f"qwen ocr provider request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            message = _response_error_message(response)
            raise OCRProviderError(
                f"qwen ocr provider request failed with status {response.status_code}: {message}"
            )

        try:
            response_payload = response.json()
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OCRProviderError("qwen ocr provider returned malformed response") from exc

        if not isinstance(content, str):
            raise OCRProviderError("qwen ocr provider returned malformed response")

        text = content.strip()
        if not text:
            raise OCRProviderError("qwen ocr provider returned empty text")
        return text


def _response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message[:500]
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message[:500]
    return response.text[:500]
