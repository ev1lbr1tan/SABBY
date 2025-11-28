import telebot
import pymysql
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# ТОКЕН БЕРЁТСЯ ИЗ ПЕРЕМЕННЫХ RAILWAY — НИКОГДА НЕ ХАРДКОДЬ В ПРОДЕ!
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не найден BOT_TOKEN в переменных окружения!")

bot = telebot.TeleBot(TOKEN)

# Подключение к MySQL из Railway (автоматически подтягиваются переменные)
DB_CONFIG = {
    'host': os.environ['MYSQLHOST'],
    'port': int(os.environ['MYSQLPORT']),
    'user': os.environ['MYSQLUSER'],
    'password': os.environ['MYSQLPASSWORD'],
    'database': os.environ['MYSQLDATABASE'],
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': True
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

# Инициализация таблиц при старте
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            service_name VARCHAR(255) NOT NULL,
            cost DECIMAL(10,2) NOT NULL,
            currency VARCHAR(10) DEFAULT 'USD',
            renewal_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.close()
    conn.close()

# === РАБОЧИЕ ФУНКЦИИ ДЛЯ MySQL (все старые удалены!) ===
def get_user_subscriptions(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, service_name, cost, currency, renewal_date
        FROM subscriptions WHERE user_id = %s
        ORDER BY renewal_date
    ''', (user_id,))
    subs = cursor.fetchall()
    cursor.close()
    conn.close()
    return subs

def add_user_subscription(user_id, service_name, cost, currency='USD', renewal_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO subscriptions (user_id, service_name, cost, currency, renewal_date)
        VALUES (%s, %s, %s, %s, %s)
    ''', (user_id, service_name, cost, currency, renewal_date))
    cursor.close()
    conn.close()

def delete_user_subscription(user_id, subscription_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE id = %s AND user_id = %s', (subscription_id, user_id))
    cursor.close()
    conn.close()

def get_user_total_cost(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(SUM(cost), 0) as total FROM subscriptions WHERE user_id = %s', (user_id,))
    total = cursor.fetchone()['total']
    cursor.close()
    conn.close()
    return float(total)

def get_upcoming_renewals_global(days=7):
    """Для ежедневной рассылки — возвращает всех пользователей и их ближайшие подписки"""
    conn = get_db_connection()
    cursor = conn.cursor()
    future_date = (datetime.now() + timedelta(days=days)).date()
    today = datetime.now().date()
    
    cursor.execute('''
        SELECT DISTINCT user_id FROM subscriptions
        WHERE renewal_date BETWEEN %s AND %s
    ''', (today, future_date))
    user_ids = [row['user_id'] for row in cursor.fetchall()]
    
    result = {}
    for uid in user_ids:
        cursor.execute('''
            SELECT service_name, cost, currency, renewal_date
            FROM subscriptions
            WHERE user_id = %s AND renewal_date BETWEEN %s AND %s
            ORDER BY renewal_date
        ''', (uid, today, future_date))
        result[uid] = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return result

# === КОМАНДЫ ===
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Добавить подписку', 'Мои подписки')
    markup.row('Удалить подписку', 'Общая сумма')
    
    bot.reply_to(message, """
Привет! Я Subby — твой контролёр подписок

Добавить подписку — добавить новую
Мои подписки — посмотреть список
Удалить подписку — по ID
Общая сумма — сколько сгорает в месяц
    """, reply_markup=markup)

# === Добавление подписки (пошагово) ===
user_states = {}

@bot.message_handler(func=lambda m: m.text == 'Добавить подписку' or m.text == '/add')
def add_start(message):
    user_states[message.from_user.id] = {}
    markup = telebot.types.ReplyKeyboardRemove()
    msg = bot.reply_to(message, "Назови сервис (например, Netflix, Я.Плюс, ChatGPT):", reply_markup=markup)
    bot.register_next_step_handler(msg, step_service)

def step_service(message):
    user_states[message.from_user.id]['service'] = message.text
    msg = bot.reply_to(message, "Стоимость в месяц? (например 9.99 или 799)")
    bot.register_next_step_handler(msg, step_cost)

def step_cost(message):
    try:
        cost = float(message.text.replace(',', '.'))
        user_states[message.from_user.id]['cost'] = cost
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for cur in ['USD', 'RUB', 'EUR', 'UAH']:
            markup.add(cur)
        msg = bot.reply_to(message, "Валюта:", reply_markup=markup)
        bot.register_next_step_handler(msg, step_currency)
    except:
        bot.reply_to(message, "Введи число")
        bot.register_next_step_handler(message, step_cost)

def step_currency(message):
    user_states[message.from_user.id]['currency'] = message.text.upper()
    msg = bot.reply_to(message, "Дата следующего списания (ГГГГ-ММ-ДД):")
    bot.register_next_step_handler(msg, step_date)

def step_date(message):
    uid = message.from_user.id
    try:
        date_obj = datetime.strptime(message.text, '%Y-%m-%d').date()
        data = user_states[uid]
        add_user_subscription(uid, data['service'], data['cost'], data['currency'], date_obj)
        bot.reply_to(message, f"Подписка «{data['service']}» добавлена!")
        del user_states[uid]
    except:
        bot.reply_to(message, "Неверная дата, формат ГГГГ-ММ-ДД")
        bot.register_next_step_handler(message, step_date)

# === Остальные команды ===
@bot.message_handler(func=lambda m: m.text in ['Мои подписки', '/list'])
def list_subs(message):
    subs = get_user_subscriptions(message.from_user.id)
    if not subs:
        bot.reply_to(message, "Подписки пусто")
        return
    
    text = "Твои подписки:\n\n"
    for s in subs:
        sym = {'USD':'$', 'RUB':'₽', 'EUR':'€', 'UAH':'₴'}.get(s['currency'], s['currency'])
        text += f"ID: <code>{s['id']}</code>\n{s['service_name']} — {s['cost']} {sym} — {s['renewal_date']}\n\n"
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text in ['Удалить подписку', '/delete'])
def delete_start(message):
    msg = bot.reply_to(message, "Введи ID подписки для удаления:")
    bot.register_next_step_handler(msg, delete_process)

def delete_process(message):
    try:
        sub_id = int(message.text)
        delete_user_subscription(message.from_user.id, sub_id)
        bot.reply_to(message, "Удалено")
    except:
        bot.reply_to(message, "Ошибка ID")

@bot.message_handler(func=lambda m: m.text in ['Общая сумма', '/total'])
def total(message):
    total = get_user_total_cost(message.from_user.id)
    bot.reply_to(message, f"В месяц улетает: {total:.2f} (сумма по всем валютам в числах)")

# === Ежедневные напоминания ===
def daily_reminders():
    upcoming = get_upcoming_renewals_global(days=7)
    for user_id, subs in upcoming.items():
        try:
            text = "Скоро спишут:\n\n"
            for s in subs:
                sym = {'USD':'$', 'RUB':'₽', 'EUR':'€', 'UAH':'₴'}.get(s['currency'], s['currency'])
                text += f"• {s['service_name']} — {s['cost']} {sym} — {s['renewal_date']}\n"
            bot.send_message(user_id, text)
        except:
            pass  # пользователь заблокировал бота

scheduler = BackgroundScheduler()
scheduler.add_job(daily_reminders, 'cron', hour=9, minute=0)  # 9:00 UTC
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# === ЗАПУСК ===
init_db()  # создаём таблицу при старте
print("Subby запущен и готов сосать деньги из подписок")
bot.infinity_polling()
