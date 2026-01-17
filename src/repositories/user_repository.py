from typing import Optional, Dict, Any
from src.repositories.base_repository import BaseRepository
from src.clients.database_client import DatabaseClient
from src.core.logger import logger
from src.core.exceptions import DatabaseError

class UserRepository(BaseRepository):
    """
    Kullanıcılar tablosuna özel veri erişim sınıfı.
    """

    def __init__(self, db_client: DatabaseClient):
        super().__init__(db_client, "users")

    def get_by_slack_id(self, slack_id: str) -> Optional[Dict[str, Any]]:
        """Slack ID'ye göre kullanıcı getirir."""
        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                sql = f"SELECT * FROM {self.table_name} WHERE slack_id = ?"
                cursor.execute(sql, (slack_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[X] UserRepository.get_by_slack_id hatası: {e}")
            raise DatabaseError(str(e))

    def update_by_slack_id(self, slack_id: str, data: Dict[str, Any]) -> bool:
        """Slack ID'ye göre kullanıcıyı günceller."""
        set_clause = ", ".join([f"{key} = ?" for key in data.keys()])
        values = list(data.values()) + [slack_id]

        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                sql = f"UPDATE {self.table_name} SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE slack_id = ?"
                cursor.execute(sql, values)
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[X] UserRepository.update_by_slack_id hatası: {e}")
            raise DatabaseError(str(e))
