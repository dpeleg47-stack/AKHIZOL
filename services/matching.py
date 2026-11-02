"""Сопоставление запрошенной позиции с товарами из каталога поставщика (иврит/русский/английский)."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# единица -> (базовая единица, множитель)
_UNITS: dict[str, tuple[str, float]] = {
    "kg": ("g", 1000), "кг": ("g", 1000), "קג": ("g", 1000),
    "g": ("g", 1), "gr": ("g", 1), "гр": ("g", 1), "г": ("g", 1), "גרם": ("g", 1), "גר": ("g", 1),
    "l": ("ml", 1000), "л": ("ml", 1000), "ליטר": ("ml", 1000), "ל": ("ml", 1000),
    "ml": ("ml", 1), "мл": ("ml", 1), "מל": ("ml", 1),
    "pcs": ("pcs", 1), "шт": ("pcs", 1), "יח": ("pcs", 1), "יחידות": ("pcs", 1),
}
_UNIT_RE = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))
_SIZE_RE = re.compile(
    rf"(?:(\d+)\s*[x×*]\s*)?(\d+(?:[.,]\d+)?)\s*({_UNIT_RE})(?![a-zа-яё\u0590-\u05ff])", re.I
)
_QUOTES = re.compile(r"[\"'׳״`]")


@dataclass
class Candidate:
    title: str
    unit_price: float
    size: str | None = None
    barcode: str | None = None
    in_stock: bool = True


@dataclass
class Match:
    candidate: Candidate
    score: float


def _clean(s: str) -> str:
    return _QUOTES.sub("", s.lower())


def parse_size(s: str | None) -> tuple[str, float] | None:
    """'6x1.5L' -> ('ml', 9000.0); '500 גרם' -> ('g', 500.0)"""
    if not s:
        return None
    m = _SIZE_RE.search(_clean(s))
    if not m:
        return None
    mult = int(m.group(1)) if m.group(1) else 1
    base, factor = _UNITS[m.group(3)]
    return base, mult * float(m.group(2).replace(",", ".")) * factor


def _tokens(s: str) -> list[str]:
    s = _SIZE_RE.sub(" ", _clean(s))
    return [t for t in re.sub(r"[^\w\s]", " ", s).split() if t]


def _name_score(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    jaccard = len(sa & sb) / len(sa | sb)
    seq = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return 0.5 * jaccard + 0.5 * seq


def score(item: dict, cand: Candidate) -> float:
    if item.get("barcode") and cand.barcode and str(item["barcode"]) == str(cand.barcode):
        return 1.0
    brand = item.get("brand") or ""
    names = [n for n in (item.get("name"), item.get("name_he")) if n]
    best = 0.0
    for n in names:
        best = max(best, _name_score(f"{brand} {n}".strip(), cand.title), _name_score(n, cand.title))
    if brand and set(_tokens(brand)) <= set(_tokens(cand.title)):
        best = min(1.0, best + 0.1)

    want = parse_size(item.get("size"))
    have = parse_size(cand.size) or parse_size(cand.title)
    if want and have:
        if want[0] == have[0] and abs(want[1] - have[1]) / want[1] <= 0.01:
            best = min(1.0, best + 0.1)
        else:
            best *= 0.3  # другая фасовка — это другой товар
    return best


def best_match(item: dict, cands: list[Candidate], threshold: float = 0.55) -> Match | None:
    scored = [Match(c, score(item, c)) for c in cands if c.in_stock]
    scored = [m for m in scored if m.score >= threshold]
    if not scored:
        return None
    top = max(m.score for m in scored)
    near = [m for m in scored if top - m.score <= 0.05]
    return min(near, key=lambda m: m.candidate.unit_price)
