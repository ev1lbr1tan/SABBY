import telebot
import sqlite3
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Инициализация бота
TOKEN = "8073011044:AAEhiaUcRdumxxOQyi29cRdqTfUygZN5BP8"  # Токен бота от BotFather
bot = telebot.TeleBot(TOKEN)

# Инициализация планировщика
scheduler = BackgroundScheduler()

def get_user_db(user_id):
    """Создает или возвращает базу данных для пользователя"""
    db_name = f"user_{user_id}.db"
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # Создание таблицы подписок, если она не существует
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            cost REAL NOT NULL,
            renewal_date DATE NOT NULL
        )
    ''')
    
    conn.commit()
    return conn

def add_subscription(user_id, service_name, cost, renewal_date):
    """Добавляет новую подписку в базу данных пользователя"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO subscriptions (service_name, cost, renewal_date)
        VALUES (?, ?, ?)
    ''', (service_name, cost, renewal_date))
    
    conn.commit()
    conn.close()

def get_subscriptions(user_id):
    """Получает все подписки пользователя"""
    conn = get_user_db(user_id)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, service_name, cost, renewal_date FROM subscriptions')
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
    # Создаем клавиатуру с кнопками
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('/add', '/list')
    markup.row('/delete', '/total')
    markup.row('/help')
    
    welcome_text = """
Привет! Я бот для отслеживания подписок. Вот что я могу:

/add - Добавить новую подписку
/list - Показать все подписки
/delete - Удалить подписку
/total - Показать общую сумму расходов
/help - Показать это сообщение снова
    """
    bot.reply_to(message, welcome_text, reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    send_welcome(message)

# Добавляем обработчик для кнопки "Добавить подписку"
@bot.message_handler(func=lambda message: message.text == '/add')
def handle_add_button(message):
    add_subscription_handler(message)

# Добавляем обработчик для кнопки "Показать все подписки"
@bot.message_handler(func=lambda message: message.text == '/list')
def handle_list_button(message):
    list_subscriptions(message)

# Добавляем обработчик для кнопки "Удалить подписку"
@bot.message_handler(func=lambda message: message.text == '/delete')
def handle_delete_button(message):
    delete_subscription_handler(message)

# Добавляем обработчик для кнопки "Общая сумма"
@bot.message_handler(func=lambda message: message.text == '/total')
def handle_total_button(message):
    total_cost(message)

# Добавляем обработчик для кнопки "Помощь"
@bot.message_handler(func=lambda message: message.text == '/help')
def handle_help_button(message):
    send_help(message)

@bot.message_handler(commands=['add'])
def add_subscription_handler(message):
    try:
        # Ожидаем ввод данных в формате: название стоимость дата
        msg = bot.reply_to(message, "Введите данные подписки в формате:\nназвание стоимость дата\nПример: Netflix 15.99 2023-12-15")
        bot.register_next_step_handler(msg, process_add_subscription)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def process_add_subscription(message):
    try:
        # Разбираем введенные данные
        data = message.text.split()
        if len(data) != 3:
            bot.reply_to(message, "Неверный формат. Пожалуйста, используйте: название стоимость дата")
            return
        
        service_name = data[0]
        cost = float(data[1])
        renewal_date = data[2]
        
        # Проверяем формат даты
        datetime.strptime(renewal_date, '%Y-%m-%d')
        
        # Добавляем подписку
        add_subscription(message.from_user.id, service_name, cost, renewal_date)
        bot.reply_to(message, f"Подписка '{service_name}' добавлена успешно!")
    except ValueError:
        bot.reply_to(message, "Неверный формат стоимости или даты. Пожалуйста, используйте: название стоимость(число) дата(ГГГГ-ММ-ДД)")
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
            response += f"ID: {sub[0]}\nНазвание: {sub[1]}\nСтоимость: ${sub[2]:.2f}\nДата обновления: {sub[3]}\n\n"
        
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