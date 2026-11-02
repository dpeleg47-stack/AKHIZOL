from services.compare import CompareResult
from services.optimizer import Plan
from services.scrapers.registry import title_of


def _plan_text(label: str, plan: Plan | None) -> str:
    if plan is None:
        return f"{label}: подходящего варианта нет"
    lines = [f"{label} — {plan.total:.2f} ₪"]
    for sup, ls in plan.assignments.items():
        lines.append(f"• {title_of(sup)}: {len(ls)} поз., {sum(t for _, t in ls):.2f} ₪")
    if plan.delivery:
        lines.append(f"• доставка: {plan.delivery:.2f} ₪")
    return "\n".join(lines)


def format_comparison(items: list[dict], result: CompareResult, out: dict[str, Plan | None]) -> str:
    single, split = out["single"], out["split"]
    parts = [_plan_text("🅰️ Один поставщик", single), _plan_text("🅱️ Сплит-корзина", split)]
    if single and split and len(split.missing) <= len(single.missing) and split.total < single.total:
        parts.append(f"💰 Сплит дешевле на {single.total - split.total:.2f} ₪")
    best = split or single
    if best and best.missing:
        names = ", ".join(items[i].get("name", "?") for i in best.missing)
        parts.append(f"❓ Не найдено ни у кого: {names}")
    if result.failed:
        parts.append("⚠️ Не ответили: " + ", ".join(title_of(k) for k in result.failed))
    if result.skipped:
        parts.append("ℹ️ Автосбор цен пока не готов: " + ", ".join(title_of(k) for k in result.skipped))
    return "\n\n".join(parts)
