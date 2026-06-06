import asyncio
import os
import random
import re
import signal
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
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
DAY_START_HOUR = int(os.getenv("DAY_START_HOUR", "10"))
DAY_END_HOUR = int(os.getenv("DAY_END_HOUR", "23"))
DAY_UTC_OFFSET = int(os.getenv("DAY_UTC_OFFSET", "10"))
AUTO_ROAST_MIN_HOURS = int(os.getenv("AUTO_ROAST_MIN_HOURS", "3"))
AUTO_ROAST_MAX_HOURS = int(os.getenv("AUTO_ROAST_MAX_HOURS", "5"))
LOAN_MIN_HOURS = int(os.getenv("LOAN_MIN_HOURS", "6"))
LOAN_MAX_HOURS = int(os.getenv("LOAN_MAX_HOURS", "12"))
SERIY_STUPIDITY_MINUTES = int(os.getenv("SERIY_STUPIDITY_MINUTES", "60"))

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

SERIY_PATTERNS = [
    re.compile(r"\bсер(ы|о|ё|е|г|ж)\w*", re.IGNORECASE),
    re.compile(r"\bсерж\w*", re.IGNORECASE),
    re.compile(r"\bбратишк[аиу]?\s+сер\w*", re.IGNORECASE),
]

SERIY_ATTACK_PATTERNS = [
    re.compile(r"\bтуп\w*", re.IGNORECASE),
    re.compile(r"\bдебил\w*", re.IGNORECASE),
    re.compile(r"\bдолбо\w*", re.IGNORECASE),
    re.compile(r"\bалкаш\w*", re.IGNORECASE),
    re.compile(r"\bбух\w*", re.IGNORECASE),
    re.compile(r"\bзанял\w*", re.IGNORECASE),
    re.compile(r"\bдолж\w*", re.IGNORECASE),
    re.compile(r"\bне\s+отда\w*", re.IGNORECASE),
    re.compile(r"\bобоср\w*", re.IGNORECASE),
    re.compile(r"\bдн[оа]\w*", re.IGNORECASE),
    re.compile(r"\bпиздабол\w*", re.IGNORECASE),
    re.compile(r"\bхуесос\w*", re.IGNORECASE),
]

RANKS = [
    (0, "Случайный свидетель Серого"),
    (5, "Подмастерье хуевой телеги"),
    (15, "Младший засаживатель Серого"),
    (30, "Жених кринжового ЗАГСа"),
    (50, "Батя мемного ребенка"),
    (80, "Тамада словесного пиздеца"),
    (120, "Профессор грязного флирта"),
    (180, "Главный алиментщик хуевой телеги"),
    (250, "Амурстальский романтик с моральным ущербом"),
    (350, "Министр семейного срача"),
    (500, "Верховный трахарь здравого смысла"),
    (700, "Архимаг ебаного лора"),
    (1000, "Финальный босс Серого"),
    (1500, "Человек, после которого Серый гуглит 'как исчезнуть'"),
    (2000, "Легенда, от которой бывшие Серого идут в ЗАГС сами"),
    (3000, "Бог кринжа, мата и семейного пиздеца"),
    (5000, "Абсолютный патриарх хуевой телеги"),
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
        title="Надеть на Братишку Серого колпак",
        cost=10,
        text="Братишка Серый получил колпак позора и теперь выглядит как ходячий проеб здравого смысла.",
    ),
    ShopItem(
        code="bench",
        title="Посадить Братишку Серого на скамейку раздумий",
        cost=20,
        text="Братишка Серый сел подумать. Судя по лицу, процесс опять нихуя не запустился.",
    ),
    ShopItem(
        code="crown",
        title="Выдать корону главного провала",
        cost=35,
        text="Братишка Серый коронован как главный проеб вечера. Корона держится плохо, потому что голова спорная.",
    ),
    ShopItem(
        code="museum",
        title="Поместить в музей спорных решений",
        cost=60,
        text="Братишка Серый выставлен в музее сомнительных решений. Табличка: 'Не повторять, блять, вообще никогда'.",
    ),
    ShopItem(
        code="pit",
        title="Скинуть в яму репутации",
        cost=90,
        text="Братишка Серый упал в яму репутации. Снизу уже стучат его прошлые проебы.",
    ),
    ShopItem(
        code="manual",
        title="Выдать инструкцию по включению мозга",
        cost=130,
        text="Братишке Серому выдали инструкцию по включению мозга. Он прочитал слово 'инструкция' и уже охуел.",
    ),
]

EXES = [
    "Кристина — королева токсичного ЗАГСа",
    "Бэлла — императрица ночного кринжа",
    "Дама из Наринэ — богиня разлитого пиздеца",
    "Амурстальская легенда — металлургиня грязного флирта",
    "Неизвестная с голосовым на 4 минуты — редкая бывшая",
    "Та самая, которая 'просто подруга' — мифическая бывшая",
    "Администраторша Серегиного стыда — эпическая бывшая",
]

EX_EVENTS = [
    (
        "Кристина вручила тебе обручальное кольцо из пивной крышки. "
        "Братишка Серый увидел это и сказал: 'ну я вообще-то тоже норм', после чего чат умер от кринжа."
    ),
    (
        "Бэлла записала тебя в женихи хуевой телеги. "
        "Серый попытался возразить, но у него опять загрузился только один нейрон."
    ),
    (
        "Дама из Наринэ принесла свадебный пакет, чек из бара и моральный ущерб. "
        "Ты получаешь статус 'почти муж пиздеца'."
    ),
    (
        "Амурстальская легенда признала тебя отцом срача. "
        "Поздравляем: у тебя родился мемный ребенок по имени Маленький Пиздец."
    ),
    (
        "Та самая 'просто подруга' оформила на тебя ипотеку кринжа. "
        "Серый стоит рядом и делает вид, что это был его план."
    ),
    (
        "Неизвестная с голосовым на 4 минуты оставила тебе аудио-проклятие. "
        "Прослушивание невозможно, психика не выдержит."
    ),
    (
        "Кристина и Бэлла одновременно тащат тебя в ЗАГС хуевой телеги. "
        "Серый бежит следом, спотыкается об свое достоинство и теряет последнее уважение."
    ),
    (
        "Бывшие Серого собрались в семейный суд. "
        "Приговор: Серый виновен в тупняке первой степени."
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
    "Братишка Серый попытался это понять, охуел и ушел перезагружаться.",
    "За такой заход Братишка Серый получает +1 к репутации ходячего сбоя.",
    "Где-то Братишка Серый снова нажал не туда. Баллы, сука, начислены.",
]

COMBO_REPLIES = [
    "Брат, ты не ругался, ты провел артиллерийскую подготовку матом.",
    "Ебать там комбо. За такое надо не баллы давать, а каску.",
    "Сообщение принято. Санитары чата уже выехали, Братишка Серый лег заранее.",
    "Ты только что сделал словесный подкат двумя ногами.",
    "Это уже не мат, это дипломная работа по деградации речи.",
    "Чат тряхнуло так, что Братишка Серый временно стал умнее, но быстро проебал эффект.",
]

IDLE_ROASTS = [
    "Хули вы утихли, уебаны? Братишка Серый где-то сидит, дрочит на свои провалы и ждет движуху.",
    "Чат сдох или вы все ушли думать? Братишка Серый тоже пытался думать, но, как обычно, обосрался.",
    "Алло, живые есть? А то тишина такая, будто Братишка Серый опять объясняет очевидное.",
    "Вы чего притихли, культурные стали? Братишка Серый уже плачет: без вашего срача он чувствует себя умным.",
    "Хватит молчать, чат. Братишка Серый от скуки начал спорить с дверью и проигрывает.",
    "Тишина подозрительная. Где мат, где срач, где очередной Серегин мысленный проеб?",
    "Чат, просыпайся. Братишка Серый уже третий раз за час наступил на одну и ту же мысль.",
    "Ну и хули тут кладбище? Напишите что-нибудь, пока Братишка Серый не объявил себя главным интеллектуалом.",
    "Проверка связи: кто живой, тот матерится. Братишка Серый, конечно, не считается, он завис на загрузке мозга.",
    "Слишком тихо. Где-то Братишка Серый решил, что это из-за его авторитета. Нельзя такое допускать.",
    "Братишка Серый опять занял 'до завтра'. Завтра, как обычно, уехало нахуй.",
    "Серый бухнул, занял, забыл, соврал и назвал это жизненной стратегией. Чат, вы это терпеть будете?",
]

SERIY_ATTACK_REPLIES = [
    "Попадание по Серому засчитано. +{bonus} бонусных очков за точный удар по его тупому биосу.",
    "Братишка Серый услышал это, хотел ответить, но опять занял мысль и не вернул. +{bonus} бонус.",
    "За хуесос Серого начислен бонус. Он попытался обидеться, но перепутал достоинство с долгом. +{bonus}.",
    "О, пошла охота на Серого. +{bonus} очков за попадание в алко-должника первой категории.",
    "Серый получил моральный подзатыльник. Где-то Кристина уже считает, сколько с него еще можно снять. +{bonus}.",
    "Ты сейчас так точно описал Серого, что он сам себе должен стал. +{bonus} бонусных.",
    "Серый опять в минусе: по деньгам, по мозгам и по репутации. +{bonus}.",
]

SERIY_SUPERCOMBO_REPLIES = [
    (
        "СУПЕРКОМБО ПО СЕРОМУ.\n\n"
        "Ты собрал полный набор: тупость, бухло, долги и пиздеж. "
        "Братишка Серый официально уходит в режим 'я завтра все объясню'."
    ),
    (
        "Критический удар по Серому.\n\n"
        "Он хотел оправдаться, но Кристина уже забрала телефон, "
        "Бэлла забрала последние деньги, а дама из Наринэ забрала остатки достоинства."
    ),
]

EXCUSES = [
    "Я перевел, просто банк тупит.",
    "Брат, завтра железно.",
    "Я не бухал, я дегустировал.",
    "Это не долг, это инвестиция в дружбу.",
    "Я бы отдал, но бывшая опять вынесла бюджет.",
    "Карта просто в бане, ща разберусь.",
    "Деньги морально устали и не дошли.",
    "Я уже почти отправил, но приложение задумалось о жизни.",
]

LORE_FACTS = [
    "Братишка Серый однажды занял у будущего себя и не отдал даже ему.",
    "Серый говорит 'я все контролирую' ровно за 12 секунд до очередного проеба.",
    "Бывшие Серого открыли общий чат, чтобы синхронизировать финансовый ущерб.",
    "Серый бухнул так, что его отмазки начали жить отдельно.",
    "Кристина считает Серого не бывшим, а подпиской на хаос.",
    "Бэлла однажды попросила у Серого 'на такси' и уехала в легенду.",
    "Дама из Наринэ видела Серого трезвым. Никто ей не поверил.",
]

LOAN_REASONS = [
    "срочно надо закрыть финансовую дыру после 'одного пива'",
    "на такси до здравого смысла, но водитель уже сомневается",
    "на пиво, но Серый клянется, что это инвестиция",
    "на подарок бывшей, чтобы она перестала орать хотя бы до вечера",
    "на закрытие долга, который он взял, чтобы закрыть прошлый долг",
    "на айфон, который он 'почти уже купил всем'",
    "на лечение похмельной гордости",
    "на срочный перевод Кристине 'чисто по-дружески'",
    "на Бэллу, такси, Наринэ и еще какую-то хуйню, которую он сам не понял",
    "на моральную компенсацию самому себе за то, что он Серый",
]

LOAN_BRAGS = [
    (
        "Братишка Серый передает: деньги ему уже нахуй не нужны.\n"
        "У него, оказывается, дохуя денег, все хорошо, он всем купил по айфону, пьет пиво и еще может тебя угостить.\n"
        "Долг, конечно, он не вернул, потому что 'это другое'."
    ),
    (
        "Серый внезапно разбогател.\n"
        "Говорит, что ваши копейки ему нахуй не упали, он уже всем заказал айфоны, просто курьер тупит.\n"
        "Пиво пьет, долг не помнит, уверенность как у миллиардера с чужими 500 рублями."
    ),
    (
        "Финансовый отчет Серого: 'Я никому не должен, это вы мне должны за мое присутствие'.\n"
        "Деньги ему больше не нужны, потому что он 'на мутках'.\n"
        "Мутки, судя по всему, опять оплатил кто-то из чата."
    ),
    (
        "Серый сообщает, что вопрос закрыт.\n"
        "Он богат, красив, пьет пиво и всем купил по айфону в параллельной реальности.\n"
        "Кто занял — тот, по версии Серого, просто участвовал в благотворительности."
    ),
]

SERIY_STUPIDITY = [
    (
        "Час тупости Серого.\n\n"
        "Братишка Серый бухнул 'чуть-чуть', изменил бывшей с другой бывшей, потом зачем-то катал обеих на Камри, "
        "а утром продал Камри 'чтобы закрыть вопрос'. Вопрос, конечно, остался, Камри ушла, Серый опять должен."
    ),
    (
        "Серый выдал новый бизнес-план.\n\n"
        "Сначала занять на пиво, потом сказать бывшей, что он 'на делах', потом прокатиться на Камри, "
        "потом продать Камри дешевле рынка и объяснить: 'я просто не хотел привязываться к железу'."
    ),
    (
        "Лор Серого обновлен.\n\n"
        "Он изменял бывшей с бывшей, пока третья бывшая ждала деньги за такси. "
        "Серый сказал, что это не измена, а 'сложная логистика чувств'. Камри в этот момент уже стояла на продаже."
    ),
    (
        "Братишка Серый опять победил здравый смысл.\n\n"
        "Напился, пообещал Кристине айфон, Бэлле поездку, даме из Наринэ возврат долга, "
        "а сам продал Камри и купил пиво. Финансовый гений, ебать."
    ),
    (
        "Серый объясняет измену:\n\n"
        "'Я никому не изменял, я просто был эмоционально в нескольких местах'. "
        "После этой фразы Камри сама захотела сняться с учета и уехать от него нахуй."
    ),
    (
        "Алко-сводка Серого.\n\n"
        "Вчера он пил с бывшей, сегодня с бывшей бывшей, завтра обещает быть нормальным. "
        "Камри продана, деньги пропиты, долг записан как 'непонятная жизненная ситуация'."
    ),
    (
        "Серый кинул бывшую так тупо, что даже его отмазка подала на увольнение.\n\n"
        "Сказал: 'я ща за пивом и обратно', вернулся без Камри, без денег, но с уверенностью, что он красавчик."
    ),
    (
        "Братишка Серый открыл школу отношений.\n\n"
        "Первый урок: как изменить бывшей с бывшей, занять у третьей, продать Камри и все равно сказать: "
        "'да вы просто не поняли мой уровень'."
    ),
    (
        "Серый снова на стиле.\n\n"
        "Бухой, в долгах, бывшие в ахуе, Камри в объявлении, а он говорит: 'я просто оптимизирую активы'. "
        "Активы оптимизировались в пиво."
    ),
    (
        "Минутка Серегиной экономики.\n\n"
        "Камри была, денег нет. Бывшая была, доверия нет. Пиво было, памяти нет. "
        "Зато Серый уверен, что все идет по плану."
    ),
]

WELCOME_TEXT = (
    "Ну че, дебилы, бот зашел в чат.\n\n"
    "Я считаю мат, выдаю очки, ранги и кринж-награды из жизни Братишки Серого.\n"
    "Материшься красиво — получаешь очки.\n"
    "Навалил хуеву телегу — ловишь ранг, бывшую Серого или семейный пиздец.\n"
    "Хуесосишь Серого по делу — получаешь бонусные очки.\n"
    "Чат затих — я сам вкину, чтобы вы не уснули нахуй.\n\n"
    "Команды:\n"
    "/rank — твой ранг\n"
    "/top — топ токсиков\n"
    "/seriy_top — топ засаживателей Серого\n"
    "/shop — магазин приколов\n"
    "/buy код — купить прикол\n"
    "/exes — бывшие Серого\n"
    "/family — дети, ЗАГСы, алименты\n"
    "/debt — долги Серого\n"
    "/excuse — тупая отмазка Серого\n"
    "/lore — факт из жизни Серого\n"
    "/sergey_on — включить автоподъебы\n"
    "/sergey_off — выключить\n"
    "/sergey_ping — пнуть чат сразу\n"
    "/loan_ping — запустить займ Серого с кнопками\n"
    "/stupid_ping — выдать тупость Серого сразу"
)


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
            seriy_hits INTEGER NOT NULL DEFAULT 0,
            ex_events INTEGER NOT NULL DEFAULT 0,
            meme_children INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
        """
    )
    for column in ("seriy_hits", "ex_events", "meme_children"):
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
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
            last_roast_at INTEGER NOT NULL DEFAULT 0,
            next_roast_at INTEGER NOT NULL DEFAULT 0,
            next_loan_at INTEGER NOT NULL DEFAULT 0,
            next_stupidity_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for column in ("next_roast_at", "next_loan_at", "next_stupidity_at"):
        try:
            conn.execute(f"ALTER TABLE chat_settings ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ex_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            ex_name TEXT NOT NULL,
            event_text TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seriy_stats (
            chat_id INTEGER PRIMARY KEY,
            debt INTEGER NOT NULL DEFAULT 0,
            humiliation_count INTEGER NOT NULL DEFAULT 0,
            excuse_count INTEGER NOT NULL DEFAULT 0,
            borrowed_total INTEGER NOT NULL DEFAULT 0,
            loan_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for column in ("borrowed_total", "loan_count"):
        try:
            conn.execute(f"ALTER TABLE seriy_stats ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seriy_loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at INTEGER NOT NULL,
            due_at INTEGER NOT NULL,
            resolved_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS loan_lenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(loan_id, user_id)
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


def seriy_bonus(text: str) -> tuple[int, str | None]:
    mentions_seriy = any(pattern.search(text) for pattern in SERIY_PATTERNS)
    if not mentions_seriy:
        return 0, None

    hits = sum(len(pattern.findall(text)) for pattern in SERIY_ATTACK_PATTERNS)
    if hits <= 0:
        return 0, None

    lowered = text.lower()
    has_brain = any(word in lowered for word in ("туп", "дебил", "долбо"))
    has_alcohol = any(word in lowered for word in ("бух", "алкаш"))
    has_debt = any(word in lowered for word in ("занял", "долж", "не отда"))

    if has_brain and has_alcohol and has_debt:
        return 15, random.choice(SERIY_SUPERCOMBO_REPLIES)
    if hits >= 3:
        return 10, random.choice(SERIY_ATTACK_REPLIES).format(bonus=10)
    return 7, random.choice(SERIY_ATTACK_REPLIES).format(bonus=7)


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


def top_seriy_users(conn: sqlite3.Connection, chat_id: int, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM users
        WHERE chat_id = ? AND seriy_hits > 0
        ORDER BY seriy_hits DESC, points DESC
        LIMIT ?
        """,
        (chat_id, limit),
    ).fetchall()


def random_roast_delay() -> int:
    min_seconds = AUTO_ROAST_MIN_HOURS * 60 * 60
    max_seconds = AUTO_ROAST_MAX_HOURS * 60 * 60
    return random.randint(min_seconds, max_seconds)


def random_loan_delay() -> int:
    min_seconds = LOAN_MIN_HOURS * 60 * 60
    max_seconds = LOAN_MAX_HOURS * 60 * 60
    return random.randint(min_seconds, max_seconds)


def now_in_day_window() -> bool:
    tz = timezone(timedelta(hours=DAY_UTC_OFFSET))
    hour = datetime.now(tz).hour
    if DAY_START_HOUR <= DAY_END_HOUR:
        return DAY_START_HOUR <= hour < DAY_END_HOUR
    return hour >= DAY_START_HOUR or hour < DAY_END_HOUR


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
    now = int(time.time())
    next_roast_at = now + random_roast_delay() if enabled else 0
    next_loan_at = now + random_loan_delay() if enabled else 0
    next_stupidity_at = now + SERIY_STUPIDITY_MINUTES * 60 if enabled else 0
    conn.execute(
        """
        UPDATE chat_settings
        SET idle_roast_enabled = ?, next_roast_at = ?, next_loan_at = ?, next_stupidity_at = ?
        WHERE chat_id = ?
        """,
        (1 if enabled else 0, next_roast_at, next_loan_at, next_stupidity_at, message.chat.id),
    )
    conn.commit()


def idle_roast_chats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    now = int(time.time())
    if not now_in_day_window():
        return []
    return conn.execute(
        """
        SELECT * FROM chat_settings
        WHERE idle_roast_enabled = 1
          AND next_roast_at > 0
          AND next_roast_at <= ?
        """,
        (now,),
    ).fetchall()


def loan_chats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    now = int(time.time())
    if not now_in_day_window():
        return []
    return conn.execute(
        """
        SELECT * FROM chat_settings
        WHERE idle_roast_enabled = 1
          AND next_loan_at > 0
          AND next_loan_at <= ?
        """,
        (now,),
    ).fetchall()


def stupidity_chats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    now = int(time.time())
    if not now_in_day_window():
        return []
    return conn.execute(
        """
        SELECT * FROM chat_settings
        WHERE idle_roast_enabled = 1
          AND next_stupidity_at > 0
          AND next_stupidity_at <= ?
        """,
        (now,),
    ).fetchall()


def due_loans(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    now = int(time.time())
    return conn.execute(
        """
        SELECT * FROM seriy_loans
        WHERE status = 'active' AND due_at <= ?
        """,
        (now,),
    ).fetchall()


def add_seriy_hit(conn: sqlite3.Connection, chat_id: int, user_id: int, bonus: int) -> None:
    debt_delta = random.randint(300, 2500)
    conn.execute(
        """
        UPDATE users
        SET seriy_hits = seriy_hits + 1, points = points + ?
        WHERE chat_id = ? AND user_id = ?
        """,
        (bonus, chat_id, user_id),
    )
    conn.execute(
        """
        INSERT INTO seriy_stats(chat_id, debt, humiliation_count)
        VALUES (?, ?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET
            debt = debt + excluded.debt,
            humiliation_count = humiliation_count + 1
        """,
        (chat_id, debt_delta),
    )
    conn.commit()


def maybe_add_ex_reward(conn: sqlite3.Connection, chat_id: int, user_id: int, force: bool = False) -> str | None:
    if not force and random.random() > 0.45:
        return None
    ex_name = random.choice(EXES)
    event_text = random.choice(EX_EVENTS)
    meme_child = 1 if "родился" in event_text or "ребенок" in event_text else 0
    conn.execute(
        """
        INSERT INTO ex_rewards(chat_id, user_id, ex_name, event_text)
        VALUES (?, ?, ?, ?)
        """,
        (chat_id, user_id, ex_name, event_text),
    )
    conn.execute(
        """
        UPDATE users
        SET ex_events = ex_events + 1,
            meme_children = meme_children + ?
        WHERE chat_id = ? AND user_id = ?
        """,
        (meme_child, chat_id, user_id),
    )
    conn.commit()
    return f"Бонус-ивент: {ex_name}\n{event_text}"


def user_ex_summary(conn: sqlite3.Connection, chat_id: int, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ex_name, COUNT(*) AS count
        FROM ex_rewards
        WHERE chat_id = ? AND user_id = ?
        GROUP BY ex_name
        ORDER BY count DESC, ex_name
        """,
        (chat_id, user_id),
    ).fetchall()


def seriy_stats(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row:
    conn.execute(
        "INSERT OR IGNORE INTO seriy_stats(chat_id) VALUES (?)",
        (chat_id,),
    )
    conn.commit()
    return conn.execute("SELECT * FROM seriy_stats WHERE chat_id = ?", (chat_id,)).fetchone()


def create_loan(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row:
    now = int(time.time())
    amount = random.randrange(100, 5001, 100)
    reason = random.choice(LOAN_REASONS)
    due_at = now + random.randint(20 * 60, 30 * 60)
    conn.execute(
        """
        INSERT INTO seriy_loans(chat_id, amount, reason, created_at, due_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (chat_id, amount, reason, now, due_at),
    )
    loan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "UPDATE chat_settings SET next_loan_at = ? WHERE chat_id = ?",
        (now + random_loan_delay(), chat_id),
    )
    conn.commit()
    return conn.execute("SELECT * FROM seriy_loans WHERE id = ?", (loan_id,)).fetchone()


def loan_keyboard(loan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💸 Занять Серому", callback_data=f"lend:{loan_id}"),
                InlineKeyboardButton(text="🧾 Спросить долг", callback_data=f"ask:{loan_id}"),
            ]
        ]
    )


def loan_request_text(loan: sqlite3.Row) -> str:
    return (
        f"Братишка Серый просит занять {loan['amount']} ₽.\n\n"
        f"Причина: {loan['reason']}.\n\n"
        "Кто выручит финансового гения? Жмите кнопку, потом будете с него спрашивать эту хуйню."
    )


def loan_lenders(conn: sqlite3.Connection, loan_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM loan_lenders
        WHERE loan_id = ?
        ORDER BY created_at
        """,
        (loan_id,),
    ).fetchall()


def loan_by_id(conn: sqlite3.Connection, loan_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM seriy_loans WHERE id = ?", (loan_id,)).fetchone()


def add_lender(
    conn: sqlite3.Connection,
    loan: sqlite3.Row,
    user_id: int,
    full_name: str,
) -> bool:
    now = int(time.time())
    try:
        conn.execute(
            """
            INSERT INTO loan_lenders(loan_id, chat_id, user_id, full_name, amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (loan["id"], loan["chat_id"], user_id, full_name, loan["amount"], now),
        )
    except sqlite3.IntegrityError:
        return False
    conn.execute(
        """
        INSERT INTO users(chat_id, user_id, username, full_name, points, messages, toxic_hits)
        VALUES (?, ?, NULL, ?, 5, 0, 0)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            full_name = excluded.full_name,
            points = users.points + 5
        """,
        (loan["chat_id"], user_id, full_name),
    )
    conn.execute(
        """
        INSERT INTO seriy_stats(chat_id, debt, borrowed_total, loan_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET
            debt = debt + excluded.debt,
            borrowed_total = borrowed_total + excluded.borrowed_total,
            loan_count = loan_count + 1
        """,
        (loan["chat_id"], loan["amount"], loan["amount"]),
    )
    conn.commit()
    return True


def close_loan(conn: sqlite3.Connection, loan_id: int) -> None:
    now = int(time.time())
    conn.execute(
        "UPDATE seriy_loans SET status = 'closed', resolved_at = ? WHERE id = ?",
        (now, loan_id),
    )
    conn.commit()


async def send_loan_request(bot: Bot, chat_id: int) -> None:
    with connect() as conn:
        loan = create_loan(conn, chat_id)
    await bot.send_message(chat_id, loan_request_text(loan), reply_markup=loan_keyboard(loan["id"]))


async def send_loan_final(bot: Bot, loan: sqlite3.Row) -> None:
    with connect() as conn:
        lenders = loan_lenders(conn, loan["id"])
        close_loan(conn, loan["id"])

    if lenders:
        names = ", ".join(row["full_name"] for row in lenders)
        prefix = (
            f"Финал займа Серого на {loan['amount']} ₽.\n"
            f"Деньги заняли: {names}.\n\n"
        )
    else:
        prefix = (
            f"Финал займа Серого на {loan['amount']} ₽.\n"
            "Ему никто не занял. Он сказал, что вы все жмоты, хотя сам должен половине чата и одному бармену из Наринэ.\n\n"
        )
    await bot.send_message(loan["chat_id"], prefix + random.choice(LOAN_BRAGS))


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
    await message.answer(WELCOME_TEXT)


@dp.message(F.new_chat_members)
async def new_chat_members(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    if any(member.id == me.id for member in message.new_chat_members):
        await message.answer(WELCOME_TEXT)


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


@dp.message(Command("seriy_top"))
async def seriy_top_command(message: Message) -> None:
    with connect() as conn:
        rows = top_seriy_users(conn, message.chat.id)
    if not rows:
        await message.answer("Серого пока никто нормально не засадил. Позорная тишина.")
        return
    lines = ["Топ тех, кто лучше всех хуесосит Братишку Серого:"]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row['full_name']} — {row['seriy_hits']} попаданий по Серому")
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


@dp.message(Command("exes"))
async def exes_command(message: Message) -> None:
    if not message.from_user:
        return
    with connect() as conn:
        row = get_user(conn, message.chat.id, message.from_user.id)
        rewards = user_ex_summary(conn, message.chat.id, message.from_user.id)

    if not row or not rewards:
        await message.answer("У тебя пока нет бывших Серого. Матерись красивее, брачный пиздец сам себя не соберет.")
        return

    lines = [f"Бывшие Братишки Серого у {row['full_name']}:"]
    for reward in rewards:
        lines.append(f"{reward['ex_name']} — {reward['count']} раз")
    lines.append("")
    lines.append(f"Мемные дети хуевой телеги: {row['meme_children']}")
    lines.append(f"Уровень кринжа: {'промышленный' if row['ex_events'] >= 5 else 'домашний, но мерзкий'}")
    await message.answer("\n".join(lines))


@dp.message(Command("family"))
async def family_command(message: Message) -> None:
    if not message.from_user:
        return
    with connect() as conn:
        row = get_user(conn, message.chat.id, message.from_user.id)
    if not row:
        await message.answer("Семейного пиздеца пока нет. Серый даже тут успел ничего не оформить.")
        return
    status = "Жених хуевой телеги" if row["ex_events"] >= 3 else "Случайный гость кринжового ЗАГСа"
    await message.answer(
        f"Семейное дело {row['full_name']}:\n"
        f"Статус: {status}\n"
        f"Бывшие-ивенты: {row['ex_events']}\n"
        f"Мемные дети: {row['meme_children']}\n"
        "Алименты: моральные, бесконечные, как отмазки Серого."
    )


@dp.message(Command("debt"))
async def debt_command(message: Message) -> None:
    with connect() as conn:
        stats = seriy_stats(conn, message.chat.id)
    await message.answer(
        f"Долг Братишки Серого: {stats['debt']} виртуальных рублей.\n"
        f"Сколько раз Серого размазали: {stats['humiliation_count']}\n"
        f"Последняя отмазка: '{random.choice(EXCUSES)}'"
    )


@dp.message(Command("excuse"))
async def excuse_command(message: Message) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO seriy_stats(chat_id, excuse_count)
            VALUES (?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET excuse_count = excuse_count + 1
            """,
            (message.chat.id,),
        )
        conn.commit()
    await message.answer(f"Новая тупая отмазка Серого:\n'{random.choice(EXCUSES)}'")


@dp.message(Command("lore"))
async def lore_command(message: Message) -> None:
    await message.answer(random.choice(LORE_FACTS))


@dp.message(Command("sergey_on"))
async def sergey_on_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Эту кнопку хаоса может нажимать только админ чата.")
        return
    with connect() as conn:
        set_idle_roast(conn, message, True)
    await message.answer(
        f"Автоподъебы включены. Днем я буду вкидывать раз в {AUTO_ROAST_MIN_HOURS}-{AUTO_ROAST_MAX_HOURS} часов. "
        f"Плюс раз в {SERIY_STUPIDITY_MINUTES} минут Серый будет выдавать тупость про бухло, бывших и Камри."
    )


@dp.message(Command("sergey_off"))
async def sergey_off_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Выключать этот цирк может только админ чата.")
        return
    with connect() as conn:
        set_idle_roast(conn, message, False)
    await message.answer("Автоподъебы выключены. Братишка Серый временно выдохнул, зря конечно.")


@dp.message(Command("sergey_ping"))
async def sergey_ping_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Пинговать Братишку Серого может только админ чата.")
        return
    await message.answer(random.choice(IDLE_ROASTS))


@dp.message(Command("loan_ping"))
async def loan_ping_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Запускать финансовый цирк Серого может только админ чата.")
        return
    with connect() as conn:
        touch_chat(conn, message)
    await send_loan_request(bot, message.chat.id)


@dp.message(Command("stupid_ping"))
async def stupid_ping_command(message: Message, bot: Bot) -> None:
    if not await is_chat_admin(bot, message):
        await message.answer("Доставать Серегину тупость из архива может только админ чата.")
        return
    await message.answer(random.choice(SERIY_STUPIDITY))


@dp.callback_query(F.data.startswith("lend:"))
async def lend_callback(query: CallbackQuery) -> None:
    if not query.message or not query.from_user or not query.data:
        return
    loan_id = int(query.data.split(":", 1)[1])
    with connect() as conn:
        loan = loan_by_id(conn, loan_id)
        if not loan or loan["status"] != "active":
            await query.answer("Поздно, Серый уже переобулся.", show_alert=True)
            return
        ok = add_lender(conn, loan, query.from_user.id, query.from_user.full_name)
        row = get_user(conn, loan["chat_id"], query.from_user.id)

    if not ok:
        await query.answer("Ты уже занял Серому. Теперь молись, чтобы он вспомнил.", show_alert=True)
        return

    await query.answer("Серый записал тебя в список финансово доверчивых.", show_alert=False)
    await query.message.answer(
        f"{query.from_user.full_name} занял Братишке Серому {loan['amount']} ₽.\n"
        f"+5 очков за финансовую наивность | всего: {row['points']}\n"
        "Серый сказал: 'брат, я завтра железно', и это уже звучит как уголовная сказка."
    )


@dp.callback_query(F.data.startswith("ask:"))
async def ask_loan_callback(query: CallbackQuery) -> None:
    if not query.message or not query.data:
        return
    loan_id = int(query.data.split(":", 1)[1])
    with connect() as conn:
        loan = loan_by_id(conn, loan_id)
        if not loan:
            await query.answer("Этот долг исчез так же мутно, как Серые обещания.", show_alert=True)
            return
        lenders = loan_lenders(conn, loan_id)

    await query.answer("Серый уже придумывает отмазку.", show_alert=False)
    if lenders:
        names = ", ".join(row["full_name"] for row in lenders)
        text = (
            f"По займу Серого на {loan['amount']} ₽ уже попали: {names}.\n"
            f"Текущая отмазка: '{random.choice(EXCUSES)}'\n"
            "Спросить можно, вернуть почти нереально."
        )
    else:
        text = (
            f"Серому пока никто не занял {loan['amount']} ₽.\n"
            "Редкий момент, когда чат оказался умнее Серого."
        )
    await query.message.answer(text)


@dp.message(F.text)
async def score_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    with connect() as conn:
        touch_chat(conn, message)
    text = message.text or ""
    points = score_text(text)
    bonus_points, bonus_reply = seriy_bonus(text)
    if points <= 0:
        with connect() as conn:
            upsert_user(conn, message, 0)
            if bonus_points > 0 and message.from_user:
                add_seriy_hit(conn, message.chat.id, message.from_user.id, bonus_points)
                row = get_user(conn, message.chat.id, message.from_user.id)
                await message.reply(
                    f"{bonus_reply}\n"
                    f"+{bonus_points} бонусных очк. | всего: {row['points']} | ранг: {rank_for(row['points'])}"
                )
        return

    with connect() as conn:
        row = upsert_user(conn, message, points)
        ex_reward = None
        if message.from_user:
            if bonus_points > 0:
                add_seriy_hit(conn, message.chat.id, message.from_user.id, bonus_points)
                row = get_user(conn, message.chat.id, message.from_user.id)
            ex_reward = maybe_add_ex_reward(conn, message.chat.id, message.from_user.id, force=points >= 5)

    if SPICY_MODE:
        replies = COMBO_REPLIES if points >= 5 else SPICY_REPLIES
        reply = replies[row["toxic_hits"] % len(replies)]
        lines = [reply]
        if bonus_reply:
            lines.append(bonus_reply)
        if ex_reward:
            lines.append(ex_reward)
        lines.append(f"+{points + bonus_points} очк. | всего: {row['points']} | ранг: {rank_for(row['points'])}")
        await message.reply("\n\n".join(lines))


async def idle_roast_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(60)
        with connect() as conn:
            rows = idle_roast_chats(conn)
            loan_rows = loan_chats(conn)
            stupidity_rows = stupidity_chats(conn)
            due_loan_rows = due_loans(conn)
            now = int(time.time())
        for row in rows:
            try:
                await bot.send_message(row["chat_id"], random.choice(IDLE_ROASTS))
                next_roast_at = now + random_roast_delay()
                with connect() as conn:
                    conn.execute(
                        """
                        UPDATE chat_settings
                        SET last_roast_at = ?, next_roast_at = ?
                        WHERE chat_id = ?
                        """,
                        (now, next_roast_at, row["chat_id"]),
                    )
                    conn.commit()
            except Exception:
                pass
        for row in loan_rows:
            try:
                await send_loan_request(bot, row["chat_id"])
            except Exception:
                pass
        for row in stupidity_rows:
            try:
                await bot.send_message(row["chat_id"], random.choice(SERIY_STUPIDITY))
                next_stupidity_at = now + SERIY_STUPIDITY_MINUTES * 60
                with connect() as conn:
                    conn.execute(
                        """
                        UPDATE chat_settings
                        SET next_stupidity_at = ?
                        WHERE chat_id = ?
                        """,
                        (next_stupidity_at, row["chat_id"]),
                    )
                    conn.commit()
            except Exception:
                pass
        for loan in due_loan_rows:
            try:
                await send_loan_final(bot, loan)
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
