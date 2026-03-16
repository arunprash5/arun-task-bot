import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram_bot_calendar import DetailedTelegramCalendar


TOKEN = os.getenv("BOT_TOKEN")

# ---------------- DATABASE ----------------

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

conn.commit()

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task", callback_data="add")],
        [InlineKeyboardButton("📋 Today", callback_data="today")],
        [InlineKeyboardButton("📅 Week", callback_data="week")]
    ])

    await update.message.reply_text(
        "Task Manager\n\nChoose an option:",
        reply_markup=keyboard
    )


# ---------------- MENU ----------------

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "add":

        context.user_data["state"] = "adding"

        await query.message.reply_text("Send task description")

    elif query.data == "today":

        await show_today(query.message)

    elif query.data == "week":

        await show_week(query.message)


# ---------------- TEXT ROUTER ----------------

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):

    state = context.user_data.get("state")

    # ADD TASK
    if state == "adding":

        task = update.message.text

        context.user_data["task_text"] = task
        context.user_data["state"] = None

        calendar, step = DetailedTelegramCalendar(
            calendar_id=1,
            min_date=datetime.now(),
            locale="en"
        ).build()

        await update.message.reply_text(
            "Select task date",
            reply_markup=calendar
        )

        return

    # EDIT TASK
    if state == "editing":

        task_id = context.user_data["edit_id"]
        new_text = update.message.text

        cursor.execute(
            "UPDATE tasks SET task=? WHERE id=?",
            (new_text, task_id)
        )

        conn.commit()

        context.user_data["state"] = None

        await update.message.reply_text("Task updated ✏️")


# ---------------- CALENDAR ----------------

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, key, step = DetailedTelegramCalendar(calendar_id=1).process(query.data)

    if not result and key:

        await query.edit_message_reply_markup(reply_markup=key)

    elif result:

        task = context.user_data.get("task_text")
        user_id = query.from_user.id

        cursor.execute(
            "INSERT INTO tasks (user_id, task, task_date) VALUES (?, ?, ?)",
            (user_id, task, result.strftime("%Y-%m-%d"))
        )

        conn.commit()

        await query.edit_message_text(
            f"Task saved ✅\n\n{task}\n{result.strftime('%d %b %Y')}"
        )


# ---------------- TODAY ----------------

async def show_today(message):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
    SELECT id, task FROM tasks
    WHERE task_date=? AND status='pending'
    """, (today.strftime("%Y-%m-%d"),))

    rows = cursor.fetchall()

    if not rows:
        await message.reply_text("No tasks today 🎉")
        return

    for task_id, task in rows:

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{task_id}"),
                InlineKeyboardButton("✅ Done", callback_data=f"done_{task_id}")
            ]
        ])

        await message.reply_text(task, reply_markup=keyboard)


# ---------------- WEEK ----------------

async def show_week(message):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    end = today + timedelta(days=7)

    cursor.execute("""
    SELECT task, task_date FROM tasks
    WHERE task_date BETWEEN ? AND ?
    AND status='pending'
    ORDER BY task_date
    """, (
        today.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d")
    ))

    rows = cursor.fetchall()

    if not rows:
        await message.reply_text("No tasks next 7 days 🎉")
        return

    msg = "Next 7 Days\n\n"

    for task, date in rows:

        formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")
        msg += f"{formatted} - {task}\n"

    await message.reply_text(msg)


# ---------------- EDIT ----------------

async def edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    task_id = query.data.split("_")[1]

    context.user_data["state"] = "editing"
    context.user_data["edit_id"] = task_id

    await query.message.reply_text("Send new task text")


# ---------------- DONE ----------------

async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    task_id = query.data.split("_")[1]

    cursor.execute(
        "UPDATE tasks SET status='completed' WHERE id=?",
        (task_id,)
    )

    conn.commit()

    await query.edit_message_text("Task completed ✅")


# ---------------- REMINDER ----------------

async def reminder(context):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
    SELECT user_id, task FROM tasks
    WHERE task_date=? AND status='pending'
    """, (today.strftime("%Y-%m-%d"),))

    rows = cursor.fetchall()

    for user_id, task in rows:

        await context.bot.send_message(
            chat_id=user_id,
            text=f"Reminder 🔔\n\n{task}"
        )


# ---------------- EVENING CHECK ----------------

async def evening_check(context):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
    SELECT id, user_id, task FROM tasks
    WHERE task_date=? AND status='pending'
    """, (today.strftime("%Y-%m-%d"),))

    rows = cursor.fetchall()

    for task_id, user_id, task in rows:

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done", callback_data=f"done_{task_id}")]
        ])

        await context.bot.send_message(
            chat_id=user_id,
            text=f"Did you finish?\n\n{task}",
            reply_markup=keyboard
        )


# ---------------- SCHEDULER ----------------

async def post_init(application):

    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Kolkata"))

    scheduler.add_job(
        reminder,
        "cron",
        hour=18,
        minute=0,
        args=[application]
    )

    scheduler.add_job(
        evening_check,
        "cron",
        hour=21,
        minute=0,
        args=[application]
    )

    scheduler.start()


# ---------------- APP ----------------

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))

app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(add|today|week)$"))
app.add_handler(CallbackQueryHandler(edit_handler, pattern="^edit_"))
app.add_handler(CallbackQueryHandler(done_handler, pattern="^done_"))

app.add_handler(CallbackQueryHandler(calendar_handler, pattern="^calendar"))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

print("Bot running...")
app.run_polling()
