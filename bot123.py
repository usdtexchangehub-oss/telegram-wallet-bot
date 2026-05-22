# =========================
# TELEGRAM WALLET BOT
# SAFE VERSION
# =========================

import os
import sqlite3
import random
import csv
from datetime import datetime, date

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMINS = [5304912608]

# =========================
# DATABASE
# =========================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    price INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    user_id INTEGER,
    service TEXT,
    price INTEGER,
    status TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    utr TEXT PRIMARY KEY,
    user_id INTEGER,
    amount INTEGER,
    status TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    msg_id TEXT PRIMARY KEY,
    user_id INTEGER,
    msg TEXT,
    status TEXT,
    created_at TEXT
)
""")

conn.commit()

# =========================
# DEFAULT SERVICES
# =========================

services = [
    ("Swiggy", 10),
    ("Zomato", 10),
    ("Dominos", 10),
]

for s, p in services:
    cursor.execute(
        "INSERT OR IGNORE INTO services VALUES (?,?)",
        (s, p)
    )

conn.commit()

# =========================
# MENU
# =========================

menu = [
    ["💰 Add Balance", "🛒 Buy Service"],
    ["👛 Wallet", "📦 My Orders"],
    ["💳 Payments", "📩 Message Admin"],
]

# =========================
# HELPERS
# =========================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin(uid):
    return uid in ADMINS


def ensure_user(uid):
    cursor.execute(
        "INSERT OR IGNORE INTO users VALUES (?,0)",
        (uid,)
    )
    conn.commit()


def get_balance(uid):
    ensure_user(uid)

    row = cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()

    return row[0] if row else 0


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    ensure_user(uid)

    await update.message.reply_text(
        "👋 Welcome",
        reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True)
    )


# =========================
# WALLET
# =========================

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    bal = get_balance(uid)

    await update.message.reply_text(
        f"💰 Wallet Balance: ₹{bal}"
    )


# =========================
# ADD BALANCE
# =========================

async def add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton("₹10", callback_data="amt_10"),
            InlineKeyboardButton("₹20", callback_data="amt_20"),
        ],
        [
            InlineKeyboardButton("₹50", callback_data="amt_50"),
            InlineKeyboardButton("₹100", callback_data="amt_100"),
        ],
    ]

    await update.message.reply_photo(
        photo=open("qr.jpg", "rb"),
        caption="📲 Select amount → Pay → Send only UTR",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# BUY SERVICE
# =========================

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):

    rows = cursor.execute(
        "SELECT name, price FROM services"
    ).fetchall()

    buttons = []

    for name, price in rows:
        buttons.append([
            InlineKeyboardButton(
                f"{name} - ₹{price}",
                callback_data=f"buy_{name}"
            )
        ])

    await update.message.reply_text(
        "🛒 Select Service",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================
# MY ORDERS
# =========================

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    rows = cursor.execute("""
    SELECT order_id, service, price, status
    FROM orders
    WHERE user_id=?
    ORDER BY created_at DESC
    LIMIT 10
    """, (uid,)).fetchall()

    if not rows:
        await update.message.reply_text("📦 No orders.")
        return

    text = "📦 Your Orders\n\n"

    for oid, service, price, status in rows:
        text += (
            f"🧾 {oid}\n"
            f"Service: {service}\n"
            f"Price: ₹{price}\n"
            f"Status: {status}\n\n"
        )

    await update.message.reply_text(text)


# =========================
# PAYMENTS
# =========================

async def payment_history(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    rows = cursor.execute("""
    SELECT utr, amount, status
    FROM payments
    WHERE user_id=?
    ORDER BY created_at DESC
    LIMIT 10
    """, (uid,)).fetchall()

    if not rows:
        await update.message.reply_text("💳 No payments.")
        return

    text = "💳 Payments\n\n"

    for utr, amount, status in rows:
        text += (
            f"UTR: {utr}\n"
            f"Amount: ₹{amount}\n"
            f"Status: {status}\n\n"
        )

    await update.message.reply_text(text)


# =========================
# MESSAGE ADMIN
# =========================

async def message_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["state"] = "msg_admin"

    await update.message.reply_text(
        "📩 Send your message for admin."
    )


# =========================
# ADMIN PANEL
# =========================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    keyboard = [

        [InlineKeyboardButton(
            "➕ Add Balance",
            callback_data="admin_add_balance"
        )],

        [InlineKeyboardButton(
            "👥 Users + Balances",
            callback_data="admin_users"
        )],

        [InlineKeyboardButton(
            "📦 Orders",
            callback_data="admin_orders"
        )],

        [InlineKeyboardButton(
            "💸 Refund Order",
            callback_data="admin_refund"
        )],

        [InlineKeyboardButton(
            "📢 Broadcast",
            callback_data="admin_broadcast"
        )],

    ]

    await update.message.reply_text(
        "🛠 Admin Panel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# BUTTONS
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    data = query.data

    uid = query.from_user.id

    ensure_user(uid)

    # =========================
    # AMOUNT
    # =========================

    if data.startswith("amt_"):

        amount = int(data.split("_")[1])

        context.user_data["expected_amount"] = amount

        await query.message.reply_text(
            f"💳 You selected ₹{amount}\n\n"
            f"Send only UTR."
        )

        return

    # =========================
    # BUY
    # =========================

    if data.startswith("buy_"):

        service = data.replace("buy_", "")

        row = cursor.execute(
            "SELECT price FROM services WHERE name=?",
            (service,)
        ).fetchone()

        if not row:
            await query.message.reply_text(
                "❌ Service not found."
            )
            return

        price = row[0]

        bal = get_balance(uid)

        if bal < price:
            await query.message.reply_text(
                "❌ Low balance."
            )
            return

        order_id = "ORD" + str(
            random.randint(100000, 999999)
        )

        cursor.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=?",
            (price, uid)
        )

        cursor.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?)",
            (
                order_id,
                uid,
                service,
                price,
                "pending",
                now(),
            )
        )

        conn.commit()

        await query.message.reply_text(
            f"✅ {service} ordered.\n"
            f"🧾 Order ID: {order_id}\n"
            f"Status: Pending"
        )

        keyboard = [

            [InlineKeyboardButton(
                "📩 Send Message",
                callback_data=f"sendmsg_{uid}_{order_id}"
            )],

            [InlineKeyboardButton(
                "✅ Complete",
                callback_data=f"complete_{uid}_{order_id}"
            )],

            [InlineKeyboardButton(
                "❌ Refund",
                callback_data=f"refund_{uid}_{order_id}_{price}"
            )],

        ]

        for admin_id in ADMINS:

            await context.bot.send_message(
                admin_id,
                f"🛒 New Order\n\n"
                f"Order ID: {order_id}\n"
                f"User: {uid}\n"
                f"Service: {service}\n"
                f"Price: ₹{price}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        return

    # =========================
    # APPROVE PAYMENT
    # =========================

    if data.startswith("approve_"):

        if not is_admin(uid):
            return

        _, target_uid, amount, utr = data.split("_", 3)

        cursor.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (int(amount), int(target_uid))
        )

        cursor.execute(
            "UPDATE payments SET status='approved' WHERE utr=?",
            (utr,)
        )

        conn.commit()

        await context.bot.send_message(
            int(target_uid),
            f"✅ Payment Approved\n₹{amount} added."
        )

        await query.message.edit_text(
            f"✅ Approved\n"
            f"User: {target_uid}\n"
            f"Amount: ₹{amount}"
        )

        return

    # =========================
    # REJECT PAYMENT
    # =========================

    if data.startswith("reject_"):

        if not is_admin(uid):
            return

        _, target_uid, amount, utr = data.split("_", 3)

        cursor.execute(
            "UPDATE payments SET status='rejected' WHERE utr=?",
            (utr,)
        )

        conn.commit()

        await context.bot.send_message(
            int(target_uid),
            f"❌ Payment Rejected\nUTR: {utr}"
        )

        await query.message.edit_text(
            f"❌ Rejected\n"
            f"User: {target_uid}\n"
            f"Amount: ₹{amount}"
        )

        return

    # =========================
    # COMPLETE ORDER
    # =========================

    if data.startswith("complete_"):

        if not is_admin(uid):
            return

        _, target_uid, order_id = data.split("_")

        cursor.execute(
            "UPDATE orders SET status='completed' WHERE order_id=?",
            (order_id,)
        )

        conn.commit()

        await context.bot.send_message(
            int(target_uid),
            f"✅ Order Completed\nOrder ID: {order_id}"
        )

        await query.message.edit_text(
            f"✅ Order Completed\n{order_id}"
        )

        return

    # =========================
    # REFUND
    # =========================

    if data.startswith("refund_"):

        if not is_admin(uid):
            return

        _, target_uid, order_id, amount = data.split("_")

        cursor.execute(
            "UPDATE orders SET status='refunded' WHERE order_id=?",
            (order_id,)
        )

        cursor.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (int(amount), int(target_uid))
        )

        conn.commit()

        await context.bot.send_message(
            int(target_uid),
            f"💸 Refund Sent\n"
            f"Order ID: {order_id}\n"
            f"₹{amount} refunded."
        )

        await query.message.edit_text(
            f"💸 Refunded\n{order_id}"
        )

        return

    # =========================
    # SEND MESSAGE
    # =========================

    if data.startswith("sendmsg_"):

        if not is_admin(uid):
            return

        _, target_uid, order_id = data.split("_")

        context.user_data["state"] = "send_msg"
        context.user_data["target_uid"] = int(target_uid)
        context.user_data["order_id"] = order_id

        await query.message.reply_text(
            f"📩 Type message for user.\n"
            f"Order ID: {order_id}"
        )

        return

    # =========================
    # ADMIN ADD BALANCE
    # =========================

    if data == "admin_add_balance":

        context.user_data["state"] = "admin_add_balance"

        await query.message.reply_text(
            "Send:\n"
            "UserID | Amount\n\n"
            "Example:\n"
            "123456789 | 50"
        )

        return

    # =========================
    # ADMIN USERS
    # =========================

    if data == "admin_users":

        rows = cursor.execute("""
        SELECT user_id, balance
        FROM users
        ORDER BY user_id DESC
        LIMIT 50
        """).fetchall()

        text = "👥 Users\n\n"

        for u, b in rows:
            text += f"{u} → ₹{b}\n"

        await query.message.reply_text(text)

        return

    # =========================
    # ADMIN ORDERS
    # =========================

    if data == "admin_orders":

        rows = cursor.execute("""
        SELECT order_id, user_id, service, price, status
        FROM orders
        ORDER BY created_at DESC
        LIMIT 30
        """).fetchall()

        text = "📦 Orders\n\n"

        for oid, u, s, p, st in rows:

            text += (
                f"{oid}\n"
                f"User: {u}\n"
                f"{s} - ₹{p}\n"
                f"Status: {st}\n\n"
            )

        await query.message.reply_text(text)

        return

    # =========================
    # BROADCAST
    # =========================

    if data == "admin_broadcast":

        context.user_data["state"] = "broadcast"

        await query.message.reply_text(
            "📢 Send broadcast message."
        )

        return


# =========================
# TEXT HANDLER
# =========================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    ensure_user(uid)

    text = update.message.text.strip()

    state = context.user_data.get("state")

    # =========================
    # MESSAGE ADMIN
    # =========================

    if state == "msg_admin":

        msg_id = "MSG" + str(
            random.randint(100000, 999999)
        )

        cursor.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?)",
            (
                msg_id,
                uid,
                text,
                "open",
                now(),
            )
        )

        conn.commit()

        for admin_id in ADMINS:

            await context.bot.send_message(
                admin_id,
                f"📩 User Message\n\n"
                f"User: {uid}\n"
                f"Message: {text}"
            )

        await update.message.reply_text(
            "✅ Message sent to admin."
        )

        context.user_data.pop("state", None)

        return

    # =========================
    # ADMIN SEND USER MESSAGE
    # =========================

    if state == "send_msg":

        target_uid = context.user_data["target_uid"]

        order_id = context.user_data["order_id"]

        await context.bot.send_message(
            target_uid,
            f"📩 Admin Message\n"
            f"Order ID: {order_id}\n\n"
            f"{text}"
        )

        await update.message.reply_text(
            "✅ Message sent."
        )

        context.user_data.pop("state", None)

        return

    # =========================
    # ADMIN ADD BALANCE
    # =========================

    if state == "admin_add_balance":

        if not is_admin(uid):
            return

        try:

            target_uid, amount = text.split("|")

            target_uid = int(target_uid.strip())

            amount = int(amount.strip())

            ensure_user(target_uid)

            cursor.execute(
                "UPDATE users SET balance=balance+? WHERE user_id=?",
                (amount, target_uid)
            )

            conn.commit()

            await context.bot.send_message(
                target_uid,
                f"✅ Admin added ₹{amount}"
            )

            await update.message.reply_text(
                f"✅ ₹{amount} added to {target_uid}"
            )

        except:

            await update.message.reply_text(
                "❌ Wrong format."
            )

        context.user_data.pop("state", None)

        return

    # =========================
    # BROADCAST
    # =========================

    if state == "broadcast":

        if not is_admin(uid):
            return

        users = cursor.execute(
            "SELECT user_id FROM users"
        ).fetchall()

        sent = 0

        for row in users:

            try:

                await context.bot.send_message(
                    row[0],
                    text
                )

                sent += 1

            except:
                pass

        await update.message.reply_text(
            f"📢 Broadcast sent to {sent} users."
        )

        context.user_data.pop("state", None)

        return

    # =========================
    # PAYMENT UTR
    # =========================

    expected_amount = context.user_data.get(
        "expected_amount"
    )

    if expected_amount:

        utr = text

        old = cursor.execute(
            "SELECT utr FROM payments WHERE utr=?",
            (utr,)
        ).fetchone()

        if old:

            await update.message.reply_text(
                "❌ UTR already used."
            )

            return

        cursor.execute(
            "INSERT INTO payments VALUES (?,?,?,?,?)",
            (
                utr,
                uid,
                expected_amount,
                "pending",
                now(),
            )
        )

        conn.commit()

        keyboard = [[

            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"approve_{uid}_{expected_amount}_{utr}"
            ),

            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"reject_{uid}_{expected_amount}_{utr}"
            ),

        ]]

        for admin_id in ADMINS:

            await context.bot.send_message(
                admin_id,
                f"💳 Payment Request\n\n"
                f"User: {uid}\n"
                f"Amount: ₹{expected_amount}\n"
                f"UTR: {utr}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        await update.message.reply_text(
            "⏳ Payment submitted."
        )

        context.user_data.pop(
            "expected_amount",
            None
        )

        return


# =========================
# PHOTO
# =========================

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    for admin_id in ADMINS:

        await context.bot.send_photo(
            admin_id,
            update.message.photo[-1].file_id,
            caption=f"🧾 Screenshot from {uid}"
        )

    await update.message.reply_text(
        "✅ Screenshot sent.\nNow send UTR."
    )


# =========================
# APP
# =========================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(MessageHandler(
    filters.Regex("^💰 Add Balance$"),
    add_balance
))

app.add_handler(MessageHandler(
    filters.Regex("^🛒 Buy Service$"),
    buy
))

app.add_handler(MessageHandler(
    filters.Regex("^👛 Wallet$"),
    wallet
))

app.add_handler(MessageHandler(
    filters.Regex("^📦 My Orders$"),
    my_orders
))

app.add_handler(MessageHandler(
    filters.Regex("^💳 Payments$"),
    payment_history
))

app.add_handler(MessageHandler(
    filters.Regex("^📩 Message Admin$"),
    message_admin
))

app.add_handler(CallbackQueryHandler(buttons))

app.add_handler(MessageHandler(
    filters.PHOTO,
    photo_handler
))

app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    text_handler
))

print("Bot running...")

app.run_polling()
