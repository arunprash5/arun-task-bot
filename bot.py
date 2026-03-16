import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler


TOKEN = os.getenv("BOT_TOKEN")

# ---------- DATABASE ----------
conn = sqlite3.connect("tasks.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    task_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

conn.commit()

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task", callback_data="add")],
        [
            InlineKeyboardButton("📅 Today", callback_data="today"),
            InlineKeyboardButton("📆 Month", callback_data="month"),
            InlineKeyboardButton("🗓 Year", callback_data="year"),
        ],
    ])

    await update.message.reply_text(
        "Welcome!\n\nChoose an option or type task directly:\n\n"
        "Example:\n"
        "24 Mar 2026 - Pay EB bill",
        reply_markup=keyboard
    )


# ---------- BUTTON HANDLER ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data

    if action == "add":

        await query.message.reply_text(
            "Send task like:\n\n24 Mar 2026 - Pay EB bill"
        )

    elif action == "today":

        await show_today(query.message, user_id)

    elif action == "month":

        await show_month(query.message, user_id)

    elif action == "year":

        await show_year(query.message, user_id)


# ---------- MESSAGE HANDLER ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.message.from_user.id

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )
    conn.commit()

    try:

        parts = user_text.split("-", 1)

        date_part = parts[0].strip()
        task_part = parts[1].strip()

        task_date = datetime.strptime(date_part, "%d %b %Y")

        cursor.execute(
            "INSERT INTO tasks (user_id, task, task_date) VALUES (?, ?, ?)",
            (
                user_id,
                task_part,
                task_date.strftime("%Y-%m-%d")
            )
        )

        conn.commit()

        await update.message.reply_text("Task saved ✅")

    except Exception:

        await update.message.reply_text(
            "Invalid format.\n\nExample:\n"
            "24 Mar 2026 - Pay EB bill"
        )


# ---------- TODAY ----------
async def show_today(message, user_id):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
        SELECT task FROM tasks
        WHERE user_id = ?
        AND task_date = ?
    """, (
        user_id,
        today.strftime("%Y-%m-%d")
    ))

    rows = cursor.fetchall()

    if not rows:

        await message.reply_text("No tasks today 🎉")
        return

    message_text = "Today's Tasks:\n\n"

    for (task,) in rows:
        message_text += f"• {task}\n"

    await message.reply_text(message_text)


# ---------- MONTH ----------
async def show_month(message, user_id):

    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    start = now.replace(day=1).date()
    end = (start + timedelta(days=31)).replace(day=1)

    cursor.execute("""
        SELECT task, task_date FROM tasks
        WHERE user_id = ?
        AND task_date BETWEEN ? AND ?
        ORDER BY task_date
    """, (
        user_id,
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d")
    ))

    rows = cursor.fetchall()

    if not rows:

        await message.reply_text("No tasks this month 🎉")
        return

    message_text = "This Month:\n\n"

    for task, date in rows:

        formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")

        message_text += f"{formatted} - {task}\n"

    await message.reply_text(message_text)


# ---------- YEAR ----------
async def show_year(message, user_id):

    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    start = now.replace(month=1, day=1).date()
    end = now.replace(month=12, day=31).date()

    cursor.execute("""
        SELECT task, task_date FROM tasks
        WHERE user_id = ?
        AND task_date BETWEEN ? AND ?
        ORDER BY task_date
    """, (
        user_id,
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d")
    ))

    rows = cursor.fetchall()

    if not rows:

        await message.reply_text("No tasks this year 🎉")
        return

    message_text = "This Year:\n\n"

    for task, date in rows:

        formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")

        message_text += f"{formatted} - {task}\n"

    await message.reply_text(message_text)


# ---------- WEEK COMMAND ----------
async def week_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    await send_upcoming_tasks(context.bot, user_id)


# ---------- UPCOMING TASKS ----------
async def send_upcoming_tasks(bot, user_id):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    end_date = today + timedelta(days=7)

    cursor.execute("""
        SELECT task, task_date FROM tasks
        WHERE user_id = ?
        AND task_date BETWEEN ? AND ?
        ORDER BY task_date ASC
    """, (
        user_id,
        today.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    rows = cursor.fetchall()

    if not rows:

        await bot.send_message(
            chat_id=user_id,
            text="No tasks in next 7 days 🎉"
        )
        return

    message = "🌅 Good morning!\n\nYour next 7 days tasks:\n\n"

    for task, date in rows:

        formatted_date = datetime.strptime(
            date, "%Y-%m-%d"
        ).strftime("%d %b")

        message += f"{formatted_date} - {task}\n"

    await bot.send_message(chat_id=user_id, text=message)


# ---------- DAILY JOB ----------
async def morning_reminder(context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (user_id,) in users:

        await send_upcoming_tasks(context.bot, user_id)


# ---------- START SCHEDULER ----------
async def post_init(application):

    scheduler = AsyncIOScheduler(
        timezone=ZoneInfo("Asia/Kolkata")
    )

    scheduler.add_job(
        morning_reminder,
        "cron",
        hour=7,
        minute=0,
        args=[application],
    )

    scheduler.start()


# ---------- APP ----------
app = (
    ApplicationBuilder()
    .token(TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))

app.add_handler(CallbackQueryHandler(button_handler))

app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
)

app.add_handler(CommandHandler("week", week_tasks))

print("Bot is running...")

app.run_polling(drop_pending_updates=True)
