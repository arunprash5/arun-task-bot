import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

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

conn.commit()


# ---------- START MENU ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task", callback_data="add_task")],
        [InlineKeyboardButton("📅 This Week", callback_data="week_tasks")],
        [InlineKeyboardButton("📋 Today", callback_data="today_tasks")]
    ])

    await update.message.reply_text(
        "Task Manager\n\nChoose an option:",
        reply_markup=keyboard
    )


# ---------- BUTTON MENU ----------
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data


    if data == "add_task":

        context.user_data["adding_task"] = True

        await query.message.reply_text(
            "Send me the task description"
        )


    elif data == "week_tasks":

        await show_week_tasks(query.message, context)


    elif data == "today_tasks":

        await show_today_tasks(query.message, context)


# ---------- RECEIVE TASK TEXT ----------
async def receive_task(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("adding_task"):
        return

    task = update.message.text

    context.user_data["task_text"] = task
    context.user_data["adding_task"] = False

    calendar, step = DetailedTelegramCalendar().build()

    await update.message.reply_text(
        "Select task date",
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


# ---------- TODAY TASKS ----------
async def show_today_tasks(message, context):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
    SELECT task FROM tasks
    WHERE task_date = ?
    AND status='pending'
    """, (today.strftime("%Y-%m-%d"),))

    rows = cursor.fetchall()

    if not rows:

        await message.reply_text("No tasks today 🎉")
        return

    msg = "Today's Tasks\n\n"

    for (task,) in rows:
        msg += f"• {task}\n"

    await message.reply_text(msg)


# ---------- WEEK TASKS ----------
async def show_week_tasks(message, context):

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

        await message.reply_text("No tasks in next 7 days 🎉")
        return

    msg = "Next 7 Days\n\n"

    for task, date in rows:

        formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")
        msg += f"{formatted} - {task}\n"

    await message.reply_text(msg)


# ---------- EVENING CHECK ----------
async def check_today_tasks(context):

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    cursor.execute("""
    SELECT id, user_id, task
    FROM tasks
    WHERE task_date=?
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
            text=f"Did you complete?\n\n{task}",
            reply_markup=keyboard
        )


# ---------- COMPLETE BUTTON ----------
async def completion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

        await query.edit_message_text("Nice! Task completed ✅")


# ---------- SCHEDULER ----------
async def post_init(application):

    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Kolkata"))

    scheduler.add_job(
        check_today_tasks,
        "cron",
        hour=20,
        minute=0,
        args=[application]
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

app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(add_task|week_tasks|today_tasks)$"))
app.add_handler(CallbackQueryHandler(completion_handler, pattern="^done_"))
app.add_handler(CallbackQueryHandler(calendar_handler))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task))

print("Bot running...")
app.run_polling()
