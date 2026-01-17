from src.repositories.base_repository import BaseRepository
from src.clients.database_client import DatabaseClient

class PollRepository(BaseRepository):
    """
    Oylama başlıkları (Polls) için veritabanı erişim sınıfı.
    """

    def __init__(self, db_client: DatabaseClient):
        super().__init__(db_client, "polls")
