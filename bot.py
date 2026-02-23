import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

TOKEN = "8695529169:AAHoQeVxDMcbz4gGZDIs8TLOrRvDiqNBxuk"

# ---------- DATABASE SETUP ----------
conn = sqlite3.connect("tasks.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    task_date TEXT
)
""")
conn.commit()


# ---------- SAVE TASK ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.message.from_user.id

    try:
        # Expecting format: 24 Feb 2026 - Pay EB bill
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

    except:
        await update.message.reply_text(
            "Send in this format:\n\n24 Feb 2026 - Pay EB bill"
        )


# ---------- WEEK COMMAND ----------
async def week_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    today = datetime.today().date()
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
        await update.message.reply_text("No tasks in next 7 days 🎉")
        return

    message = "Your next 7 days tasks:\n\n"

    for task, date in rows:
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b")
        message += f"{formatted_date} - {task}\n"

    await update.message.reply_text(message)


# ---------- APP ----------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("week", week_tasks))

print("Bot is running...")
app.run_polling()
