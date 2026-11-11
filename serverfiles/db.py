"""Мини-база на SQLite: ключи, платежи, пробные периоды."""
import os
import sqlite3
import time

# База лежит рядом с bot.py, независимо от того, откуда запущен бот
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

_db = sqlite3.connect(DB_PATH)
_db.row_factory = sqlite3.Row


def _add_column(table: str, column: str, decl: str):
    cols = [r["name"] for r in _db.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        _db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init():
    _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS trials (
            user_id INTEGER PRIMARY KEY,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id TEXT NOT NULL,
            protocol TEXT NOT NULL,
            config TEXT NOT NULL,
            tariff TEXT NOT NULL,
            source TEXT NOT NULL,
            charge_id TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS keys_user ON keys (user_id);
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            value INTEGER NOT NULL,
            max_uses INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS promo_uses (
            code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            used_at INTEGER NOT NULL,
            PRIMARY KEY (code, user_id)
        );
        CREATE TABLE IF NOT EXISTS user_promo (
            user_id INTEGER PRIMARY KEY,
            code TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subs (
            user_id INTEGER PRIMARY KEY,
            expires_at INTEGER NOT NULL,
            extra_devices INTEGER NOT NULL DEFAULT 0,
            is_trial INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS banned (
            user_id INTEGER PRIMARY KEY,
            banned_at INTEGER NOT NULL,
            banned_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS banned (
            user_id INTEGER PRIMARY KEY,
            banned_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
            charge_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            tariff TEXT NOT NULL,
            amount INTEGER NOT NULL,
            kind TEXT NOT NULL,
            key_id INTEGER,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    _add_column("keys", "revoked", "INTEGER NOT NULL DEFAULT 0")
    _add_column("payments", "extras", "INTEGER NOT NULL DEFAULT 0")
    # Люди, у которых были ключи до появления подписок: их ключи становятся устройствами подписки
    _db.execute(
        """INSERT OR IGNORE INTO subs (user_id, expires_at, extra_devices, is_trial)
           SELECT user_id, MAX(expires_at), 0,
                  CASE WHEN SUM(source != 'trial') = 0 THEN 1 ELSE 0 END
           FROM keys WHERE source != 'admin' AND revoked = 0 GROUP BY user_id"""
    )
    # Люди, которые пользовались ботом до появления таблицы users, попадают в неё сразу
    now = int(time.time())
    _db.execute(
        """INSERT OR IGNORE INTO users (user_id, first_seen, last_seen)
           SELECT user_id, ?, ? FROM (
               SELECT user_id FROM keys UNION SELECT user_id FROM payments
               UNION SELECT user_id FROM trials
           )""",
        (now, now),
    )
    _db.commit()


# ---------- Пользователи ----------

def upsert_user(user_id: int, username: str | None, first_name: str | None):
    now = int(time.time())
    _db.execute(
        """INSERT INTO users (user_id, username, first_name, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               first_name = excluded.first_name,
               last_seen = excluded.last_seen""",
        (user_id, username, first_name, now, now),
    )
    _db.commit()


def get_user(user_id: int):
    return _db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def count_users() -> int:
    return _db.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def list_users(limit: int, offset: int):
    """Пользователи с числом ключей и суммой оплат, недавно заходившие — первыми."""
    now = int(time.time())
    return _db.execute(
        """SELECT u.user_id, u.username, u.first_name, u.first_seen, u.last_seen,
               (SELECT COUNT(*) FROM keys k WHERE k.user_id = u.user_id AND k.revoked = 0) AS keys_n,
               (SELECT COUNT(*) FROM keys k
                  WHERE k.user_id = u.user_id AND k.revoked = 0 AND k.expires_at > ?) AS keys_active,
               (SELECT COALESCE(SUM(p.amount), 0) FROM payments p
                  WHERE p.user_id = u.user_id AND p.status = 'paid') AS stars
           FROM users u ORDER BY u.last_seen DESC LIMIT ? OFFSET ?""",
        (now, limit, offset),
    ).fetchall()


# ---------- Пробный период ----------

def has_trial(user_id: int) -> bool:
    if _db.execute("SELECT 1 FROM trials WHERE user_id = ?", (user_id,)).fetchone():
        return True
    row = _db.execute(
        "SELECT 1 FROM keys WHERE user_id = ? AND source = 'trial'", (user_id,)
    ).fetchone()
    return row is not None


def claim_trial(user_id: int) -> bool:
    """Занимает пробный период. True — получилось, False — уже брал."""
    if has_trial(user_id):
        return False
    cur = _db.execute(
        "INSERT OR IGNORE INTO trials (user_id, created_at) VALUES (?, ?)",
        (user_id, int(time.time())),
    )
    _db.commit()
    return cur.rowcount == 1


def release_trial(user_id: int):
    """Освобождает пробный период, если ключ создать не удалось."""
    _db.execute("DELETE FROM trials WHERE user_id = ?", (user_id,))
    _db.commit()


# ---------- Ключи ----------

def add_key(user_id, client_id, protocol, config, tariff, source, charge_id, expires_at) -> int:
    cur = _db.execute(
        """INSERT INTO keys
           (user_id, client_id, protocol, config, tariff, source, charge_id, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, str(client_id), protocol, config, tariff, source, charge_id,
         int(time.time()), int(expires_at)),
    )
    _db.commit()
    return cur.lastrowid


def user_keys(user_id: int):
    """Все ключи человека, кроме удалённых им устройств."""
    return _db.execute(
        "SELECT * FROM keys WHERE user_id = ? AND revoked = 0 ORDER BY id DESC", (user_id,)
    ).fetchall()


def device_keys(user_id: int):
    """Ключи-устройства подписки (без ключей, выданных админом), от старых к новым."""
    return _db.execute(
        "SELECT * FROM keys WHERE user_id = ? AND revoked = 0 AND source != 'admin' ORDER BY id",
        (user_id,),
    ).fetchall()


def revoke_key(key_id: int):
    """Помечает устройство удалённым (на сервере его отключает бот)."""
    _db.execute("UPDATE keys SET revoked = 1 WHERE id = ?", (key_id,))
    _db.commit()


def get_key(key_id: int):
    return _db.execute("SELECT * FROM keys WHERE id = ?", (key_id,)).fetchone()


def set_expiry(key_id: int, expires_at: int):
    _db.execute("UPDATE keys SET expires_at = ? WHERE id = ?", (int(expires_at), key_id))
    _db.commit()


# ---------- Админы, добавленные в боте ----------

def is_extra_admin(user_id: int) -> bool:
    return _db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone() is not None


def list_admin_ids() -> list[int]:
    return [r["user_id"] for r in _db.execute("SELECT user_id FROM admins ORDER BY added_at")]


def add_admin(user_id: int, added_by: int) -> bool:
    cur = _db.execute(
        "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
        (user_id, added_by, int(time.time())),
    )
    _db.commit()
    return cur.rowcount == 1


def del_admin(user_id: int) -> bool:
    cur = _db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    _db.commit()
    return cur.rowcount == 1


# ---------- Блокировки ----------

def is_banned(user_id: int) -> bool:
    return _db.execute("SELECT 1 FROM banned WHERE user_id = ?", (user_id,)).fetchone() is not None


def ban_user(user_id: int, by: int):
    _db.execute(
        "INSERT OR IGNORE INTO banned (user_id, banned_at, banned_by) VALUES (?, ?, ?)",
        (user_id, int(time.time()), by),
    )
    _db.commit()


def unban_user(user_id: int) -> bool:
    cur = _db.execute("DELETE FROM banned WHERE user_id = ?", (user_id,))
    _db.commit()
    return cur.rowcount == 1


# ---------- Поиск, рассылки, отчёты для админ-панели ----------

def find_user(query: str):
    """Пользователь по id или @username (без учёта регистра)."""
    q = query.strip().lstrip("@")
    if q.isdigit():
        return get_user(int(q))
    return _db.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (q,)
    ).fetchone()


AUDIENCES = {
    "all": "Все пользователи",
    "active": "С активной подпиской",
    "expired": "С истёкшей подпиской",
    "soon": "Подписка истекает в ближайшие 3 дня",
    "nobuy": "Никогда не покупали и без подписки",
}


def broadcast_ids(audience: str) -> list[int]:
    now = int(time.time())
    if audience == "active":
        sql, args = "SELECT user_id FROM subs WHERE expires_at > ?", (now,)
    elif audience == "expired":
        sql, args = "SELECT user_id FROM subs WHERE expires_at <= ?", (now,)
    elif audience == "soon":
        sql, args = "SELECT user_id FROM subs WHERE expires_at > ? AND expires_at <= ?", (now, now + 3 * 86400)
    elif audience == "nobuy":
        sql, args = (
            """SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM subs)
               AND user_id NOT IN (SELECT user_id FROM payments WHERE status = 'paid')""", ()
        )
    else:
        sql, args = "SELECT user_id FROM users", ()
    ids = [r[0] for r in _db.execute(sql, args)]
    banned = {r[0] for r in _db.execute("SELECT user_id FROM banned")}
    return [i for i in ids if i not in banned]


def expiring_subs(within_seconds: int, limit: int):
    now = int(time.time())
    return _db.execute(
        """SELECT s.user_id, s.expires_at, s.is_trial, u.username, u.first_name
           FROM subs s LEFT JOIN users u ON u.user_id = s.user_id
           WHERE s.expires_at > ? AND s.expires_at <= ? ORDER BY s.expires_at LIMIT ?""",
        (now, now + within_seconds, limit),
    ).fetchall()


def revenue_by_day(days: int):
    """[(YYYY-MM-DD по МСК, число платежей, сумма звёзд)], свежие дни первыми."""
    since = int(time.time()) - days * 86400
    return _db.execute(
        """SELECT strftime('%Y-%m-%d', created_at + 10800, 'unixepoch') AS day,
                  COUNT(*), COALESCE(SUM(amount), 0)
           FROM payments WHERE status = 'paid' AND created_at >= ?
           GROUP BY day ORDER BY day DESC""",
        (since,),
    ).fetchall()


def tariff_counts():
    return _db.execute(
        """SELECT tariff, COUNT(*), COALESCE(SUM(amount), 0) FROM payments
           WHERE status = 'paid' GROUP BY tariff ORDER BY COUNT(*) DESC"""
    ).fetchall()


def export_users():
    return _db.execute(
        """SELECT u.user_id, u.username, u.first_name, u.first_seen, u.last_seen,
                  s.expires_at AS sub_until,
                  (SELECT COALESCE(SUM(p.amount), 0) FROM payments p
                     WHERE p.user_id = u.user_id AND p.status = 'paid') AS stars
           FROM users u LEFT JOIN subs s ON s.user_id = u.user_id ORDER BY u.first_seen"""
    ).fetchall()


def export_payments():
    return _db.execute(
        """SELECT p.charge_id, p.user_id, u.username, p.tariff, p.extras, p.amount, p.status, p.created_at
           FROM payments p LEFT JOIN users u ON u.user_id = p.user_id ORDER BY p.created_at"""
    ).fetchall()


# ---------- Бан, поиск, рассылки, копия ----------

def is_banned(user_id: int) -> bool:
    return _db.execute("SELECT 1 FROM banned WHERE user_id = ?", (user_id,)).fetchone() is not None


def ban_user(user_id: int):
    _db.execute("INSERT OR IGNORE INTO banned (user_id, banned_at) VALUES (?, ?)", (user_id, int(time.time())))
    _db.commit()


def unban_user(user_id: int):
    _db.execute("DELETE FROM banned WHERE user_id = ?", (user_id,))
    _db.commit()


def search_users(query: str, limit: int = 8):
    """Поиск по id, @username или части имени (без учёта регистра, в том числе для кириллицы)."""
    q = query.strip().lstrip("@").lower()
    if not q:
        return []
    if q.isdigit():
        row = get_user(int(q))
        if row is not None:
            return [row]
    found = []
    for u in _db.execute("SELECT * FROM users ORDER BY last_seen DESC"):
        if q in (u["username"] or "").lower() or q in (u["first_name"] or "").lower():
            found.append(u)
            if len(found) >= limit:
                break
    return found


def expiring_subs(within_days: int):
    """Подписки, которые закончатся в ближайшие within_days дней (ещё не истёкшие)."""
    now = int(time.time())
    return _db.execute(
        """SELECT s.*, u.username, u.first_name FROM subs s
           LEFT JOIN users u ON u.user_id = s.user_id
           WHERE s.expires_at > ? AND s.expires_at <= ?
             AND s.user_id NOT IN (SELECT user_id FROM banned)
           ORDER BY s.expires_at""",
        (now, now + within_days * 86400),
    ).fetchall()


def audience_ids(kind: str) -> list[int]:
    """Кому слать рассылку: all | active | expired | none (без подписки). Заблокированные исключены."""
    now = int(time.time())
    base = "SELECT u.user_id FROM users u WHERE u.user_id NOT IN (SELECT user_id FROM banned)"
    if kind == "active":
        sql = base + " AND u.user_id IN (SELECT user_id FROM subs WHERE expires_at > ?)"
    elif kind == "expired":
        sql = base + " AND u.user_id IN (SELECT user_id FROM subs WHERE expires_at <= ?)"
    elif kind == "none":
        sql = base + " AND u.user_id NOT IN (SELECT user_id FROM subs) AND ? IS NOT NULL"
    else:
        sql = base + " AND ? IS NOT NULL"
    return [r[0] for r in _db.execute(sql, (now,))]


def backup(path: str):
    dest = sqlite3.connect(path)
    try:
        _db.backup(dest)
    finally:
        dest.close()


# ---------- Подписки ----------

def get_sub(user_id: int):
    return _db.execute("SELECT * FROM subs WHERE user_id = ?", (user_id,)).fetchone()


def set_sub(user_id: int, expires_at: int, extra_devices: int, is_trial: int):
    _db.execute(
        """INSERT INTO subs (user_id, expires_at, extra_devices, is_trial) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at,
               extra_devices = excluded.extra_devices, is_trial = excluded.is_trial""",
        (user_id, int(expires_at), extra_devices, is_trial),
    )
    _db.commit()


# ---------- Платежи ----------

def record_payment(charge_id, user_id, tariff, amount, kind, key_id, extras=0) -> bool:
    """Записывает платёж. False — такой платёж уже обработан (защита от дублей)."""
    cur = _db.execute(
        """INSERT OR IGNORE INTO payments
           (charge_id, user_id, tariff, amount, kind, key_id, status, created_at, extras)
           VALUES (?, ?, ?, ?, ?, ?, 'paid', ?, ?)""",
        (charge_id, user_id, tariff, amount, kind, key_id, int(time.time()), extras),
    )
    _db.commit()
    return cur.rowcount == 1


def set_payment_key(charge_id: str, key_id: int):
    _db.execute("UPDATE payments SET key_id = ? WHERE charge_id = ?", (key_id, charge_id))
    _db.commit()


def get_payment(charge_id: str):
    return _db.execute("SELECT * FROM payments WHERE charge_id = ?", (charge_id,)).fetchone()


def set_payment_status(charge_id: str, status: str):
    _db.execute("UPDATE payments SET status = ? WHERE charge_id = ?", (status, charge_id))
    _db.commit()


# ---------- Промокоды ----------
# kind: 'days' — бесплатный ключ на value дней; 'percent' — скидка value % на покупку/продление.
# max_uses = 0 — без ограничения числа активаций; expires_at = 0 — без срока действия.

def create_promo(code: str, kind: str, value: int, max_uses: int, expires_at: int) -> bool:
    cur = _db.execute(
        """INSERT OR IGNORE INTO promos (code, kind, value, max_uses, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (code, kind, value, max_uses, int(expires_at), int(time.time())),
    )
    _db.commit()
    return cur.rowcount == 1


def get_promo(code: str):
    return _db.execute("SELECT * FROM promos WHERE code = ?", (code,)).fetchone()


def list_promos(limit: int = 30):
    return _db.execute(
        "SELECT * FROM promos ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


def deactivate_promo(code: str) -> bool:
    cur = _db.execute("UPDATE promos SET active = 0 WHERE code = ?", (code,))
    _db.commit()
    return cur.rowcount == 1


def promo_problem(code: str, user_id: int) -> str | None:
    """Почему промокод нельзя использовать. None — можно."""
    p = get_promo(code)
    if p is None:
        return "Такого промокода нет."
    if not p["active"]:
        return "Этот промокод отключён."
    if p["expires_at"] and p["expires_at"] <= time.time():
        return "Срок действия промокода истёк."
    if _db.execute(
        "SELECT 1 FROM promo_uses WHERE code = ? AND user_id = ?", (code, user_id)
    ).fetchone():
        return "Ты уже использовал этот промокод."
    if p["max_uses"] and p["used"] >= p["max_uses"]:
        return "Этот промокод уже использован максимальное число раз."
    return None


def redeem_promo(code: str, user_id: int) -> bool:
    """Списывает одну активацию. False — нельзя (уже использован этим человеком, лимит, срок)."""
    cur = _db.execute(
        "INSERT OR IGNORE INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
        (code, user_id, int(time.time())),
    )
    if cur.rowcount != 1:
        _db.rollback()
        return False
    cur = _db.execute(
        """UPDATE promos SET used = used + 1
           WHERE code = ? AND active = 1
             AND (max_uses = 0 OR used < max_uses)
             AND (expires_at = 0 OR expires_at > ?)""",
        (code, int(time.time())),
    )
    if cur.rowcount != 1:
        _db.rollback()
        return False
    _db.commit()
    return True


def unredeem_promo(code: str, user_id: int):
    """Возвращает активацию (если ключ по промокоду выдать не удалось)."""
    cur = _db.execute(
        "DELETE FROM promo_uses WHERE code = ? AND user_id = ?", (code, user_id)
    )
    if cur.rowcount == 1:
        _db.execute("UPDATE promos SET used = MAX(used - 1, 0) WHERE code = ?", (code,))
    _db.commit()


def set_pending(user_id: int, code: str):
    _db.execute(
        "INSERT INTO user_promo (user_id, code) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET code = excluded.code",
        (user_id, code),
    )
    _db.commit()


def get_pending(user_id: int) -> str | None:
    row = _db.execute("SELECT code FROM user_promo WHERE user_id = ?", (user_id,)).fetchone()
    return row["code"] if row else None


def clear_pending(user_id: int):
    _db.execute("DELETE FROM user_promo WHERE user_id = ?", (user_id,))
    _db.commit()


# ---------- Данные для админ-панели ----------

def all_keys():
    return _db.execute("SELECT * FROM keys").fetchall()


def count_payments() -> int:
    return _db.execute("SELECT COUNT(*) FROM payments").fetchone()[0]


def list_payments(limit: int, offset: int):
    return _db.execute(
        """SELECT p.*, u.username, u.first_name
           FROM payments p LEFT JOIN users u ON u.user_id = p.user_id
           ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()


def user_payments(user_id: int, limit: int = 5):
    return _db.execute(
        "SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


def admin_stats() -> dict:
    now = int(time.time())
    q = lambda sql, *a: _db.execute(sql, a).fetchone()[0]
    paid_since = lambda sec: q(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND created_at > ?",
        now - sec,
    )
    return {
        "users": q("SELECT COUNT(*) FROM users"),
        "buyers": q(
            "SELECT COUNT(DISTINCT user_id) FROM payments WHERE status IN ('paid', 'failed')"
        ),
        "keys_total": q("SELECT COUNT(*) FROM keys WHERE revoked = 0"),
        "keys_active": q("SELECT COUNT(*) FROM keys WHERE revoked = 0 AND expires_at > ?", now),
        "keys_paid": q("SELECT COUNT(*) FROM keys WHERE source = 'paid'"),
        "keys_trial": q("SELECT COUNT(*) FROM keys WHERE source = 'trial'"),
        "keys_promo": q("SELECT COUNT(*) FROM keys WHERE source = 'promo'"),
        "keys_admin": q("SELECT COUNT(*) FROM keys WHERE source = 'admin'"),
        "pay_count": q("SELECT COUNT(*) FROM payments WHERE status = 'paid'"),
        "pay_sum": q("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'"),
        "fail_count": q("SELECT COUNT(*) FROM payments WHERE status = 'failed'"),
        "fail_sum": q("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'failed'"),
        "ref_sum": q("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'refunded'"),
        "subs_active": q("SELECT COUNT(*) FROM subs WHERE expires_at > ?", now),
        "extras_sold": q("SELECT COALESCE(SUM(extras), 0) FROM payments WHERE status = 'paid'"),
        "sum_24h": paid_since(86400),
        "sum_7d": paid_since(7 * 86400),
        "sum_30d": paid_since(30 * 86400),
    }


# ---------- Статистика для админа ----------

def stats() -> dict:
    now = int(time.time())
    q = lambda sql, *a: _db.execute(sql, a).fetchone()[0]
    return {
        "users": q("SELECT COUNT(DISTINCT user_id) FROM keys"),
        "keys_total": q("SELECT COUNT(*) FROM keys"),
        "keys_active": q("SELECT COUNT(*) FROM keys WHERE revoked = 0 AND expires_at > ?", now),
        "payments": q("SELECT COUNT(*) FROM payments"),
        "payments_failed": q("SELECT COUNT(*) FROM payments WHERE status = 'failed'"),
        "stars": q("SELECT COALESCE(SUM(amount), 0) FROM payments"),
    }


def key_by_config(config: str):
    """Живой ключ по тексту (vpn://...) — для отдельного приложения."""
    if not config or len(config) > 20000:
        return None
    return _db.execute("SELECT * FROM keys WHERE config = ? AND revoked = 0 LIMIT 1", (config,)).fetchone()
