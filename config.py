from dataclasses import dataclass
from os import getenv
from dotenv import load_dotenv

@dataclass
class Config:
    bot_token: str
    max_timers: int = 3  # максимальное количество таймеров на пользователя
    max_duration: int = 168  # максимальная длительность таймера в часах (1 неделя)
    min_duration: int = 1  # минимальная длительность таймера в часах
    backup_interval: int = 24 * 60 * 60  # интервал создания бэкапов (24 часа)
    maintenance_interval: int = 12 * 60 * 60  # интервал обслуживания БД (12 часов)
    backup_keep_days: int = 7  # сколько дней хранить бэкапы
    check_interval: int = 60  # интервал проверки таймеров (в секундах)

def load_config() -> Config:
    load_dotenv()
    
    token = getenv('BOT_TOKEN')
    if not token:
        raise ValueError("BOT_TOKEN не найден в .env файле")
        
    return Config(bot_token=token)
