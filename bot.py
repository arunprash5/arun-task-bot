import os
import sqlite3
import dateparser

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram_bot_calendar import DetailedTelegramCalendar


TOKEN = os.getenv("BOT_TOKEN")

# ---------- DATABASE ----------
conn = sqlite3.connect("tasks.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    task_date TEXT,
    status TEXT DEFAULT 'pending'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

conn.commit()

# ---------- PARSE DATE ----------
def extract_date(text):
    dt = dateparser.parse(
        text,
        settings={'PREFER_DATES_FROM': 'future'}
    )
    return dt

# ---------- ADD TASK ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    text = update.message.text

    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    lines = text.split("\n")

    saved = 0

    for line in lines:

        dt = extract_date(line)

        if not dt:
            continue

        task = line.replace(str(dt.date()), "").strip()

        cursor.execute(
            "INSERT INTO tasks (user_id, task, task_date) VALUES (?, ?, ?)",
            (user_id, task, dt.strftime("%Y-%m-%d"))
        )

        saved += 1

    conn.commit()

    if saved:
        await update.message.reply_text(f"{saved} task(s) saved ✅")
    else:
        await update.message.reply_text(
            "Couldn't detect a date.\nExample:\nPay EB bill tomorrow"
        )

# ---------- WEEK VIEW ----------
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
        AND status='pending'
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

    message = "🌅 Next 7 days tasks:\n\n"

    for task, date in rows:
        formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")
        message += f"{formatted} - {task}\n"

    await bot.send_message(chat_id=user_id, text=message)

# ---------- EVENING CHECK ----------
async def check_today_tasks(context):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
    SELECT id, user_id, task
    FROM tasks
    WHERE task_date = ?
    AND status='pending'
    """, (today.strftime("%Y-%m-%d"),))

    rows = cursor.fetchall()

    for task_id, user_id, task in rows:

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ YES", callback_data=f"done_{task_id}"),
                InlineKeyboardButton("❌ NO", callback_data=f"no_{task_id}")
            ]
        ])

        await context.bot.send_message(
            chat_id=user_id,
            text=f"Did you complete this task?\n\n{task}",
            reply_markup=keyboard
        )

# ---------- BUTTON HANDLER ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("done_"):

        task_id = data.split("_")[1]

        cursor.execute(
            "UPDATE tasks SET status='completed' WHERE id=?",
            (task_id,)
        )
        conn.commit()

        await query.edit_message_text("Great job! Task completed ✅")

    elif data.startswith("no_"):

        task_id = data.split("_")[1]

        context.user_data["reschedule_task"] = task_id

        calendar, step = DetailedTelegramCalendar().build()

        await query.message.reply_text(
            "Select new date",
            reply_markup=calendar
        )

# ---------- CALENDAR ----------
async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, key, step = DetailedTelegramCalendar().process(query.data)

    if not result and key:
        await query.edit_message_reply_markup(reply_markup=key)

    elif result:

        task_id = context.user_data.get("reschedule_task")

        cursor.execute(
            "UPDATE tasks SET task_date=? WHERE id=?",
            (result.strftime("%Y-%m-%d"), task_id)
        )

        conn.commit()

        await query.edit_message_text(
            f"Task rescheduled to {result.strftime('%d %b')} 👍"
        )

# ---------- MORNING REMINDER ----------
async def morning_reminder(context):

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (user_id,) in users:
        await send_upcoming_tasks(context.bot, user_id)

# ---------- START SCHEDULER ----------
async def post_init(application):

    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Kolkata"))

    scheduler.add_job(
        morning_reminder,
        "cron",
        hour=7,
        minute=0,
        args=[application]
    )

    scheduler.add_job(
        check_today_tasks,
        "cron",
        hour=20,
        minute=0,
        args=[application]
    )

    scheduler.start()

# ---------- BOT ----------
app = (
    ApplicationBuilder()
    .token(TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("week", week_tasks))
app.add_handler(CallbackQueryHandler(button_handler, pattern="^(done_|no_)"))
app.add_handler(CallbackQueryHandler(calendar_handler))

print("Bot running...")

app.run_polling()
