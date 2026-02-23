import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# TOKEN from Railway environment variable
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


# ---------- SAVE TASK ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.message.from_user.id

    # Save user so we know whom to send 7am reminders
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    try:
        # format: 24 Feb 2026 - Pay EB bill
        parts = user_text.split("-", 1)
        date_part = parts[0].strip()
        task_part = parts[1].strip()

        task_date = datetime.strptime(date_part, "%d %b %Y")

        cursor.execute(
            "INSERT INTO tasks (user_id, task, task_date) VALUES (?, ?, ?)",
            (user_id, task_part, task_date.strftime("%Y-%m-%d"))
        )
        conn.commit()

        await update.message.reply_text("Task saved ✅")

    except Exception:
        await update.message.reply_text(
            "Send in this format:\n\n24 Feb 2026 - Pay EB bill"
        )


# ---------- WEEK COMMAND ----------
async def week_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await send_upcoming_tasks(context.bot, user_id)


# ---------- CORE FUNCTION ----------
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
        await bot.send_message(chat_id=user_id, text="No tasks in next 7 days 🎉")
        return

    message = "🌅 Good morning!\n\nYour next 7 days tasks:\n\n"

    for task, date in rows:
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")
        message += f"{formatted_date} - {task}\n"

    await bot.send_message(chat_id=user_id, text=message)


# ---------- DAILY JOB ----------
async def morning_reminder(app):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (user_id,) in users:
        await send_upcoming_tasks(app.bot, user_id)


# ---------- SCHEDULER (IST TIMEZONE) ----------
scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Kolkata"))

def start_scheduler(app):
    # 7:00 AM IST every day
    scheduler.add_job(morning_reminder, "cron", hour=7, minute=0, args=[app])
    scheduler.start()


# ---------- APP ----------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("week", week_tasks))

start_scheduler(app)

print("Bot is running...")
app.run_polling()
