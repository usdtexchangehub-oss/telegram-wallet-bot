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

BOT_TOKEN = os.getenv"8594253029:AAGaKE2kWGQIfMPM_Ja8YvZ-24wGlG8OQH8"
ADMINS = [5304912608]

NUMBER_PRICE = 10
LOW_STOCK_LIMIT = 5

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
CREATE TABLE IF NOT EXISTS number_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    user_id INTEGER,
    msg TEXT,
    status TEXT,
    created_at TEXT
)
""")

conn.commit()

default_services = [
    ("Swiggy", 10),
    ("Zomato", 10),
    ("Dominos", 10),
    ("Any Service", 15),
]

for name, price in default_services:
    cursor.execute("INSERT OR IGNORE INTO services VALUES (?, ?)", (name, price))

conn.commit()

menu = [
    ["💰 Add Balance", "🛒 Buy Service"],
    ["📱 Get Number", "👛 Wallet"],
    ["📦 My Orders", "💳 Payments"],
    ["🎫 Support"],
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin(user_id):
    return user_id in ADMINS


def ensure_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 0)", (user_id,))
    conn.commit()


def get_balance(user_id):
    ensure_user(user_id)
    row = cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user_id,)
    ).fetchone()
    return row[0] if row else 0


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    await update.message.reply_text(
        "👋 Welcome",
        reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True)
    )


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)

    await update.message.reply_text(f"💰 Wallet Balance: ₹{balance}")


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
        caption="📲 Select amount → Pay using QR → Send only UTR",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    services = cursor.execute(
        "SELECT name, price FROM services"
    ).fetchall()

    buttons = [
        [InlineKeyboardButton(f"{name} - ₹{price}", callback_data=f"buy_{name}")]
        for name, price in services
    ]

    await update.message.reply_text(
        "🛒 Select service:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)

    if balance < NUMBER_PRICE:
        await update.message.reply_text(
            f"❌ Low balance.\nNumber price: ₹{NUMBER_PRICE}"
        )
        return

    item = cursor.execute(
        "SELECT id, number FROM number_stock ORDER BY id ASC LIMIT 1"
    ).fetchone()

    if not item:
        await update.message.reply_text("❌ Number stock empty. Contact admin.")
        return

    number_id, number = item

    cursor.execute(
        "UPDATE users SET balance=balance-? WHERE user_id=?",
        (NUMBER_PRICE, user_id)
    )
    cursor.execute(
        "DELETE FROM number_stock WHERE id=?",
        (number_id,)
    )
    conn.commit()

    stock = cursor.execute(
        "SELECT COUNT(*) FROM number_stock"
    ).fetchone()[0]

    if stock < LOW_STOCK_LIMIT:
        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"⚠️ Low stock alert: only {stock} numbers left."
            )

    await update.message.reply_text(
        f"✅ ₹{NUMBER_PRICE} deducted.\n\n"
        f"📱 Your number:\n{number}\n\n"
        f"Now click 🛒 Buy Service."
    )


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    orders = cursor.execute(
        """
        SELECT order_id, service, price, status, created_at
        FROM orders
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (user_id,)
    ).fetchall()

    if not orders:
        await update.message.reply_text("📦 No orders yet.")
        return

    msg = "📦 Your Orders:\n\n"

    for order_id, service, price, status, created_at in orders:
        msg += (
            f"🧾 {order_id}\n"
            f"Service: {service}\n"
            f"Price: ₹{price}\n"
            f"Status: {status}\n"
            f"Date: {created_at}\n\n"
        )

    await update.message.reply_text(msg)


async def payment_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    payments = cursor.execute(
        """
        SELECT utr, amount, status, created_at
        FROM payments
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (user_id,)
    ).fetchall()

    if not payments:
        await update.message.reply_text("💳 No payments yet.")
        return

    msg = "💳 Your Payments:\n\n"

    for utr, amount, status, created_at in payments:
        msg += (
            f"UTR: {utr}\n"
            f"Amount: ₹{amount}\n"
            f"Status: {status}\n"
            f"Date: {created_at}\n\n"
        )

    await update.message.reply_text(msg)


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "support"

    await update.message.reply_text("🎫 Send your support message now.")


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Number", callback_data="admin_add_number"),
            InlineKeyboardButton("📦 View Stock", callback_data="admin_stock"),
        ],
        [
            InlineKeyboardButton("💳 View Payments", callback_data="admin_payments"),
            InlineKeyboardButton("👤 View Users", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton("➕ Add Service", callback_data="admin_add_service"),
            InlineKeyboardButton("❌ Remove Service", callback_data="admin_remove_service"),
        ],
        [
            InlineKeyboardButton("💰 Change Price", callback_data="admin_change_price"),
        ],
        [
            InlineKeyboardButton("🔍 Search Order", callback_data="admin_search_order"),
        ],
        [
            InlineKeyboardButton("📤 Export Orders", callback_data="admin_export_orders"),
            InlineKeyboardButton("📤 Export Payments", callback_data="admin_export_payments"),
        ],
        [
            InlineKeyboardButton("📊 Daily Report", callback_data="admin_daily_report"),
        ],
    ]

    await update.message.reply_text(
        "🛠 Admin Panel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    ensure_user(user_id)

    if data.startswith("amt_"):
        amount = int(data.split("_")[1])
        context.user_data["expected_amount"] = amount

        await query.message.reply_text(
            f"💳 You selected ₹{amount}\n\n"
            f"1. Pay this exact amount using QR\n"
            f"2. Send only UTR number"
        )
        return

    if data.startswith("buy_"):
        service = data.replace("buy_", "")

        row = cursor.execute(
            "SELECT price FROM services WHERE name=?",
            (service,)
        ).fetchone()

        if not row:
            await query.edit_message_text("❌ Service not found.")
            return

        price = row[0]
        balance = get_balance(user_id)

        if balance < price:
            await query.edit_message_text("❌ Low balance.")
            return

        order_id = "ORD" + str(random.randint(100000, 999999))

        cursor.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=?",
            (price, user_id)
        )
        cursor.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, user_id, service, price, "pending", now())
        )
        conn.commit()

        await query.edit_message_text(
            f"✅ {service} ordered.\n"
            f"🧾 Order ID: {order_id}\n"
            f"Status: Pending"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "📩 Send Message",
                    callback_data=f"sendmsg_{user_id}_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Complete Order",
                    callback_data=f"complete_{user_id}_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Cancel + Refund",
                    callback_data=f"cancel_{user_id}_{order_id}_{price}"
                )
            ],
        ]

        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"🛒 New Order\n\n"
                f"Order ID: {order_id}\n"
                f"User: {user_id}\n"
                f"Service: {service}\n"
                f"Price: ₹{price}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    if data.startswith("sendmsg_"):
        if not is_admin(user_id):
            return

        _, target_user_id, order_id = data.split("_")

        context.user_data["state"] = "send_order_message"
        context.user_data["send_to_user"] = int(target_user_id)
        context.user_data["send_order_id"] = order_id

        await query.message.reply_text(
            f"✍️ Type message to send to user.\n"
            f"Order ID: {order_id}"
        )
        return

    if data.startswith("requestsend_"):
        _, target_user_id, order_id = data.split("_")

        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"📩 Message Requested\n"
                f"User: {target_user_id}\n"
                f"Order ID: {order_id}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "✍️ Send Message",
                            callback_data=f"sendmsgadmin_{target_user_id}_{order_id}"
                        )
                    ]
                ])
            )

        await query.message.reply_text("⏳ Message requested. Please wait.")
        return

    if data.startswith("sendmsgadmin_"):
        if not is_admin(user_id):
            return

        _, target_user_id, order_id = data.split("_")

        context.user_data["state"] = "admin_send_msg"
        context.user_data["send_to_user"] = int(target_user_id)
        context.user_data["send_order_id"] = order_id

        await query.message.reply_text("✍️ Type message now:")
        return

    if data.startswith("ap_"):
        if not is_admin(user_id):
            return

        _, target_user_id, amount, utr = data.split("_", 3)

        cursor.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (int(amount), int(target_user_id))
        )
        cursor.execute(
            "UPDATE payments SET status='approved' WHERE utr=?",
            (utr,)
        )
        conn.commit()

        await context.bot.send_message(
            int(target_user_id),
            f"✅ Payment approved.\n₹{amount} added to wallet."
        )

        await query.edit_message_text(
            f"✅ Payment Approved\n"
            f"User: {target_user_id}\n"
            f"Amount: ₹{amount}\n"
            f"UTR: {utr}"
        )
        return

    if data.startswith("rej_"):
        if not is_admin(user_id):
            return

        _, target_user_id, amount, utr = data.split("_", 3)

        cursor.execute(
            "UPDATE payments SET status='rejected' WHERE utr=?",
            (utr,)
        )
        conn.commit()

        await context.bot.send_message(
            int(target_user_id),
            f"❌ Payment rejected.\nUTR: {utr}"
        )

        await query.edit_message_text(
            f"❌ Payment Rejected\n"
            f"User: {target_user_id}\n"
            f"Amount: ₹{amount}\n"
            f"UTR: {utr}"
        )
        return

    if data.startswith("complete_"):
        if not is_admin(user_id):
            return

        _, target_user_id, order_id = data.split("_")

        cursor.execute(
            "UPDATE orders SET status='completed' WHERE order_id=?",
            (order_id,)
        )
        conn.commit()

        await context.bot.send_message(
            int(target_user_id),
            f"✅ Your order is completed.\n🧾 Order ID: {order_id}"
        )

        await query.edit_message_text(
            f"✅ Order Completed\nOrder ID: {order_id}"
        )
        return

    if data.startswith("cancel_"):
        if not is_admin(user_id):
            return

        _, target_user_id, order_id, price = data.split("_")

        cursor.execute(
            "UPDATE orders SET status='cancelled_refunded' WHERE order_id=?",
            (order_id,)
        )
        cursor.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (int(price), int(target_user_id))
        )
        conn.commit()

        await context.bot.send_message(
            int(target_user_id),
            f"❌ Order cancelled.\n"
            f"🧾 Order ID: {order_id}\n"
            f"💰 ₹{price} refunded."
        )

        await query.edit_message_text(
            f"❌ Cancelled + Refunded\nOrder ID: {order_id}"
        )
        return

    if not is_admin(user_id):
        return

    if data == "admin_add_number":
        context.user_data["state"] = "admin_add_number"
        await query.message.reply_text("📱 Send the number to add.")
        return

    if data == "admin_stock":
        stock = cursor.execute(
            "SELECT COUNT(*) FROM number_stock"
        ).fetchone()[0]

        await query.message.reply_text(f"📦 Number Stock: {stock}")
        return

    if data == "admin_payments":
        total = cursor.execute(
            "SELECT COUNT(*) FROM payments"
        ).fetchone()[0]

        pending = cursor.execute(
            "SELECT COUNT(*) FROM payments WHERE status='pending'"
        ).fetchone()[0]

        approved = cursor.execute(
            "SELECT COUNT(*) FROM payments WHERE status='approved'"
        ).fetchone()[0]

        rejected = cursor.execute(
            "SELECT COUNT(*) FROM payments WHERE status='rejected'"
        ).fetchone()[0]

        await query.message.reply_text(
            f"💳 Payments\n"
            f"Total: {total}\n"
            f"Pending: {pending}\n"
            f"Approved: {approved}\n"
            f"Rejected: {rejected}"
        )
        return

    if data == "admin_users":
        users = cursor.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        await query.message.reply_text(f"👤 Total Users: {users}")
        return

    if data == "admin_broadcast":
        context.user_data["state"] = "admin_broadcast"
        await query.message.reply_text("📢 Send broadcast message.")
        return

    if data == "admin_add_service":
        context.user_data["state"] = "admin_add_service"
        await query.message.reply_text(
            "Send service like:\n"
            "Service Name | Price\n\n"
            "Example:\n"
            "Netflix | 20"
        )
        return

    if data == "admin_remove_service":
        context.user_data["state"] = "admin_remove_service"
        await query.message.reply_text("Send exact service name to remove.")
        return

    if data == "admin_change_price":
        context.user_data["state"] = "admin_change_price"
        await query.message.reply_text(
            "Send like:\n"
            "Service Name | New Price\n\n"
            "Example:\n"
            "Swiggy | 10"
        )
        return

    if data == "admin_search_order":
        context.user_data["state"] = "admin_search_order"
        await query.message.reply_text("Send Order ID.")
        return

    if data == "admin_export_orders":
        rows = cursor.execute("SELECT * FROM orders").fetchall()

        with open("orders.csv", "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["order_id", "user_id", "service", "price", "status", "created_at"])
            writer.writerows(rows)

        await query.message.reply_document(open("orders.csv", "rb"))
        return

    if data == "admin_export_payments":
        rows = cursor.execute("SELECT * FROM payments").fetchall()

        with open("payments.csv", "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["utr", "user_id", "amount", "status", "created_at"])
            writer.writerows(rows)

        await query.message.reply_document(open("payments.csv", "rb"))
        return

    if data == "admin_daily_report":
        today = date.today().strftime("%Y-%m-%d")

        approved = cursor.execute(
            """
            SELECT SUM(amount)
            FROM payments
            WHERE status='approved' AND created_at LIKE ?
            """,
            (today + "%",)
        ).fetchone()[0] or 0

        orders = cursor.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at LIKE ?
            """,
            (today + "%",)
        ).fetchone()[0]

        completed = cursor.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='completed' AND created_at LIKE ?
            """,
            (today + "%",)
        ).fetchone()[0]

        await query.message.reply_text(
            f"📊 Daily Report\n"
            f"Date: {today}\n"
            f"Payments: ₹{approved}\n"
            f"Orders: {orders}\n"
            f"Completed: {completed}"
        )
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    text = update.message.text.strip()
    state = context.user_data.get("state")

    if state == "support":
        ticket_id = "TCK" + str(random.randint(100000, 999999))

        cursor.execute(
            "INSERT INTO tickets VALUES (?, ?, ?, ?, ?)",
            (ticket_id, user_id, text, "open", now())
        )
        conn.commit()

        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"🎫 New Ticket\n"
                f"Ticket: {ticket_id}\n"
                f"User: {user_id}\n\n{text}"
            )

        await update.message.reply_text(
            f"✅ Support ticket sent.\nTicket ID: {ticket_id}"
        )

        context.user_data.pop("state", None)
        return

    if is_admin(user_id):
        if state == "send_order_message":
            target_user_id = context.user_data["send_to_user"]
            order_id = context.user_data["send_order_id"]

            keyboard = [[
                InlineKeyboardButton(
                    "📩 Send",
                    callback_data=f"requestsend_{target_user_id}_{order_id}"
                )
            ]]

            await context.bot.send_message(
                target_user_id,
                f"📩 Message from Admin\n"
                f"🧾 Order ID: {order_id}\n\n{text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            await update.message.reply_text("✅ Message sent to user.")

            context.user_data.pop("state", None)
            context.user_data.pop("send_to_user", None)
            context.user_data.pop("send_order_id", None)
            return

        if state == "admin_send_msg":
            target_user_id = context.user_data["send_to_user"]
            order_id = context.user_data["send_order_id"]

            await context.bot.send_message(
                target_user_id,
                f"📩 Message from Admin\n"
                f"🧾 Order ID: {order_id}\n\n{text}"
            )

            await update.message.reply_text("✅ Message sent to user.")

            context.user_data.pop("state", None)
            context.user_data.pop("send_to_user", None)
            context.user_data.pop("send_order_id", None)
            return

        if state == "admin_add_number":
            cursor.execute(
                "INSERT INTO number_stock (number) VALUES (?)",
                (text,)
            )
            conn.commit()

            await update.message.reply_text("✅ Number added.")
            context.user_data.pop("state", None)
            return

        if state == "admin_broadcast":
            users = cursor.execute(
                "SELECT user_id FROM users"
            ).fetchall()

            sent = 0

            for user in users:
                try:
                    await context.bot.send_message(user[0], text)
                    sent += 1
                except Exception:
                    pass

            await update.message.reply_text(
                f"📢 Broadcast sent to {sent} users."
            )

            context.user_data.pop("state", None)
            return

        if state == "admin_add_service":
            try:
                name, price = text.split("|")
                name = name.strip()
                price = int(price.strip())

                cursor.execute(
                    "INSERT OR REPLACE INTO services VALUES (?, ?)",
                    (name, price)
                )
                conn.commit()

                await update.message.reply_text(
                    f"✅ Service added/updated:\n{name} - ₹{price}"
                )

            except Exception:
                await update.message.reply_text(
                    "❌ Format wrong. Use:\nService Name | Price"
                )

            context.user_data.pop("state", None)
            return

        if state == "admin_remove_service":
            cursor.execute(
                "DELETE FROM services WHERE name=?",
                (text,)
            )
            conn.commit()

            await update.message.reply_text(
                f"❌ Service removed: {text}"
            )

            context.user_data.pop("state", None)
            return

        if state == "admin_change_price":
            try:
                name, price = text.split("|")
                name = name.strip()
                price = int(price.strip())

                cursor.execute(
                    "UPDATE services SET price=? WHERE name=?",
                    (price, name)
                )
                conn.commit()

                await update.message.reply_text(
                    f"💰 Price updated:\n{name} - ₹{price}"
                )

            except Exception:
                await update.message.reply_text(
                    "❌ Format wrong. Use:\nService Name | New Price"
                )

            context.user_data.pop("state", None)
            return

        if state == "admin_search_order":
            order = cursor.execute(
                "SELECT * FROM orders WHERE order_id=?",
                (text,)
            ).fetchone()

            if order:
                await update.message.reply_text(
                    f"🔍 Order Found\n"
                    f"Order ID: {order[0]}\n"
                    f"User: {order[1]}\n"
                    f"Service: {order[2]}\n"
                    f"Price: ₹{order[3]}\n"
                    f"Status: {order[4]}\n"
                    f"Date: {order[5]}"
                )
            else:
                await update.message.reply_text("❌ Order not found.")

            context.user_data.pop("state", None)
            return

    expected_amount = context.user_data.get("expected_amount")

    if expected_amount:
        utr = text

        if cursor.execute(
            "SELECT utr FROM payments WHERE utr=?",
            (utr,)
        ).fetchone():
            await update.message.reply_text(
                "❌ This UTR is already submitted."
            )
            return

        cursor.execute(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?)",
            (utr, user_id, expected_amount, "pending", now())
        )
        conn.commit()

        keyboard = [[
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"ap_{user_id}_{expected_amount}_{utr}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"rej_{user_id}_{expected_amount}_{utr}"
            )
        ]]

        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"💳 Payment Request\n"
                f"User: {user_id}\n"
                f"Amount: ₹{expected_amount}\n"
                f"UTR: {utr}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        await update.message.reply_text(
            "⏳ Payment submitted. Waiting for approval."
        )

        context.user_data.pop("expected_amount", None)
        return


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    for admin_id in ADMINS:
        await context.bot.send_photo(
            admin_id,
            update.message.photo[-1].file_id,
            caption=f"🧾 Payment screenshot from user {user_id}"
        )

    await update.message.reply_text(
        "✅ Screenshot sent to admin. Now send UTR."
    )


app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(MessageHandler(filters.Regex("^💰 Add Balance$|^Add Balance$"), add_balance))
app.add_handler(MessageHandler(filters.Regex("^🛒 Buy Service$|^Buy Service$"), buy))
app.add_handler(MessageHandler(filters.Regex("^📱 Get Number$|^Get Number$"), get_number))
app.add_handler(MessageHandler(filters.Regex("^👛 Wallet$|^Wallet$"), wallet))
app.add_handler(MessageHandler(filters.Regex("^📦 My Orders$|^My Orders$"), my_orders))
app.add_handler(MessageHandler(filters.Regex("^💳 Payments$|^Payments$"), payment_history))
app.add_handler(MessageHandler(filters.Regex("^🎫 Support$|^Support$"), support))

app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("Bot running...")
app.run_polling()