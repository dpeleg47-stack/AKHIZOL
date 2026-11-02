import re

_CART = re.compile(
    r"(добав|полож|собер|закин|оформ)\w*.{0,25}корзин|в корзину|add.{0,15}cart|(תוסיף|הוסף|תכניס|תוסיפו).{0,10}סל",
    re.I,
)


def is_cart_intent(text: str) -> bool:
    """Короткая команда вроде «добавь в корзину». Длинные сообщения — это списки товаров."""
    t = text.strip()
    return len(t) <= 60 and bool(_CART.search(t))
