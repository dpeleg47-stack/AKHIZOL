"""Каталог поддерживаемых B2B-поставщиков. portal_url заполняется после проверки веб-версии
портала; scraper_ready=True — когда написан и протестирован Playwright-скрипт."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SupplierInfo:
    key: str
    title: str
    portal_url: str | None = None  # TODO: URL страницы входа веб-версии
    scraper_ready: bool = False
    hidden: bool = False  # не показывать в /connect (демо)


SUPPLIERS: dict[str, SupplierInfo] = {
    s.key: s
    for s in [
        SupplierInfo("shufersal_business", "שופרסל עסקים (Shufersal Business)"),
        SupplierInfo("open_israel", "Open Israel"),
        SupplierInfo("my_diplomat", "MyDiplomat"),
        SupplierInfo("self_order", "SelfOrder"),
        SupplierInfo("tavili", "TAVILI"),
        SupplierInfo("picksale", "PickSale"),
        SupplierInfo("strauss_up", "שטראוס UP (Strauss UP)"),
    ]
}


def title_of(key: str) -> str:
    info = SUPPLIERS.get(key)
    return info.title if info else key
