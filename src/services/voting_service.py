import json
from typing import List, Dict, Any, Optional
from src.core.logger import logger
from src.core.exceptions import CemilBotError
from src.commands import ChatManager
from src.repositories import PollRepository, VoteRepository
from src.clients import CronClient

class VotingService:
    """
    Oylama süreçlerini (Açma, Oy Verme, Sonuçlandırma) yöneten servis.
    """

    def __init__(
        self, 
        chat_manager: ChatManager, 
        poll_repo: PollRepository, 
        vote_repo: VoteRepository,
        cron_client: CronClient
    ):
        self.chat = chat_manager
        self.poll_repo = poll_repo
        self.vote_repo = vote_repo
        self.cron = cron_client

    async def create_poll(
        self, 
        channel_id: str, 
        topic: str, 
        options: List[str], 
        creator_id: str, 
        allow_multiple: bool = False,
        duration_minutes: int = 60
    ):
        """Yeni bir oylama başlatır."""
        try:
            logger.info(f"[>] Oylama başlatılıyor: {topic}")
            
            poll_id = self.poll_repo.create({
                "topic": topic,
                "options": json.dumps(options),
                "creator_id": creator_id,
                "allow_multiple": 1 if allow_multiple else 0,
                "is_closed": 0
            })

            # Slack Mesajı Oluştur (ASCII ONLY)
            blocks = self._build_poll_blocks(poll_id, topic, options, allow_multiple)
            
            response = self.chat.post_message(
                channel=channel_id,
                text=f"Yeni Oylama: {topic}",
                blocks=blocks
            )
            
            # Zamanlayıcı ekle (Otonom Kapanış)
            self.cron.add_once_job(
                func=self.close_poll,
                delay_minutes=duration_minutes,
                job_id=f"close_poll_{poll_id}",
                args=[channel_id, poll_id]
            )

            return poll_id

        except Exception as e:
            logger.error(f"[X] VotingService.create_poll hatası: {e}")
            raise CemilBotError(f"Oylama başlatılamadı: {e}")

    def cast_vote(self, poll_id: str, user_id: str, option_index: int) -> Dict[str, Any]:
        """
        Kullanıcının oyunu işler. Toggle (Aç/Kapa) ve Switch (Değiştir) mantığı içerir.
        """
        try:
            poll = self.poll_repo.get(poll_id)
            if not poll or poll["is_closed"]:
                return {"success": False, "message": "Bu oylama kapalı veya bulunamadı."}

            # 1. Kullanıcı bu seçeneğe daha önce oy vermiş mi? (Toggle Mantığı)
            if self.vote_repo.has_user_voted(poll_id, user_id, option_index):
                # Oyu geri al (Sil)
                self.vote_repo.delete_vote(poll_id, user_id, option_index)
                return {"success": True, "message": "Oyunuz geri alındı."}

            # 2. Çoklu oy kapalıysa, diğer oyları temizle (Switch Mantığı)
            if not poll["allow_multiple"]:
                # Kullanıcının önceki tüm oylarını sil
                self.vote_repo.delete_all_user_votes(poll_id, user_id)

            # 3. Yeni oyu kaydet
            self.vote_repo.create({
                "poll_id": poll_id,
                "user_id": user_id,
                "option_index": option_index
            })

            return {"success": True, "message": "Oyunuz kaydedildi!"}

        except Exception as e:
            logger.error(f"[X] VotingService.cast_vote hatası: {e}")
            return {"success": False, "message": "Oy pusulanda bir sorun çıktı, tekrar dener misin? 🗳️"}

    async def close_poll(self, channel_id: str, poll_id: str):
        """Oylamayı kapatır ve sonuçları açıklar."""
        try:
            poll = self.poll_repo.get(poll_id)
            if not poll or poll["is_closed"]:
                return

            # Oylamayı veritabanında kapat
            self.poll_repo.update(poll_id, {"is_closed": 1})

            # Sonuçları hesapla
            results = self._calculate_results(poll_id, json.loads(poll["options"]))
            
            # Sonuç Mesajı (ASCII Grafik)
            result_text = self._build_result_text(poll["topic"], results)
            
            self.chat.post_message(
                channel=channel_id,
                text=f"Oylama Sonuçlandı: {poll['topic']}",
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"[v] *OYLAMA SONUÇLANDI*\n\n{result_text}"}
                    }
                ]
            )
            logger.info(f"[+] Oylama başarıyla sonuçlandırıldı: {poll_id}")

        except Exception as e:
            logger.error(f"[X] VotingService.close_poll hatası: {e}")

    def _build_poll_blocks(self, poll_id: str, topic: str, options: List[str], allow_multiple: bool) -> List[Dict]:
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"[*] *{topic}*\n_Oylamak için aşağıdaki butonları kullanın._"}
            },
            {"type": "divider"}
        ]
        
        for i, opt in enumerate(options):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"[{i+1}] {opt}"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Oy Ver"},
                    "value": f"vote_{poll_id}_{i}",
                    "action_id": f"poll_vote_{i}"
                }
            })
            
        policy_info = "Çoklu oy atabilirsiniz." if allow_multiple else "Yalnızca bir seçim yapabilirsiniz."
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"[i] Bilgi: {policy_info}"}]
        })
        
        return blocks

    def _calculate_results(self, poll_id: str, options: List[str]) -> List[Dict]:
        query = "SELECT option_index, COUNT(*) as count FROM votes WHERE poll_id = ? GROUP BY option_index"
        
        counts_map = {}
        try:
            with self.poll_repo.db_client.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, [poll_id])
                rows = cursor.fetchall()
                for row in rows:
                    counts_map[row["option_index"]] = row["count"]
        except Exception as e:
            logger.error(f"[X] VotingService._calculate_results hatası: {e}")

        total_votes = sum(counts_map.values())
        
        results = []
        for i, opt in enumerate(options):
            count = counts_map.get(i, 0)
            percent = (count / total_votes * 100) if total_votes > 0 else 0
            results.append({
                "option": opt,
                "count": count,
                "percent": percent
            })
        return results

    def _build_result_text(self, topic: str, results: List[Dict]) -> str:
        text = f"[*] *Konu:* {topic}\n\n"
        for res in results:
            bar_count = int(res["percent"] / 10)
            bar = "=" * bar_count + "-" * (10 - bar_count)
            text += f"{res['option']}\n[{bar}] %{res['percent']:.1f} ({res['count']} Oy)\n\n"
        return text
