import json
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.payment import pay_keyboard
from bot.middlewares.subscription import SubscriptionMiddleware
from core import ai_parser
from core.consents import audit, get_consent, levels_for
from core.database import Order, SupplierContact, get_or_create_user
from core.permissions import Level, PermissionDenied
from services import messenger
from services.compare import build_scraper, gather_prices
from services.optimizer import Plan, Supplier, best_kind, delivery_cost, optimize
from services.report import format_comparison
from services.scrapers.registry import title_of

log = logging.getLogger(__name__)
router = Router()
router.message.middleware(SubscriptionMiddleware())

KIND_LABEL = {"single": "А (один поставщик)", "split": "Б (сплит-корзина)"}


async def _denied(call: CallbackQuery, session: AsyncSession) -> bool:
    user = await get_or_create_user(session, call.from_user.id, call.from_user.username)
    if user.has_access():
        return False
    await call.answer()
    await call.message.answer("⏳ Бесплатный период закончился. Оформите подписку:", reply_markup=pay_keyboard())
    return True


def _plan_to_dict(plan: Plan | None, smap: dict[str, Supplier], titles: dict) -> dict | None:
    if plan is None:
        return None
    sups = {}
    for name, ls in plan.assignments.items():
        sub = round(sum(t for _, t in ls), 2)
        sups[name] = {
            "lines": [[i, t, titles.get(name, {}).get(i, "")] for i, t in ls],  # [idx, сумма, найденное название]
            "subtotal": sub,
            "delivery": delivery_cost(smap[name], sub),
        }
    return {"total": plan.total, "missing": plan.missing, "suppliers": sups}


# ---------- сравнение: бот сам собирает цены у подключённых поставщиков ----------
async def run_compare(target: Message, user_id: int, state: FSMContext, session: AsyncSession):
    items = (await state.get_data()).get("items")
    if not items:
        await target.answer("Сначала пришлите список товаров.")
        return
    wait = await target.answer("🔎 Собираю цены у ваших поставщиков, это может занять минуту…")
    result = await gather_prices(session, user_id, items)
    if not result.suppliers:
        extra = f"\nАвтосбор для этих поставщиков ещё не готов: {', '.join(title_of(k) for k in result.skipped)}" if result.skipped else ""
        await wait.edit_text(
            "Мне пока не у кого брать цены. Подключите кабинет поставщика: /connect (доступ только на чтение цен)." + extra
        )
        return
    qty = [float(it.get("quantity") or 1) for it in items]
    out = optimize(qty, result.suppliers, result.prices)
    smap = {s.name: s for s in result.suppliers}
    plans = {k: _plan_to_dict(v, smap, result.titles) for k, v in out.items()}
    await state.update_data(plans=plans, drafts={}, carts={}, pending_cart=None)

    text = format_comparison(items, result, out)
    kind = best_kind(plans)
    levels = await levels_for(session, user_id)
    needs = kind and any(
        max(levels.get(s, Level.NONE), Level.PRICES) < Level.CART for s in plans[kind]["suppliers"]
    )
    text += "\n\n💬 Скажите «добавь в корзину» — и я соберу корзину" + (
        " (один раз попрошу разрешение)." if needs else "."
    )

    kb = InlineKeyboardBuilder()
    same = plans["single"] and plans["split"] and plans["single"]["suppliers"].keys() == plans["split"]["suppliers"].keys()
    if plans["single"]:
        kb.button(text="🧺 Корзина А", callback_data="cart:single")
        kb.button(text="📨 Заявка А", callback_data="ord:single")
    if plans["split"] and not same:
        kb.button(text="🧺 Корзина Б", callback_data="cart:split")
        kb.button(text="📨 Заявка Б", callback_data="ord:split")
    kb.adjust(2)
    await wait.edit_text(text, reply_markup=kb.as_markup())


@router.message(Command("compare"))
async def cmd_compare(message: Message, state: FSMContext, session: AsyncSession):
    await run_compare(message, message.from_user.id, state, session)


@router.callback_query(F.data == "cmp")
async def cb_compare(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    if await _denied(call, session):
        return
    await call.answer()
    await run_compare(call.message, call.from_user.id, state, session)


# ---------- корзина («добавь в корзину»; нужен Level.CART) ----------
async def run_cart(target: Message, uid: int, state: FSMContext, session: AsyncSession, kind: str):
    data = await state.get_data()
    plan = (data.get("plans") or {}).get(kind)
    items = data.get("items") or []
    if not plan:
        await target.answer("Список устарел — пришлите его заново, я сравню цены.")
        return
    levels = await levels_for(session, uid)
    carts = dict(data.get("carts") or {})
    blocked = False
    for sup, info in plan["suppliers"].items():
        title = title_of(sup)
        if sup in carts:
            await target.answer(f"🧺 {title}: уже в корзине.")
            continue
        lvl = max(levels.get(sup, Level.NONE), Level.PRICES)
        if lvl < Level.CART:
            blocked = True
            kb = InlineKeyboardBuilder()
            kb.button(text="🔓 Разрешить корзину", callback_data=f"accup:{sup}:2")
            await target.answer(
                f"🔒 {title}: пока у меня доступ только к ценам. Чтобы собрать корзину, нужно ваше разрешение.",
                reply_markup=kb.as_markup(),
            )
            continue
        scraper = await build_scraper(session, uid, sup)
        if scraper is None:
            await target.answer(f"⚠️ {title}: нет сохранённого доступа.")
            continue
        lines = [{**items[ln[0]], "matched_title": ln[2], "line_total": ln[1]} for ln in info["lines"]]
        try:
            await scraper.login()
            res = await scraper.add_to_cart(lines)
        except NotImplementedError as e:
            await target.answer(f"ℹ️ {title}: {e}.")
            continue
        except PermissionDenied as e:
            await target.answer(f"🔒 {title}: {e}")
            continue
        except Exception:
            log.exception("cart failed")
            await target.answer(f"⚠️ {title}: не удалось собрать корзину.")
            continue
        finally:
            await scraper.close()
        await audit(session, uid, sup, "cart", f"{len(lines)} поз., {res.total:.2f}")
        payable = round(res.total + info["delivery"], 2)
        carts[sup] = {"payable": payable}
        kb = InlineKeyboardBuilder()
        if lvl >= Level.PAY:
            kb.button(text=f"💳 Оформить и оплатить ≈{payable:.2f} ₪", callback_data=f"chk:{sup}")
        tail = "" if lvl >= Level.PAY else "\nОформить и оплатить заказ вы можете сами в кабинете поставщика."
        link = f"\n{res.url}" if res.url else ""
        await target.answer(
            f"🧺 {title}: корзина собрана, к оплате ≈{payable:.2f} ₪ (с доставкой).{link}{tail}",
            reply_markup=kb.as_markup() if lvl >= Level.PAY else None,
        )
    await state.update_data(carts=carts, pending_cart=kind if blocked else None)


@router.callback_query(F.data.startswith("cart:"))
async def cb_cart(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    if await _denied(call, session):
        return
    await call.answer()
    await run_cart(call.message, call.from_user.id, state, session, call.data[5:])


# ---------- оплата (Level.PAY, лимит и подтверждение каждого заказа) ----------
async def _pay_context(call: CallbackQuery, state: FSMContext, session: AsyncSession, sup: str):
    cart = ((await state.get_data()).get("carts") or {}).get(sup)
    consent = await get_consent(session, call.from_user.id, sup)
    if not cart or not consent or consent.level < Level.PAY or not consent.order_limit:
        await call.answer("Корзина устарела или нет разрешения на оплату", show_alert=True)
        return None
    if cart["payable"] > consent.order_limit:
        await call.answer()
        await call.message.answer(
            f"⛔ Сумма {cart['payable']:.2f} ₪ выше вашего лимита {consent.order_limit:.0f} ₪. Изменить лимит: /access"
        )
        return None
    return cart["payable"], consent.order_limit


@router.callback_query(F.data.startswith("chk:"))
async def cb_chk(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    if await _denied(call, session):
        return
    sup = call.data[4:]
    ctx = await _pay_context(call, state, session, sup)
    if not ctx:
        return
    payable, limit = ctx
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, оплатить", callback_data=f"chkok:{sup}")
    kb.button(text="Отмена", callback_data="chkno")
    kb.adjust(1)
    await call.answer()
    await call.message.answer(
        f"Подтвердите оплату\n{title_of(sup)}\nСумма ≈{payable:.2f} ₪ (ваш лимит {limit:.0f} ₪)\n"
        "Способ оплаты — тот, что сохранён в вашем кабинете поставщика.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "chkno")
async def cb_chkno(call: CallbackQuery):
    await call.answer("Отменено")
    await call.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("chkok:"))
async def cb_chkok(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    if await _denied(call, session):
        return
    sup, uid = call.data[6:], call.from_user.id
    ctx = await _pay_context(call, state, session, sup)
    if not ctx:
        return
    payable, limit = ctx
    # Убираем корзину из состояния ДО оплаты: повторное нажатие не создаст второй платёж.
    carts = dict((await state.get_data()).get("carts") or {})
    carts.pop(sup, None)
    await state.update_data(carts=carts)
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)

    scraper = await build_scraper(session, uid, sup)
    if scraper is None:
        await call.message.answer("⚠️ Нет сохранённого доступа.")
        return
    try:
        await scraper.login()
        res = await scraper.checkout(expected_total=payable, max_total=limit)
    except (PermissionDenied, NotImplementedError) as e:
        await call.message.answer(f"🔒 {e}")
        return
    except Exception:
        log.exception("checkout failed")
        await audit(session, uid, sup, "pay_error", f"{payable:.2f}")
        await call.message.answer(
            "⚠️ Ошибка при оформлении. Проверьте статус заказа в кабинете поставщика, прежде чем повторять."
        )
        return
    finally:
        await scraper.close()
    session.add(Order(telegram_id=uid, supplier=sup, channel="portal", total=res.total,
                      items_json="[]", message=res.confirmation, status="paid"))
    await audit(session, uid, sup, "pay", f"{res.total:.2f} {res.confirmation}")
    await call.message.answer(f"✅ Заказ оформлен: {title_of(sup)}, {res.total:.2f} ₪\nПодтверждение: {res.confirmation}")


# ---------- заявки менеджерам (каждое сообщение — только после вашей кнопки) ----------
@router.callback_query(F.data.startswith("ord:"))
async def cb_order(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    if await _denied(call, session):
        return
    data = await state.get_data()
    plan = (data.get("plans") or {}).get(call.data[4:])
    items = data.get("items") or []
    if not plan:
        await call.answer("Список устарел — повторите сравнение", show_alert=True)
        return
    await call.answer()
    drafts = {}
    for sup, info in plan["suppliers"].items():
        lines = [items[ln[0]] for ln in info["lines"]]
        try:
            text = await ai_parser.compose_hebrew_order(title_of(sup), lines)
        except Exception:
            log.exception("compose failed, using template")
            text = messenger.fallback_hebrew_order(lines)
        total = round(info["subtotal"] + info["delivery"], 2)
        drafts[sup] = {"text": text, "total": total, "items": lines}
        contact = await session.scalar(
            select(SupplierContact).where(
                SupplierContact.telegram_id == call.from_user.id, SupplierContact.supplier == sup
            )
        )
        kb, note = None, "\n\n⚠️ Контакт менеджера не задан — /contact"
        if contact:
            b = InlineKeyboardBuilder()
            b.button(text="📤 Отправить менеджеру", callback_data=f"send:{sup}")
            kb, note = b.as_markup(), ""
        await call.message.answer(f"📨 {title_of(sup)} — ≈{total:.2f} ₪\n\n{text}{note}", reply_markup=kb)
    await state.update_data(drafts=drafts)


@router.callback_query(F.data.startswith("send:"))
async def cb_send(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    if await _denied(call, session):
        return
    sup = call.data[5:]
    draft = ((await state.get_data()).get("drafts") or {}).get(sup)
    contact = await session.scalar(
        select(SupplierContact).where(SupplierContact.telegram_id == call.from_user.id, SupplierContact.supplier == sup)
    )
    if not draft or not contact:
        await call.answer("Черновик устарел или нет контакта", show_alert=True)
        return
    await call.answer()
    try:
        channel = await messenger.send_order(contact, draft["text"])
    except Exception as e:
        log.exception("send failed")
        await call.message.answer(f"⚠️ Не удалось отправить: {e}")
        return
    session.add(Order(telegram_id=call.from_user.id, supplier=sup, channel=channel, total=draft["total"],
                      items_json=json.dumps(draft["items"], ensure_ascii=False), message=draft["text"]))
    await audit(session, call.from_user.id, sup, "send_order", channel)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"✅ Заявка отправлена: {title_of(sup)} ({channel}).")


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession):
    rows = (
        await session.scalars(
            select(Order).where(Order.telegram_id == message.from_user.id).order_by(Order.created_at.desc()).limit(5)
        )
    ).all()
    if not rows:
        await message.answer("Заказов пока нет.")
        return
    await message.answer(
        "🧾 Последние заказы:\n"
        + "\n".join(f"{o.created_at:%d.%m %H:%M} · {title_of(o.supplier)} · ≈{o.total:.2f} ₪ · {o.channel}" for o in rows)
    )
