import aiosqlite
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
from logger import setup_logger

logger = setup_logger('database')

class Database:
    def __init__(self, db_name: str = "timer_bot.db"):
        self.db_name = db_name

    async def create_tables(self):
        """Создает необходимые таблицы в базе данных"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    active_timers INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS timers (
                    timer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    duration INTEGER,
                    timer_number INTEGER,
                    status TEXT DEFAULT 'active',
                    notified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            await db.commit()

    async def check_database_integrity(self) -> bool:
        """Проверяет целостность базы данных"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute("PRAGMA integrity_check") as cursor:
                    result = await cursor.fetchone()
                    if result[0] != "ok":
                        logger.error(f"Database integrity check failed: {result[0]}")
                        return False
                    return True
        except Exception as e:
            logger.error(f"Database integrity check error: {e}")
            return False

    async def optimize_database(self):
        """Оптимизирует базу данных"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("PRAGMA optimize")
                await db.execute("VACUUM")
                logger.info("Database optimization completed")
        except Exception as e:
            logger.error(f"Database optimization error: {e}")

    async def add_user(self, user_id: int, username: str) -> bool:
        """Добавляет нового пользователя"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
                    (user_id, username)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    async def add_timer(self, user_id: int, duration: int) -> Optional[int]:
        """Добавляет новый таймер"""
        try:
            start_time = datetime.now()
            end_time = start_time + timedelta(hours=duration)
            
            async with aiosqlite.connect(self.db_name) as db:
                # Получаем количество активных таймеров
                async with db.execute(
                    'SELECT COUNT(*) FROM timers WHERE user_id = ? AND status = "active"',
                    (user_id,)
                ) as cursor:
                    if (await cursor.fetchone())[0] >= 3:
                        return None

                # Добавляем таймер
                cursor = await db.execute('''
                    INSERT INTO timers (
                        user_id, start_time, end_time, duration, timer_number, status
                    ) VALUES (?, ?, ?, ?, 
                        (SELECT COALESCE(MAX(timer_number), 0) + 1 
                         FROM timers WHERE user_id = ?), 
                        'active'
                    )
                ''', (
                    user_id, 
                    start_time.timestamp(), 
                    end_time.timestamp(),
                    duration,
                    user_id
                ))
                
                # Обновляем количество активных таймеров
                await db.execute('''
                    UPDATE users 
                    SET active_timers = (
                        SELECT COUNT(*) 
                        FROM timers 
                        WHERE user_id = ? AND status = 'active'
                    )
                    WHERE user_id = ?
                ''', (user_id, user_id))
                
                await db.commit()
                return cursor.lastrowid

        except Exception as e:
            logger.error(f"Error adding timer: {e}")
            return None

    async def get_active_timers(self, user_id: int) -> List[Dict]:
        """Получает список активных таймеров пользователя"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute('''
                    SELECT * FROM timers 
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY timer_number
                ''', (user_id,)) as cursor:
                    return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting active timers: {e}")
            return []

    async def check_expired_timers(self) -> List[Dict]:
        """Проверяет и возвращает истекшие таймеры"""
        try:
            current_time = datetime.now().timestamp()
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute('''
                    SELECT t.*, u.username 
                    FROM timers t
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.status = 'active' 
                    AND t.end_time <= ?
                    AND t.notified = FALSE
                ''', (current_time,)) as cursor:
                    expired_timers = [dict(row) for row in await cursor.fetchall()]

                # Обновляем статус истекших таймеров
                if expired_timers:
                    timer_ids = [timer['timer_id'] for timer in expired_timers]
                    placeholders = ','.join('?' * len(timer_ids))
                    await db.execute(f'''
                        UPDATE timers 
                        SET status = 'completed', notified = TRUE 
                        WHERE timer_id IN ({placeholders})
                    ''', timer_ids)
                    
                    # Обновляем количество активных таймеров для пользователей
                    await db.execute('''
                        UPDATE users 
                        SET active_timers = (
                            SELECT COUNT(*) 
                            FROM timers 
                            WHERE user_id = users.user_id AND status = 'active'
                        )
                    ''')
                    
                    await db.commit()

                return expired_timers

        except Exception as e:
            logger.error(f"Error checking expired timers: {e}")
            return []

    async def delete_timer(self, user_id: int, timer_number: int) -> bool:
        """Удаляет таймер пользователя"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute('''
                    UPDATE timers 
                    SET status = 'cancelled' 
                    WHERE user_id = ? AND timer_number = ? AND status = 'active'
                ''', (user_id, timer_number))
                
                # Обновляем количество активных таймеров
                await db.execute('''
                    UPDATE users 
                    SET active_timers = (
                        SELECT COUNT(*) 
                        FROM timers 
                        WHERE user_id = ? AND status = 'active'
                    )
                    WHERE user_id = ?
                ''', (user_id, user_id))
                
                await db.commit()
                return True

        except Exception as e:
            logger.error(f"Error deleting timer: {e}")
            return False
