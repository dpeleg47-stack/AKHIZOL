import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import services.scrapers  # noqa: F401
from core import crypto
from core.consents import get_level
from core.database import SupplierCredential
from core.permissions import Level
from services.matching import best_match
from services.optimizer import Supplier
from services.scrapers.base import SCRAPERS, SupplierScraper

log = logging.getLogger(__name__)


@dataclass
class CompareResult:
    suppliers: list[Supplier] = field(default_factory=list)
    prices: dict[str, dict[int, float]] = field(default_factory=dict)
    titles: dict[str, dict[int, str]] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)  # подключены, но скрейпера ещё нет


def query_for(item: dict) -> str:
    name = item.get("name_he") or item.get("name") or ""
    return " ".join(p for p in (name, item.get("brand"), item.get("size")) if p)


async def connected_suppliers(session: AsyncSession, telegram_id: int) -> list[str]:
    rows = await session.scalars(
        select(SupplierCredential.supplier).where(SupplierCredential.telegram_id == telegram_id)
    )
    keys = list(dict.fromkeys(rows))
    keys += [k for k, cls in SCRAPERS.items() if cls.demo and k not in keys]
    return keys


async def build_scraper(session: AsyncSession, telegram_id: int, key: str) -> SupplierScraper | None:
    """Скрейпер с правами, которые пользователь реально выдал (минимум — чтение цен)."""
    cls = SCRAPERS.get(key)
    if cls is None:
        return None
    level = max(await get_level(session, telegram_id, key), Level.PRICES)
    if cls.demo:
        return cls("", "", level)
    row = await session.scalar(
        select(SupplierCredential).where(
            SupplierCredential.telegram_id == telegram_id, SupplierCredential.supplier == key
        )
    )
    if row is None:
        return None
    return cls(crypto.decrypt(row.login_enc), crypto.decrypt(row.password_enc), level)


async def _run(scraper: SupplierScraper, items: list[dict]):
    try:
        await scraper.login()
        terms = await scraper.terms()
        prices: dict[int, float] = {}
        titles: dict[int, str] = {}
        for i, it in enumerate(items):
            m = best_match(it, await scraper.search(query_for(it)))
            if m:
                prices[i] = m.candidate.unit_price
                titles[i] = m.candidate.title
        return scraper.name, terms, prices, titles, None
    except Exception as e:  # изолируем сбой одного поставщика
        log.exception("scraper %s failed", scraper.name)
        return scraper.name, None, {}, {}, str(e)[:120]
    finally:
        await scraper.close()


async def gather_prices(session: AsyncSession, telegram_id: int, items: list[dict]) -> CompareResult:
    """Сам ходит во все подключённые кабинеты (только чтение) и собирает цены."""
    res = CompareResult()
    scrapers: list[SupplierScraper] = []
    for key in await connected_suppliers(session, telegram_id):
        if key not in SCRAPERS:
            res.skipped.append(key)
            continue
        try:
            s = await build_scraper(session, telegram_id, key)
        except Exception:
            res.failed[key] = "не удалось расшифровать данные"
            continue
        if s:
            scrapers.append(s)

    for name, terms, prices, titles, err in await asyncio.gather(*(_run(s, items) for s in scrapers)):
        if err or terms is None:
            res.failed[name] = err or "нет данных"
            continue
        res.suppliers.append(terms)
        res.prices[name] = prices
        res.titles[name] = titles
    return res
