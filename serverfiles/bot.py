import asyncio
import datetime as dt
import html
import logging
import os
import re
import secrets
import time
from types import SimpleNamespace

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    MenuButtonWebApp,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)
from dotenv import load_dotenv

import db
import vpn_api
import webapp

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Укажи BOT_TOKEN в файле .env")

# Твой Telegram ID (узнать у @userinfobot): сюда приходят ошибки, тебе доступны /stats и /refund
# Можно несколько админов через запятую: ADMIN_ID=111111,222222
ADMIN_IDS = [int(x) for x in re.split(r"[,\s]+", os.getenv("ADMIN_ID", "")) if x.isdigit() and int(x)]
ADMIN_ID = ADMIN_IDS[0] if ADMIN_IDS else 0
# Контакт для вопросов по оплате, например @my_support
SUPPORT = os.getenv("SUPPORT_CONTACT", "@твой_username")
# TRIAL_PUBLIC=1 — пробник виден всем; 0 — только админу
TRIAL_PUBLIC = os.getenv("TRIAL_PUBLIC", "1") == "1"

DAY = 86400
MSK = dt.timezone(dt.timedelta(hours=3))

# Тарифы: id -> (название, дней, цена в рублях, цена в звёздах)
TARIFFS = {
    "m1": ("1 месяц", 30, 249, 167),
    "m3": ("3 месяца", 90, 675, 453),
    "m6": ("6 месяцев", 180, 1350, 906),
    "m12": ("12 месяцев", 365, 2700, 1811),
}
TRIAL = ("Пробный период", 3)  # (название, дней)

# Устройства: в подписку входит BASE_DEVICES, докупить можно до MAX_EXTRA штук при покупке/продлении.
BASE_DEVICES = 3
TRIAL_DEVICES = 1
MAX_EXTRA = 5
EXTRA_RUB = 50  # доп. устройство: разово за покупку или продление, до конца оплаченного срока
EXTRA_STARS = int(os.getenv("EXTRA_DEVICE_STARS", "34") or 34)

class UserTracker(BaseMiddleware):
    """Запоминает каждого, кто пишет боту (имя, @username, когда заходил) — для админ-панели."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is not None and not user.is_bot:
            try:
                db.upsert_user(user.id, user.username, user.first_name)
            except Exception:
                logging.exception("Не удалось сохранить пользователя")
            try:
                banned = db.is_banned(user.id) and not is_admin(user.id)
            except Exception:
                logging.exception("Не удалось проверить бан")
                banned = False
            if banned:
                await reject_banned(event)
                return None
        return await handler(event, data)


async def reject_banned(update):
    """Заблокированному человеку бот не отвечает ничем, кроме короткого отказа."""
    text = f"Доступ к боту ограничен. Если это ошибка, напиши в поддержку: {SUPPORT}"
    try:
        if getattr(update, "callback_query", None):
            await update.callback_query.answer("Доступ ограничен", show_alert=True)
        elif getattr(update, "pre_checkout_query", None):
            await update.pre_checkout_query.answer(ok=False, error_message="Доступ ограничен")
        elif getattr(update, "message", None):
            await update.message.answer(text)
    except Exception:
        logging.exception("Не удалось ответить заблокированному")


bot = Bot(BOT_TOKEN)
dp = Dispatcher()
dp.update.outer_middleware(UserTracker())
db.init()


# ---------- Вспомогательное ----------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or db.is_extra_admin(user_id)


def all_admin_ids() -> list[int]:
    """Админы из .env (главные) и добавленные в боте вручную."""
    return ADMIN_IDS + [a for a in db.list_admin_ids() if a not in ADMIN_IDS]


def fmt_date(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, MSK).strftime("%d.%m.%Y %H:%M")


def days_left(ts: int) -> int:
    return max(0, -(-(ts - int(time.time())) // DAY))  # округление вверх


def is_active(key) -> bool:
    return key["expires_at"] > time.time()


def key_title(key) -> str:
    mark = "🟢" if is_active(key) else "🔴"
    return f"{mark} {tariff_name(key['tariff'])} — до {fmt_date(key['expires_at'])[:10]}"


def tariff_name(tid: str) -> str:
    if tid == "trial":
        return TRIAL[0]
    if tid == "promo":
        return "Промокод"
    if tid == "admin":
        return "Выдан админом"
    if tid == "dev":
        return "Доп. устройство"
    return TARIFFS[tid][0]


# ---------- Цены и промокоды (общие функции) ----------

CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")


def stars_price(tid: str, percent: int = 0) -> int:
    return max(1, int(TARIFFS[tid][3] * (100 - percent) / 100 + 0.5))


def rub_price(tid: str, percent: int = 0) -> int:
    return max(1, int(TARIFFS[tid][2] * (100 - percent) / 100 + 0.5))


def price_label(tid: str, percent: int = 0) -> str:
    label = f"{TARIFFS[tid][0]} — {rub_price(tid, percent)} ₽ / {stars_price(tid, percent)} ⭐"
    return label + (f" (−{percent}%)" if percent else "")


def with_code(payload: str, code: str | None) -> str:
    return f"{payload}:{code}" if code else payload


def active_discount(user_id: int) -> tuple[str | None, int]:
    """Промокод со скидкой, который пользователь применил (если он ещё действует)."""
    code = db.get_pending(user_id)
    if not code:
        return None, 0
    promo = db.get_promo(code)
    if promo is None or promo["kind"] != "percent" or db.promo_problem(code, user_id):
        db.clear_pending(user_id)
        return None, 0
    return code, promo["value"]


def trial_available(user_id: int) -> bool:
    if is_admin(user_id):
        return True  # админ может брать пробник сколько угодно раз, для проверок
    return TRIAL_PUBLIC and not db.has_trial(user_id)


_locks: dict[int, asyncio.Lock] = {}


def user_lock(user_id: int) -> asyncio.Lock:
    """Один пользователь — одна операция с ключами за раз (нет гонок при быстрых нажатиях)."""
    return _locks.setdefault(user_id, asyncio.Lock())


def sub_state(user_id: int) -> dict:
    """Подписка человека: сама запись, устройства, лимит и доп. устройства."""
    sub = db.get_sub(user_id)
    keys = db.device_keys(user_id)
    active = bool(sub) and sub["expires_at"] > time.time()
    if sub is not None and sub["is_trial"]:
        extras, limit = 0, TRIAL_DEVICES
    else:
        extras = sub["extra_devices"] if sub else 0
        limit = BASE_DEVICES + extras
    return {"sub": sub, "keys": keys, "active": active, "extras": extras, "limit": limit}


def extras_bounds(user_id: int) -> tuple[int, int]:
    """(минимум доп. устройств в заказе, значение по умолчанию). Минимум нужен, чтобы занятые
    устройства поместились в лимит."""
    st = sub_state(user_id)
    lo = max(0, len(st["keys"]) - BASE_DEVICES)
    keep = st["extras"] if st["active"] else 0
    return lo, min(max(keep, lo), MAX_EXTRA)


def order_total(tid: str, extras: int, percent: int = 0) -> tuple[int, int]:
    """Итог заказа (рубли, звёзды). Скидка по промокоду действует только на тариф."""
    return (
        rub_price(tid, percent) + extras * EXTRA_RUB,
        stars_price(tid, percent) + extras * EXTRA_STARS,
    )


async def show(
    call: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
):
    """Меняет текст сообщения (или подпись, если это картинка); если нельзя — шлёт новое."""
    try:
        if call.message.photo:
            await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode=parse_mode)
        else:
            await call.message.edit_text(text, reply_markup=kb, parse_mode=parse_mode)
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode=parse_mode)


async def notify_admin(text: str):
    for admin_id in all_admin_ids():
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logging.exception("Не удалось написать админу %s", admin_id)


# ---------- Клавиатуры ----------

# Мини-приложение: публичный HTTPS-адрес страницы (например https://app.example.com). Пусто = выключено.
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080") or 8080)

CHANNEL_URL = "https://t.me/Ossetian_VPN"  # кнопка «Наш канал» в главном меню


def support_url() -> str | None:
    """Ссылка на поддержку, если SUPPORT_CONTACT задан как @ник."""
    m = re.fullmatch(r"@([A-Za-z0-9_]{4,32})", SUPPORT)
    return f"https://t.me/{m.group(1)}" if m else None


def main_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))])
    rows += [
        [InlineKeyboardButton(text="🔥 Подключиться", callback_data="connect")],
        [InlineKeyboardButton(text="📱 Моя подписка", callback_data="mysub")],
        [InlineKeyboardButton(text="🛒 Купить / продлить", callback_data="buy")],
    ]
    if trial_available(user_id):
        rows.append([InlineKeyboardButton(text="🎁 Пробный период (3 дня)", callback_data="trial")])
    row = [InlineKeyboardButton(text="🎟 Промокод", callback_data="promo")]
    if support_url():
        row.append(InlineKeyboardButton(text="💬 Поддержка", url=support_url()))
    rows.append(row)
    rows.append([
        InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet"),
        InlineKeyboardButton(text="❓ Как подключиться", callback_data="help"),
    ])
    rows.append([InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← В меню", callback_data="menu")]]
    )


def tariffs_kb(prefix: str, back: str, user_id: int) -> InlineKeyboardMarkup:
    """prefix: 'tariff:' — выбор тарифа для покупки или продления."""
    _, pct = active_discount(user_id)
    rows = [
        [InlineKeyboardButton(text=price_label(tid, pct), callback_data=f"{prefix}{tid}")]
        for tid in TARIFFS
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Меню ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Картинка над меню: положи свой файл welcome.jpg рядом с bot.py (или укажи WELCOME_IMAGE в .env)
WELCOME_IMAGE = os.path.join(BASE_DIR, os.getenv("WELCOME_IMAGE", "welcome.jpg"))
_welcome_file_id: str | None = None

# Тексты приветствия: поправь под себя (подпись под картинкой не должна быть длиннее 1024 символов)
WELCOME_TAGLINE = "Быстрый и простой VPN: оплатил, получил ключ, подключился."
ADVANTAGES = [
    "Ключ выдаётся сразу после оплаты",
    f"До {BASE_DEVICES} устройств в одной подписке, ещё можно докупить",
    "Личный кабинет: ключи и сроки всегда под рукой",
]


def fmt_left(ts: int) -> str:
    left = int(ts - time.time())
    if left <= 0:
        return "срок истёк"
    days, rest = divmod(left, DAY)
    hours, rest = divmod(rest, 3600)
    if days:
        return f"{days} дн. {hours} ч"
    return f"{hours} ч {rest // 60} мин"


def primary_key(user_id: int):
    """Основной ключ: активный с самым поздним сроком, а если активных нет — последний по сроку."""
    keys = db.user_keys(user_id)
    if not keys:
        return None
    active = [k for k in keys if is_active(k)]
    return max(active or keys, key=lambda k: k["expires_at"])


def menu_text(user_id: int, first_name: str | None) -> str:
    name = html.escape(first_name or "друг")
    keys = db.user_keys(user_id)
    st = sub_state(user_id)
    active = [k for k in keys if is_active(k)]
    if st["sub"] is not None and st["active"]:
        sub = (
            "• Статус: активна ✅\n"
            f"• Осталось: <b>{fmt_left(st['sub']['expires_at'])}</b>\n"
            f"• Устройства: <b>{len(st['keys'])} из {st['limit']}</b>"
        )
    elif active:
        best = max(active, key=lambda k: k["expires_at"])
        sub = (
            "• Статус: активна ✅\n"
            f"• Осталось: <b>{fmt_left(best['expires_at'])}</b>"
        )
    elif keys:
        sub = "• Статус: срок истёк ❌\n• Продли подписку, и ключ снова заработает"
    else:
        sub = "• Подписки пока нет\n• Купи VPN или возьми пробный период"
    advantages = "\n".join(f"• {html.escape(a)}" for a in ADVANTAGES)
    return (
        f"🔒 <b>Привет, {name}!</b>\n\n"
        f"{html.escape(WELCOME_TAGLINE)}\n\n"
        f"⭐ <b>Наши преимущества</b>\n<blockquote>{advantages}</blockquote>\n\n"
        f"💫 <b>Ваша подписка:</b>\n<blockquote>{sub}</blockquote>"
    )


async def send_menu(message: Message):
    """Главное меню: с картинкой, если есть файл welcome.jpg, иначе просто текстом."""
    global _welcome_file_id
    user = message.from_user
    text = menu_text(user.id, user.first_name)
    kb = main_menu(user.id)
    if os.path.exists(WELCOME_IMAGE) and len(text) <= 1024:
        try:
            sent = await message.answer_photo(
                _welcome_file_id or FSInputFile(WELCOME_IMAGE),
                caption=text, parse_mode="HTML", reply_markup=kb,
            )
            if not _welcome_file_id and getattr(sent, "photo", None):
                _welcome_file_id = sent.photo[-1].file_id  # дальше картинка не загружается заново
            return
        except Exception:
            _welcome_file_id = None
            logging.exception("Не удалось отправить картинку меню, шлю текстом")
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@dp.message(CommandStart())
@dp.message(Command("menu"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await send_menu(message)


@dp.callback_query(F.data == "menu")
async def menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = call.from_user
    await show(call, menu_text(user.id, user.first_name), main_menu(user.id), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "connect")
async def connect(call: CallbackQuery):
    """«Подключиться»: присылает ключ (если устройство одно) или предлагает выбрать устройство."""
    uid = call.from_user.id
    st = sub_state(uid)
    if st["sub"] is None or not st["active"]:
        rows = []
        if st["sub"] is not None:
            text = "Срок подписки истёк. Продли её, и ключи снова заработают."
            rows.append([btn("🔄 Продлить подписку", "buy")])
        else:
            text = "У тебя пока нет подписки. Купи VPN или возьми пробный период."
            if trial_available(uid):
                rows.append([btn("🎁 Пробный период (3 дня)", "trial")])
            rows.append([btn("🛒 Купить VPN", "buy")])
        rows.append([btn("← В меню", "menu")])
        await show(call, text, InlineKeyboardMarkup(inline_keyboard=rows))
        await call.answer()
        return
    if len(st["keys"]) == 1:
        key = st["keys"][0]
        await call.answer()
        await send_key(
            uid, key["config"],
            f"🔑 Ключ №{key['id']}, осталось {fmt_left(key['expires_at'])}.",
        )
        return
    text, kb = cabinet_view(uid)  # устройств несколько (или ни одного): выбираем в кабинете
    await show(call, text, kb)
    await call.answer()


@dp.callback_query(F.data == "mysub")
async def my_subscription(call: CallbackQuery):
    uid = call.from_user.id
    st = sub_state(uid)
    sub = st["sub"]
    if sub is None:
        rows = []
        if trial_available(uid):
            rows.append([btn("🎁 Пробный период (3 дня)", "trial")])
        rows.append([btn("🛒 Купить VPN", "buy")])
        rows.append([btn("← В меню", "menu")])
        await show(
            call, "📱 <b>Моя подписка</b>\n\nУ тебя пока нет подписки.",
            InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
        )
        await call.answer()
        return
    status = "активна ✅" if st["active"] else "срок истёк ❌"
    extra = f" (включено {BASE_DEVICES} + доп. {st['extras']})" if st["extras"] else ""
    text = (
        "📱 <b>Моя подписка</b>\n\n"
        f"<blockquote>Статус: {status}\n"
        f"Действует до: {fmt_date(sub['expires_at'])} (МСК)\n"
        f"Осталось: <b>{fmt_left(sub['expires_at'])}</b>\n"
        f"Устройства: <b>{len(st['keys'])} из {st['limit']}</b>{extra}</blockquote>\n\n"
        f"<i>Не хватает устройств? Докупи при продлении: +{EXTRA_RUB} ₽ за устройство. "
        "При продлении новый срок прибавляется к текущему: дни не сгорают.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn("🔥 Подключиться", "connect"), btn("📱 Устройства", "cabinet")],
        [btn("🔄 Продлить / докупить устройства", "buy")],
        [btn("🎟 Активировать промокод", "promo")],
        [btn("← В меню", "menu")],
    ])
    await show(call, text, kb, parse_mode="HTML")
    await call.answer()


HELP_TEXT = (
    "Как подключиться:\n"
    "1. Установи приложение AmneziaVPN (Windows, Mac, Android, iPhone).\n"
    "2. В боте открой «Личный кабинет» → своё устройство → «Показать ключ» и скопируй ключ.\n"
    "3. В приложении нажми «Добавить» → вставить ключ → «Подключиться».\n\n"
    f"В подписку входит {BASE_DEVICES} устройства: для каждого свой ключ, его можно добавить в "
    f"«Личном кабинете». Больше устройств можно докупить при покупке или продлении (+{EXTRA_RUB} ₽ "
    "за устройство). Передавать ключи другим людям не нужно.\n\n"
    f"Вопросы и проблемы: {SUPPORT}"
)

# Шаблон правил: перечитай и поправь под себя (это не юридическая консультация)
RULES_TEXT = (
    "📄 Политика и соглашение\n\n"
    f"1. В подписку входит {BASE_DEVICES} устройства (можно докупить дополнительные). Каждое "
    "устройство использует свой ключ. Передавать ключи другим людям и перепродавать доступ нельзя.\n"
    "2. Нельзя использовать VPN для незаконной деятельности, спама, атак на других и "
    "нарушения чужих прав, а также для скачивания торрентов.\n"
    "3. Срок действия ключа указан в «Личном кабинете». По окончании срока ключ перестаёт "
    "работать, продлить его можно в боте.\n"
    "4. Сервис предоставляется «как есть». Мы стараемся обеспечить стабильную работу, но не "
    "можем гарантировать, что VPN будет работать у любого оператора и в любой сети.\n"
    "5. При нарушении правил доступ может быть отключён.\n\n"
    f"Вопросы: {SUPPORT}"
)


@dp.callback_query(F.data == "help")
async def help_(call: CallbackQuery):
    await show(call, HELP_TEXT, back_to_menu())
    await call.answer()


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP_TEXT, reply_markup=back_to_menu())


@dp.message(Command("rules"))
async def rules_cmd(message: Message):
    await message.answer(RULES_TEXT, reply_markup=back_to_menu())


# ---------- Личный кабинет ----------

@dp.message(Command("cabinet"))
async def cabinet_cmd(message: Message):
    text, kb = cabinet_view(message.from_user.id)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "cabinet")
async def cabinet(call: CallbackQuery):
    text, kb = cabinet_view(call.from_user.id)
    await show(call, text, kb)
    await call.answer()


def device_title(key, index: int) -> str:
    mark = "🟢" if is_active(key) else "🔴"
    return f"{mark} Устройство {index} · ключ №{key['id']}"


def cabinet_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    st = sub_state(user_id)
    gifts = [k for k in db.user_keys(user_id) if k["source"] == "admin"]  # ключи, выданные админом
    if st["sub"] is None and not gifts:
        return (
            "👤 Личный кабинет\n\nУ тебя пока нет подписки.",
            InlineKeyboardMarkup(inline_keyboard=[
                [btn("🛒 Купить VPN", "buy")],
                [btn("← В меню", "menu")],
            ]),
        )
    rows = []
    lines = ["👤 Личный кабинет\n"]
    if st["sub"] is not None:
        sub = st["sub"]
        if st["active"]:
            lines.append(f"Подписка: активна ✅, осталось {fmt_left(sub['expires_at'])}")
        else:
            lines.append("Подписка: срок истёк ❌")
        lines.append(f"Действует до: {fmt_date(sub['expires_at'])} (МСК)")
        lines.append(f"Устройства: {len(st['keys'])} из {st['limit']}")
        if st["keys"]:
            lines.append("\nНажми на устройство, чтобы получить ключ:")
        else:
            lines.append("\nУстройств пока нет. Добавь первое.")
        for i, k in enumerate(st["keys"], 1):
            rows.append([btn(device_title(k, i), f"key:{k['id']}")])
        if st["active"] and len(st["keys"]) < st["limit"]:
            rows.append([btn("➕ Добавить устройство", "adddev")])
        rows.append([btn("🔄 Продлить / докупить устройства", "buy")])
    for k in gifts:
        rows.append([btn(f"🎁 Ключ от админа №{k['id']} · {key_title(k)[2:]}"[:60], f"key:{k['id']}")])
    rows.append([btn("← В меню", "menu")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def own_key(user_id: int, key_id: int):
    """Ключ, только если он принадлежит этому пользователю и не удалён."""
    key = db.get_key(key_id)
    if key is None or key["user_id"] != user_id or key["revoked"]:
        return None
    return key


@dp.callback_query(F.data.startswith("key:"))
async def key_view(call: CallbackQuery):
    key = own_key(call.from_user.id, int(call.data.split(":")[1]))
    if key is None:
        await call.answer("Ключ не найден", show_alert=True)
        return
    is_device = key["source"] != "admin"
    if is_active(key):
        status = f"🟢 Активен, осталось {fmt_left(key['expires_at'])}"
    else:
        status = "🔴 Срок истёк" + (": продли подписку, и ключ снова заработает" if is_device else "")
    text = (
        f"🔑 Ключ №{key['id']}\n"
        f"{'Устройство подписки' if is_device else 'Выдан админом'}\n"
        f"Статус: {status}\n"
        f"Действует до: {fmt_date(key['expires_at'])} (МСК)\n"
        f"Выдан: {fmt_date(key['created_at'])}"
    )
    rows = [[btn("📋 Показать ключ", f"showkey:{key['id']}"), btn("📎 Файл для AmneziaVPN", f"keyfile:{key['id']}")]]
    if is_device:
        rows.append([btn("🗑 Удалить устройство", f"deldev:{key['id']}")])
    rows.append([btn("← Личный кабинет", "cabinet")])
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@dp.callback_query(F.data.startswith("showkey:"))
async def show_key(call: CallbackQuery):
    key = own_key(call.from_user.id, int(call.data.split(":")[1]))
    if key is None:
        await call.answer("Ключ не найден", show_alert=True)
        return
    await call.answer()
    await send_key(call.from_user.id, key["config"], "🔑 Твой ключ.")


@dp.callback_query(F.data.startswith("keyfile:"))
async def key_file(call: CallbackQuery):
    key = own_key(call.from_user.id, int(call.data.split(":")[1]))
    if key is None:
        await call.answer("Ключ не найден", show_alert=True)
        return
    await call.answer()
    await bot.send_document(
        call.from_user.id,
        BufferedInputFile(key["config"].encode(), filename=f"vpn-key-{key['id']}.vpn"),
        caption="Файл-ключ для приложения AmneziaVPN: «Добавить» → из файла. "
                "Если файл не открывается, возьми текстовый ключ кнопкой «Показать ключ».",
    )


@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ---------- Устройства ----------

@dp.callback_query(F.data == "adddev")
async def add_device(call: CallbackQuery):
    uid = call.from_user.id
    async with user_lock(uid):
        st = sub_state(uid)
        if not st["active"]:
            await call.answer("Подписка не активна. Сначала продли её.", show_alert=True)
            return
        if len(st["keys"]) >= st["limit"]:
            await call.answer(
                f"Лимит устройств: {st['limit']}. Докупить можно при продлении подписки.",
                show_alert=True,
            )
            return
        await call.answer()
        try:
            days = (st["sub"]["expires_at"] - time.time()) / DAY
            new_id = await create_and_store(uid, "dev", "paid", None, days=days)
            db.set_expiry(new_id, st["sub"]["expires_at"])  # срок устройства = срок подписки
        except Exception as exc:
            logging.exception("Не удалось добавить устройство: user=%s", uid)
            await call.message.answer("Не удалось добавить устройство. Попробуй чуть позже.")
            await notify_admin(f"⚠️ Ошибка добавления устройства\nuser={uid}\n{type(exc).__name__}: {exc}"[:900])
            return
    key = db.get_key(new_id)
    await send_key(
        uid, key["config"],
        f"🔑 Новое устройство, ключ №{new_id}.",
    )
    text, kb = cabinet_view(uid)
    await call.message.answer(text, reply_markup=kb)


_del_log: dict[int, list[float]] = {}
MAX_DELETES_PER_DAY = 3  # чтобы не плодить отключённых клиентов на сервере


def delete_quota_left(user_id: int) -> int:
    recent = [t for t in _del_log.get(user_id, []) if t > time.time() - DAY]
    _del_log[user_id] = recent
    return MAX_DELETES_PER_DAY - len(recent)


@dp.callback_query(F.data.startswith("deldev:"))
async def delete_device_confirm(call: CallbackQuery):
    key = own_key(call.from_user.id, int(call.data.split(":")[1]))
    if key is None or key["source"] == "admin":
        await call.answer("Недоступно", show_alert=True)
        return
    await show(
        call,
        f"Удалить устройство (ключ №{key['id']})? Ключ перестанет работать, а место освободится: "
        "ты сможешь добавить другое устройство. Удалять можно не чаще "
        f"{MAX_DELETES_PER_DAY} раз в сутки.",
        InlineKeyboardMarkup(inline_keyboard=[
            [btn("🗑 Да, удалить", f"deldevy:{key['id']}")],
            [btn("← Нет", f"key:{key['id']}")],
        ]),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("deldevy:"))
async def delete_device(call: CallbackQuery):
    uid = call.from_user.id
    key = own_key(uid, int(call.data.split(":")[1]))
    if key is None or key["source"] == "admin":
        await call.answer("Недоступно", show_alert=True)
        return
    if delete_quota_left(uid) <= 0:
        await call.answer("Слишком часто. Попробуй завтра.", show_alert=True)
        return
    try:
        await vpn_api.set_status(key["client_id"], key["protocol"], "disabled", int(key["expires_at"]))
    except Exception as exc:
        logging.exception("Не удалось отключить устройство: key=%s", key["id"])
        await call.answer("Не удалось удалить устройство. Попробуй позже.", show_alert=True)
        await notify_admin(f"⚠️ Ошибка удаления устройства\nuser={uid} key={key['id']}\n{type(exc).__name__}: {exc}"[:900])
        return
    db.revoke_key(key["id"])
    _del_log.setdefault(uid, []).append(time.time())
    text, kb = cabinet_view(uid)
    await show(call, "🗑 Устройство удалено.\n\n" + text, kb)
    await call.answer()


# ---------- Покупка ----------

@dp.callback_query(F.data == "buy")
async def buy(call: CallbackQuery):
    code, pct = active_discount(call.from_user.id)
    note = f"\n\n🎟 Применён промокод {code}: скидка {pct}%." if code else ""
    await show(
        call,
        f"Выбери тариф. В подписку входит {BASE_DEVICES} устройства. "
        f"Больше можно докупить на следующем шаге: +{EXTRA_RUB} ₽ за устройство." + note,
        tariffs_kb("tariff:", "menu", call.from_user.id),
    )
    await call.answer()


def order_view(user_id: int, tid: str, n: int) -> tuple[str, InlineKeyboardMarkup]:
    """Экран заказа: тариф, число доп. устройств, итоговая цена и кнопки оплаты."""
    name, days, rub, stars = TARIFFS[tid]
    lo, _ = extras_bounds(user_id)
    n = min(max(n, lo), MAX_EXTRA)
    code, pct = active_discount(user_id)
    rub_total, stars_total = order_total(tid, n, pct)
    st = sub_state(user_id)
    lines = [f"Тариф: {name}", f"Срок: {days} дн."]
    if st["active"]:
        lines.append(f"Срок прибавится к текущему (сейчас до {fmt_date(st['sub']['expires_at'])}).")
    lines.append(
        f"Устройства: {BASE_DEVICES} включено" + (f" + {n} доп. = {BASE_DEVICES + n}" if n else "")
    )
    if pct:
        lines.append(f"🎟 Промокод {code}: скидка {pct}% на тариф")
    lines.append(f"\nИтого: {rub_total} ₽ или {stars_total} ⭐")
    if n:
        lines.append(
            f"(тариф {rub_price(tid, pct)} ₽ + {n} × {EXTRA_RUB} ₽ за доп. устройства)"
        )
    lines.append(
        f"\nДоп. устройство: +{EXTRA_RUB} ₽ один раз, действует до конца оплаченного срока. "
        "При продлении докупается заново."
    )
    counter = [btn(f"Доп. устройства: {n}", "noop")]
    if n > lo:
        counter.insert(0, btn("➖", f"tariff:{tid}:{n - 1}"))
    if n < MAX_EXTRA:
        counter.append(btn("➕", f"tariff:{tid}:{n + 1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        counter,
        [btn("⭐ Оплатить звёздами", f"pay_stars:{tid}:{n}")],
        [btn("🏦 Оплатить по СБП", f"pay_sbp:{tid}:{n}")],
        [btn("← Назад", "buy")],
    ])
    return "\n".join(lines), kb


@dp.callback_query(F.data.startswith("tariff:"))
async def choose_tariff(call: CallbackQuery):
    parts = call.data.split(":")
    tid = parts[1]
    if tid not in TARIFFS:
        await call.answer("Тариф не найден", show_alert=True)
        return
    _, default = extras_bounds(call.from_user.id)
    n = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else default
    text, kb = order_view(call.from_user.id, tid, n)
    await show(call, text, kb)
    await call.answer()


@dp.callback_query(F.data.startswith("pay_stars:"))
async def pay_stars(call: CallbackQuery):
    parts = call.data.split(":")
    tid = parts[1]
    n = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    uid = call.from_user.id
    if tid not in TARIFFS or n > MAX_EXTRA:
        await call.answer("Тариф недоступен", show_alert=True)
        return
    lo, _ = extras_bounds(uid)
    if n < lo:
        await call.answer(
            "У тебя занято больше устройств. Удали лишние в кабинете или выбери больше доп. устройств.",
            show_alert=True,
        )
        return
    code, pct = active_discount(uid)
    _, stars_total = order_total(tid, n, pct)
    await send_invoice(uid, tid, with_code(f"sub:{tid}:{n}", code), n, stars_total)
    await call.answer()


async def send_invoice(chat_id: int, tid: str, payload: str, extras: int, stars: int):
    name, days, rub, _ = TARIFFS[tid]
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"VPN — {name}",
        description=f"Подписка на {days} дн., устройств: {BASE_DEVICES + extras}",
        payload=payload,  # вернётся после оплаты
        currency="XTR",  # XTR = Telegram Stars
        prices=[LabeledPrice(label=f"{name}, устройств: {BASE_DEVICES + extras}", amount=stars)],
        provider_token="",  # для звёзд всегда пустой; позиция в счёте должна быть одна
    )


def parse_payload(payload: str):
    """sub:<тариф>:<доп. устройства>[:<код>] -> (тариф, доп. устройства, код | None)."""
    parts = payload.split(":")
    if (
        parts[0] == "sub" and len(parts) in (3, 4) and parts[1] in TARIFFS
        and parts[2].isdigit() and int(parts[2]) <= MAX_EXTRA
    ):
        code = parts[3] if len(parts) == 4 else None
        if code is None or CODE_RE.match(code):
            return parts[1], int(parts[2]), code
    return None


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    # Ответить нужно за 10 секунд
    parsed = parse_payload(query.invoice_payload)
    if parsed is None:
        await query.answer(ok=False, error_message="Тариф недоступен")
        return
    tid, n, code = parsed
    lo, _ = extras_bounds(query.from_user.id)
    if n < lo:
        await query.answer(
            ok=False, error_message="Занято больше устройств, чем в заказе. Оформи заказ заново."
        )
        return
    pct = 0
    if code:
        promo = db.get_promo(code)
        if (
            promo is None
            or promo["kind"] != "percent"
            or db.promo_problem(code, query.from_user.id)
        ):
            await query.answer(
                ok=False, error_message="Промокод больше не действует. Оформи заказ заново."
            )
            return
        pct = promo["value"]
    if query.total_amount != order_total(tid, n, pct)[1]:
        await query.answer(ok=False, error_message="Цена изменилась. Оформи заказ заново.")
        return
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    pay = message.successful_payment
    user_id = message.from_user.id
    charge_id = pay.telegram_payment_charge_id
    parsed = parse_payload(pay.invoice_payload)
    if parsed is None:
        logging.error("Неизвестный payload платежа: %s charge_id=%s", pay.invoice_payload, charge_id)
        await notify_admin(f"⚠️ Платёж с неизвестным payload\nuser={user_id}\ncharge_id={charge_id}")
        await message.answer(f"Оплата получена, но возникла ошибка. Напиши в поддержку: {SUPPORT}")
        return
    tid, extras, code = parsed

    # Защита от повторной обработки одного платежа
    if not db.record_payment(charge_id, user_id, tid, pay.total_amount, "stars", None, extras):
        logging.warning("Повторный платёж, пропускаем: charge_id=%s", charge_id)
        return

    logging.info("Оплата звёздами: user=%s тариф=%s доп.устройств=%s сумма=%s charge_id=%s",
                 user_id, tid, extras, pay.total_amount, charge_id)
    await message.answer("✅ Оплата получена. Оформляю подписку…")
    try:
        end_ts, created = await apply_subscription(
            user_id, TARIFFS[tid][1], extras=extras, tariff=tid, source="paid"
        )
        devices = db.device_keys(user_id)
        first_key = created or (devices[0]["id"] if devices else None)
        if first_key:
            db.set_payment_key(charge_id, first_key)
        st = sub_state(user_id)
        await message.answer(
            f"✅ Подписка {'оформлена' if created else 'продлена'} до {fmt_date(end_ts)} (МСК).\n"
            f"Устройств: {len(devices)} из {st['limit']}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [btn("👤 Личный кабинет", "cabinet")], [btn("← В меню", "menu")],
            ]),
        )
        if created:
            key = db.get_key(created)
            await send_key(
                user_id, key["config"],
                "🔑 Твой первый ключ. Ещё устройства можно добавить в «Личном кабинете».",
            )
        if code:
            # Скидка использована: списываем активацию промокода и сбрасываем применённый код
            if not db.redeem_promo(code, user_id):
                logging.warning("Промокод %s не списан (лимит/дубль), но платёж уже прошёл", code)
            db.clear_pending(user_id)
    except Exception as exc:
        logging.exception("Не удалось оформить подписку: user=%s charge_id=%s", user_id, charge_id)
        db.set_payment_status(charge_id, "failed")
        await message.answer(
            "Оплата прошла, но оформить подписку не получилось. Мы уже знаем об этом. "
            f"Напиши в поддержку {SUPPORT}: оформим вручную или вернём звёзды."
        )
        await notify_admin(
            f"⚠️ Ошибка после оплаты\nuser={user_id}\nтариф={tid} доп.устройств={extras}\n"
            f"charge_id={charge_id}\n\n{type(exc).__name__}: {exc}"[:900]
            + f"\n\nВернуть звёзды: /refund {charge_id}"
        )


# ---------- Пробный период ----------

async def start_trial(user_id: int) -> tuple[bool, str]:
    """Выдаёт пробный период. Возвращает (получилось ли, сообщение человеку)."""
    if not TRIAL_PUBLIC and not is_admin(user_id):
        return False, "Недоступно"
    if db.get_sub(user_id) is not None:
        return False, "Пробный период доступен только тем, у кого ещё не было подписки"
    if not is_admin(user_id) and not db.claim_trial(user_id):
        return False, "Пробный период уже использован"
    try:
        end_ts, created = await apply_subscription(
            user_id, TRIAL[1], trial=True, tariff="trial", source="trial"
        )
    except Exception as exc:
        logging.exception("Не удалось создать пробный ключ: user=%s", user_id)
        if not is_admin(user_id):
            db.release_trial(user_id)  # ключ не создался — пусть попробует ещё раз
        await notify_admin(f"⚠️ Ошибка пробного ключа\nuser={user_id}\n{type(exc).__name__}: {exc}"[:900])
        return False, "Не удалось создать ключ. Попробуй ещё раз чуть позже."
    key = db.get_key(created)
    await send_key(
        user_id, key["config"],
        f"🔑 Пробный ключ на {TRIAL[1]} дн. (1 устройство). Он всегда доступен в «Личном кабинете».",
    )
    return True, "Пробный период включён. Ключ также отправлен в чат с ботом."


@dp.callback_query(F.data == "trial")
async def trial(call: CallbackQuery):
    ok, message = await start_trial(call.from_user.id)
    if ok:
        await call.answer()
    else:
        await call.answer(message, show_alert=True)


# ---------- Создание ключей и подписка ----------

async def create_and_store(
    user_id: int, tid: str, source: str, charge_id: str | None, days: float | None = None
) -> int:
    if days is None:
        days = TRIAL[1] if tid == "trial" else TARIFFS[tid][1]
    client_id, config, protocol, end_ts = await vpn_api.create_client(
        name=f"tg{user_id}-{int(time.time())}", days=days
    )
    try:
        return db.add_key(user_id, client_id, protocol, config, tid, source, charge_id, end_ts)
    except Exception:
        # Ключ уже создан на сервере, но не записался в базу: сохраняем его в лог, чтобы выдать вручную
        logging.critical("Ключ создан, но не записан в базу: user=%s client_id=%s", user_id, client_id)
        raise


async def apply_subscription(
    user_id: int, days: float, *, extras: int | None = None, trial: bool = False,
    tariff: str, source: str,
) -> tuple[int, int | None]:
    """Создаёт или продлевает подписку и приводит срок всех устройств к одной дате.

    Новый срок прибавляется к текущему (или к «сейчас», если подписка истекла).
    extras=None — доп. устройства не менять (промокоды), число — выбор в заказе.
    Возвращает (дата окончания, id нового ключа или None, если ключ не создавался).
    """
    async with user_lock(user_id):
        now = time.time()
        sub = db.get_sub(user_id)
        cur_end = sub["expires_at"] if sub else 0
        end_ts = int(max(now, cur_end) + days * DAY)
        if trial:
            new_extras, is_trial = 0, 1
        elif extras is None:
            keep = sub["extra_devices"] if (sub and not sub["is_trial"] and cur_end > now) else 0
            new_extras, is_trial = keep, 0
        else:
            new_extras, is_trial = extras, 0

        devices = db.device_keys(user_id)
        created = None
        if not devices:  # первое устройство создаём сразу
            created = await create_and_store(user_id, tariff, source, None, days=(end_ts - now) / DAY)
            db.set_expiry(created, end_ts)
        failed = []
        for key in devices:
            try:
                await vpn_api.renew_client(key["client_id"], key["protocol"], end_ts)
                db.set_expiry(key["id"], end_ts)
            except Exception:
                logging.exception("Не удалось продлить устройство: key=%s", key["id"])
                failed.append(key["id"])
        if failed:
            raise RuntimeError(f"не удалось продлить устройства: {failed}")
        db.set_sub(user_id, end_ts, new_extras, is_trial)
        return end_ts, created


KEY_NAME = os.getenv("KEY_NAME", "Ossetian VPN")
AMNEZIA_HINT = "Вставь ключ в приложение AmneziaVPN («Добавить» → вставить ключ) и нажми «Подключиться»."


def display_key(config: str) -> tuple[str, str]:
    """Что показывать человеку: (ключ, подсказка). Ключ Amnezia (vpn://)."""
    return config, AMNEZIA_HINT


async def send_key(chat_id: int, config: str, caption: str):
    """Ключ одним компактным сообщением: длинный текст свёрнут, раскрывается по нажатию."""
    config, hint = display_key(config)
    if len(config) < 3500:
        await bot.send_message(
            chat_id,
            f"{html.escape(caption)}\n\n"
            f"<blockquote expandable><code>{html.escape(config)}</code></blockquote>\n"
            f"{html.escape(hint)}\nНажми на ключ, чтобы скопировать.",
            parse_mode="HTML",
        )
    else:
        await bot.send_message(chat_id, f"{html.escape(caption)}\n\n{html.escape(hint)}", parse_mode="HTML")
        parts = [config[i:i + 3500] for i in range(0, len(config), 3500)]
        for n, part in enumerate(parts, 1):
            await bot.send_message(
                chat_id, f"Часть {n} из {len(parts)} (склей подряд без пробелов)\n<code>{html.escape(part)}</code>",
                parse_mode="HTML",
            )


# ---------- Промокоды ----------

class PromoInput(StatesGroup):
    waiting = State()


PROMO_ASK = "🎟 Отправь промокод одним сообщением."
_promo_fails: dict[int, list] = {}  # user_id -> [число ошибок, время окончания блокировки]


def promo_lock_left(user_id: int) -> int:
    rec = _promo_fails.get(user_id)
    return max(0, int(rec[1] - time.time())) if rec else 0


def promo_fail(user_id: int):
    """5 неверных кодов подряд — блокировка ввода на 10 минут (защита от подбора)."""
    rec = _promo_fails.setdefault(user_id, [0, 0.0])
    rec[0] += 1
    if rec[0] >= 5:
        rec[0], rec[1] = 0, time.time() + 600


def after_promo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="buy")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="🎟 Ввести другой промокод", callback_data="promo")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")],
    ])


async def process_promo(user_id: int, raw: str) -> str:
    """Применяет промокод. Возвращает текст ответа пользователю."""
    wait = promo_lock_left(user_id)
    if wait > 0:
        return f"Слишком много неверных попыток. Попробуй через {wait // 60 + 1} мин."
    code = raw.strip().upper()
    promo = db.get_promo(code) if CODE_RE.match(code) else None
    if promo is None:
        promo_fail(user_id)
        return "Такого промокода нет. Проверь, правильно ли он написан."
    problem = db.promo_problem(code, user_id)
    if problem:
        return problem

    if promo["kind"] == "percent":
        db.set_pending(user_id, code)
        return (
            f"✅ Промокод принят: скидка {promo['value']}% на следующую покупку или продление. "
            "Выбери тариф, цены уже со скидкой."
        )

    # kind == "days": бесплатные дни подписки (доп. устройства не меняются)
    if not db.redeem_promo(code, user_id):
        return "Этот промокод уже недоступен."
    try:
        end_ts, created = await apply_subscription(
            user_id, promo["value"], extras=None, tariff="promo", source="promo"
        )
    except Exception as exc:
        logging.exception("Не удалось применить промокод: user=%s code=%s", user_id, code)
        db.unredeem_promo(code, user_id)  # активация не потрачена
        await notify_admin(
            f"⚠️ Ошибка промокода {code}\nuser={user_id}\n{type(exc).__name__}: {exc}"[:900]
        )
        return "Не удалось применить промокод. Он не потрачен, попробуй ещё раз чуть позже."
    if created:
        key = db.get_key(created)
        await send_key(
            user_id, key["config"],
            "🎁 Твой ключ. Он всегда доступен в «Личном кабинете».",
        )
    return f"✅ Промокод активирован: +{promo['value']} дн. Подписка действует до {fmt_date(end_ts)} (МСК)."


@dp.callback_query(F.data == "promo")
async def promo_button(call: CallbackQuery, state: FSMContext):
    await state.set_state(PromoInput.waiting)
    await show(call, PROMO_ASK, back_to_menu())
    await call.answer()


@dp.message(Command("promo"))
async def promo_cmd(message: Message, command: CommandObject, state: FSMContext):
    if not command.args:
        await state.set_state(PromoInput.waiting)
        await message.answer(PROMO_ASK, reply_markup=back_to_menu())
        return
    await state.clear()
    text = await process_promo(message.from_user.id, command.args)
    await message.answer(text, reply_markup=after_promo_kb())


@dp.message(PromoInput.waiting, F.text, ~F.text.startswith("/"))
async def promo_text(message: Message, state: FSMContext):
    await state.clear()
    text = await process_promo(message.from_user.id, message.text)
    await message.answer(text, reply_markup=after_promo_kb())


PROMO_USAGE = (
    "Создать промокод:\n"
    "/newpromo <КОД|auto> <days|percent> <значение> [макс_активаций] [дней_действия]\n\n"
    "• days — бесплатный ключ на N дней, percent — скидка N% на покупку или продление\n"
    "• макс_активаций: по умолчанию 1, 0 — без лимита\n"
    "• дней_действия: по умолчанию без срока\n"
    "• КОД: латинские буквы, цифры, - и _ (3–32 символа); auto — случайный код\n\n"
    "Примеры:\n"
    "/newpromo auto days 7 1\n"
    "/newpromo SALE20 percent 20 100 30"
)


@dp.message(Command("newpromo"))
async def newpromo(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    parts = (command.args or "").split()
    if len(parts) < 3:
        await message.answer(PROMO_USAGE)
        return
    code, kind = parts[0].upper(), parts[1].lower()
    try:
        value = int(parts[2])
        max_uses = int(parts[3]) if len(parts) > 3 else 1
        valid_days = int(parts[4]) if len(parts) > 4 else 0
    except ValueError:
        await message.answer(PROMO_USAGE)
        return
    if code == "AUTO":
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    if not CODE_RE.match(code):
        await message.answer("Код: только латинские буквы, цифры, - и _, длина 3–32.")
        return
    if kind == "days" and not 1 <= value <= 365:
        await message.answer("Для days значение от 1 до 365 дней.")
        return
    if kind == "percent" and not 1 <= value <= 99:
        await message.answer("Для percent значение от 1 до 99.")
        return
    if kind not in ("days", "percent") or max_uses < 0 or valid_days < 0:
        await message.answer(PROMO_USAGE)
        return
    expires_at = int(time.time() + valid_days * DAY) if valid_days else 0
    if not db.create_promo(code, kind, value, max_uses, expires_at):
        await message.answer("Такой промокод уже есть.")
        return
    what = f"бесплатный ключ на {value} дн." if kind == "days" else f"скидка {value}%"
    limit = f"{max_uses} активаций" if max_uses else "без лимита активаций"
    until = f"до {fmt_date(expires_at)}" if expires_at else "без срока действия"
    await message.answer(
        f"✅ Промокод создан: {code}\n{what}, {limit}, {until}.\n\n"
        "Пользователь вводит его в боте: «🎟 Промокод» или /promo " + code
    )


@dp.message(Command("promos"))
async def promos(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(promos_text())


def promos_text() -> str:
    rows = db.list_promos()
    if not rows:
        return "Промокодов пока нет. Создать: /newpromo"
    lines = []
    for p in rows:
        what = f"+{p['value']} дн." if p["kind"] == "days" else f"-{p['value']}%"
        limit = p["max_uses"] or "∞"
        until = fmt_date(p["expires_at"])[:10] if p["expires_at"] else "без срока"
        off = "" if p["active"] else " [выключен]"
        lines.append(f"{p['code']}: {what}, использован {p['used']}/{limit}, {until}{off}")
    return "\n".join(lines) + "\n\nСоздать: /newpromo\nОтключить: /delpromo <КОД>"


@dp.message(Command("delpromo"))
async def delpromo(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    code = (command.args or "").strip().upper()
    if code and db.deactivate_promo(code):
        await message.answer(f"Промокод {code} отключён.")
    else:
        await message.answer("Использование: /delpromo <КОД> (такого кода нет или он не указан)")


# ---------- Админ-панель (команда /admin, доступна только тебе по ADMIN_ID) ----------

async def ADMIN_ONLY(event) -> bool:
    """Фильтр: пропускает только админов (из .env или добавленных в боте).
    Обязательно async: обычные функции-фильтры aiogram гоняет в другом потоке, где SQLite не работает."""
    user = getattr(event, "from_user", None)
    return bool(user) and is_admin(user.id)

PAGE = 8
SERVER_LIMIT = int(os.getenv("SERVER_CLIENT_LIMIT", "10") or 10)
STATUS_ICON = {"paid": "✅", "failed": "⚠️", "refunded": "↩️"}
KEY_DAYS = (1, 3, 7, 30, 90, 365)


def who(username, first_name, user_id) -> str:
    name = f"@{username}" if username else (first_name or "без имени")
    return f"{name} ({user_id})"


def human_bytes(n) -> str:
    n = float(n or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📊 Статистика", "adm:stat"), btn("👥 Пользователи", "adm:usr:0")],
        [btn("🧾 Покупки", "adm:pay:0"), btn("📡 Активность", "adm:act")],
        [btn("🔑 Создать ключ", "adm:newkey"), btn("🎟 Промокоды", "adm:promos")],
        [btn("🔎 Найти человека", "adm:find"), btn("⏳ Скоро истекают", "adm:exp")],
        [btn("📣 Рассылка", "adm:bc"), btn("💾 Резервная копия", "adm:backup")],
        [btn("👮 Админы", "adm:admins")],
    ])


def admin_back_kb(extra: list | None = None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append([btn("← Админ-панель", "adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nav_row(prefix: str, page: int, total: int) -> list:
    pages = max(1, -(-total // PAGE))
    row = []
    if page > 0:
        row.append(btn("◀", f"{prefix}:{page - 1}"))
    row.append(btn(f"{page + 1}/{pages}", "adm:noop"))
    if page + 1 < pages:
        row.append(btn("▶", f"{prefix}:{page + 1}"))
    return row


async def server_clients():
    """Клиенты с сервера или None, если сервер недоступен."""
    try:
        return await vpn_api.list_clients()
    except Exception:
        logging.exception("Не удалось получить клиентов с сервера")
        return None


async def stats_text() -> str:
    s = db.admin_stats()
    clients = await server_clients()
    if clients is None:
        server = "Сервер: нет данных (проверь, что API на сервере работает)"
    else:
        server = f"Клиентов на сервере: {len(clients)} (лимит хостинга ≈ {SERVER_LIMIT})"
        if len(clients) > SERVER_LIMIT:
            server += " ⚠️ лимит превышен"
    return (
        "📊 Статистика\n\n"
        f"Пользователей: {s['users']}, из них покупали: {s['buyers']}\n"
        f"Активных подписок: {s['subs_active']}, докуплено устройств: {s['extras_sold']}\n"
        f"Ключей: {s['keys_total']}, активных сейчас: {s['keys_active']}\n"
        f"  платные: {s['keys_paid']}, пробные: {s['keys_trial']}, "
        f"по промокодам: {s['keys_promo']}, выданные админом: {s['keys_admin']}\n\n"
        f"Покупок и продлений: {s['pay_count']}, получено {s['pay_sum']} ⭐\n"
        f"  за 24 часа: {s['sum_24h']} ⭐, за 7 дней: {s['sum_7d']} ⭐, за 30 дней: {s['sum_30d']} ⭐\n"
        f"С ошибкой выдачи: {s['fail_count']} ({s['fail_sum']} ⭐), возвращено: {s['ref_sum']} ⭐\n\n"
        f"{server}"
    )


def payments_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    total = db.count_payments()
    if total == 0:
        return "🧾 Покупок пока нет.", admin_back_kb()
    page = min(max(page, 0), (total - 1) // PAGE)
    lines = [f"🧾 Покупки (всего {total})\n"]
    for p in db.list_payments(PAGE, page * PAGE):
        name = tariff_name(p["tariff"])
        lines.append(
            f"{STATUS_ICON.get(p['status'], '•')} {fmt_date(p['created_at'])[:16]} · "
            f"{who(p['username'], p['first_name'], p['user_id'])} · {name}"
            + (f" +{p['extras']} устр." if p["extras"] else "") + f" · {p['amount']} ⭐"
        )
        if p["status"] == "failed":
            lines.append(f"    ключ не выдан, вернуть звёзды: /refund {p['charge_id']}")
    lines.append("\n✅ оплачено  ⚠️ ошибка выдачи  ↩️ возвращено")
    return "\n".join(lines), admin_back_kb([nav_row("adm:pay", page, total)])


def users_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    total = db.count_users()
    if total == 0:
        return "👥 Пользователей пока нет.", admin_back_kb()
    page = min(max(page, 0), (total - 1) // PAGE)
    rows = []
    for u in db.list_users(PAGE, page * PAGE):
        label = f"{who(u['username'], u['first_name'], u['user_id'])} · 🔑{u['keys_active']}/{u['keys_n']} · {u['stars']}⭐"
        rows.append([btn(label[:60], f"adm:u:{u['user_id']}")])
    rows.append(nav_row("adm:usr", page, total))
    text = (
        f"👥 Пользователи (всего {total})\n\n"
        "Сверху те, кто заходил недавно. В кнопке: активные ключи/всего ключей и сумма оплат. "
        "Нажми на человека, чтобы увидеть детали."
    )
    return text, admin_back_kb(rows)


def user_card(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    u = db.get_user(uid)
    if u is None:
        return "Пользователь не найден.", admin_back_kb()
    keys = db.user_keys(uid)
    pays = db.user_payments(uid, 5)
    st = sub_state(uid)
    lines = [
        f"👤 {who(u['username'], u['first_name'], uid)}" + ("  🚫 ЗАБЛОКИРОВАН" if db.is_banned(uid) else ""),
        f"Впервые в боте: {fmt_date(u['first_seen'])[:10]}, последний раз: {fmt_date(u['last_seen'])}",
    ]
    if st["sub"] is not None:
        lines.append(
            f"Подписка: {'активна' if st['active'] else 'истекла'} до {fmt_date(st['sub']['expires_at'])}, "
            f"устройств {len(st['keys'])} из {st['limit']}"
            + (" (пробная)" if st["sub"]["is_trial"] else "")
        )
    lines.append(f"\nКлючи ({len(keys)}):")
    rows = []
    for k in keys[:8]:
        lines.append(f"{'🟢' if is_active(k) else '🔴'} №{k['id']} · {tariff_name(k['tariff'])} · до {fmt_date(k['expires_at'])[:10]}")
    for k in [k for k in keys if is_active(k)][:4]:
        rows.append([btn(f"🚫 Отключить ключ №{k['id']}", f"adm:rv:{k['id']}")])
    if not keys:
        lines.append("нет")
    lines.append("\nПлатежи:")
    for p in pays:
        lines.append(f"{STATUS_ICON.get(p['status'], '•')} {fmt_date(p['created_at'])[:16]} · {tariff_name(p['tariff'])}"
                     + (f" +{p['extras']} устр." if p['extras'] else "") + f" · {p['amount']} ⭐")
    if not pays:
        lines.append("нет")
    rows.append([btn("➕ +7 дн. подписке", f"adm:gsub:{uid}:7"), btn("➕ +30 дн. подписке", f"adm:gsub:{uid}:30")])
    rows.append([btn("🔑 Отдельный ключ 7 дн.", f"adm:give:{uid}:7"), btn("🔑 Ключ 30 дн.", f"adm:give:{uid}:30")])
    if uid not in ADMIN_IDS and not db.is_extra_admin(uid):
        if db.is_banned(uid):
            rows.append([btn("✅ Разблокировать в боте", f"adm:unban:{uid}")])
        else:
            rows.append([btn("🚫 Заблокировать в боте", f"adm:ban:{uid}")])
    rows.append([btn("← К списку", "adm:usr:0")])
    return "\n".join(lines), admin_back_kb(rows)


def activity_text(peers: list[dict]) -> str:
    """Кто сейчас подключён и кто недавно пользовался VPN (по данным сервера)."""
    by_client = {str(k["client_id"]): k for k in db.all_keys()}
    now = time.time()
    online = sum(1 for p in peers if p.get("online"))
    day = sum(1 for p in peers if (p.get("lastHandshake") or 0) > now - DAY)
    lines = [
        "📡 Активность на сервере\n",
        f"Клиентов на сервере: {len(peers)}, онлайн сейчас: {online}, были на связи за 24 ч: {day}\n",
    ]
    for p in sorted(peers, key=lambda p: p.get("lastHandshake") or 0, reverse=True)[:12]:
        key = by_client.get(str(p.get("id")))
        uid = key["user_id"] if key else None
        if uid is None:  # запасной вариант: бот называет клиентов tg<user_id>-<время>
            m = re.match(r"^tg(\d+)-", p.get("username") or "")
            uid = int(m.group(1)) if m else None
        if uid is not None:
            u = db.get_user(uid)
            owner = who(u["username"], u["first_name"], uid) if u else str(uid)
        else:
            owner = f"вне бота: {p.get('username') or str(p.get('id') or '?')[:8]}"
        hs = p.get("lastHandshake") or 0
        seen = fmt_date(hs)[:16] if hs else "не подключался"
        traffic = p.get("traffic") or {}
        lines.append(
            f"{'🟢' if p.get('online') else '⚪'} {owner} · {seen} · "
            f"↓{human_bytes(traffic.get('received'))} ↑{human_bytes(traffic.get('sent'))}"
        )
    if not peers:
        lines.append("Клиентов нет.")
    lines.append("\n🟢 онлайн, ⚪ не в сети. ↓ получено клиентом, ↑ отправлено.")
    return "\n".join(lines)


async def admin_make_key(chat_id: int, uid: int, days: int):
    """Создаёт ключ для пользователя uid (для себя: uid = id админа) и присылает его в чат админа."""
    new_id = await create_and_store(uid, "admin", "admin", None, days=days)
    key = db.get_key(new_id)
    owner = "" if uid == chat_id else f" для пользователя {uid} (он увидит его в «Личном кабинете»)"
    await send_key(chat_id, key["config"], f"🔑 Ключ №{new_id} на {days} дн.{owner}")


@dp.message(Command("admin"), ADMIN_ONLY)
async def admin_cmd(message: Message):
    await message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


@dp.callback_query(F.data.startswith("adm:"), ADMIN_ONLY)
async def admin_cb(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    act, args = parts[1], parts[2:]
    await call.answer()
    try:
        if act == "menu":
            await state.clear()
            await show(call, "🛠 Админ-панель", admin_menu_kb())
        elif act == "find":
            await state.set_state(AdminInput.search)
            await show(call, "🔎 Отправь id, @username или часть имени человека одним сообщением.", admin_back_kb())
        elif act == "exp":
            await show(call, *expiring_view())
        elif act == "remind":
            sent, skipped = await send_reminders()
            await show(call, f"📨 Напоминания отправлены: {sent}. Пропущено: {skipped} "
                             "(уже получали за последние сутки или закрыли бота).", admin_back_kb())
        elif act == "bc":
            await show(call, *broadcast_audience_view())
        elif act == "bca" and args[0] in AUDIENCES:
            await state.set_state(AdminInput.broadcast)
            await state.update_data(audience=args[0])
            await show(call, f"📣 Рассылка: {AUDIENCES[args[0]]} ({len(db.audience_ids(args[0]))} чел.).\n\n"
                             "Отправь текст сообщения одним сообщением. Можно с жирным и курсивом. "
                             "Перед отправкой я покажу предпросмотр.", admin_back_kb())
        elif act == "bcgo":
            data = await state.get_data()
            await state.clear()
            if not data.get("text"):
                await show(call, "Текст рассылки потерян. Начни заново.", admin_back_kb())
            else:
                ids = db.audience_ids(data["audience"])
                start_broadcast(call.from_user.id, ids, data["text"])
                await show(call, f"📣 Рассылка запущена: {len(ids)} получателей. Итог пришлю сюда.", admin_back_kb())
        elif act == "backup":
            await send_backup(call.from_user.id)
        elif act in ("ban", "unban"):
            target = int(args[0])
            if act == "ban" and is_admin(target):
                await call.message.answer("Админа заблокировать нельзя.")
            else:
                (db.ban_user if act == "ban" else db.unban_user)(target)
                await show(call, *user_card(target))
        elif act == "gsub" and 1 <= int(args[1]) <= 365:
            await admin_add_days(call, int(args[0]), int(args[1]))
        elif act == "stat":
            await show(call, await stats_text(), admin_back_kb())
        elif act == "pay":
            await show(call, *payments_page(int(args[0])))
        elif act == "usr":
            await show(call, *users_page(int(args[0])))
        elif act == "u":
            await show(call, *user_card(int(args[0])))
        elif act == "act":
            peers = await server_clients()
            text = activity_text(peers) if peers is not None else "Сервер недоступен: проверь API."
            await show(call, text, admin_back_kb())
        elif act == "admins":
            await show(call, admins_text(), admin_back_kb())
        elif act == "promos":
            await show(call, promos_text(), admin_back_kb())
        elif act == "newkey":
            rows = [[btn(f"{d} дн.", f"adm:mk:{d}") for d in KEY_DAYS[i:i + 3]] for i in (0, 3)]
            await show(
                call,
                "🔑 Создать ключ для себя. На сколько дней?\n"
                "(Его можно переслать клиенту. Ключ будет и в твоём «Личном кабинете».)",
                admin_back_kb(rows),
            )
        elif act == "mk" and int(args[0]) in KEY_DAYS:
            await admin_make_key(call.from_user.id, call.from_user.id, int(args[0]))
        elif act == "give" and 1 <= int(args[1]) <= 365:
            await admin_make_key(call.from_user.id, int(args[0]), int(args[1]))
        elif act == "rv":
            key = db.get_key(int(args[0]))
            if key is None:
                await call.message.answer("Ключ не найден.")
                return
            await show(
                call,
                f"Отключить ключ №{key['id']} ({tariff_name(key['tariff'])}, владелец {key['user_id']})?\n"
                "Он перестанет работать. Человек сможет включить его снова, продлив в кабинете.",
                InlineKeyboardMarkup(inline_keyboard=[
                    [btn("🚫 Да, отключить", f"adm:rvy:{key['id']}")],
                    [btn("← Нет", f"adm:u:{key['user_id']}")],
                ]),
            )
        elif act == "rvy":
            key = db.get_key(int(args[0]))
            if key is None:
                await call.message.answer("Ключ не найден.")
                return
            await vpn_api.set_status(key["client_id"], key["protocol"], "disabled", int(key["expires_at"]))
            db.set_expiry(key["id"], int(time.time()))
            await show(call, f"🚫 Ключ №{key['id']} отключён.", admin_back_kb(
                [[btn("← К пользователю", f"adm:u:{key['user_id']}")]]
            ))
    except Exception as exc:
        logging.exception("Ошибка админ-панели: %s", call.data)
        await call.message.answer(f"Ошибка: {type(exc).__name__}: {exc}"[:500])


# ---------- Расширенные функции админ-панели ----------

class AdminInput(StatesGroup):
    search = State()
    broadcast = State()


AUDIENCES = {
    "all": "все пользователи",
    "active": "с активной подпиской",
    "expired": "у кого подписка истекла",
    "none": "без подписки (не покупали)",
}
_bg_tasks: set = set()
_reminded: dict[int, float] = {}  # user_id -> когда отправили напоминание


def search_view(query: str) -> tuple[str, InlineKeyboardMarkup]:
    found = db.search_users(query)
    if not found:
        return "Никого не нашёл. Попробуй id, @username или часть имени.", admin_back_kb()
    rows = [[btn(f"{who(u['username'], u['first_name'], u['user_id'])}"[:60], f"adm:u:{u['user_id']}")] for u in found]
    return f"🔎 Найдено: {len(found)}. Нажми на человека.", admin_back_kb(rows)


@dp.message(AdminInput.search, ADMIN_ONLY, F.text, ~F.text.startswith("/"))
async def admin_search_text(message: Message, state: FSMContext):
    await state.clear()
    text, kb = search_view(message.text)
    await message.answer(text, reply_markup=kb)


@dp.message(Command("user"), ADMIN_ONLY)
async def user_cmd(message: Message, command: CommandObject):
    if not (command.args or "").strip():
        await message.answer("Использование: /user <id | @username | часть имени>")
        return
    text, kb = search_view(command.args)
    await message.answer(text, reply_markup=kb)


def expiring_view() -> tuple[str, InlineKeyboardMarkup]:
    subs = db.expiring_subs(3)
    if not subs:
        return "⏳ В ближайшие 3 дня никто не заканчивает подписку.", admin_back_kb()
    lines = [f"⏳ Подписка заканчивается в ближайшие 3 дня: {len(subs)}\n"]
    for r in subs[:25]:
        lines.append(f"• {who(r['username'], r['first_name'], r['user_id'])}: осталось {fmt_left(r['expires_at'])}"
                     + (" (пробная)" if r["is_trial"] else ""))
    if len(subs) > 25:
        lines.append(f"…и ещё {len(subs) - 25}")
    return "\n".join(lines), admin_back_kb([[btn(f"📨 Напомнить всем ({len(subs)})", "adm:remind")]])


async def send_reminders() -> tuple[int, int]:
    sent = skipped = 0
    for r in db.expiring_subs(3):
        uid = r["user_id"]
        if _reminded.get(uid, 0) > time.time() - 20 * 3600 or db.is_banned(uid):
            skipped += 1
            continue
        try:
            await bot.send_message(
                uid,
                f"⏳ Твоя подписка на VPN заканчивается через {fmt_left(r['expires_at'])}. "
                "Продли её, чтобы доступ не отключился.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn("🔄 Продлить", "buy")]]),
            )
            _reminded[uid] = time.time()
            sent += 1
        except Exception:
            skipped += 1
        await asyncio.sleep(0.06)  # лимит Telegram — около 30 сообщений в секунду
    return sent, skipped


def broadcast_audience_view() -> tuple[str, InlineKeyboardMarkup]:
    rows = [[btn(f"{name} ({len(db.audience_ids(key))})", f"adm:bca:{key}")] for key, name in AUDIENCES.items()]
    return "📣 Рассылка. Кому отправить?", admin_back_kb(rows)


@dp.message(AdminInput.broadcast, ADMIN_ONLY, F.text, ~F.text.startswith("/"))
async def admin_broadcast_text(message: Message, state: FSMContext):
    data = await state.get_data()
    html = message.html_text
    if len(html) > 3800:
        await message.answer("Слишком длинный текст (больше ~3800 символов). Сократи и отправь снова.")
        return
    await state.update_data(text=html)
    count = len(db.audience_ids(data.get("audience", "all")))
    await message.answer(
        f"Предпросмотр рассылки ({AUDIENCES.get(data.get('audience'), '')}, {count} чел.):\n\n{html}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [btn(f"✅ Отправить {count} чел.", "adm:bcgo")],
            [btn("✖ Отмена", "adm:menu")],
        ]),
    )


def start_broadcast(admin_id: int, ids: list[int], text: str):
    task = asyncio.create_task(run_broadcast(admin_id, ids, text))
    _bg_tasks.add(task)  # держим ссылку, иначе задачу может убрать сборщик мусора
    task.add_done_callback(_bg_tasks.discard)


async def run_broadcast(admin_id: int, ids: list[int], text: str):
    sent = failed = 0
    for uid in ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1  # заблокировал бота, удалил чат и т.п.
        await asyncio.sleep(0.06)
    logging.info("Рассылка завершена: отправлено=%s, не доставлено=%s", sent, failed)
    try:
        await bot.send_message(admin_id, f"📣 Рассылка завершена. Доставлено: {sent}, не доставлено: {failed}.")
    except Exception:
        logging.exception("Не удалось отправить итог рассылки")


async def admin_add_days(call: CallbackQuery, uid: int, days: int):
    """Добавляет дни к подписке человека (создаёт подписку и первый ключ, если её не было)."""
    try:
        end_ts, created = await apply_subscription(uid, days, extras=None, tariff="promo", source="promo")
    except Exception as exc:
        logging.exception("Не удалось добавить дни: user=%s", uid)
        await call.message.answer(f"Не удалось: {type(exc).__name__}: {exc}"[:400])
        return
    told = ""
    try:
        await bot.send_message(uid, f"🎁 Тебе добавлено {days} дн. подписки. Теперь она действует до {fmt_date(end_ts)} (МСК).")
        if created:
            key = db.get_key(created)
            await send_key(uid, key["config"], "🔑 Твой ключ.")
    except Exception:
        told = " Написать ему бот не смог (он не нажимал /start)."
    await show(call, f"✅ Подписке добавлено {days} дн., теперь до {fmt_date(end_ts)}.{told}", *[user_card(uid)[1]])


def backup_bytes() -> bytes:
    """Целостная копия базы (SQLite backup API работает и пока бот пишет в базу)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "backup.db")
        db.backup(path)
        with open(path, "rb") as f:
            return f.read()


async def send_backup(chat_id: int):
    name = f"vpnbot-{dt.datetime.now(MSK).strftime('%Y%m%d-%H%M')}.db"
    await bot.send_document(
        chat_id, BufferedInputFile(backup_bytes(), filename=name),
        caption="💾 Копия базы бота. В ней есть ключи пользователей: храни её в надёжном месте. "
                "Чтобы восстановить, положи файл в /opt/vpnbot/bot.db вместо текущего.",
    )


async def backup_loop():
    """Раз в BACKUP_HOURS часов (по умолчанию 24) присылает копию базы главным админам."""
    hours = float(os.getenv("BACKUP_HOURS", "24") or 0)
    if hours <= 0:
        return
    await asyncio.sleep(300)
    while True:
        for admin_id in ADMIN_IDS:
            try:
                await send_backup(admin_id)
            except Exception:
                logging.exception("Не удалось отправить авто-копию админу %s", admin_id)
        await asyncio.sleep(hours * 3600)


# ---------- СБП (заглушка до следующего шага) ----------

@dp.callback_query(F.data.startswith("pay_sbp:"))
async def pay_sbp_stub(call: CallbackQuery):
    await call.answer("Оплата по СБП будет подключена на следующем шаге", show_alert=True)


# ---------- Поддержка и админ ----------

@dp.message(Command("paysupport"))
async def paysupport(message: Message):
    # Telegram требует, чтобы у бота с платежами была эта команда
    await message.answer(f"По вопросам оплаты и возврата напишите сюда: {SUPPORT}")


@dp.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    s = db.stats()
    await message.answer(
        f"Пользователей с ключами: {s['users']}\n"
        f"Ключей всего: {s['keys_total']}, активных: {s['keys_active']}\n"
        f"Платежей: {s['payments']} (с ошибкой выдачи: {s['payments_failed']})\n"
        f"Получено звёзд: {s['stars']} ⭐"
    )


@dp.message(Command("refund"))
async def refund(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    charge_id = (command.args or "").strip()
    pay = db.get_payment(charge_id) if charge_id else None
    if pay is None:
        await message.answer("Использование: /refund <charge_id> (id платежа есть в уведомлении об ошибке)")
        return
    if pay["status"] == "refunded":
        await message.answer("Этот платёж уже возвращён.")
        return
    try:
        await bot.refund_star_payment(
            user_id=pay["user_id"], telegram_payment_charge_id=charge_id
        )
    except Exception as exc:
        await message.answer(f"Не удалось вернуть звёзды: {exc}")
        return
    db.set_payment_status(charge_id, "refunded")
    await message.answer("✅ Звёзды возвращены.")
    try:
        await bot.send_message(pay["user_id"], "Мы вернули тебе звёзды за неудачный платёж.")
    except Exception:
        pass


def admins_text() -> str:
    lines = ["👮 Админы\n"]
    for a in ADMIN_IDS:
        u = db.get_user(a)
        lines.append(f"👑 {who(u['username'], u['first_name'], a) if u else a} (главный, из .env)")
    for a in db.list_admin_ids():
        if a not in ADMIN_IDS:
            u = db.get_user(a)
            lines.append(f"• {who(u['username'], u['first_name'], a) if u else a}: убрать /deladmin {a}")
    lines.append("\nДобавить: /addadmin <id>. Свой id человек узнаёт у бота @userinfobot.")
    return "\n".join(lines)


async def set_admin_menu(admin_id: int) -> bool:
    cmds = COMMON_COMMANDS + [BotCommand(command="admin", description="🛠 Админ-панель")]
    try:
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=admin_id))
        return True
    except Exception:
        # пока человек не нажал /start у бота, Telegram не даёт настроить его меню
        logging.warning("Меню админа %s не настроено: пусть сначала нажмёт /start", admin_id)
        return False


@dp.message(Command("admins"), ADMIN_ONLY)
async def admins_cmd(message: Message):
    await message.answer(admins_text())


@dp.message(Command("addadmin"), ADMIN_ONLY)
async def addadmin(message: Message, command: CommandObject):
    arg = (command.args or "").strip()
    if not arg.isdigit() or not 0 < int(arg) < 10**15:
        await message.answer("Использование: /addadmin <id>, например /addadmin 123456789\n"
                             "Id человека можно узнать у бота @userinfobot.")
        return
    new_id = int(arg)
    if is_admin(new_id):
        await message.answer("Этот человек уже админ.")
        return
    db.add_admin(new_id, message.from_user.id)
    menu_ok = await set_admin_menu(new_id)
    try:
        await bot.send_message(new_id, "🛠 Тебе выдан доступ к админ-панели бота. Открой её командой /admin.")
        told = "Ему отправлено уведомление."
    except Exception:
        told = "Написать ему бот пока не может: пусть откроет бота и нажмёт /start, затем /admin."
    await message.answer(f"✅ Админом добавлен {new_id}. {told}")
    if not menu_ok:
        logging.info("Админ %s добавлен без пункта в меню команд", new_id)
    who_added = message.from_user
    await notify_admin(f"👮 {who_added.full_name} (id {who_added.id}) добавил админа {new_id}")


@dp.message(Command("deladmin"), ADMIN_ONLY)
async def deladmin(message: Message, command: CommandObject):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Использование: /deladmin <id>. Список: /admins")
        return
    target = int(arg)
    if target in ADMIN_IDS:
        await message.answer("Главных админов из .env через бота убрать нельзя.")
        return
    if not db.del_admin(target):
        await message.answer("Такого админа нет в списке.")
        return
    try:  # возвращаем обычное меню команд
        await bot.set_my_commands(COMMON_COMMANDS, scope=BotCommandScopeChat(chat_id=target))
    except Exception:
        pass
    await message.answer(f"✅ Админ {target} убран.")
    who_removed = message.from_user
    await notify_admin(f"👮 {who_removed.full_name} (id {who_removed.id}) убрал админа {target}")


COMMON_COMMANDS = [
    BotCommand(command="start", description="Перезапустить бота"),
    BotCommand(command="cabinet", description="Личный кабинет"),
    BotCommand(command="promo", description="Ввести промокод"),
    BotCommand(command="rules", description="📄 Политика и соглашение"),
    BotCommand(command="help", description="Помощь"),
]


async def setup_commands():
    """Меню команд слева от поля ввода. /paysupport в меню нет, но команда работает."""
    await bot.set_my_commands(COMMON_COMMANDS)
    for admin_id in all_admin_ids():  # у админов в меню есть ещё и админ-панель
        await set_admin_menu(admin_id)


# ---------- Мини-приложение ----------

def webapp_state(user: dict) -> dict:
    """Всё, что нужно странице мини-приложения, чтобы нарисовать экраны. Сами ключи сюда не входят."""
    uid = user["id"]
    st = sub_state(uid)
    sub = st["sub"]
    code, pct = active_discount(uid)
    lo, default = extras_bounds(uid)
    return {
        "user": {"id": uid, "name": user.get("first_name") or user.get("username") or "",
                 "photo": user.get("photo_url"), "username": user.get("username") or ""},
        "sub": None if sub is None else {
            "active": st["active"], "expires_at": sub["expires_at"], "date": fmt_date(sub["expires_at"]),
            "left": fmt_left(sub["expires_at"]), "trial": bool(sub["is_trial"]),
        },
        "devices": {"used": len(st["keys"]), "limit": st["limit"], "base": BASE_DEVICES},
        "keys": [
            {"id": k["id"], "n": i, "active": is_active(k), "date": fmt_date(k["expires_at"])}
            for i, k in enumerate(st["keys"], 1)
        ],
        "gifts": [
            {"id": k["id"], "active": is_active(k), "date": fmt_date(k["expires_at"])}
            for k in db.user_keys(uid) if k["source"] == "admin"
        ],
        "tariffs": [
            {"id": tid, "name": name, "days": days, "rub": rub_price(tid, pct),
             "stars": stars_price(tid, pct), "rub_full": rub}
            for tid, (name, days, rub, _) in TARIFFS.items()
        ],
        "extra": {"rub": EXTRA_RUB, "stars": EXTRA_STARS, "min": lo, "default": default, "max": MAX_EXTRA},
        "discount": {"code": code, "percent": pct} if code else None,
        "trial": {"available": trial_available(uid), "days": TRIAL[1]},
        "links": {"support": support_url(), "channel": CHANNEL_URL},
        "help": HELP_TEXT,
        "rules": RULES_TEXT,
    }


def webapp_key(user_id: int, key_id: int) -> dict | None:
    key = own_key(user_id, key_id)
    if key is None:
        return None
    link, hint = display_key(key["config"])
    return {"key": link, "hint": hint, "active": is_active(key), "kind": "vpn"}


async def webapp_invoice(user_id: int, tid: str, extras: int) -> str:
    """Ссылка на счёт в звёздах: приложение открывает её, дальше оплату принимают обычные обработчики бота."""
    if tid not in TARIFFS or not 0 <= extras <= MAX_EXTRA:
        raise ValueError("Тариф недоступен")
    lo, _ = extras_bounds(user_id)
    if extras < lo:
        raise ValueError("Занято больше устройств, чем в заказе. Увеличь число доп. устройств.")
    code, pct = active_discount(user_id)
    _, stars = order_total(tid, extras, pct)
    name, days, _, _ = TARIFFS[tid]
    return await bot.create_invoice_link(
        title=f"VPN — {name}",
        description=f"Подписка на {days} дн., устройств: {BASE_DEVICES + extras}",
        payload=with_code(f"sub:{tid}:{extras}", code),
        currency="XTR",
        prices=[LabeledPrice(label=f"{name}, устройств: {BASE_DEVICES + extras}", amount=stars)],
        provider_token="",
    )


def app_info(raw_key: str) -> dict | None:
    """Данные для отдельного приложения (Windows/Android): по ключу находим подписку его владельца."""
    row = db.key_by_config(raw_key.strip())
    if row is None:
        return None
    uid = row["user_id"]
    st = sub_state(uid)
    sub = st["sub"]
    return {
        "active": is_active(row),
        "key_expires_at": row["expires_at"],
        "sub": None if sub is None else {
            "active": st["active"], "expires_at": sub["expires_at"], "date": fmt_date(sub["expires_at"]),
            "left": fmt_left(sub["expires_at"]), "trial": bool(sub["is_trial"]),
        },
        "devices": {"used": len(st["keys"]), "limit": st["limit"]},
        "servers": APP_SERVERS,
        "now": int(time.time()),
    }


def _load_app_servers() -> list:
    """Дополнительные серверы из .env: SERVERS=Название|vpn://ключ;Название2|vpn://ключ2 (необязательно)."""
    out = []
    for part in os.getenv("SERVERS", "").split(";"):
        if "|" in part:
            name, key = part.split("|", 1)
            if name.strip() and key.strip().startswith("vpn://"):
                out.append({"name": name.strip(), "key": key.strip()})
    return out


APP_SERVERS = _load_app_servers()


def webapp_context() -> SimpleNamespace:
    return SimpleNamespace(
        bot_token=BOT_TOKEN,
        state=webapp_state,
        app_info=app_info,
        key=webapp_key,
        invoice=webapp_invoice,
        promo=process_promo,
        trial=start_trial,
        is_banned=lambda uid: db.is_banned(uid) and not is_admin(uid),
    )


async def start_webapp():
    """Запускает сервер мини-приложения и ставит кнопку «Приложение» слева от поля ввода."""
    if not WEBAPP_URL:
        return
    if not WEBAPP_URL.startswith("https://"):
        logging.error("WEBAPP_URL должен начинаться с https:// (требование Telegram). Мини-приложение выключено.")
        return
    await webapp.start(webapp_context(), port=WEBAPP_PORT)
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Приложение", web_app=WebAppInfo(url=WEBAPP_URL))
        )
    except Exception:
        logging.exception("Не удалось поставить кнопку «Приложение»")


async def main():
    try:
        await setup_commands()
    except Exception:
        logging.exception("Не удалось настроить меню команд")  # на работу бота не влияет
    asyncio.create_task(backup_loop())
    await start_webapp()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
