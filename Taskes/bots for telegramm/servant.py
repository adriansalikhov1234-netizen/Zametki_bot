"""
Telegram "почтовый мост" бот.

Логика:
  Я (MY_USER_ID) -> личка боту -> бот пересылает текст в TARGET_CHAT_ID (от имени бота)
  ЛЮБОЕ сообщение в TARGET_CHAT_ID (не от самого бота) -> бот пересылает его мне в личку,
  подписывая автора его @username, например: "@абубандит : привет"

  /image -> следующее сообщение, которое я пришлю боту, должно быть картинкой.
            Если это картинка — она отправится в группу.
            Если это не картинка — бот сообщит об этом и отменит ожидание.

Требует python-telegram-bot >= 22 (асинхронный API) и python-dotenv.

ВАЖНО: чтобы бот видел ВСЕ обычные сообщения в группе, а не только реплаи на
свои сообщения и команды, нужно отключить Group Privacy у бота через
@BotFather -> /setprivacy -> Disable. Без этого Telegram вообще не присылает
боту обычные сообщения из группы, и пересылка тебе работать не будет.
"""

import logging
import os

from dotenv import load_dotenv, set_key
from telegram import BotCommand, ReplyParameters, Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --------------------------------------------------------------------------
# Настройка
# --------------------------------------------------------------------------

ENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
)
load_dotenv(ENV_PATH)

BOT_TOKEN = os.getenv("SERVANT_BOT_TOKEN")
MY_USER_ID = int(os.getenv("SERVANT_MY_USER_ID", "0"))
TARGET_CHAT_ID = int(os.getenv("SERVANT_TARGET_CHAT_ID", "0"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Бот однопользовательский (только MY_USER_ID может им управлять).
AWAITING_IMAGE = False
AWAITING_STICKER = False


def _is_owner(user_id: int) -> bool:
    return user_id == MY_USER_ID


def _target_set() -> bool:
    return TARGET_CHAT_ID != 0


def _display_name(user) -> str:
    """Формирует подпись автора: @username, если он есть, иначе имя + ID."""
    if user is None:
        return "Unknown"
    if user.username:
        return f"@{user.username}"
    return f"{user.full_name} (id {user.id})"


def _remember_group_message(
    context: ContextTypes.DEFAULT_TYPE, private_message_id: int, group_message_id: int
) -> None:
    """Сохраняет связь пересланного личного сообщения с исходным сообщением группы."""
    context.bot_data.setdefault("private_to_group_message_ids", {})[
        private_message_id
    ] = group_message_id


def _reply_parameters_for_group_message(
    message, context: ContextTypes.DEFAULT_TYPE
) -> ReplyParameters | None:
    if not message.reply_to_message:
        return None

    group_message_id = context.bot_data.get(
        "private_to_group_message_ids", {}
    ).get(message.reply_to_message.message_id)
    if group_message_id is None:
        return None

    return ReplyParameters(message_id=group_message_id)


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот-мост между тобой и группой.\n\n"
        "Напиши мне текст в личку — я перешлю его в целевую группу.\n"
        "Любое сообщение в группе (кроме моих собственных) я перешлю тебе.\n"
        "Если ответишь в личке на пересланное сообщение, мой ответ попадёт в группу "
        "как ответ на исходное сообщение.\n"
        "Команды /image и /sticker позволяют отправить в группу картинку или стикер.\n\n"
        "Команды: /help"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — краткая инструкция\n"
        "/id — показать твой user ID и ID текущего чата\n"
        "/send <текст> — отправить текст в целевую группу\n"
        "/image — следующее отправленное боту изображение уйдёт в группу\n"
        "/sticker — следующий отправленный боту стикер уйдёт в группу\n"
        "/seebefore <количество> — показать сообщения до запуска бота\n"
        "/setchat — сделать текущий чат целевой группой (только владелец)\n"
        "/help — это сообщение\n\n"
        "Обычный текст в личке (без команды) автоматически пересылается в группу.\n"
        "Любое сообщение в целевой группе автоматически пересылается тебе в личку "
        "с пометкой автора вида @username. Ответь в личке на такое сообщение, "
        "чтобы отправить ответ в группу в исходной ветке."
    )


async def cmd_seebefore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сообщает об ограничении Bot API для чтения истории чата."""
    user = update.effective_user
    if not _is_owner(user.id):
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /seebefore количество")
        return

    count = int(context.args[0])
    if count < 1:
        await update.message.reply_text("Количество сообщений должно быть больше нуля.")
        return

    await update.message.reply_text(
        "Невозможно получить историю чата через Bot API: боты не могут "
        "запрашивать сообщения, отправленные до запуска или до получения обновления. "
        "Для этой функции нужен клиент пользовательского аккаунта, например Telethon."
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Твой user ID: {user_id}\nID текущего чата: {chat_id}"
    )


async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_owner(user.id):
        return  # молча игнорируем чужих

    if not _target_set():
        await update.message.reply_text(
            "TARGET_CHAT_ID ещё не задан. Используй /setchat в нужной группе."
        )
        return

    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Использование: /send текст")
        return

    await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=text)
    await update.message.reply_text("Отправлено в группу.")


async def cmd_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включает режим ожидания: следующее сообщение должно быть картинкой."""
    global AWAITING_IMAGE, AWAITING_STICKER

    user = update.effective_user
    if not _is_owner(user.id):
        return  # молча игнорируем чужих

    if not _target_set():
        await update.message.reply_text(
            "TARGET_CHAT_ID ещё не задан. Используй /setchat в нужной группе."
        )
        return

    AWAITING_IMAGE = True
    AWAITING_STICKER = False
    await update.message.reply_text(
        "Хорошо, пришли картинку — я отправлю её в группу. "
        "Если пришлёшь не картинку, я сообщу об этом и отменю ожидание."
    )


async def cmd_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включает режим ожидания следующего стикера."""
    global AWAITING_IMAGE, AWAITING_STICKER

    user = update.effective_user
    if not _is_owner(user.id):
        return

    if not _target_set():
        await update.message.reply_text(
            "TARGET_CHAT_ID ещё не задан. Используй /setchat в нужной группе."
        )
        return

    AWAITING_IMAGE = False
    AWAITING_STICKER = True
    await update.message.reply_text(
        "Хорошо, пришли стикер — я отправлю его в группу. "
        "Если пришлёшь что-то другое, ожидание отменится."
    )


async def cmd_setchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global TARGET_CHAT_ID

    user = update.effective_user
    if not _is_owner(user.id):
        return  # молча игнорируем чужих

    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text(
            "Команду /setchat нужно вызывать внутри группы, которую хочешь назначить целевой."
        )
        return

    TARGET_CHAT_ID = chat.id
    # сохраняем в .env, чтобы значение осталось после перезапуска бота
    try:
        set_key(ENV_PATH, "SERVANT_TARGET_CHAT_ID", str(TARGET_CHAT_ID))
    except Exception:
        logger.exception("Не удалось записать TARGET_CHAT_ID в .env")

    await update.message.reply_text(f"Готово! TARGET_CHAT_ID установлен: {TARGET_CHAT_ID}")


# --------------------------------------------------------------------------
# Обычные сообщения (без команд)
# --------------------------------------------------------------------------

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Личные сообщения от владельца.

    Если активен режим ожидания картинки (/image) — обрабатываем как картинку
    (или сообщаем об ошибке). Иначе, если это обычный текст — пересылаем в группу.
    """
    global AWAITING_IMAGE, AWAITING_STICKER

    user = update.effective_user
    message = update.message

    if not _is_owner(user.id):
        return  # чужие сообщения в личку боту игнорируем

    if not _target_set():
        await message.reply_text(
            "TARGET_CHAT_ID ещё не задан. Используй /setchat в нужной группе."
        )
        return

    # --- режим ожидания картинки или стикера после команды ---
    if AWAITING_IMAGE or AWAITING_STICKER:
        awaiting_image = AWAITING_IMAGE
        AWAITING_IMAGE = False  # ожидание расходуется в любом случае
        AWAITING_STICKER = False

        if awaiting_image and message.photo:
            file_id = message.photo[-1].file_id  # самое большое разрешение
            await context.bot.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=file_id,
                caption=message.caption,
            )
            await message.reply_text("Картинка отправлена в группу.")
        elif not awaiting_image and message.sticker:
            await context.bot.send_sticker(
                chat_id=TARGET_CHAT_ID,
                sticker=message.sticker.file_id,
            )
            await message.reply_text("Стикер отправлен в группу.")
        else:
            expected = "изображение" if awaiting_image else "стикер"
            command = "/image" if awaiting_image else "/sticker"
            await message.reply_text(f"Это не {expected}. Ожидание отменено; отправь {command}, чтобы попробовать снова.")
        return

    # --- обычная пересылка текста, фото и стикеров ---
    reply_parameters = _reply_parameters_for_group_message(message, context)

    if message.text:
        await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=message.text,
            reply_parameters=reply_parameters,
        )
    elif message.sticker:
        await context.bot.send_sticker(
            chat_id=TARGET_CHAT_ID,
            sticker=message.sticker.file_id,
            reply_parameters=reply_parameters,
        )
    elif message.photo:
        await context.bot.copy_message(
            chat_id=TARGET_CHAT_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
            reply_parameters=reply_parameters,
        )


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сообщения из целевой группы (кроме сообщений самого бота) -> пересылаем владельцу,
    подписывая автора его @username (или именем, если username не задан).
    """
    message = update.message
    if message is None or message.chat_id != TARGET_CHAT_ID:
        return

    bot_user = await context.bot.get_me()

    # не пересылаем сообщения, отправленные самим ботом (защита от цикла)
    if message.from_user and message.from_user.id == bot_user.id:
        return

    if not _target_set() or not MY_USER_ID:
        return

    author = _display_name(message.from_user)

    is_reply_to_bot = bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_user.id
    )
    prefix = "↩️ " if is_reply_to_bot else ""
    attribution = f"{prefix}{author}"

    if message.photo:
        caption = f"{attribution} : {message.caption}" if message.caption else attribution
        sent_message = await context.bot.send_photo(
            chat_id=MY_USER_ID,
            photo=message.photo[-1].file_id,
            caption=caption,
        )
        _remember_group_message(context, sent_message.message_id, message.message_id)
        return

    if message.sticker:
        attribution_message = await context.bot.send_message(
            chat_id=MY_USER_ID, text=attribution
        )
        sent_message = await context.bot.send_sticker(
            chat_id=MY_USER_ID,
            sticker=message.sticker.file_id,
        )
        _remember_group_message(
            context, attribution_message.message_id, message.message_id
        )
        _remember_group_message(context, sent_message.message_id, message.message_id)
        return

    text = message.text or message.caption
    if not text:
        return

    sent_message = await context.bot.send_message(
        chat_id=MY_USER_ID,
        text=f"{attribution} : {text}",
    )
    _remember_group_message(context, sent_message.message_id, message.message_id)


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Запустить бота"),
            BotCommand("help", "Список команд"),
            BotCommand("id", "Показать ID"),
            BotCommand("send", "Отправить текст в группу"),
            BotCommand("image", "Отправить изображение в группу"),
            BotCommand("sticker", "Отправить стикер в группу"),
            BotCommand("seebefore", "Показать сообщения до запуска бота"),
            BotCommand("setchat", "Назначить текущую группу целевой"),
        ]
    )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("SERVANT_BOT_TOKEN не задан. Проверь файл .env")
    if not MY_USER_ID:
        raise SystemExit("SERVANT_MY_USER_ID не задан. Проверь файл .env")

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("send", cmd_send))
    application.add_handler(CommandHandler("image", cmd_image))
    application.add_handler(CommandHandler("sticker", cmd_sticker))
    application.add_handler(CommandHandler("seebefore", cmd_seebefore))
    application.add_handler(CommandHandler("setchat", cmd_setchat))

    # личные сообщения без команд -> в группу / обработка /image
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_private_message,
        )
    )

    # любые сообщения в группах (нужно отключить Group Privacy, см. README) -> пересылаем владельцу
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUP | filters.ChatType.SUPERGROUP,
            handle_group_message,
        )
    )

    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()