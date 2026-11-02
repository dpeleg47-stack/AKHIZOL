import base64
import json
import re

from anthropic import AsyncAnthropic

from core.config import settings

_client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

SYSTEM = (
    "Ты — парсер закупочных списков для израильского розничного бизнеса. "
    "Вход: свободный текст (иврит/русский/английский) или фото накладной/списка. "
    "Верни ТОЛЬКО JSON-массив без пояснений и без markdown. Элемент: "
    '{"name": str, "name_he": str|null, "brand": str|null, "size": str|null, "quantity": number, "unit": str|null}. name_he — название товара на иврите (для поиска в каталогах), если вход не на иврите. '
    "Не выдумывай позиции, которых нет во входных данных."
)


def _extract_json(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


async def _ask(content: list[dict], system: str = SYSTEM, max_tokens: int = 2000) -> list[dict]:
    if _client is None:
        raise RuntimeError("ANTHROPIC_API_KEY не задан")
    resp = await _client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return _extract_json("".join(b.text for b in resp.content if b.type == "text"))


async def parse_text(text: str) -> list[dict]:
    return await _ask([{"type": "text", "text": text}])


async def parse_image(image_bytes: bytes, media_type: str = "image/jpeg") -> list[dict]:
    return await _ask(
        [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(image_bytes).decode(),
                },
            },
            {"type": "text", "text": "Распознай список товаров на изображении."},
        ]
    )


HEBREW_SYSTEM = (
    "Ты помощник владельца магазина в Израиле. Напиши короткое вежливое деловое сообщение "
    "менеджеру поставщика НА ИВРИТЕ с заказом: приветствие, список позиций (название, бренд, "
    "фасовка, количество) и просьба подтвердить наличие, итоговую цену и срок доставки. "
    "Не выдумывай цены, адреса и имена. Верни только текст сообщения."
)


async def compose_hebrew_order(supplier_title: str, lines: list[dict]) -> str:
    if _client is None:
        raise RuntimeError("ANTHROPIC_API_KEY не задан")
    resp = await _client.messages.create(
        model=settings.claude_model,
        max_tokens=800,
        system=HEBREW_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Поставщик: {supplier_title}\nПозиции (JSON): {json.dumps(lines, ensure_ascii=False)}",
            }
        ],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()

