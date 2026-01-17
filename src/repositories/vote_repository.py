from src.repositories.base_repository import BaseRepository
from src.clients.database_client import DatabaseClient

class VoteRepository(BaseRepository):
    """
    Kullanıcı oyları (Votes) için veritabanı erişim sınıfı.
    """

    def __init__(self, db_client: DatabaseClient):
        super().__init__(db_client, "votes")

    def has_user_voted(self, poll_id: str, user_id: str, option_index: int = None) -> bool:
        """
        Kullanıcının belirli bir oylamada (veya belirli bir seçenekte) oy verip vermediğini kontrol eder.
        """
        query = "SELECT COUNT(*) as count FROM votes WHERE poll_id = ? AND user_id = ?"
        params = [poll_id, user_id]
        
        if option_index is not None:
            query += " AND option_index = ?"
            params.append(option_index)
            
        result = self.db.execute_query(query, params)
        return result[0]["count"] > 0 if result else False
