from typing import Optional, Dict, Any, List
from src.repositories.base_repository import BaseRepository
from src.clients.database_client import DatabaseClient
from src.core.logger import logger


class ChallengeEvaluatorRepository(BaseRepository):
    """Challenge değerlendiricileri için veritabanı erişim sınıfı."""

    def __init__(self, db_client: DatabaseClient):
        super().__init__(db_client, "challenge_evaluators")

    def get_by_evaluation(self, evaluation_id: str) -> List[Dict[str, Any]]:
        """Değerlendirmeye ait tüm değerlendiricileri getirir."""
        return self.list(filters={"evaluation_id": evaluation_id})
    
    def list_by_evaluation(self, evaluation_id: str) -> List[Dict[str, Any]]:
        """Değerlendirmeye ait tüm değerlendiricileri getirir (alias)."""
        return self.get_by_evaluation(evaluation_id)

    def get_by_evaluation_and_user(
        self, 
        evaluation_id: str, 
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Belirli bir kullanıcının değerlendirmesini getirir."""
        evaluators = self.list(filters={
            "evaluation_id": evaluation_id,
            "user_id": user_id
        })
        return evaluators[0] if evaluators else None

    def has_voted(self, evaluation_id: str, user_id: str) -> bool:
        """Kullanıcı oy vermiş mi kontrol eder."""
        evaluator = self.get_by_evaluation_and_user(evaluation_id, user_id)
        return evaluator is not None and evaluator.get("vote") is not None

    def count_evaluators(self, evaluation_id: str) -> int:
        """Değerlendirmedeki toplam değerlendirici sayısını döner."""
        evaluators = self.get_by_evaluation(evaluation_id)
        return len(evaluators)

    def get_votes(self, evaluation_id: str) -> Dict[str, int]:
        """Değerlendirmenin oy sayılarını döner."""
        evaluators = self.get_by_evaluation(evaluation_id)
        true_count = sum(1 for e in evaluators if e.get("vote") == "true")
        false_count = sum(1 for e in evaluators if e.get("vote") == "false")
        return {"true": true_count, "false": false_count}
