import uuid
from typing import List, Dict, Any, Optional
from src.core.logger import logger
from src.core.exceptions import DatabaseError
from src.clients.database_client import DatabaseClient

class BaseRepository:
    """
    Genel CRUD işlemlerini yürüten temel depo (repository) sınıfı.
    Tüm yeni tablolar için bu sınıftan miras alınabilir.
    """

    def __init__(self, db_client: DatabaseClient, table_name: str):
        self.db_client = db_client
        self.table_name = table_name

    def create(self, data: Dict[str, Any]) -> str:
        """Yeni bir kayıt oluşturur."""
        # Eğer id verilmemişse UUID oluştur
        if "id" not in data:
            data["id"] = str(uuid.uuid4())
        
        columns = list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        values = list(data.values())

        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                sql = f"INSERT INTO {self.table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                cursor.execute(sql, values)
                conn.commit()
                logger.debug(f"[+] Kayıt eklendi ({self.table_name}): {data['id']}")
                return data["id"]
        except Exception as e:
            logger.error(f"[X] {self.table_name}.create hatası: {e}")
            raise DatabaseError(str(e))

    def get(self, record_id: str) -> Optional[Dict[str, Any]]:
        """ID ile tek bir kayıt getirir."""
        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                sql = f"SELECT * FROM {self.table_name} WHERE id = ?"
                cursor.execute(sql, (record_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[X] {self.table_name}.get hatası: {e}")
            raise DatabaseError(str(e))

    def update(self, record_id: str, data: Dict[str, Any]) -> bool:
        """Kayıt günceller."""
        set_clause = ", ".join([f"{key} = ?" for key in data.keys()])
        values = list(data.values()) + [record_id]

        # Eğer tabloda updated_at varsa onu da otomatik güncelle
        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                # Tabloda updated_at kolonu var mı kontrol et
                cursor.execute(f"PRAGMA table_info({self.table_name})")
                columns = [col[1] for col in cursor.fetchall()]
                if 'updated_at' in columns and 'updated_at' not in data:
                    set_clause += ", updated_at = CURRENT_TIMESTAMP"
                
                sql = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"
                cursor.execute(sql, values)
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[X] {self.table_name}.update hatası: {e}")
            raise DatabaseError(str(e))

    def delete(self, record_id: str) -> bool:
        """Kayıt siler."""
        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                sql = f"DELETE FROM {self.table_name} WHERE id = ?"
                cursor.execute(sql, (record_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[X] {self.table_name}.delete hatası: {e}")
            raise DatabaseError(str(e))

    def list(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Kayıtları listeler, isteğe bağlı filtreleme yapar."""
        sql = f"SELECT * FROM {self.table_name}"
        values = []

        if filters:
            conditions = [f"{key} = ?" for key in filters.keys()]
            sql += " WHERE " + " AND ".join(conditions)
            values = list(filters.values())

        try:
            with self.db_client.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[X] {self.table_name}.list hatası: {e}")
            raise DatabaseError(str(e))
