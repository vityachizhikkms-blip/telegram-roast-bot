import asyncio
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot.db").strip()
SPICY_MODE = os.getenv("SPICY_MODE", "true").lower() in {"1", "true", "yes", "on"}
WEBHOOK_URL = (
    os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    or os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
)
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook").strip() or "/webhook"
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Put your BotFather token into .env")


TOXIC_PATTERNS = [
    (re.compile(r"\bбл[яеи]\w*", re.IGNORECASE), 1),
    (re.compile(r"\bх[уy][йяеёию]\w*", re.IGNORECASE), 2),
    (re.compile(r"\bп[ие]зд\w*", re.IGNORECASE), 2),
    (re.compile(r"\bеб\w*", re.IGNORECASE), 2),
    (re.compile(r"\bсу(к|ч)\w*", re.IGNORECASE), 1),
    (re.compile(r"\bдолбо\w*", re.IGNORECASE), 2),
    (re.compile(r"\bидиот\w*", re.IGNORECASE), 1),
    (re.compile(r"\bтуп\w*", re.IGNORECASE), 1),
]

RANKS = [
    (0, "Чистый лист"),
    (5, "Легкий поджигатель"),
    (15, "Дворовый философ"),
    (35, "Мастер словесного шума"),
    (70, "Генерал токсичного вайба"),
    (120, "Легенда мутного чата"),
    (200, "Архимаг группового угара"),
]


@dataclass(frozen=True)
class ShopItem:
    code: str
    title: str
    cost: int
    text: str


SHOP = [
    ShopItem(
        code="hat",
        title="Надеть на Виртуального Серегу колпак",
        cost=10,
        text="Виртуальный Серега получил колпак позора и теперь выглядит как ходячее предупреждение.",
    ),
    ShopItem(
        code="bench",
        title="Посадить Виртуального Серегу на скамейку раздумий",
        cost=20,
        text="Виртуальный Серега отправлен на скамейку раздумий. Он думает, но это пока не точно.",
    ),
    ShopItem(
        code="crown",
        title="Выдать корону главного провала",
        cost=35,
        text="Виртуальный Серега торжественно коронован как главный провал вечера.",
    ),
    ShopItem(
        code="museum",
        title="Поместить в музей спорных решений",
        cost=60,
        text="Виртуальный Серега выставлен в музее спорных решений. Экскурсовод плачет, но держится.",
    ),
]

SPICY_REPLIES = [
    "Зафиксировал словесный поджог. Баллы начислены.",
    "Ого, чат слегка дымится. Держи очки.",
    "Токсикометр дернулся. Записываю в историю.",
    "Вот это эмоциональная бухгалтерия. Баллы пошли.",
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            messages INTEGER NOT NULL DEFAULT 0,
            toxic_hits INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            item_code TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def score_text(text: str) -> int:
    score = 0
    for pattern, weight in TOXIC_PATTERNS:
        score += len(pattern.findall(text)) * weight
    return score


def rank_for(points: int) -> str:
    current = RANKS[0][1]
    for threshold, title in RANKS:
        if points >= threshold:
            current = title
    return current


def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Неизвестный герой"
    return user.full_name or user.username or str(user.id)


def upsert_user(conn: sqlite3.Connection, message: Message, points_delta: int) -> sqlite3.Row:
    user = message.from_user
    if not user:
        raise ValueError("message has no from_user")

    conn.execute(
        """
        INSERT INTO users(chat_id, user_id, username, full_name, points, messages, toxic_hits)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name,
            points = users.points + excluded.points,
            messages = users.messages + 1,
            toxic_hits = users.toxic_hits + excluded.toxic_hits
        """,
        (
            message.chat.id,
            user.id,
            user.username,
            display_name(message),
            points_delta,
            points_delta,
        ),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM users WHERE chat_id = ? AND user_id = ?",
        (message.chat.id, user.id),
    ).fetchone()


def get_user(conn: sqlite3.Connection, chat_id: int, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ).fetchone()


def top_users(conn: sqlite3.Connection, chat_id: int, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM users
        WHERE chat_id = ?
        ORDER BY points DESC, toxic_hits DESC, messages DESC
        LIMIT ?
        """,
        (chat_id, limit),
    ).fetchall()


dp = Dispatcher()


@dp.message(Command("start", "help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Я считаю очки токсичного угара в группе и выдаю ранги.\n\n"
        "Команды:\n"
        "/rank - твой ранг\n"
        "/top - топ участников\n"
        "/shop - магазин приколов\n"
        "/buy код - купить прикол для Виртуального Сереги"
    )


@dp.message(Command("rank"))
async def rank_command(message: Message) -> None:
    if not message.from_user:
        return
    with connect() as conn:
        row = get_user(conn, message.chat.id, message.from_user.id)
    if not row:
        await message.answer("У тебя пока 0 очков. Чат еще не видел твоей темной стороны.")
        return
    await message.answer(
        f"{row['full_name']}\n"
        f"Очки: {row['points']}\n"
        f"Ранг: {rank_for(row['points'])}\n"
        f"Сообщений: {row['messages']}"
    )


@dp.message(Command("top"))
async def top_command(message: Message) -> None:
    with connect() as conn:
        rows = top_users(conn, message.chat.id)
    if not rows:
        await message.answer("Топ пока пуст. Подозрительно культурная группа.")
        return
    lines = ["Топ токсичного угара:"]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. {row['full_name']} - {row['points']} очк., {rank_for(row['points'])}"
        )
    await message.answer("\n".join(lines))


@dp.message(Command("shop"))
async def shop_command(message: Message) -> None:
    lines = ["Магазин виртуальных приколов:"]
    for item in SHOP:
        lines.append(f"/buy {item.code} - {item.title} ({item.cost} очк.)")
    await message.answer("\n".join(lines))


@dp.message(Command("buy"))
async def buy_command(message: Message) -> None:
    if not message.from_user:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Напиши код покупки. Например: /buy crown")
        return
    code = parts[1].strip().lower()
    item = next((entry for entry in SHOP if entry.code == code), None)
    if not item:
        await message.answer("Такого товара нет. Открой /shop и выбери код.")
        return

    with connect() as conn:
        row = get_user(conn, message.chat.id, message.from_user.id)
        points = int(row["points"]) if row else 0
        if points < item.cost:
            await message.answer(f"Не хватает очков: нужно {item.cost}, у тебя {points}.")
            return
        conn.execute(
            "UPDATE users SET points = points - ? WHERE chat_id = ? AND user_id = ?",
            (item.cost, message.chat.id, message.from_user.id),
        )
        conn.execute(
            "INSERT INTO purchases(chat_id, user_id, item_code) VALUES (?, ?, ?)",
            (message.chat.id, message.from_user.id, item.code),
        )
        conn.commit()

    await message.answer(f"{display_name(message)} покупает: {item.title}\n\n{item.text}")


@dp.message(F.text)
async def score_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    points = score_text(message.text or "")
    if points <= 0:
        with connect() as conn:
            upsert_user(conn, message, 0)
        return

    with connect() as conn:
        row = upsert_user(conn, message, points)

    if SPICY_MODE:
        reply = SPICY_REPLIES[row["toxic_hits"] % len(SPICY_REPLIES)]
        await message.reply(
            f"{reply}\n"
            f"+{points} очк. | всего: {row['points']} | ранг: {rank_for(row['points'])}"
        )


async def main() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    bot = Bot(BOT_TOKEN)

    if WEBHOOK_URL:
        app = web.Application()

        async def healthcheck(_: web.Request) -> web.Response:
            return web.Response(text="ok")

        app.router.add_get("/", healthcheck)
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        web.run_app(app, host="0.0.0.0", port=PORT)
        return

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
