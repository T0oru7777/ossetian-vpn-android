"""Сервер мини-приложения Telegram (Web App) для бота.

Делает три вещи:
  1. отдаёт страницу webapp/index.html;
  2. проверяет, что запрос пришёл из Telegram от настоящего пользователя (подпись initData);
  3. отвечает на запросы страницы: состояние подписки, ключ, счёт на оплату, промокод, пробный период.

Сама логика (подписки, цены, ключи) лежит в bot.py и передаётся сюда через объект ctx.
Сервер слушает только 127.0.0.1: наружу его выставляет прокси с HTTPS (Caddy/nginx).
"""
import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qsl

from aiohttp import web

log = logging.getLogger("webapp")

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp", "index.html")
MAX_AGE = 24 * 3600  # подпись Telegram старше суток не принимаем
RATE_LIMIT = 40  # запросов в минуту с одного пользователя
_hits: dict[int, list[float]] = {}


def validate_init_data(init_data: str, bot_token: str, max_age: int = MAX_AGE) -> dict | None:
    """Проверка подписи Telegram (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).

    Возвращает данные пользователя или None, если подпись неверна или устарела.
    """
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", None)
    if not got:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        user = json.loads(pairs["user"])
        if not isinstance(user.get("id"), int):
            return None
    except (ValueError, KeyError, TypeError):
        return None
    return user


def rate_ok(user_id: int) -> bool:
    now = time.time()
    recent = [t for t in _hits.get(user_id, []) if t > now - 60]
    recent.append(now)
    _hits[user_id] = recent
    return len(recent) <= RATE_LIMIT


# ---------- Обработчики (чистая логика, без aiohttp) ----------

async def h_state(user: dict, body: dict, ctx) -> dict:
    return ctx.state(user)


async def h_key(user: dict, body: dict, ctx) -> dict:
    key_id = body.get("id")
    if not isinstance(key_id, int):
        raise ValueError("Неверный запрос")
    data = ctx.key(user["id"], key_id)
    if data is None:
        raise LookupError("Ключ не найден")
    return data


async def h_invoice(user: dict, body: dict, ctx) -> dict:
    tid, extras = body.get("tariff"), body.get("extras", 0)
    if not isinstance(tid, str) or not isinstance(extras, int) or isinstance(extras, bool):
        raise ValueError("Неверный запрос")
    return {"link": await ctx.invoice(user["id"], tid, extras)}


async def h_promo(user: dict, body: dict, ctx) -> dict:
    code = body.get("code")
    if not isinstance(code, str) or not code.strip() or len(code) > 64:
        raise ValueError("Введи промокод")
    return {"message": await ctx.promo(user["id"], code)}


async def h_trial(user: dict, body: dict, ctx) -> dict:
    ok, message = await ctx.trial(user["id"])
    return {"ok": ok, "message": message}


ROUTES = {
    "/api/state": h_state,
    "/api/key": h_key,
    "/api/invoice": h_invoice,
    "/api/promo": h_promo,
    "/api/trial": h_trial,
}


# ---------- Склейка с aiohttp ----------

def make_app(ctx) -> web.Application:
    """ctx: объект с полями bot_token и функциями state, key, invoice, promo, trial, is_banned."""

    def api(handler):
        async def wrapper(request: web.Request) -> web.Response:
            user = validate_init_data(request.headers.get("X-Init-Data", ""), ctx.bot_token)
            if user is None:
                return web.json_response({"error": "Открой приложение через Telegram"}, status=401)
            if ctx.is_banned(user["id"]):
                return web.json_response({"error": "Доступ ограничен"}, status=403)
            if not rate_ok(user["id"]):
                return web.json_response({"error": "Слишком часто. Подожди минуту."}, status=429)
            try:
                body = await request.json() if request.can_read_body else {}
                if not isinstance(body, dict):
                    raise ValueError("Неверный запрос")
                data = await handler(user, body, ctx)
            except LookupError as exc:
                return web.json_response({"error": str(exc)}, status=404)
            except ValueError as exc:
                return web.json_response({"error": str(exc)}, status=400)
            except Exception:
                log.exception("Ошибка в мини-приложении: %s user=%s", request.path, user["id"])
                return web.json_response({"error": "Что-то пошло не так. Попробуй ещё раз."}, status=500)
            return web.json_response(data, headers={"Cache-Control": "no-store"})
        return wrapper

    async def index(request: web.Request) -> web.Response:
        with open(INDEX_PATH, "rb") as f:
            body = f.read()
        return web.Response(
            body=body, content_type="text/html", charset="utf-8",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    async def app_info(request: web.Request) -> web.Response:
        """Для отдельного приложения: ключ сам служит паролем. Без Telegram, но с лимитом запросов по IP."""
        ip = request.headers.get("X-Forwarded-For", request.remote or "").split(",")[0].strip()
        if not rate_ok(hash(ip) % 10**9 + 10**10):
            return web.json_response({"error": "Слишком часто"}, status=429)
        try:
            body = await request.json()
            key = body.get("key") if isinstance(body, dict) else None
            if not isinstance(key, str) or not key.startswith("vpn://"):
                raise ValueError
        except Exception:
            return web.json_response({"error": "Неверный запрос"}, status=400)
        data = ctx.app_info(key)
        if data is None:
            return web.json_response({"error": "Ключ не найден"}, status=404)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    app = web.Application(client_max_size=64 * 1024)
    app.router.add_post("/api/app/info", app_info)
    app.router.add_get("/", index)
    for path, handler in ROUTES.items():
        app.router.add_post(path, api(handler))
    return app


async def start(ctx, host: str = "127.0.0.1", port: int = 8080) -> web.AppRunner:
    runner = web.AppRunner(make_app(ctx))
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("Мини-приложение слушает %s:%s", host, port)
    return runner
