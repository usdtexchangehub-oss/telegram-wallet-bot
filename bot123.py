import os
import sqlite3
import random
import csv
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = [5304912608]

DB_PATH = os.getenv("DB_PATH", "bot.db")
LOW_STOCK_LIMIT = 3
REFERRAL_REWARD = 2

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# ---------------- HELPERS ----------------

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today():
    return date.today().strftime("%Y-%m-%d")

def is_admin(uid):
    return uid in ADMINS

def ensure_user(uid, ref_by=None):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance, banned, ref_by, created_at) VALUES (?,0,0,?,?)", (uid, ref_by, now()))
    conn.commit()

def get_balance(uid):
    ensure_user(uid)
    row = cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    return row[0] if row else 0

def is_banned(uid):
    ensure_user(uid)
    row = cursor.execute("SELECT banned FROM users WHERE user_id=?", (uid,)).fetchone()
    return bool(row and row[0] == 1)

def get_setting(key, default="0"):
    row = cursor.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))
    conn.commit()

def short(text, limit=3800):
    return text if len(text) <= limit else text[:limit] + "\n\n...cut..."

def add_order_log(order_id, actor_id, message):
    cursor.execute("INSERT INTO order_logs (order_id, actor_id, message, created_at) VALUES (?,?,?,?)", (order_id, actor_id, message, now()))
    conn.commit()

def clean_service_callback(name):
    return name.replace("_", " ")

# ---------------- DATABASE SAFE MIGRATION ----------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0,
    ref_by INTEGER,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    price INTEGER,
    category TEXT DEFAULT 'General',
    active INTEGER DEFAULT 1
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS service_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT,
    item TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS order_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    actor_id INTEGER,
    message TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS coupons (
    code TEXT PRIMARY KEY,
    discount INTEGER,
    uses_left INTEGER,
    active INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

# Add columns safely if old DB exists
for alter in [
    "ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN ref_by INTEGER",
    "ALTER TABLE users ADD COLUMN created_at TEXT",
    "ALTER TABLE services ADD COLUMN category TEXT DEFAULT 'General'",
    "ALTER TABLE services ADD COLUMN active INTEGER DEFAULT 1",
]:
    try:
        cursor.execute(alter)
    except Exception:
        pass

conn.commit()

default_services = [
    ("Swiggy", 10, "Food"),
    ("Zomato", 10, "Food"),
    ("Dominos", 10, "Food"),
    ("Any Service", 15, "Custom"),
]

for name, price, cat in default_services:
    cursor.execute("INSERT OR IGNORE INTO services (name, price, category, active) VALUES (?,?,?,1)", (name, price, cat))
conn.commit()

menu = [
    ["💰 Add Balance", "🛒 Buy Service"],
    ["👛 Wallet", "📦 My Orders"],
    ["💳 Payments", "📩 Message Admin"],
    ["🎟 Coupon", "👥 Referral"]
]

# ---------------- USER COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ref_by = None

    if context.args:
        try:
            ref_by = int(context.args[0])
            if ref_by == uid:
                ref_by = None
        except Exception:
            ref_by = None

    # Check if user is new BEFORE inserting
    existing = cursor.execute("SELECT user_id FROM users WHERE user_id=?", (uid,)).fetchone()

    ensure_user(uid, ref_by)

    # Referral reward: only once, only when a NEW user joins by referral link
    if ref_by and not existing:
        reward_key = f"ref_reward_{uid}"
        already_rewarded = cursor.execute("SELECT value FROM settings WHERE key=?", (reward_key,)).fetchone()

        if not already_rewarded:
            ensure_user(ref_by)
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (REFERRAL_REWARD, ref_by))
            cursor.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (reward_key, "1"))
            conn.commit()

            try:
                await context.bot.send_message(
                    ref_by,
                    f"🎉 Referral reward received!\n₹{REFERRAL_REWARD} added to your wallet."
                )
            except Exception:
                pass

    if get_setting("maintenance", "0") == "1" and not is_admin(uid):
        await update.message.reply_text("🛠 Bot is under maintenance. Please try later.")
        return

    await update.message.reply_text("👋 Welcome", reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True))

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    await update.message.reply_text(f"💰 Wallet Balance: ₹{get_balance(uid)}")

async def add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return

    keyboard = [
        [InlineKeyboardButton("₹10", callback_data="amt_10"), InlineKeyboardButton("₹20", callback_data="amt_20")],
        [InlineKeyboardButton("₹50", callback_data="amt_50"), InlineKeyboardButton("₹100", callback_data="amt_100")]
    ]
    try:
        await update.message.reply_photo(
            photo=open("qr.jpg", "rb"),
            caption="📲 Select amount → Pay using QR → Send only UTR",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except FileNotFoundError:
        await update.message.reply_text("QR image missing. Upload qr.jpg in same folder.")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if get_setting("maintenance", "0") == "1" and not is_admin(uid):
        await update.message.reply_text("🛠 Bot is under maintenance.")
        return

    rows = cursor.execute("SELECT DISTINCT category FROM services WHERE active=1 ORDER BY category").fetchall()
    if not rows:
        await update.message.reply_text("No services available.")
        return

    keyboard = [[InlineKeyboardButton(cat[0], callback_data=f"cat_{cat[0]}")] for cat in rows]
    await update.message.reply_text("🛒 Select category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    rows = cursor.execute("""
        SELECT order_id, service, price, status, created_at
        FROM orders WHERE user_id=?
        ORDER BY created_at DESC LIMIT 10
    """, (uid,)).fetchall()

    if not rows:
        await update.message.reply_text("📦 No orders yet.")
        return

    text = "📦 Your Orders:\n\n"
    for oid, service, price, status, created in rows:
        text += f"🧾 {oid}\nService: {service}\nPrice: ₹{price}\nStatus: {status}\nDate: {created}\n\n"
    await update.message.reply_text(short(text))

async def payment_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rows = cursor.execute("""
        SELECT utr, amount, status, created_at FROM payments
        WHERE user_id=? ORDER BY created_at DESC LIMIT 10
    """, (uid,)).fetchall()

    if not rows:
        await update.message.reply_text("💳 No payments yet.")
        return

    text = "💳 Your Payments:\n\n"
    for utr, amount, status, created in rows:
        text += f"UTR: {utr}\nAmount: ₹{amount}\nStatus: {status}\nDate: {created}\n\n"
    await update.message.reply_text(short(text))

async def message_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    context.user_data["state"] = "user_message_admin"
    await update.message.reply_text("📩 Type your message for admin.")

async def coupon_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    context.user_data["state"] = "coupon_apply"
    await update.message.reply_text("🎟 Send coupon code:")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={uid}"
    count = cursor.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (uid,)).fetchone()[0]
    await update.message.reply_text(
        f"👥 Your referral link:\n{link}\n\n"
        f"Total referrals: {count}\n"
        f"Reward: ₹{REFERRAL_REWARD} per new referral"
    )

# ---------------- ADMIN PANEL ----------------

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
        [InlineKeyboardButton("➕ Add Balance", callback_data="admin_add_balance"),
         InlineKeyboardButton("➖ Remove Balance", callback_data="admin_remove_balance")],
        [InlineKeyboardButton("👤 User Profile", callback_data="admin_user_profile"),
         InlineKeyboardButton("👥 Users + Balances", callback_data="admin_users_balances")],
        [InlineKeyboardButton("📦 All Orders", callback_data="admin_all_orders"),
         InlineKeyboardButton("🔍 Search Order", callback_data="admin_search_order")],
        [InlineKeyboardButton("💸 Refund Order", callback_data="admin_refund_order")],
        [InlineKeyboardButton("➕ Add Service Item", callback_data="admin_add_service_item"),
         InlineKeyboardButton("📦 Service Stock", callback_data="admin_service_stock")],
        [InlineKeyboardButton("➕ Add Service", callback_data="admin_add_service"),
         InlineKeyboardButton("❌ Remove Service", callback_data="admin_remove_service")],
        [InlineKeyboardButton("💰 Change Price", callback_data="admin_change_price"),
         InlineKeyboardButton("🗂 Set Category", callback_data="admin_set_category")],
        [InlineKeyboardButton("🎟 Add Coupon", callback_data="admin_add_coupon")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user"),
         InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user")],
        [InlineKeyboardButton("🛠 Maintenance ON/OFF", callback_data="admin_maintenance")],
        [InlineKeyboardButton("💳 Payments", callback_data="admin_payments"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📤 Export Orders", callback_data="admin_export_orders"),
         InlineKeyboardButton("📤 Export Payments", callback_data="admin_export_payments")],
        [InlineKeyboardButton("📊 Daily Report", callback_data="admin_daily_report")]
    ]
    await update.message.reply_text("🛠 Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- BUTTON HANDLER ----------------

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    ensure_user(uid)

    if is_banned(uid) and not is_admin(uid):
        await query.message.reply_text("🚫 You are blocked.")
        return

    if data.startswith("amt_"):
        amount = int(data.split("_")[1])
        context.user_data["expected_amount"] = amount
        await query.message.reply_text(f"💳 You selected ₹{amount}\n\nPay this exact amount and send only UTR.")
        return

    if data.startswith("cat_"):
        cat = data.replace("cat_", "")
        rows = cursor.execute("SELECT name, price FROM services WHERE category=? AND active=1 ORDER BY name", (cat,)).fetchall()
        if not rows:
            await query.message.reply_text("No services in this category.")
            return
        keyboard = [[InlineKeyboardButton(f"{name} - ₹{price}", callback_data=f"buy_{name}")] for name, price in rows]
        await query.message.reply_text(f"🛒 {cat} services:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("buy_"):
        service = data.replace("buy_", "")
        row = cursor.execute("SELECT price FROM services WHERE name=? AND active=1", (service,)).fetchone()
        if not row:
            await query.message.reply_text("❌ Service not found.")
            return

        price = row[0]
        balance = get_balance(uid)

        coupon_discount = context.user_data.get("coupon_discount", 0)
        final_price = max(price - coupon_discount, 0)

        if balance < final_price:
            await query.message.reply_text(f"❌ Low balance. Need ₹{final_price}")
            return

        order_id = "ORD" + str(random.randint(100000, 999999))

        cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (final_price, uid))
        cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                       (order_id, uid, service, final_price, "pending", now()))
        conn.commit()

        context.user_data.pop("coupon_discount", None)
        context.user_data.pop("coupon_code", None)

        add_order_log(order_id, uid, f"Order created for {service} ₹{final_price}")

        user_keyboard = [[InlineKeyboardButton("📲 Send Number", callback_data=f"user_senditem_{order_id}_{service}")]]

        await query.message.reply_text(
            f"✅ {service} ordered.\n🧾 Order ID: {order_id}\nPrice: ₹{final_price}\nStatus: Pending\n\nClick below to get assigned item.",
            reply_markup=InlineKeyboardMarkup(user_keyboard)
        )

        admin_keyboard = [
            [InlineKeyboardButton("📩 Send Message", callback_data=f"sendmsg_{uid}_{order_id}")],
            [InlineKeyboardButton("✅ Complete", callback_data=f"complete_{uid}_{order_id}")],
            [InlineKeyboardButton("❌ Refund", callback_data=f"refund_{uid}_{order_id}_{final_price}")]
        ]

        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"🛒 New Order\n\nOrder ID: {order_id}\nUser: {uid}\nService: {service}\nPrice: ₹{final_price}",
                reply_markup=InlineKeyboardMarkup(admin_keyboard)
            )
        return

    if data.startswith("user_senditem_"):
        _, _, order_id, service = data.split("_", 3)
        order = cursor.execute("SELECT user_id, status FROM orders WHERE order_id=?", (order_id,)).fetchone()

        if not order:
            await query.message.reply_text("❌ Order not found.")
            return

        order_user_id, status = order
        if int(order_user_id) != uid:
            await query.message.reply_text("❌ This order is not yours.")
            return

        if status in ["item_sent", "completed"]:
            await query.message.reply_text("✅ Item already assigned.")
            return

        stock = cursor.execute("SELECT id, item FROM service_items WHERE service=? ORDER BY id ASC LIMIT 1", (service,)).fetchone()
        if not stock:
            await query.message.reply_text("❌ Stock empty. Admin will contact you.")
            for admin_id in ADMINS:
                await context.bot.send_message(admin_id, f"⚠️ Stock empty for {service}\nOrder: {order_id}\nUser: {uid}")
            return

        item_id, item = stock
        cursor.execute("DELETE FROM service_items WHERE id=?", (item_id,))
        cursor.execute("UPDATE orders SET status='item_sent' WHERE order_id=?", (order_id,))
        conn.commit()

        add_order_log(order_id, uid, "Item assigned to user")

        stock_left = cursor.execute("SELECT COUNT(*) FROM service_items WHERE service=?", (service,)).fetchone()[0]
        if stock_left <= LOW_STOCK_LIMIT:
            for admin_id in ADMINS:
                await context.bot.send_message(admin_id, f"⚠️ Low stock for {service}: {stock_left} left.")

        msg_keyboard = [[InlineKeyboardButton("📩 Send Message", callback_data=f"requestmsg_{uid}_{order_id}")]]

        await query.message.reply_text(
            f"📲 Assigned Item\n🧾 Order ID: {order_id}\nService: {service}\n\n{item}\n\nTap Send Message if you need admin response.",
            reply_markup=InlineKeyboardMarkup(msg_keyboard)
        )

        for admin_id in ADMINS:
            await context.bot.send_message(admin_id, f"📲 Item assigned\nOrder: {order_id}\nUser: {uid}\nService: {service}\nStock left: {stock_left}")
        return

    if data.startswith("requestmsg_"):
        _, target_uid, order_id = data.split("_")
        for admin_id in ADMINS:
            await context.bot.send_message(
                admin_id,
                f"📩 User requested message\nUser: {target_uid}\nOrder ID: {order_id}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Reply / Send Message", callback_data=f"sendmsg_{target_uid}_{order_id}")]])
            )
        await query.message.reply_text("⏳ Request sent to admin. Please wait.")
        return

    if data.startswith("sendmsg_"):
        if not is_admin(uid):
            return
        _, target_uid, order_id = data.split("_")
        context.user_data["state"] = "send_msg"
        context.user_data["target_uid"] = int(target_uid)
        context.user_data["order_id"] = order_id
        await query.message.reply_text(f"📩 Type message for user.\nOrder ID: {order_id}")
        return

    if data.startswith("approve_"):
        if not is_admin(uid):
            return
        _, target_uid, amount, utr = data.split("_", 3)
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (int(amount), int(target_uid)))
        cursor.execute("UPDATE payments SET status='approved' WHERE utr=?", (utr,))
        conn.commit()
        await context.bot.send_message(int(target_uid), f"✅ Payment Approved\n₹{amount} added.")
        await query.message.edit_text(f"✅ Approved\nUser: {target_uid}\nAmount: ₹{amount}\nUTR: {utr}")
        return

    if data.startswith("reject_"):
        if not is_admin(uid):
            return
        _, target_uid, amount, utr = data.split("_", 3)
        cursor.execute("UPDATE payments SET status='rejected' WHERE utr=?", (utr,))
        conn.commit()
        await context.bot.send_message(int(target_uid), f"❌ Payment Rejected\nUTR: {utr}")
        await query.message.edit_text(f"❌ Rejected\nUser: {target_uid}\nAmount: ₹{amount}\nUTR: {utr}")
        return

    if data.startswith("complete_"):
        if not is_admin(uid):
            return
        _, target_uid, order_id = data.split("_")
        cursor.execute("UPDATE orders SET status='completed' WHERE order_id=?", (order_id,))
        conn.commit()
        add_order_log(order_id, uid, "Order completed by admin")
        await context.bot.send_message(int(target_uid), f"✅ Order Completed\nOrder ID: {order_id}")
        await query.message.edit_text(f"✅ Order Completed\n{order_id}")
        return

    if data.startswith("refund_"):
        if not is_admin(uid):
            return
        _, target_uid, order_id, amount = data.split("_")
        context.user_data["state"] = "refund_reason"
        context.user_data["refund_uid"] = int(target_uid)
        context.user_data["refund_order"] = order_id
        context.user_data["refund_amount"] = int(amount)
        await query.message.reply_text("💸 Send refund reason:\nExample: Bad service / No stock / User issue")
        return

    if not is_admin(uid):
        return

    # Admin panel actions
    state_map = {
        "admin_add_balance": ("admin_add_balance", "Send:\nUserID | Amount"),
        "admin_remove_balance": ("admin_remove_balance", "Send:\nUserID | Amount"),
        "admin_user_profile": ("admin_user_profile", "Send User ID:"),
        "admin_refund_order": ("admin_refund_order", "Send Order ID to refund:"),
        "admin_add_service_item": ("admin_add_service_item", "Send like:\nService Name | Item/Number"),
        "admin_broadcast": ("broadcast", "📢 Send broadcast message."),
        "admin_add_service": ("admin_add_service", "Send like:\nService Name | Price | Category"),
        "admin_remove_service": ("admin_remove_service", "Send exact service name to remove."),
        "admin_change_price": ("admin_change_price", "Send like:\nService Name | New Price"),
        "admin_set_category": ("admin_set_category", "Send like:\nService Name | Category"),
        "admin_search_order": ("admin_search_order", "Send Order ID."),
        "admin_add_coupon": ("admin_add_coupon", "Send like:\nCODE | Discount | Uses"),
        "admin_ban_user": ("admin_ban_user", "Send User ID to ban:"),
        "admin_unban_user": ("admin_unban_user", "Send User ID to unban:")
    }

    if data in state_map:
        context.user_data["state"] = state_map[data][0]
        await query.message.reply_text(state_map[data][1])
        return

    if data == "admin_dashboard":
        total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_orders = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        pending = cursor.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        completed = cursor.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0]
        refunded = cursor.execute("SELECT SUM(price) FROM orders WHERE status='refunded'").fetchone()[0] or 0
        sales = cursor.execute("SELECT SUM(price) FROM orders WHERE status IN ('pending','item_sent','completed')").fetchone()[0] or 0
        await query.message.reply_text(f"📊 Dashboard\nUsers: {total_users}\nOrders: {total_orders}\nPending: {pending}\nCompleted: {completed}\nSales: ₹{sales}\nRefunded: ₹{refunded}")
        return

    if data == "admin_users_balances":
        rows = cursor.execute("SELECT user_id, balance, banned FROM users ORDER BY user_id DESC LIMIT 50").fetchall()
        text = "👥 Users + Balances\n\n"
        for u, b, banned in rows:
            text += f"{u} → ₹{b} {'🚫' if banned else ''}\n"
        await query.message.reply_text(short(text))
        return

    if data == "admin_all_orders":
        rows = cursor.execute("SELECT order_id, user_id, service, price, status FROM orders ORDER BY created_at DESC LIMIT 30").fetchall()
        text = "📦 Orders\n\n"
        for oid, u, s, p, st in rows:
            text += f"{oid}\nUser: {u}\n{s} - ₹{p}\nStatus: {st}\n\n"
        await query.message.reply_text(short(text))
        return

    if data == "admin_service_stock":
        rows = cursor.execute("SELECT service, COUNT(*) FROM service_items GROUP BY service").fetchall()
        if not rows:
            await query.message.reply_text("📦 No service stock.")
            return
        text = "📦 Service Stock\n\n"
        for service, count in rows:
            text += f"{service}: {count}\n"
        await query.message.reply_text(text)
        return

    if data == "admin_payments":
        total = cursor.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        pending = cursor.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
        approved = cursor.execute("SELECT COUNT(*) FROM payments WHERE status='approved'").fetchone()[0]
        rejected = cursor.execute("SELECT COUNT(*) FROM payments WHERE status='rejected'").fetchone()[0]
        await query.message.reply_text(f"💳 Payments\nTotal: {total}\nPending: {pending}\nApproved: {approved}\nRejected: {rejected}")
        return

    if data == "admin_maintenance":
        current = get_setting("maintenance", "0")
        new = "0" if current == "1" else "1"
        set_setting("maintenance", new)
        await query.message.reply_text(f"🛠 Maintenance {'ON' if new == '1' else 'OFF'}")
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
        approved = cursor.execute("SELECT SUM(amount) FROM payments WHERE status='approved' AND created_at LIKE ?", (today() + "%",)).fetchone()[0] or 0
        orders = cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (today() + "%",)).fetchone()[0]
        completed = cursor.execute("SELECT COUNT(*) FROM orders WHERE status='completed' AND created_at LIKE ?", (today() + "%",)).fetchone()[0]
        await query.message.reply_text(f"📊 Daily Report\nDate: {today()}\nPayments: ₹{approved}\nOrders: {orders}\nCompleted: {completed}")
        return

# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    text = update.message.text.strip()
    state = context.user_data.get("state")

    if state == "user_message_admin":
        msg_id = "MSG" + str(random.randint(100000, 999999))
        cursor.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (msg_id, uid, text, "open", now()))
        conn.commit()
        for admin_id in ADMINS:
            await context.bot.send_message(admin_id, f"📩 User Message\nUser: {uid}\nMessage ID: {msg_id}\n\n{text}")
        await update.message.reply_text("✅ Message sent to admin.")
        context.user_data.pop("state", None)
        return

    if state == "send_msg":
        if not is_admin(uid):
            return
        target_uid = context.user_data["target_uid"]
        order_id = context.user_data["order_id"]
        await context.bot.send_message(target_uid, f"📩 Admin Message\nOrder ID: {order_id}\n\n{text}")
        add_order_log(order_id, uid, f"Admin message: {text}")
        await update.message.reply_text("✅ Message sent.")
        context.user_data.pop("state", None)
        context.user_data.pop("target_uid", None)
        context.user_data.pop("order_id", None)
        return

    if state == "refund_reason":
        if not is_admin(uid):
            return
        target_uid = context.user_data["refund_uid"]
        order_id = context.user_data["refund_order"]
        amount = context.user_data["refund_amount"]
        cursor.execute("UPDATE orders SET status='refunded' WHERE order_id=?", (order_id,))
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, target_uid))
        conn.commit()
        add_order_log(order_id, uid, f"Refunded ₹{amount}. Reason: {text}")
        await context.bot.send_message(target_uid, f"💸 Refund Sent\nOrder ID: {order_id}\nAmount: ₹{amount}\nReason: {text}")
        await update.message.reply_text(f"✅ Refunded ₹{amount} to {target_uid}")
        for k in ["state", "refund_uid", "refund_order", "refund_amount"]:
            context.user_data.pop(k, None)
        return

    if is_admin(uid):
        if state == "admin_add_balance":
            try:
                target_uid, amount = text.split("|")
                target_uid, amount = int(target_uid.strip()), int(amount.strip())
                ensure_user(target_uid)
                cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, target_uid))
                conn.commit()
                await context.bot.send_message(target_uid, f"✅ Admin added ₹{amount}")
                await update.message.reply_text(f"✅ ₹{amount} added to {target_uid}")
            except Exception:
                await update.message.reply_text("❌ Wrong format. Use: UserID | Amount")
            context.user_data.pop("state", None)
            return

        if state == "admin_remove_balance":
            try:
                target_uid, amount = text.split("|")
                target_uid, amount = int(target_uid.strip()), int(amount.strip())
                ensure_user(target_uid)
                cursor.execute("UPDATE users SET balance=MAX(balance-?,0) WHERE user_id=?", (amount, target_uid))
                conn.commit()
                await context.bot.send_message(target_uid, f"➖ Admin removed ₹{amount} from wallet.")
                await update.message.reply_text(f"✅ ₹{amount} removed from {target_uid}")
            except Exception:
                await update.message.reply_text("❌ Wrong format. Use: UserID | Amount")
            context.user_data.pop("state", None)
            return

        if state == "admin_user_profile":
            try:
                target_uid = int(text)
                bal = get_balance(target_uid)
                orders = cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (target_uid,)).fetchone()[0]
                pays = cursor.execute("SELECT COUNT(*) FROM payments WHERE user_id=?", (target_uid,)).fetchone()[0]
                banned = cursor.execute("SELECT banned FROM users WHERE user_id=?", (target_uid,)).fetchone()[0]
                await update.message.reply_text(f"👤 User Profile\nID: {target_uid}\nBalance: ₹{bal}\nOrders: {orders}\nPayments: {pays}\nBanned: {'Yes' if banned else 'No'}")
            except Exception:
                await update.message.reply_text("❌ Invalid User ID")
            context.user_data.pop("state", None)
            return

        if state == "admin_add_service_item":
            try:
                service, item = text.split("|", 1)
                service, item = service.strip(), item.strip()
                cursor.execute("INSERT INTO service_items (service, item, created_at) VALUES (?,?,?)", (service, item, now()))
                conn.commit()
                await update.message.reply_text(f"✅ Item added for {service}")
            except Exception:
                await update.message.reply_text("❌ Use: Service Name | Item/Number")
            context.user_data.pop("state", None)
            return

        if state == "broadcast":
            users = cursor.execute("SELECT user_id FROM users").fetchall()
            sent = 0
            for row in users:
                try:
                    await context.bot.send_message(row[0], text)
                    sent += 1
                except Exception:
                    pass
            await update.message.reply_text(f"📢 Broadcast sent to {sent} users.")
            context.user_data.pop("state", None)
            return

        if state == "admin_add_service":
            try:
                parts = [p.strip() for p in text.split("|")]
                service = parts[0]
                price = int(parts[1])
                category = parts[2] if len(parts) >= 3 else "General"
                cursor.execute("INSERT OR REPLACE INTO services (name, price, category, active) VALUES (?,?,?,1)", (service, price, category))
                conn.commit()
                await update.message.reply_text(f"✅ Service added/updated:\n{service} - ₹{price} - {category}")
            except Exception:
                await update.message.reply_text("❌ Use: Service Name | Price | Category")
            context.user_data.pop("state", None)
            return

        if state == "admin_remove_service":
            cursor.execute("UPDATE services SET active=0 WHERE name=?", (text,))
            conn.commit()
            await update.message.reply_text(f"❌ Service hidden: {text}")
            context.user_data.pop("state", None)
            return

        if state == "admin_change_price":
            try:
                service, price = text.split("|")
                service, price = service.strip(), int(price.strip())
                cursor.execute("UPDATE services SET price=? WHERE name=?", (price, service))
                conn.commit()
                await update.message.reply_text(f"💰 Price updated:\n{service} - ₹{price}")
            except Exception:
                await update.message.reply_text("❌ Use: Service Name | New Price")
            context.user_data.pop("state", None)
            return

        if state == "admin_set_category":
            try:
                service, category = text.split("|")
                service, category = service.strip(), category.strip()
                cursor.execute("UPDATE services SET category=? WHERE name=?", (category, service))
                conn.commit()
                await update.message.reply_text(f"🗂 Category updated:\n{service} → {category}")
            except Exception:
                await update.message.reply_text("❌ Use: Service Name | Category")
            context.user_data.pop("state", None)
            return

        if state == "admin_add_coupon":
            try:
                code, discount, uses = text.split("|")
                code, discount, uses = code.strip().upper(), int(discount.strip()), int(uses.strip())
                cursor.execute("INSERT OR REPLACE INTO coupons VALUES (?,?,?,1)", (code, discount, uses))
                conn.commit()
                await update.message.reply_text(f"🎟 Coupon added: {code} ₹{discount}, uses {uses}")
            except Exception:
                await update.message.reply_text("❌ Use: CODE | Discount | Uses")
            context.user_data.pop("state", None)
            return

        if state == "admin_ban_user":
            try:
                target_uid = int(text)
                ensure_user(target_uid)
                cursor.execute("UPDATE users SET banned=1 WHERE user_id=?", (target_uid,))
                conn.commit()
                await update.message.reply_text(f"🚫 User banned: {target_uid}")
            except Exception:
                await update.message.reply_text("❌ Invalid User ID")
            context.user_data.pop("state", None)
            return

        if state == "admin_unban_user":
            try:
                target_uid = int(text)
                ensure_user(target_uid)
                cursor.execute("UPDATE users SET banned=0 WHERE user_id=?", (target_uid,))
                conn.commit()
                await update.message.reply_text(f"✅ User unbanned: {target_uid}")
            except Exception:
                await update.message.reply_text("❌ Invalid User ID")
            context.user_data.pop("state", None)
            return

        if state == "admin_refund_order":
            order = cursor.execute("SELECT user_id, price FROM orders WHERE order_id=?", (text,)).fetchone()
            if not order:
                await update.message.reply_text("❌ Order not found.")
            else:
                target_uid, amount = order
                context.user_data["state"] = "refund_reason"
                context.user_data["refund_uid"] = target_uid
                context.user_data["refund_order"] = text
                context.user_data["refund_amount"] = amount
                await update.message.reply_text("💸 Send refund reason:")
            return

        if state == "admin_search_order":
            order = cursor.execute("SELECT * FROM orders WHERE order_id=?", (text,)).fetchone()
            if order:
                logs = cursor.execute("SELECT actor_id, message, created_at FROM order_logs WHERE order_id=? ORDER BY id DESC LIMIT 5", (text,)).fetchall()
                msg = f"🔍 Order Found\nOrder ID: {order[0]}\nUser: {order[1]}\nService: {order[2]}\nPrice: ₹{order[3]}\nStatus: {order[4]}\nDate: {order[5]}\n\nRecent logs:\n"
                for actor, m, t in logs:
                    msg += f"{t} | {actor}: {m}\n"
                await update.message.reply_text(short(msg))
            else:
                await update.message.reply_text("❌ Order not found.")
            context.user_data.pop("state", None)
            return

    if state == "coupon_apply":
        code = text.upper()
        row = cursor.execute("SELECT discount, uses_left, active FROM coupons WHERE code=?", (code,)).fetchone()
        if not row or row[2] != 1 or row[1] <= 0:
            await update.message.reply_text("❌ Invalid or expired coupon.")
        else:
            discount = row[0]
            cursor.execute("UPDATE coupons SET uses_left=uses_left-1 WHERE code=?", (code,))
            conn.commit()
            context.user_data["coupon_discount"] = discount
            context.user_data["coupon_code"] = code
            await update.message.reply_text(f"✅ Coupon applied: ₹{discount} discount on next order.")
        context.user_data.pop("state", None)
        return

    expected_amount = context.user_data.get("expected_amount")
    if expected_amount:
        utr = text
        old = cursor.execute("SELECT utr FROM payments WHERE utr=?", (utr,)).fetchone()
        if old:
            await update.message.reply_text("❌ UTR already used.")
            return

        cursor.execute("INSERT INTO payments VALUES (?,?,?,?,?)", (utr, uid, expected_amount, "pending", now()))
        conn.commit()

        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}_{expected_amount}_{utr}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}_{expected_amount}_{utr}")
        ]]

        for admin_id in ADMINS:
            await context.bot.send_message(admin_id, f"💳 Payment Request\n\nUser: {uid}\nAmount: ₹{expected_amount}\nUTR: {utr}", reply_markup=InlineKeyboardMarkup(keyboard))

        await update.message.reply_text("⏳ Payment submitted.")
        context.user_data.pop("expected_amount", None)
        return

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    for admin_id in ADMINS:
        await context.bot.send_photo(admin_id, update.message.photo[-1].file_id, caption=f"🧾 Screenshot from {uid}")
    await update.message.reply_text("✅ Screenshot sent.\nNow send UTR.")

# ---------------- APP ----------------

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(MessageHandler(filters.Regex("^💰 Add Balance$"), add_balance))
app.add_handler(MessageHandler(filters.Regex("^🛒 Buy Service$"), buy))
app.add_handler(MessageHandler(filters.Regex("^👛 Wallet$"), wallet))
app.add_handler(MessageHandler(filters.Regex("^📦 My Orders$"), my_orders))
app.add_handler(MessageHandler(filters.Regex("^💳 Payments$"), payment_history))
app.add_handler(MessageHandler(filters.Regex("^📩 Message Admin$"), message_admin))
app.add_handler(MessageHandler(filters.Regex("^🎟 Coupon$"), coupon_start))
app.add_handler(MessageHandler(filters.Regex("^👥 Referral$"), referral))

app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("Bot running...")
app.run_polling()
