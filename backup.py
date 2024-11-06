import shutil
from datetime import datetime
from pathlib import Path
import asyncio
import aiosqlite
from logger import setup_logger

logger = setup_logger('backup')

class DatabaseBackup:
    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)

    async def create_backup(self) -> bool:
        """Создает резервную копию базы данных"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"backup_{timestamp}.db"

            async with aiosqlite.connect(self.db_path) as db:
                # Проверяем целостность перед backup
                async with db.execute("PRAGMA integrity_check") as cursor:
                    result = await cursor.fetchone()
                    if result[0] != "ok":
                        logger.error(f"Database integrity check failed: {result[0]}")
                        return False

                # Создаем backup
                await db.execute("VACUUM INTO ?", (str(backup_path),))

            logger.info(f"Backup created successfully: {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return False

    def cleanup_old_backups(self, keep_days: int = 7):
        """Удаляет старые резервные копии"""
        try:
            current_time = datetime.now()
            for backup_file in self.backup_dir.glob("backup_*.db"):
                file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                if (current_time - file_time).days > keep_days:
                    backup_file.unlink()
                    logger.info(f"Deleted old backup: {backup_file}")

        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")

    async def restore_from_backup(self, backup_path: str) -> bool:
        """Восстанавливает базу данных из резервной копии"""
        try:
            # Создаем временную копию текущей базы
            temp_backup = self.db_path + ".temp"
            shutil.copy2(self.db_path, temp_backup)

            try:
                # Восстанавливаем из backup
                shutil.copy2(backup_path, self.db_path)
                
                # Проверяем целостность восстановленной базы
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("PRAGMA integrity_check") as cursor:
                        result = await cursor.fetchone()
                        if result[0] != "ok":
                            raise Exception("Restored database integrity check failed")

                # Удаляем временную копию
                Path(temp_backup).unlink()
                logger.info(f"Database restored successfully from {backup_path}")
                return True

            except Exception as e:
                # При ошибке восстанавливаем из временной копии
                shutil.copy2(temp_backup, self.db_path)
                Path(temp_backup).unlink()
                raise e

        except Exception as e:
            logger.error(f"Database restoration failed: {e}")
            return False

    async def get_latest_backup(self) -> Optional[Path]:
        """Возвращает путь к последнему бэкапу"""
        try:
            backup_files = list(self.backup_dir.glob("backup_*.db"))
            if backup_files:
                return max(backup_files, key=lambda x: x.stat().st_mtime)
            return None
        except Exception as e:
            logger.error(f"Failed to get latest backup: {e}")
            return None
