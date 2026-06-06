import asyncio
import os
import random
import re
import signal
import sqlite3
import time
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
IDLE_ROAST_MINUTES = int(os.getenv("IDLE_ROAST_MINUTES", "45"))

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
    (0, "Свидетель Серегиного тупняка"),
    (5, "Начинающий матерщинник"),
    (15, "Уличный засаживатель"),
    (35, "Мастер грязного захода"),
    (70, "Токсичный инженер"),
    (120, "Генерал словесной помойки"),
    (200, "Архимаг ебаного вайба"),
    (350, "Верховный инспектор Серегиного дна"),
    (500, "Босс финального срача"),
    (750, "Легенда чата без тормозов"),
    (1000, "Абсолютный чемпион токсик-лиги"),
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
        text="Виртуальный Серега получил колпак позора и теперь выглядит как ходячий проеб здравого смысла.",
    ),
    ShopItem(
        code="bench",
        title="Посадить Виртуального Серегу на скамейку раздумий",
        cost=20,
        text="Виртуальный Серега сел подумать. Судя по лицу, процесс опять нихуя не запустился.",
    ),
    ShopItem(
        code="crown",
        title="Выдать корону главного провала",
        cost=35,
        text="Виртуальный Серега коронован как главный проеб вечера. Корона держится плохо, потому что голова спорная.",
    ),
    ShopItem(
        code="museum",
        title="Поместить в музей спорных решений",
        cost=60,
        text="Виртуальный Серега выставлен в музее сомнительных решений. Табличка: 'Не повторять, блять, вообще никогда'.",
    ),
    ShopItem(
        code="pit",
        title="Скинуть в яму репутации",
        cost=90,
        text="Виртуальный Серега упал в яму репутации. Снизу уже стучат его прошлые проебы.",
    ),
    ShopItem(
        code="manual",
        title="Выдать инструкцию по включению мозга",
        cost=130,
        text="Виртуальному Сереге выдали инструкцию по включению мозга. Он прочитал слово 'инструкция' и уже охуел.",
    ),
]

SPICY_REPLIES = [
    "Нихуясе ты заебенил по дикой. Токсикометр аж присел.",
    "Вот это высер, конечно. Начисляю баллы за художественный ущерб.",
    "Ебать ты зарядил. Чат получил моральную царапину.",
    "Словесная граната прилетела. Баллы на счет, психика в минус.",
    "Ты сейчас не сообщение написал, а маленький акт цифрового хулиганства.",
    "Мат обнаружен. Уровень культуры просел, зато рейтинг попер.",
    "Это было грязно, громко и, к сожалению, эффективно. Баллы начислены.",
    "Чат официально потрогали немытыми словами. +очки.",
    "Ты сейчас так навалил, что даже фильтр сказал: 'я в отпуск, нахуй'.",
    "Виртуальный Серега попытался это понять, охуел и ушел перезагружаться.",
    "За такой заход Виртуальный Серега получает +1 к репутации ходячего сбоя.",
    "Где-то Виртуальный Серега снова нажал не туда. Баллы, сука, начислены.",
]

COMBO_REPLIES = [
    "Брат, ты не ругался, ты провел артиллерийскую подготовку матом.",
    "Ебать там комбо. За такое надо не баллы давать, а каску.",
    "Сообщение принято. Санитары чата уже выехали, Виртуальный Серега лег заранее.",
    "Ты только что сделал словесный подкат двумя ногами.",
    "Это уже не мат, это дипломная работа по деградации речи.",
    "Чат тряхнуло так, что Виртуальный Серега временно стал умнее, но быстро проебал эффект.",
]

IDLE_ROASTS = [
    "Хули вы утихли, уебаны? Виртуальный Серега где-то сидит, дрочит на свои провалы и ждет движуху.",
    "Чат сдох или вы все ушли думать? Виртуальный Серега тоже пытался думать, но, как обычно, обосрался.",
    "Алло, живые есть? А то тишина такая, будто Виртуальный Серега опять объясняет очевидное.",
    "Вы чего притихли, культурные стали? Виртуальный Серега уже плачет: без вашего срача он чувствует себя умным.",
    "Хватит молчать, чат. Виртуальный Серега от скуки начал спорить с дверью и проигрывает.",
    "Тишина подозрительная. Где мат, где срач, где очередной Серегин мысленный проеб?",
    "Чат, просыпайся. Виртуальный Серега уже третий раз за час наступил на одну и ту же мысль.",
    "Ну и хули тут кладбище? Напишите что-нибудь, пока Виртуальный Серега не объявил себя главным интеллектуалом.",
    "Проверка связи: кто живой, тот матерится. Виртуальный Серега, конечно, не считается, он завис на загрузке мозга.",
    "Слишком тихо. Где-то Виртуальный Серега решил, что это из-за его авторитета. Нельзя такое допускать.",
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            idle_roast_enabled INTEGER NOT NULL DEFAULT 0,
            last_seen_at INTEGER NOT NULL DEFAULT 0,
            last_roast_at INTEGER NOT NULL DEFAULT 0
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


def touch_chat(conn: sqlite3.Connection, message: Message) -> None:
    title = message.chat.title or getattr(message.chat, "full_name", None) or str(message.chat.id)
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO chat_settings(chat_id, title, last_seen_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = excluded.title,
            last_seen_at = excluded.last_seen_at
        """,
        (message.chat.id, title, now),
    )
    conn.commit()


def set_idle_roast(conn: sqlite3.Connection, message: Message, enabled: bool) -> None:
    touch_chat(conn, message)
    conn.execute(
        "UPDATE chat_settings SET idle_roast_enabled = ? WHERE chat_id = ?",
        (1 if enabled else 0, message.chat.id),
    )
    conn.commit()


def idle_roast_chats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    min_interval = IDLE_ROAST_MINUTES * 60
    now = int(time.time())
    return conn.execute(
        """
        SELECT * FROM chat_settings
        WHERE idle_roast_enabled = 1
          AND ? - last_seen_at >= ?
          AND ? - last_roast_at >= ?
        """,
        (now, min_interval, now, min_interval),
    ).fetchall()


async def is_chat_admin(bot: Bot, message: Message) -> bool:
    if not message.from_user:
        return False
    if message.chat.type == "private":
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    except Exception:
        return False
    return str(member.status) in {"creator", "administrator", "ChatMemberStatus.CREATOR", "ChatMemberStatus.ADMINISTRATOR"}


dp = Dispatcher()


@dp.message(Command("start", "help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Я считаю очки токсичного угара в группе и выдаю ранги.\n\n"
        "Команды:\n"
        "/rank - твой ранг\n"
        "/top - топ участников\n"
        "/shop - магазин приколов\n"
        "/buy код - купить прикол для Виртуального Сереги\n"
        "/sergey_on - включить автоподъебы, когда чат затих\n"
        "/sergey_off - выключить автоподъебы\n"
        "/sergey_ping - проверить автоподъеб сразу"
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


@dp.message(Command("sergey_on"))
async def sergey_on_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Эту кнопку хаоса может нажимать только админ чата.")
        return
    with connect() as conn:
        set_idle_roast(conn, message, True)
    await message.answer(
        f"Автоподъебы включены. Если чат затихнет на {IDLE_ROAST_MINUTES} минут, "
        "Виртуальный Серега получит очередной словесный подзатыльник."
    )


@dp.message(Command("sergey_off"))
async def sergey_off_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Выключать этот цирк может только админ чата.")
        return
    with connect() as conn:
        set_idle_roast(conn, message, False)
    await message.answer("Автоподъебы выключены. Виртуальный Серега временно выдохнул, зря конечно.")


@dp.message(Command("sergey_ping"))
async def sergey_ping_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Пинговать Виртуального Серегу может только админ чата.")
        return
    await message.answer(random.choice(IDLE_ROASTS))


@dp.message(F.text)
async def score_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    with connect() as conn:
        touch_chat(conn, message)
    points = score_text(message.text or "")
    if points <= 0:
        with connect() as conn:
            upsert_user(conn, message, 0)
        return

    with connect() as conn:
        row = upsert_user(conn, message, points)

    if SPICY_MODE:
        replies = COMBO_REPLIES if points >= 5 else SPICY_REPLIES
        reply = replies[row["toxic_hits"] % len(replies)]
        await message.reply(
            f"{reply}\n"
            f"+{points} очк. | всего: {row['points']} | ранг: {rank_for(row['points'])}"
        )


async def idle_roast_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(60)
        with connect() as conn:
            rows = idle_roast_chats(conn)
            now = int(time.time())
            for row in rows:
                try:
                    await bot.send_message(row["chat_id"], random.choice(IDLE_ROASTS))
                    conn.execute(
                        "UPDATE chat_settings SET last_roast_at = ? WHERE chat_id = ?",
                        (now, row["chat_id"]),
                    )
                    conn.commit()
                except Exception:
                    pass


async def main() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    bot = Bot(BOT_TOKEN)
    asyncio.create_task(idle_roast_loop(bot))

    if WEBHOOK_URL:
        app = web.Application()

        async def healthcheck(_: web.Request) -> web.Response:
            return web.Response(text="ok")

        app.router.add_get("/", healthcheck)
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
        await site.start()

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

        await stop_event.wait()
        await runner.cleanup()
        return

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
