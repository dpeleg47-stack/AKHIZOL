"""Оптимизация корзины: лучший «всё у одного» и лучший сплит между 2–3 поставщиками."""
from dataclasses import dataclass, field
from itertools import combinations


@dataclass(frozen=True)
class Supplier:
    name: str
    delivery_fee: float = 0.0
    free_delivery_from: float | None = None  # порог бесплатной доставки
    min_order: float = 0.0


@dataclass
class Plan:
    assignments: dict[str, list[tuple[int, float]]]  # supplier -> [(item_idx, line_total)]
    subtotal: float
    delivery: float
    missing: list[int] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.delivery, 2)


def delivery_cost(s: Supplier, subtotal: float) -> float:
    if s.free_delivery_from is not None and subtotal >= s.free_delivery_from:
        return 0.0
    return s.delivery_fee


def _build(subset: tuple[Supplier, ...], qty: list[float], prices: dict[str, dict[int, float]]) -> Plan | None:
    assign: dict[str, list[tuple[int, float]]] = {s.name: [] for s in subset}
    missing: list[int] = []
    for i, q in enumerate(qty):
        cands = [(prices[s.name][i], s.name) for s in subset if i in prices.get(s.name, {})]
        if not cands:
            missing.append(i)
            continue
        price, name = min(cands)
        assign[name].append((i, round(price * q, 2)))

    subtotal = delivery = 0.0
    final: dict[str, list[tuple[int, float]]] = {}
    for s in subset:
        lines = assign[s.name]
        if not lines:
            continue
        sub = sum(t for _, t in lines)
        if sub < s.min_order:
            return None  # не добираем минимальный заказ — вариант невалиден
        subtotal += sub
        delivery += delivery_cost(s, sub)
        final[s.name] = lines
    if not final:
        return None
    return Plan(final, round(subtotal, 2), round(delivery, 2), missing)


def optimize(
    qty: list[float],
    suppliers: list[Supplier],
    prices: dict[str, dict[int, float]],
    max_split: int = 3,
) -> dict[str, Plan | None]:
    """qty[i] — количество позиции i; prices[supplier][i] — цена за единицу.
    Возвращает {'single': Plan|None, 'split': Plan|None}. Планы с меньшим числом
    пропущенных позиций всегда лучше; при равенстве — дешевле итог."""

    def key(p: Plan):
        return (len(p.missing), p.total)

    best_single: Plan | None = None
    best_split: Plan | None = None
    for r in range(1, min(max_split, len(suppliers)) + 1):
        for subset in combinations(suppliers, r):
            plan = _build(subset, qty, prices)
            if plan is None:
                continue
            if r == 1 and (best_single is None or key(plan) < key(best_single)):
                best_single = plan
            if best_split is None or key(plan) < key(best_split):
                best_split = plan
    return {"single": best_single, "split": best_split}


def best_kind(plans: dict | None) -> str | None:
    """Какой из планов ({'single': {...}, 'split': {...}}, значения — dict с 'missing' и 'total')
    считать лучшим: меньше ненайденных позиций, затем дешевле. При равенстве — 'single'."""
    cands = [(len(p["missing"]), p["total"], k) for k, p in (plans or {}).items() if p]
    return min(cands)[2] if cands else None
