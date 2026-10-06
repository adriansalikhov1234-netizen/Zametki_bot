import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))


BOT_TOKEN = os.getenv("BOT_TOKEN")
REMINDERS_FILE = Path(__file__).resolve().with_name("reminders.json")

WAITING_NOTE = 0

TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")

NOTE_RE = re.compile(
    r"^\s*1\s*\.\s*(?P<task>.+?)\s+2\s*\.\s*(?P<time>.+?)\s*$",
    re.DOTALL,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def load_storage() -> dict:
    try:
        with REMINDERS_FILE.open("r", encoding="utf-8") as storage_file:
            storage = json.load(storage_file)
    except FileNotFoundError:
        return {"profiles": {}, "reminders": []}
    except (json.JSONDecodeError, OSError):
        logger.exception("Не удалось прочитать файл данных")
        return {"profiles": {}, "reminders": []}

    if isinstance(storage, list):
        return {"profiles": {}, "reminders": storage}

    if not isinstance(storage, dict):
        logger.error("Файл данных должен содержать JSON-объект")
        return {"profiles": {}, "reminders": []}

    reminders = storage.get("reminders", [])
    profiles = storage.get("profiles", {})
    return {
        "profiles": profiles if isinstance(profiles, dict) else {},
        "reminders": reminders if isinstance(reminders, list) else [],
    }


def save_storage(storage: dict) -> None:
    temporary_file = REMINDERS_FILE.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as storage_file:
        json.dump(storage, storage_file, ensure_ascii=False, indent=2)
    temporary_file.replace(REMINDERS_FILE)


def load_reminders() -> list[dict]:
    return load_storage()["reminders"]


def save_reminders(reminders: list[dict]) -> None:
    storage = load_storage()
    storage["reminders"] = reminders
    save_storage(storage)


def get_profile(user_id: int) -> dict:
    return load_storage()["profiles"].get(str(user_id), {})


def save_profile(user_id: int, timezone_name: str) -> None:
    storage = load_storage()
    profile = storage["profiles"].setdefault(str(user_id), {})
    profile["timezone"] = timezone_name
    save_storage(storage)


async def restore_reminders(application: Application) -> None:
    if application.job_queue is None:
        logger.error("Планировщик напоминаний недоступен")
        return

    for reminder in load_reminders():
        try:
            remind_at = datetime.fromisoformat(reminder["remind_at"])
            delay = max(
                0,
                (remind_at - datetime.now(remind_at.tzinfo)).total_seconds(),
            )
            application.job_queue.run_once(
                send_reminder,
                when=delay,
                chat_id=reminder["chat_id"],
                data=reminder,
                name=f"note_{reminder['id']}",
            )
        except (KeyError, TypeError, ValueError):
            logger.exception("Пропущено некорректное напоминание: %r", reminder)


# ---------------------------------------------------------------------------
# Reply-кнопки
# ---------------------------------------------------------------------------

reply_keyboard = ReplyKeyboardMarkup(
    [
        ["1. О боте"],
        ["2. Как пользоваться"],
        ["3. Задать регион времени"],
        ["4. Профиль"],
    ],
    resize_keyboard=True,
)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот для заметок 📝\n\n"
        "Я могу создавать напоминания и отправлять их в указанное время.\n\n"
        "Выбери нужный пункт ниже:",
        reply_markup=reply_keyboard,
    )


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Доступные команды:\n\n"
        "/start — открыть главное меню\n"
        "/help — помощь\n"
        "/note — создать заметку\n"
        "/cancel — отменить создание заметки"
    )


# ---------------------------------------------------------------------------
# Обработка Reply-кнопок через if / elif / else
# ---------------------------------------------------------------------------

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text

    # 1. О боте
    if text == "1. О боте":
        await update.message.reply_text(
            "🤖 О боте\n\n"
            "Я — бот для напоминаний и заметок.\n"
            "Ты указываешь, что нужно сделать и во сколько это напомнить.\n\n"
            "После наступления указанного времени я отправлю тебе сообщение."
        )

    # 2. Как пользоваться
    elif text == "2. Как пользоваться":
        await update.message.reply_text(
            "📖 Как пользоваться\n\n"
            "1️⃣ Нажми /note.\n\n"
            "2️⃣ Заполни сообщение по шаблону:\n\n"
            "1. Купить молоко\n"
            "2. 18:30\n\n"
            "3️⃣ Бот сохранит заметку.\n\n"
            "4️⃣ В указанное время ты получишь напоминание ⏰\n\n"
            "Для отмены создания заметки используй /cancel."
        )

    # 3. Задать регион времени
    elif text == "3. Задать регион времени":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🇰🇿 Казахстанский",
                        callback_data="timezone_kazakhstan",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🇷🇺 Российский",
                        callback_data="timezone_russia",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🇬🇧 Великобритания",
                        callback_data="timezone_uk",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            "🌍 Выбери регион времени.\n\n"
            "🇰🇿 Казахстанский — время Казахстана.\n"
            "🇷🇺 Российский — время Москвы.\n"
            "🇬🇧 Великобритания — время Лондона.\n\n"
            "Регион будет использоваться для расчёта времени напоминаний.",
            reply_markup=keyboard,
        )

    # Профиль пользователя
    elif text == "4. Профиль":
        user_id = update.effective_user.id
        timezone_name = get_profile(user_id).get(
            "timezone",
            "Asia/Almaty",
        )
        user_reminders = [
            reminder
            for reminder in load_reminders()
            if reminder.get("user_id") == user_id
            or (
                "user_id" not in reminder
                and reminder.get("chat_id") == update.effective_chat.id
            )
        ]

        note_lines = []
        for reminder in sorted(
            user_reminders,
            key=lambda item: item.get("remind_at", ""),
        ):
            try:
                remind_at = datetime.fromisoformat(reminder["remind_at"])
                note_lines.append(
                    f"• {remind_at:%d.%m %H:%M} — {reminder['task']}"
                )
            except (KeyError, TypeError, ValueError):
                continue

        notes = "\n".join(note_lines) if note_lines else "Пока нет активных заметок."
        await update.message.reply_text(
            "👤 Профиль\n\n"
            f"🌍 Регион: {timezone_name}\n\n"
            f"📝 Напоминания:\n{notes}"
        )

    # Если пользователь отправил другой текст
    else:
        return


# ---------------------------------------------------------------------------
# Обработка Inline-кнопок выбора региона
# ---------------------------------------------------------------------------

async def timezone_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    if query.data == "timezone_kazakhstan":
        context.user_data["timezone"] = "Asia/Almaty"
        save_profile(update.effective_user.id, "Asia/Almaty")

        await query.edit_message_text(
            "🇰🇿 Казахстанский регион выбран.\n\n"
            "Часовой пояс: Asia/Almaty\n"
            "Теперь время напоминаний будет рассчитываться "
            "по времени Казахстана."
        )

    elif query.data == "timezone_russia":
        context.user_data["timezone"] = "Europe/Moscow"
        save_profile(update.effective_user.id, "Europe/Moscow")

        await query.edit_message_text(
            "🇷🇺 Российский регион выбран.\n\n"
            "Часовой пояс: Europe/Moscow\n"
            "Теперь время напоминаний будет рассчитываться "
            "по московскому времени."
        )

    elif query.data == "timezone_uk":
        context.user_data["timezone"] = "Europe/London"
        save_profile(update.effective_user.id, "Europe/London")

        await query.edit_message_text(
            "🇬🇧 Регион Великобритании выбран.\n\n"
            "Часовой пояс: Europe/London\n"
            "Время будет рассчитываться по времени Лондона."
        )


# ---------------------------------------------------------------------------
# /note
# ---------------------------------------------------------------------------

async def note_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    await update.message.reply_text(
        "📝 Что нужно сделать и во сколько?\n\n"
        "Заполни по шаблону:\n\n"
        "1. что нужно сделать\n"
        "2. время\n\n"
        "Например:\n"
        "1. Позвонить маме\n"
        "2. 18:30\n\n"
        "Для отмены — /cancel"
    )

    return WAITING_NOTE


# ---------------------------------------------------------------------------
# Получение заметки
# ---------------------------------------------------------------------------

async def note_receive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    text = update.message.text

    match = NOTE_RE.match(text)

    if not match:
        await update.message.reply_text(
            "❌ Не удалось разобрать сообщение.\n\n"
            "Используй такой формат:\n\n"
            "1. Купить молоко\n"
            "2. 12:00"
        )

        return ConversationHandler.END

    task = match.group("task").strip()
    time_str = match.group("time").strip()

    time_match = TIME_RE.fullmatch(time_str)

    if not time_match:
        await update.message.reply_text(
            f"❌ Время «{time_str}» указано неправильно.\n\n"
            "Используй формат ЧЧ:ММ.\n"
            "Например: 09:30 или 18:45."
        )

        return ConversationHandler.END

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    # Если пользователь не выбрал регион,
    # используем Казахстан по умолчанию
    timezone_name = context.user_data.get(
        "timezone",
        get_profile(update.effective_user.id).get("timezone", "Asia/Almaty"),
    )

    timezone = ZoneInfo(timezone_name)

    now = datetime.now(timezone)

    remind_at = now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

    if remind_at <= now:
        remind_at += timedelta(days=1)

    if context.job_queue is None:
        await update.message.reply_text(
            "⚠️ Планировщик напоминаний недоступен.\n\n"
            'Установи пакет:\n'
            'pip install "python-telegram-bot[job-queue]"'
        )

        return ConversationHandler.END

    reminder = {
        "id": f"{update.effective_chat.id}_{remind_at.timestamp()}",
        "chat_id": update.effective_chat.id,
        "user_id": update.effective_user.id,
        "task": task,
        "remind_at": remind_at.isoformat(),
    }
    reminders = load_reminders()
    reminders.append(reminder)
    save_reminders(reminders)

    context.job_queue.run_once(
        send_reminder,
        when=remind_at,
        chat_id=update.effective_chat.id,
        data=reminder,
        name=f"note_{reminder['id']}",
    )

    day = "сегодня" if remind_at.date() == now.date() else "завтра"

    await update.message.reply_text(
        "✅ Заметка сохранена!\n\n"
        f"📌 Дело: {task}\n"
        f"⏰ Напомню: {day} в {remind_at:%H:%M}\n"
        f"🌍 Регион: {timezone_name}"
    )

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Отправка напоминания
# ---------------------------------------------------------------------------

async def send_reminder(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    job = context.job

    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ Напоминание!\n\n{job.data['task']}",
    )

    reminders = load_reminders()
    save_reminders(
        [reminder for reminder in reminders if reminder.get("id") != job.data["id"]]
    )


# ---------------------------------------------------------------------------
# /cancel
# ---------------------------------------------------------------------------

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    await update.message.reply_text(
        "❌ Создание заметки отменено."
    )

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Запуск бота
# ---------------------------------------------------------------------------

def main() -> None:

    if not BOT_TOKEN:
        raise SystemExit(
            "❌ Не найден BOT_TOKEN в файле .env"
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(restore_reminders)
        .build()
    )

    # Диалог /note
    note_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("note", note_start)
        ],

        states={
            WAITING_NOTE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    note_receive,
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("note", note_start),
        ],
    )

    # Команды
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    # Inline-кнопки
    app.add_handler(
        CallbackQueryHandler(
            timezone_callback,
            pattern="^timezone_",
        )
    )

    # Reply-кнопки
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            menu_handler,
        )
    )

    # /note
    app.add_handler(note_conversation)

    logger.info("Бот запущен")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()