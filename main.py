from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.types import Message
from datetime import datetime, timedelta
import asyncio
import signal
from pathlib import Path

from config import Config, load_config
from database import Database
from backup import DatabaseBackup
from logger import setup_logger

# Инициализация логгера
logger = setup_logger('main')

class TimerBot:
    def __init__(self, config: Config):
        self.config = config
        self.bot = Bot(token=config.bot_token)
        self.dp = Dispatcher()
        self.db = Database()
        self.backup = DatabaseBackup("timer_bot.db")
        self.running = True
        
        # Регистрация обработчиков команд
        self.register_handlers()

    def register_handlers(self):
        """Регистрация обработчиков команд бота"""
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_help, Command("help"))
        self.dp.message.register(self.cmd_timer, Command("timer"))
        self.dp.message.register(self.cmd_list, Command("list"))
        self.dp.message.register(self.cmd_delete, Command("delete"))

    async def cmd_start(self, message: Message):
        """Обработчик команды /start"""
        try:
            user_id = message.from_user.id
            username = message.from_user.username or str(user_id)
            
            await self.db.add_user(user_id, username)
            
            await message.answer(
                "👋 Привет! Я бот для управления таймерами.\n\n"
                "Доступные команды:\n"
                "/timer <часы> - установить таймер\n"
                "/list - показать активные таймеры\n"
                "/delete <номер> - удалить таймер\n"
                "/help - показать справку"
            )
            logger.info(f"New user started bot: {user_id} ({username})")
            
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")

    async def cmd_help(self, message: Message):
        """Обработчик команды /help"""
        try:
            help_text = (
                "📝 Справка по командам:\n\n"
                "1️⃣ /timer <часы> - установить таймер\n"
                "   Пример: /timer 5 - установить таймер на 5 часов\n\n"
                "2️⃣ /list - показать все активные таймеры\n\n"
                "3️⃣ /delete <номер> - удалить таймер по его номеру\n"
                "   Пример: /delete 1 - удалить таймер №1\n\n"
                f"❗️ Максимум {self.config.max_timers} активных таймеров\n"
                f"⏰ Минимальное время: {self.config.min_duration} час\n"
                f"⏰ Максимальное время: {self.config.max_duration} часов"
            )
            await message.answer(help_text)
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")

    async def cmd_timer(self, message: Message):
        """Обработчик команды /timer"""
        try:
            user_id = message.from_user.id
            args = message.text.split()
            
            if len(args) != 2:
                await message.answer(
                    "❌ Неверный формат команды.\n"
                    "Используйте: /timer <часы>\n"
                    "Пример: /timer 5"
                )
                return

            try:
                duration = int(args[1])
            except ValueError:
                await message.answer("❌ Продолжительность должна быть целым числом часов.")
                return

            if not self.config.min_duration <= duration <= self.config.max_duration:
                await message.answer(
                    f"❌ Продолжительность должна быть от {self.config.min_duration} "
                    f"до {self.config.max_duration} часов."
                )
                return

            timer_id = await self.db.add_timer(user_id, duration)
            
            if timer_id is None:
                await message.answer(
                    f"❌ Достигнут лимит активных таймеров ({self.config.max_timers}).\n"
                    "Удалите неиспользуемые таймеры командой /delete"
                )
                return

            end_time = datetime.now() + timedelta(hours=duration)
            await message.answer(
                f"✅ Таймер установлен!\n"
                f"⏰ Завершится: {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"⌛️ Длительность: {duration} ч."
            )
            logger.info(f"Timer {timer_id} created by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in timer command: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")

    async def cmd_list(self, message: Message):
        """Обработчик команды /list"""
        try:
            user_id = message.from_user.id
            timers = await self.db.get_active_timers(user_id)
            
            if not timers:
                await message.answer("У вас нет активных таймеров.")
                return

            response = "📋 Ваши активные таймеры:\n\n"
            for timer in timers:
                end_time = datetime.fromtimestamp(timer['end_time'])
                remaining = end_time - datetime.now()
                hours = remaining.total_seconds() // 3600
                minutes = (remaining.total_seconds() % 3600) // 60
                
                response += (
                    f"🔔 Таймер #{timer['timer_number']}\n"
                    f"⏰ Завершится: {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                    f"⌛️ Осталось: {int(hours)}ч {int(minutes)}мин\n\n"
                )

            await message.answer(response)
            
        except Exception as e:
            logger.error(f"Error in list command: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")

    async def cmd_delete(self, message: Message):
        """Обработчик команды /delete"""
        try:
            user_id = message.from_user.id
            args = message.text.split()
            
            if len(args) != 2:
                await message.answer(
                    "❌ Неверный формат команды.\n"
                    "Используйте: /delete <номер>\n"
                    "Пример: /delete 1"
                )
                return

            try:
                timer_number = int(args[1])
            except ValueError:
                await message.answer("❌ Номер таймера должен быть целым числом.")
                return

            if await self.db.delete_timer(user_id, timer_number):
                await message.answer(f"✅ Таймер #{timer_number} удален.")
                logger.info(f"Timer {timer_number} deleted by user {user_id}")
            else:
                await message.answer(f"❌ Таймер #{timer_number} не найден.")
                
        except Exception as e:
            logger.error(f"Error in delete command: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")

    async def check_timers(self):
        """Проверка и обработка истекших таймеров"""
        while self.running:
            try:
                expired_timers = await self.db.check_expired_timers()
                
                for timer in expired_timers:
                    user_id = timer['user_id']
                    timer_number = timer['timer_number']
                    try:
                        await self.bot.send_message(
                            user_id,
                            f"⏰ Таймер #{timer_number} завершен!"
                        )
                        logger.info(f"Timer {timer_number} notification sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send timer notification: {e}")

                await asyncio.sleep(self.config.check_interval)
                
            except Exception as e:
                logger.error(f"Error in timer checker: {e}")
                await asyncio.sleep(10)  # Короткая пауза при ошибке

    async def maintenance_task(self):
        """Задача обслуживания базы данных"""
        while self.running:
            try:
                # Проверка целостности БД
                if not await self.db.check_database_integrity():
                    logger.error("Database integrity check failed")
                    # Попытка восстановления из последнего бэкапа
                    latest_backup = await self.backup.get_latest_backup()
                    if latest_backup:
                        if await self.backup.restore_from_backup(str(latest_backup)):
                            logger.info("Database restored from backup")
                        else:
                            logger.error("Failed to restore database from backup")

                # Создание бэкапа
                if await self.backup.create_backup():
                    self.backup.cleanup_old_backups(self.config.backup_keep_days)

                # Оптимизация БД
                await self.db.optimize_database()
                
                await asyncio.sleep(self.config.maintenance_interval)
                
            except Exception as e:
                logger.error(f"Error in maintenance task: {e}")
                await asyncio.sleep(60)  # Короткая пауза при ошибке

    async def start(self):
        """Запуск бота"""
        try:
            # Создаем таблицы в БД
            await self.db.create_tables()
            
            # Запускаем фоновые задачи
            asyncio.create_task(self.check_timers())
            asyncio.create_task(self.maintenance_task())
            
            # Запускаем бота
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
        finally:
            self.running = False

def setup_signal_handlers(timer_bot: TimerBot):
    """Настройка обработчиков сигналов"""
    def signal_handler(signum, frame):
        logger.info("Received signal to terminate")
        timer_bot.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Главная функция"""
    try:
        # Загружаем конфигурацию
        config = load_config()
        
        # Создаем экземпляр бота
        timer_bot = TimerBot(config)
        
        # Настраиваем обработчики сигналов
        setup_signal_handlers(timer_bot)
        
        # Запускаем бота
        logger.info("Starting bot...")
        await timer_bot.start()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
if __name__ == '__main__':
    config = load_config()
    timer_bot = TimerBot(config)
    setup_signal_handlers(timer_bot)
    asyncio.run(timer_bot.start())
