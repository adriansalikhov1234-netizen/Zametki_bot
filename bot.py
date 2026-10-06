import math
import os
import re
import random
import sqlite3
import subprocess
import sys
import time
from datetime import timedelta

requirements_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", requirements_file],
    check=True,
)

import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
from fish_images import FISH_IMAGE_URLS

load_dotenv()

# Настройка интентов (нужно для чтения содержимого сообщений)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
last_pie_feed: dict[int, float] = {}
FISH_POST_INTERVAL = 24 * 60 * 60
fish_commands_synced = False
RABBIT_IMAGE_URLS = (
    "https://upload.wikimedia.org/wikipedia/commons/4/4a/Albino_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/6/6b/Angora_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/d/d3/Black_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/f/fe/Black_Tan_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/c/cc/Brindle_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/a/a7/Bunny_in_a_small_zoo.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/6/67/Bunny_in_a_small_zoo_2.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/f/fa/Bunny_rabbit_at_Alligator_Bay%2C_Beauvoir%2C_France.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/2/22/Coconut_the_rabbit_01.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/d/d4/Coconut_the_rabbit_02.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/3/3a/Coconut_the_rabbit_03.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/4/44/Coconut_the_rabbit_04.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/e/e8/Coconut_the_rabbit_05.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/e/ef/Coconut_the_rabbit_06.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/b/bd/Coconut_the_rabbit_07.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/8f/Coconut_the_rabbit_10.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/d/d4/Coconut_the_rabbit_11.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/1/19/Coconut_the_rabbit_12.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/b/bf/Coconut_the_rabbit_13.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/0/09/Coconut_the_rabbit_14.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/83/Coconut_the_rabbit_15.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/86/Coconut_the_rabbit_16.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/b/b9/Coconut_the_rabbit_17.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/84/Coconut_the_rabbit_18.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/c/c3/Coconut_the_rabbit_22.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/1/1e/Coconut_the_rabbit_23.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/5/55/Dillute_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/c/c9/Dwarf_rabbit_on_a_leash.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/a/a6/Holly_the_rabbit_01.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/e/ea/Holly_the_rabbit_02.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/9/97/Holly_the_rabbit_03.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/e/e9/Holly_the_rabbit_04.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/3/39/Holly_the_rabbit_05.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/f/fc/Holly_the_rabbit_06.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/5/5e/Holly_the_rabbit_07.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/e/e2/Holly_the_rabbit_08.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/3/39/Lapin_blanc.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/82/Night_in_Luna_Park%2C_Coney_Island_%281905%29.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/0/09/Peaches_the_rabbit_02.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/d/d3/Peaches_the_rabbit_03.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/8f/Peaches_the_rabbit_04.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/1/17/Peaches_the_rabbit_05.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/9/92/Rabbit_24.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/4/49/Rabbit_bunny.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/0/00/Rabbit_den_hole_in_Parco_Alto_Milanese_-_Busto_Arsizio%2C_Lombardy%2C_Italy_-_2021-04-05.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/8e/Rabbit_in.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/a/ab/Rabbit_s.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/7/70/Red_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/2/29/Rex_Rabbit_Illustration.png",
    "https://upload.wikimedia.org/wikipedia/commons/2/2f/Wild_Rabbit_Illustration.png",
)
database = sqlite3.connect(os.path.join(os.path.dirname(__file__), "beshbarmak.db"))
database.execute(
    """
    CREATE TABLE IF NOT EXISTS beshbarmak_users (
        user_id INTEGER PRIMARY KEY,
        balance_tiyn INTEGER NOT NULL DEFAULT 0,
        beshbarmak_count INTEGER NOT NULL DEFAULT 0,
        last_cook_at REAL NOT NULL DEFAULT 0
    )
    """
)
database.execute(
    """
    CREATE TABLE IF NOT EXISTS rabbit_images (
        url TEXT PRIMARY KEY,
        used INTEGER NOT NULL DEFAULT 0
    )
    """
)
database.execute(
    """
    CREATE TABLE IF NOT EXISTS daily_fish_posts (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        channel_id INTEGER NOT NULL,
        next_post_at REAL NOT NULL
    )
    """
)
database.execute(
    """
    CREATE TABLE IF NOT EXISTS fish_command_users (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        added_by INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
database.commit()


@tasks.loop(seconds=60)
async def post_daily_fish_photo():
    schedule = database.execute(
        "SELECT channel_id, next_post_at FROM daily_fish_posts WHERE id = 1"
    ).fetchone()
    if schedule is None or time.time() < schedule[1]:
        return

    try:
        channel = bot.get_channel(schedule[0])
        if channel is None:
            channel = await bot.fetch_channel(schedule[0])
        embed = discord.Embed(title="Рыба дня")
        embed.set_image(url=random.choice(FISH_IMAGE_URLS))
        await channel.send(embed=embed)
    except discord.HTTPException as error:
        print(f"Не удалось отправить фото рыбы: {error}")
        return

    database.execute(
        "UPDATE daily_fish_posts SET next_post_at = ? WHERE id = 1",
        (time.time() + FISH_POST_INTERVAL,),
    )
    database.commit()


@bot.event
async def on_ready():
    global fish_commands_synced
    print(f"Бот запущен как {bot.user}")
    if not fish_commands_synced:
        try:
            await bot.tree.sync()
            fish_commands_synced = True
        except discord.HTTPException as error:
            print(f"Не удалось синхронизировать slash-команды: {error}")
    if not post_daily_fish_photo.is_running():
        post_daily_fish_photo.start()


@bot.tree.command(name="mute", description="Выдать участнику тайм-аут")
@discord.app_commands.guild_only()
@discord.app_commands.rename(member="участник", duration="время")
@discord.app_commands.describe(
    member="Участник, которого нужно замьютить",
    duration="Длительность: 30m, 2h или 1d (максимум 28d)",
)
async def mute_member(
    interaction: discord.Interaction, member: discord.Member, duration: str
):
    guild = interaction.guild
    if guild is None or interaction.user.id != guild.owner_id:
        await interaction.response.send_message(
            "Этой командой может пользоваться только создатель сервера.",
            ephemeral=True,
        )
        return

    match = re.fullmatch(r"([1-9]\d*)([smhdсмчд])", duration.casefold())
    if match is None:
        await interaction.response.send_message(
            "Укажи время в формате 30m, 2h или 1d.", ephemeral=True
        )
        return

    unit_seconds = {
        "s": 1,
        "с": 1,
        "m": 60,
        "м": 60,
        "h": 3600,
        "ч": 3600,
        "d": 86400,
        "д": 86400,
    }
    duration_seconds = int(match.group(1)) * unit_seconds[match.group(2)]
    if duration_seconds > 28 * 24 * 60 * 60:
        await interaction.response.send_message(
            "Максимальная длительность тайм-аута — 28 дней.", ephemeral=True
        )
        return

    try:
        await member.timeout(
            timedelta(seconds=duration_seconds),
            reason=f"Timeout by server owner {interaction.user}",
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Не удалось замьютить участника. Проверь, что у бота есть право «Модерировать участников» и его роль выше роли участника.",
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "Discord не смог применить тайм-аут. Попробуй ещё раз.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"{member.mention}, ты улетаешь в арбуз на {duration}."
    )


async def require_fish_admin(interaction: discord.Interaction) -> bool:
    if interaction.guild is not None and interaction.user.guild_permissions.administrator:
        return True

    await interaction.response.send_message(
        "Управлять списком рыб могут только администраторы.", ephemeral=True
    )
    return False


@bot.tree.command(name="fishallow", description="Разрешить пользователю команду рыб")
@discord.app_commands.guild_only()
@discord.app_commands.rename(user="пользователь")
@discord.app_commands.describe(user="Пользователь, которому нужно выдать доступ")
async def fish_allow_user(interaction: discord.Interaction, user: discord.Member):
    if not await require_fish_admin(interaction):
        return

    database.execute(
        "INSERT OR IGNORE INTO fish_command_users (guild_id, user_id, added_by) VALUES (?, ?, ?)",
        (interaction.guild_id, user.id, interaction.user.id),
    )
    database.commit()
    await interaction.response.send_message(
        f"{user.mention} может использовать команду рыб.", ephemeral=True
    )


@bot.tree.command(name="fishremove", description="Убрать пользователя из списка рыб")
@discord.app_commands.guild_only()
@discord.app_commands.rename(user="пользователь")
@discord.app_commands.describe(user="Пользователь, у которого нужно забрать доступ")
async def fish_remove_user(interaction: discord.Interaction, user: discord.Member):
    if not await require_fish_admin(interaction):
        return

    database.execute(
        "DELETE FROM fish_command_users WHERE guild_id = ? AND user_id = ?",
        (interaction.guild_id, user.id),
    )
    database.commit()
    await interaction.response.send_message(
        f"{user.mention} убран из списка пользователей команды рыб.",
        ephemeral=True,
    )


@bot.tree.command(name="fishlist", description="Показать список пользователей команды рыб")
@discord.app_commands.guild_only()
async def fish_list_users(interaction: discord.Interaction):
    if not await require_fish_admin(interaction):
        return

    users = database.execute(
        "SELECT user_id FROM fish_command_users WHERE guild_id = ? ORDER BY user_id",
        (interaction.guild_id,),
    ).fetchall()
    if not users:
        response = "Список пуст."
    else:
        response = "Разрешённые пользователи:\n" + "\n".join(
            f"<@{user_id}>" for (user_id,) in users
        )
    await interaction.response.send_message(response, ephemeral=True)


@bot.listen("on_message")
async def start_daily_fish_posts(message):
    if message.author.bot or message.guild is None:
        return

    action = " ".join(message.content.casefold().split())
    if action not in {"рыбы", "!рыбы"}:
        return
    is_admin = message.author.guild_permissions.administrator
    is_allowed = database.execute(
        "SELECT 1 FROM fish_command_users WHERE guild_id = ? AND user_id = ?",
        (message.guild.id, message.author.id),
    ).fetchone() is not None
    if not is_admin and not is_allowed:
        await message.reply(
            "У тебя нет доступа к команде рыб. Попроси администратора добавить тебя в список."
        )
        return

    database.execute(
        """
        INSERT INTO daily_fish_posts (id, channel_id, next_post_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            channel_id = excluded.channel_id,
            next_post_at = excluded.next_post_at
        """,
        (message.channel.id, time.time()),
    )
    database.commit()
    await message.reply("Ежедневная публикация рыб включена в этом канале.")


@bot.command(name="стопрыбы")
@commands.guild_only()
async def stop_daily_fish_posts(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.reply("Останавливать публикацию рыб может только администратор.")
        return

    database.execute("DELETE FROM daily_fish_posts WHERE id = 1")
    database.commit()
    await ctx.reply("Ежедневная публикация рыб остановлена.")


@bot.command(name="вась")
async def vasya(ctx):
    await ctx.send("а")


@bot.command(name="выключиться")
@commands.is_owner()
async def shutdown(ctx):
    await ctx.send("меня мама кушать позвала")
    await bot.close()


@bot.listen("on_message")
async def send_rabbit_photo(message):
    if message.author.bot or " ".join(message.content.casefold().split()) != "кролики":
        return

    for url in RABBIT_IMAGE_URLS:
        database.execute("INSERT OR IGNORE INTO rabbit_images (url) VALUES (?)", (url,))

    unused_urls = [
        url
        for url in RABBIT_IMAGE_URLS
        if database.execute(
            "SELECT used FROM rabbit_images WHERE url = ?", (url,)
        ).fetchone()[0] == 0
    ]
    if not unused_urls:
        for url in RABBIT_IMAGE_URLS:
            database.execute("UPDATE rabbit_images SET used = 0 WHERE url = ?", (url,))
        unused_urls = list(RABBIT_IMAGE_URLS)

    image_url = random.choice(unused_urls)
    database.execute("UPDATE rabbit_images SET used = 1 WHERE url = ?", (image_url,))
    database.commit()

    embed = discord.Embed(title="Кролики")
    embed.set_image(url=image_url)
    await message.reply(embed=embed)


@bot.listen("on_message")
async def feed_with_pie(message):
    parts = message.content.split()
    if len(parts) == 3 and parts[:2] == ["накормить", "пирогом"] and parts[2].isdigit():
        pie_count = int(parts[2])
        if pie_count > 99:
            await message.reply("вот это ты пулемёт,ты давай там не наглей")
            return

        current_time = time.monotonic()
        last_feed_time = last_pie_feed.get(message.author.id)
        if last_feed_time is not None and current_time - last_feed_time < 60:
            await message.reply("ты чё серунь, не так быстро, подожди минуту перед тем как накормить кого-то ещё.")
            return

        reference = message.reference
        if reference is None or reference.message_id is None:
            await message.reply("Ответьте на сообщение пользователя, которого хотите накормить.")
            return

        target_message = reference.resolved
        if not isinstance(target_message, discord.Message):
            try:
                target_message = await message.channel.fetch_message(reference.message_id)
            except discord.HTTPException:
                await message.reply("Не удалось найти сообщение пользователя, которого нужно накормить.")
                return

        if target_message.author.bot:
            await message.reply("Ответьте на сообщение пользователя, которого хотите накормить.")
            return

        last_pie_feed[message.author.id] = time.monotonic()
        await message.channel.send(
            f"{target_message.author.mention} накормлен пирогом x{pie_count} 💩"
        )


@bot.listen("on_message")
async def handle_beshbarmak(message):
    if message.author.bot:
        return

    action = " ".join(message.content.casefold().split())
    if action not in {"баланс", "приготовить бешбармак", "продать бешбармак"}:
        return

    user_id = message.author.id
    database.execute(
        "INSERT OR IGNORE INTO beshbarmak_users (user_id) VALUES (?)",
        (user_id,),
    )
    user = database.execute(
        """
        SELECT balance_tiyn, beshbarmak_count, last_cook_at
        FROM beshbarmak_users
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if action == "баланс":
        balance = f"{user[0] / 100:,.2f}".replace(",", " ").replace(".", ",")
        await message.reply(f"Твой баланс: {balance} ₸.")
        return

    if action == "приготовить бешбармак":
        current_time = time.time()
        cooldown = 180
        seconds_left = cooldown - (current_time - user[2])
        if seconds_left > 0:
            remaining = math.ceil(seconds_left)
            minutes, seconds = divmod(remaining, 60)
            await message.reply(
                f"Подожди ещё {minutes} мин. {seconds} сек. перед следующей готовкой."
            )
            return

        database.execute(
            """
            UPDATE beshbarmak_users
            SET beshbarmak_count = beshbarmak_count + 1, last_cook_at = ?
            WHERE user_id = ?
            """,
            (current_time, user_id),
        )
        database.commit()
        await message.reply(
            f"Бешбармак готов! В запасе: {user[1] + 1}. Приготовить ещё можно через 3 минуты."
        )
        return

    if user[1] == 0:
        await message.reply("У тебя нет бешбармака на продажу. Сначала приготовь его.")
        return

    reward_per_item_tiyn = random.randint(500_000, 1_000_000)
    if reward_per_item_tiyn % 100 == 0:
        reward_per_item_tiyn += 1 if reward_per_item_tiyn < 1_000_000 else -1
    reward_tiyn = reward_per_item_tiyn * user[1]

    database.execute(
        """
        UPDATE beshbarmak_users
        SET beshbarmak_count = 0,
            balance_tiyn = balance_tiyn + ?
        WHERE user_id = ?
        """,
        (reward_tiyn, user_id),
    )
    database.commit()
    balance_tiyn = user[0] + reward_tiyn
    reward = f"{reward_tiyn / 100:,.2f}".replace(",", " ").replace(".", ",")
    balance = f"{balance_tiyn / 100:,.2f}".replace(",", " ").replace(".", ",")
    await message.reply(
        f"Продано порций: {user[1]}. Выручка: {reward} ₸. Твой баланс: {balance} ₸."
    )


# Токен бота берём из .env, чтобы не хранить его в коде
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

if not TOKEN:
    raise SystemExit(
        "Ошибка: DISCORD_TOKEN не найден в файле .env. "
        "Добавь строку DISCORD_TOKEN=... в корень проекта."
    )

try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print(
        "Ошибка входа: токен неверный или устарел. "
        "Зайди на https://discord.com/developers/applications, открой своего бота, "
        "вкладка Bot -> нажми Reset Token и скопируй новый."
    )
except discord.errors.PrivilegedIntentsRequired:
    print(
        "Ошибка: не включён Message Content Intent. "
        "Зайди на https://discord.com/developers/applications, открой своего бота, "
        "вкладка Bot -> включи переключатель 'MESSAGE CONTENT INTENT' -> Save Changes."
    )