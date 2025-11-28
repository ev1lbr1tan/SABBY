import telebot
import pymysql
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Инициализация бота
TOKEN = "8073011044:AAEhiaUcRdumxxOQyi29cRdqTfUygZN5BP8"  # Токен бота от BotFather
bot = telebot.TeleBot(TOKEN)

# Инициализация планировщика
scheduler = BackgroundScheduler()

# Конфигурация базы данных MySQL
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'subscription_bot',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    """Создает и возвращает соединение с базой данных MySQL"""
    connection = pymysql.connect(**DB_CONFIG)
    return connection

def init_db():
    """Инициализирует базу данных и создает таблицу подписок, если она не существует"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    # Создание таблицы подписок, если она не существует
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            service_name VARCHAR(255) NOT NULL,
            cost DECIMAL(10, 2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            renewal_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    connection.commit()
    cursor.close()
    connection.close()

def get_user_subscriptions(user_id):
    """Получает все подписки пользователя"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute('''
            SELECT id, service_name, cost, currency, renewal_date
            FROM subscriptions
            WHERE user_id = %s
            ORDER BY renewal_date
        ''', (user_id,))
        
        subscriptions = cursor.fetchall()
        cursor.close()
        connection.close()
        return subscriptions
    except Exception as e:
        print(f"Ошибка при получении подписок: {e}")
        return []

def add_user_subscription(user_id, service_name, cost, currency, renewal_date):
    """Добавляет новую подписку пользователя в базу данных"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    cursor.execute('''
        INSERT INTO subscriptions (user_id, service_name, cost, currency, renewal_date)
        VALUES (%s, %s, %s, %s, %s)
    ''', (user_id, service_name, cost, currency, renewal_date))
    
    connection.commit()
    cursor.close()
    connection.close()

def delete_user_subscription(user_id, subscription_id):
    """Удаляет подписку пользователя по ID"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    cursor.execute('''
        DELETE FROM subscriptions
        WHERE id = %s AND user_id = %s
    ''', (subscription_id, user_id))
    
    connection.commit()
    cursor.close()
    connection.close()

def get_user_total_cost(user_id):
    """Вычисляет общую стоимость всех подписок пользователя"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    cursor.execute('''
        SELECT SUM(cost)
        FROM subscriptions
        WHERE user_id = %s
    ''', (user_id,))
    
    result = cursor.fetchone()
    total = float(result['SUM(cost)']) if result['SUM(cost)'] else 0.0
    cursor.close()
    connection.close()
    return total

def get_upcoming_renewals(user_id, days=7):
    """Получает подписки пользователя, которые обновляются в течение заданного количества дней"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    # Вычисляем дату через заданное количество дней
    future_date = datetime.now() + timedelta(days=days)
    
    cursor.execute('''
        SELECT service_name, cost, currency, renewal_date
        FROM subscriptions
        WHERE user_id = %s AND renewal_date <= %s AND renewal_date >= %s
        ORDER BY renewal_date
    ''', (user_id, future_date.strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d')))
    
    upcoming = cursor.fetchall()
    cursor.close()
    connection.close()
    return upcoming

def add_subscription(user_id, service_name, cost, currency, renewal_date):
    """Добавляет новую подписку в базу данных пользователя"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO subscriptions (service_name, cost, currency, renewal_date)
        VALUES (?, ?, ?, ?)
    ''', (service_name, cost, currency, renewal_date))
    
    conn.commit()
    conn.close()

def get_subscriptions(user_id):
    """Получает все подписки пользователя"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, service_name, cost, currency, renewal_date FROM subscriptions')
    subscriptions = cursor.fetchall()
    
    conn.close()
    return subscriptions

def delete_subscription(user_id, subscription_id):
    """Удаляет подписку пользователя по ID"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM subscriptions WHERE id = ?', (subscription_id,))
    
    conn.commit()
    conn.close()

def get_total_cost(user_id):
    """Вычисляет общую стоимость всех подписок пользователя"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    cursor.execute('SELECT SUM(cost) FROM subscriptions')
    total = cursor.fetchone()[0] or 0
    
    conn.close()
    return total

def get_upcoming_renewals(user_id, days=7):
    """Получает подписки, которые обновляются в течение заданного количества дней"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    # Вычисляем дату через заданное количество дней
    future_date = datetime.now() + timedelta(days=days)
    
    cursor.execute('''
        SELECT service_name, cost, renewal_date 
        FROM subscriptions 
        WHERE renewal_date <= ? AND renewal_date >= ?
        ORDER BY renewal_date
    ''', (future_date.strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d')))
    
    upcoming = cursor.fetchall()
    conn.close()
    return upcoming

# Команды бота
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Создаем стильную клавиатуру с кнопками
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('➕ Добавить подписку', '📋 Мои подписки')
    markup.row('❌ Удалить подписку', '💰 Общая сумма')
    markup.row('❓ Помощь')
    
    welcome_text = """
Привет! Я бот для отслеживания подписок. Вот что я могу:

➕ Добавить подписку - Пошаговое добавление новой подписки
📋 Мои подписки - Показать все ваши подписки
❌ Удалить подписку - Удалить подписку по ID
💰 Общая сумма - Показать общую сумму расходов
❓ Помощь - Показать это сообщение снова
    """
    bot.reply_to(message, welcome_text, reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    send_welcome(message)

# Добавляем обработчик для кнопки "Добавить подписку"
@bot.message_handler(func=lambda message: message.text == '➕ Добавить подписку' or message.text == '/add')
def handle_add_button(message):
    add_subscription_handler(message)

# Добавляем обработчик для кнопки "Показать все подписки"
@bot.message_handler(func=lambda message: message.text == '📋 Мои подписки' or message.text == '/list')
def handle_list_button(message):
    list_subscriptions(message)

# Добавляем обработчик для кнопки "Удалить подписку"
@bot.message_handler(func=lambda message: message.text == '❌ Удалить подписку' or message.text == '/delete')
def handle_delete_button(message):
    delete_subscription_handler(message)

# Добавляем обработчик для кнопки "Общая сумма"
@bot.message_handler(func=lambda message: message.text == '💰 Общая сумма' or message.text == '/total')
def handle_total_button(message):
    total_cost(message)

# Добавляем обработчик для кнопки "Помощь"
@bot.message_handler(func=lambda message: message.text == '❓ Помощь' or message.text == '/help')
def handle_help_button(message):
    send_help(message)

# Словарь для хранения временных данных пользователя при добавлении подписки
user_states = {}

@bot.message_handler(commands=['add'])
def add_subscription_handler(message):
    try:
        # Инициализируем состояние пользователя
        user_states[message.from_user.id] = {}
        
        # Создаем клавиатуру с вариантами сервисов
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        # Расширяем список сервисов
        services = [
            'Netflix', 'Amazon Prime Video', 'Disney+', 'Apple TV+', 'HBO Max', 'Paramount+',
            'Spotify', 'Apple Music', 'YouTube Music', 'Yandex Music', 'Deezer', 'Tidal',
            'Kinopoisk', 'Okko', 'Premier', 'Amediateka', 'More.tv', 'ivi', 'megogo',
            'Microsoft 365', 'Adobe Creative Cloud', 'Google One', 'iCloud+', 'Dropbox',
            'Other'
        ]
        # Разбиваем на строки по 2 кнопки
        for i in range(0, len(services), 2):
            if i+1 < len(services):
                markup.row(services[i], services[i+1])
            else:
                markup.row(services[i])
        
        msg = bot.reply_to(message, "Выберите сервис или введите свой:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_service_name)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def process_service_name(message):
    try:
        user_states[message.from_user.id]['service_name'] = message.text
        
        # Создаем клавиатуру с валютами
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        currencies = ['USD', 'EUR', 'RUB', 'UAH', 'KZT', 'BYN']
        markup.row('USD', 'EUR')
        markup.row('RUB', 'UAH')
        markup.row('KZT', 'BYN')
        
        msg = bot.reply_to(message, "Выберите валюту:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_currency)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def process_currency(message):
    try:
        user_states[message.from_user.id]['currency'] = message.text
        
        # Запрашиваем стоимость подписки
        msg = bot.reply_to(message, "Введите стоимость подписки:")
        bot.register_next_step_handler(msg, process_cost)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def process_cost(message):
    try:
        cost = float(message.text)
        user_states[message.from_user.id]['cost'] = cost
        
        # Запрашиваем дату обновления
        msg = bot.reply_to(message, "Введите дату обновления подписки в формате ГГГГ-ММ-ДД (например, 2023-12-15):")
        bot.register_next_step_handler(msg, process_renewal_date)
    except ValueError:
        bot.reply_to(message, "Неверный формат стоимости. Пожалуйста, введите число.")
        bot.register_next_step_handler(message, process_cost)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def process_renewal_date(message):
    try:
        # Проверяем формат даты
        renewal_date = message.text
        datetime.strptime(renewal_date, '%Y-%m-%d')
        
        # Получаем данные из состояния пользователя
        user_id = message.from_user.id
        service_name = user_states[user_id]['service_name']
        currency = user_states[user_id]['currency']
        cost = user_states[user_id]['cost']
        
        # Добавляем подписку
        add_subscription(user_id, service_name, cost, currency, renewal_date)
        
        # Очищаем состояние пользователя
        del user_states[user_id]
        
        # Возвращаем стандартную клавиатуру
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('/add', '/list')
        markup.row('/delete', '/total')
        markup.row('/help')
        
        bot.reply_to(message, f"Подписка '{service_name}' добавлена успешно!", reply_markup=markup)
    except ValueError:
        bot.reply_to(message, "Неверный формат даты. Пожалуйста, используйте формат ГГГГ-ММ-ДД (например, 2023-12-15).")
        bot.register_next_step_handler(message, process_renewal_date)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

@bot.message_handler(commands=['list'])
def list_subscriptions(message):
    try:
        subscriptions = get_subscriptions(message.from_user.id)
        
        if not subscriptions:
            bot.reply_to(message, "У вас нет подписок.")
            return
        
        response = "Ваши подписки:\n\n"
        for sub in subscriptions:
            # Определяем символ валюты для отображения
            currency_symbols = {
                'USD': '$',
                'EUR': '€',
                'RUB': '₽',
                'UAH': '₴',
                'KZT': '₸',
                'BYN': 'Br'
            }
            currency_symbol = currency_symbols.get(sub[3], sub[3])  # Используем код валюты, если символ не найден
            
            response += f"ID: {sub[0]}\nНазвание: {sub[1]}\nСтоимость: {sub[2]:.2f} {currency_symbol}\nДата обновления: {sub[4]}\n\n"
        
        bot.reply_to(message, response)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

@bot.message_handler(commands=['delete'])
def delete_subscription_handler(message):
    try:
        msg = bot.reply_to(message, "Введите ID подписки для удаления:")
        bot.register_next_step_handler(msg, process_delete_subscription)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def process_delete_subscription(message):
    try:
        subscription_id = int(message.text)
        delete_subscription(message.from_user.id, subscription_id)
        bot.reply_to(message, f"Подписка с ID {subscription_id} удалена.")
    except ValueError:
        bot.reply_to(message, "Неверный ID. Пожалуйста, введите числовое значение.")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

@bot.message_handler(commands=['total'])
def total_cost(message):
    try:
        total = get_total_cost(message.from_user.id)
        bot.reply_to(message, f"Общая стоимость всех подписок: ${total:.2f}")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

# Функция для отправки уведомлений
def send_daily_notifications():
    # В реальной реализации здесь нужно будет пройтись по всем пользователям
    # Для простоты в этом примере мы не реализуем механизм отслеживания пользователей
    # В production-среде вы можете хранить список пользователей в отдельной таблице
    pass

# Запуск планировщика
scheduler.add_job(send_daily_notifications, 'cron', hour=9, minute=0)  # Ежедневно в 9:00 UTC
scheduler.start()

# Регистрируем функцию остановки планировщика при завершении работы
atexit.register(lambda: scheduler.shutdown())

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling(none_stop=True)