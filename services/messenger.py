"""Отправка заказов менеджерам: WhatsApp (Green API) или email (SMTP)."""
import asyncio
import re
import smtplib
from email.message import EmailMessage

import aiohttp

from core.config import settings
from core.database import SupplierContact


def normalize_phone(raw: str) -> str | None:
    """Израильский номер -> 972XXXXXXXXX (без +). None, если не похоже на номер."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    if digits.startswith("972") and 11 <= len(digits) <= 12:
        return digits
    return None


def fallback_hebrew_order(lines: list[dict]) -> str:
    rows = []
    for ln in lines:
        name = " ".join(p for p in (ln.get("name_he") or ln.get("name"), ln.get("brand"), ln.get("size")) if p)
        qty = f"{ln.get('quantity', 1):g}" + (f" {ln['unit']}" if ln.get("unit") else "")
        rows.append(f"• {name} — {qty}")
    return (
        "שלום,\nאשמח להזמין את הפריטים הבאים:\n" + "\n".join(rows) +
        "\nאבקש לאשר זמינות, מחיר סופי וזמן אספקה. תודה!"
    )


async def send_whatsapp(phone: str, text: str) -> None:
    url = f"https://api.green-api.com/waInstance{settings.green_api_instance}/sendMessage/{settings.green_api_token}"
    async with aiohttp.ClientSession() as http:
        async with http.post(url, json={"chatId": f"{phone}@c.us", "message": text}) as r:
            if r.status != 200:
                raise RuntimeError(f"Green API: HTTP {r.status}")


def _send_email_sync(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from or settings.smtp_user, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    await asyncio.to_thread(_send_email_sync, to, subject, body)


async def send_order(contact: SupplierContact, text: str) -> str:
    """Возвращает использованный канал: 'whatsapp' | 'email'."""
    if contact.whatsapp and settings.green_api_instance and settings.green_api_token:
        await send_whatsapp(contact.whatsapp, text)
        return "whatsapp"
    if contact.email and settings.smtp_host:
        await send_email(contact.email, "הזמנה חדשה", text)
        return "email"
    raise RuntimeError("Нет настроенного канала отправки (Green API или SMTP)")
