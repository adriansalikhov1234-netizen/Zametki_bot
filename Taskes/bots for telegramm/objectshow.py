import asyncio
import json
import logging
import os
import random
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
	Application,
	CommandHandler,
	ContextTypes,
	MessageHandler,
	filters,
)


ENV_PATH = os.path.abspath(
	os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
)
load_dotenv(ENV_PATH)

BOT2_TOKEN = os.getenv("BOT2_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
BUTTON_TEXT = "Случайное видео"
HASHTAGS = ("#обджектшоу", "#objectshow")

logging.basicConfig(
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
	level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _duration_seconds(duration: str) -> int:
	match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
	if match is None:
		return 0

	hours, minutes, seconds = (int(value or 0) for value in match.groups())
	return hours * 3600 + minutes * 60 + seconds


def find_videos() -> list[str]:
	"""Ищет свежие видео с одним из нужных хештегов через YouTube Data API."""
	video_ids: set[str] = set()

	for video_duration in ("medium", "long"):
		query = urlencode(
			{
				"key": YOUTUBE_API_KEY,
				"part": "snippet",
				"q": "|".join(HASHTAGS),
				"type": "video",
				"videoDuration": video_duration,
				"maxResults": 25,
			}
		)
		with urlopen(
			f"https://www.googleapis.com/youtube/v3/search?{query}", timeout=15
		) as response:
			results = json.load(response)

		for item in results.get("items", []):
			snippet = item.get("snippet", {})
			description = snippet.get("description", "")
			if not any(
				tag.casefold() in description.casefold() for tag in HASHTAGS
			):
				continue

			video_id = item.get("id", {}).get("videoId")
			if video_id:
				video_ids.add(video_id)

	if not video_ids:
		return []

	details_query = urlencode(
		{
			"key": YOUTUBE_API_KEY,
			"part": "contentDetails",
			"id": ",".join(video_ids),
		}
	)
	with urlopen(
		f"https://www.googleapis.com/youtube/v3/videos?{details_query}", timeout=15
	) as response:
		details = json.load(response)

	return [
		f"https://www.youtube.com/watch?v={item['id']}"
		for item in details.get("items", [])
		if _duration_seconds(item.get("contentDetails", {}).get("duration", "")) >= 60
	]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	keyboard = ReplyKeyboardMarkup(
		[[KeyboardButton(BUTTON_TEXT)]],
		resize_keyboard=True,
	)
	await update.effective_message.reply_text(
		"Нажми кнопку, и я пришлю случайное видео про объект-шоу.",
		reply_markup=keyboard,
	)


async def send_random_video(
	update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
	message = update.effective_message
	if message is None:
		return

	try:
		videos = await asyncio.to_thread(find_videos)
	except HTTPError as error:
		try:
			api_error = json.loads(error.read().decode("utf-8")).get("error", {})
		except (UnicodeDecodeError, json.JSONDecodeError):
			api_error = {}

		api_message = api_error.get("message", "")
		logger.error("Ошибка YouTube API HTTP %s: %s", error.code, api_message)
		await message.reply_text(
			f"Ошибка YouTube API ({error.code}): "
			f"{api_message or 'проверь ключ и настройки YouTube Data API v3.'}"
		)
		return
	except (URLError, TimeoutError, json.JSONDecodeError) as error:
		logger.exception("Не удалось выполнить поиск видео: %s", error)
		await message.reply_text(
			"Не получилось найти видео. Попробуй ещё раз немного позже."
		)
		return

	if not videos:
		await message.reply_text(
			"Пока не нашёл видео c хештегами #обджектшоу или #objectshow."
		)
		return

	await message.reply_text(random.choice(videos))


def main() -> None:
	if not BOT2_TOKEN:
		raise SystemExit("Добавь BOT2_TOKEN в корневой файл .env.")
	if not YOUTUBE_API_KEY:
		raise SystemExit("Добавь YOUTUBE_API_KEY в корневой файл .env.")

	application = Application.builder().token(BOT2_TOKEN).build()
	application.add_handler(CommandHandler("start", start))
	application.add_handler(
		MessageHandler(filters.TEXT & filters.Regex(f"^{BUTTON_TEXT}$"), send_random_video)
	)
	application.run_polling()


if __name__ == "__main__":
	main()
