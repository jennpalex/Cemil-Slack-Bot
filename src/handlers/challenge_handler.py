"""
Challenge Hub komut handler'ları.
"""

import asyncio
from slack_bolt import App
from src.core.logger import logger
from src.core.settings import get_settings
from src.core.rate_limiter import get_rate_limiter
from src.core.validators import ChallengeStartRequest, ChallengeJoinRequest
from src.commands import ChatManager
from src.services import ChallengeHubService
from src.repositories import UserRepository


def setup_challenge_handlers(
    app: App,
    challenge_service: ChallengeHubService,
    chat_manager: ChatManager,
    user_repo: UserRepository
):
    """Challenge handler'larını kaydeder."""
    settings = get_settings()
    rate_limiter = get_rate_limiter(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window
    )

    @app.command("/challenge")
    def handle_challenge_command(ack, body):
        """Challenge komutları."""
        ack()
        user_id = body["user_id"]
        channel_id = body["channel_id"]
        text = body.get("text", "").strip()

        # Komut parse et
        parts = text.split(maxsplit=1)
        if not parts:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=(
                    "📋 *Challenge Komutları:*\n\n"
                    "`/challenge start <takım> \"<tema>\" [süre] [zorluk]` - Yeni challenge başlat\n"
                    "`/challenge join [challenge_id]` - Challenge'a katıl\n"
                    "`/challenge status` - Challenge durumunu görüntüle\n\n"
                    "Örnek: `/challenge start 4 \"AI Chatbot\" 48 intermediate`"
                )
            )
            return

        subcommand = parts[0].lower()
        subcommand_text = parts[1] if len(parts) > 1 else ""

        # Kullanıcı bilgisini al
        try:
            user_data = user_repo.get_by_slack_id(user_id)
            user_name = user_data.get('full_name', user_id) if user_data else user_id
        except Exception:
            user_name = user_id

        logger.info(f"[>] /challenge {subcommand} komutu geldi | Kullanıcı: {user_name} ({user_id})")

        # Rate limiting
        allowed, error_msg = rate_limiter.is_allowed(user_id)
        if not allowed:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=error_msg
            )
            return

        if subcommand == "start":
            handle_start_challenge(subcommand_text, user_id, channel_id)
        elif subcommand == "join":
            handle_join_challenge(subcommand_text, user_id, channel_id)
        elif subcommand == "status":
            handle_challenge_status(user_id, channel_id)
        else:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=f"❌ Bilinmeyen komut: {subcommand}"
            )

    def handle_start_challenge(text: str, user_id: str, channel_id: str):
        """Challenge başlatma."""
        try:
            request = ChallengeStartRequest.parse_from_text(text)
        except ValueError as ve:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=f"❌ Format hatası: {str(ve)}\n\nÖrnek: `/challenge start 4 \"AI Chatbot\" 48 intermediate`"
            )
            return

        async def process_start():
            result = await challenge_service.start_challenge(
                creator_id=user_id,
                theme=request.theme,
                team_size=request.team_size,
                deadline_hours=request.deadline_hours,
                difficulty=request.difficulty
            )

            if result["success"]:
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=result["message"]
                )
            else:
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=result["message"]
                )

        asyncio.run(process_start())

    def handle_join_challenge(text: str, user_id: str, channel_id: str):
        """Challenge'a katılma."""
        try:
            request = ChallengeJoinRequest.parse_from_text(text)
        except ValueError as ve:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=f"❌ Format hatası: {str(ve)}"
            )
            return

        async def process_join():
            result = await challenge_service.join_challenge(
                challenge_id=request.challenge_id,
                user_id=user_id
            )

            if result["success"]:
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=result["message"]
                )
            else:
                error_msg = result["message"]
                if result.get("error_code") == "ALREADY_PARTICIPATING":
                    error_msg = (
                        "❌ *Zaten Bu Challenge'a Katıldınız*\n\n"
                        "Aynı challenge'a iki kez katılamazsınız. "
                        "Başka bir challenge'a katılabilir veya yeni bir challenge başlatabilirsiniz."
                    )
                
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=error_msg
                )

        asyncio.run(process_join())

    def handle_challenge_status(user_id: str, channel_id: str):
        """Challenge durumunu göster."""
        # TODO: Implement
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text="📊 Challenge durumu özelliği yakında eklenecek."
        )

    @app.action("challenge_join_button")
    def handle_challenge_join_button(ack, body):
        """Challenge'a katıl butonuna tıklama."""
        ack()
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        challenge_id = body["actions"][0]["value"]
        
        # Eğer zaten katıldıysa
        if challenge_id == "joined":
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text="✅ Zaten bu challenge'a katıldınız."
            )
            return
        
        # Kullanıcı bilgisini al
        try:
            user_data = user_repo.get_by_slack_id(user_id)
            user_name = user_data.get('full_name', user_id) if user_data else user_id
        except Exception:
            user_name = user_id
        
        logger.info(f"[>] Challenge join butonu tıklandı | Kullanıcı: {user_name} ({user_id}) | Challenge: {challenge_id}")
        
        async def process_join():
            result = await challenge_service.join_challenge(
                challenge_id=challenge_id,
                user_id=user_id
            )
            
            if result["success"]:
                # Başarılı mesajı gönder
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=result["message"]
                )
                
                # Mesajı güncelle - butonu disable et ve katılımcı sayısını güncelle
                try:
                    import copy
                    message_ts = body["message"]["ts"]
                    blocks = copy.deepcopy(body["message"]["blocks"])
                    
                    # Challenge bilgisini al (servis üzerinden)
                    from src.repositories import ChallengeHubRepository, ChallengeParticipantRepository
                    from src.clients import DatabaseClient
                    from src.core.settings import get_settings
                    
                    settings = get_settings()
                    db_client = DatabaseClient(db_path=settings.database_path)
                    hub_repo = ChallengeHubRepository(db_client)
                    participant_repo = ChallengeParticipantRepository(db_client)
                    
                    challenge = hub_repo.get(challenge_id)
                    if challenge:
                        participants = participant_repo.get_team_members(challenge_id)
                        participant_count = len(participants)
                        team_size = challenge["team_size"]
                        
                        # Butonu disable et veya kaldır
                        updated_blocks = []
                        for block in blocks:
                            if block.get("type") == "actions":
                                # Butonları güncelle
                                updated_elements = []
                                for element in block.get("elements", []):
                                    if element.get("action_id") == "challenge_join_button":
                                        if participant_count >= team_size:
                                            # Takım doldu - butonu kaldır
                                            continue
                                        else:
                                            # Butonu disable et
                                            element["text"]["text"] = "✅ Katıldınız"
                                            element["value"] = "joined"
                                            element["style"] = None
                                            element.pop("action_id", None)
                                            updated_elements.append(element)
                                    else:
                                        updated_elements.append(element)
                                
                                if updated_elements:
                                    block["elements"] = updated_elements
                                    updated_blocks.append(block)
                                # Eğer tüm butonlar kaldırıldıysa, actions block'unu ekleme
                            else:
                                # Context'i güncelle
                                if block.get("type") == "context" and challenge:
                                    block["elements"][0]["text"] = f"Challenge ID: `{challenge_id[:8]}...` | Durum: {participant_count}/{team_size} kişi"
                                updated_blocks.append(block)
                        
                        # Mesajı güncelle
                        chat_manager.update_message(
                            channel=channel_id,
                            ts=message_ts,
                            text="🔥 Yeni Challenge Açıldı!",
                            blocks=updated_blocks
                        )
                except Exception as e:
                    logger.debug(f"[i] Mesaj güncelleme hatası (normal): {e}")
                
            else:
                error_msg = result["message"]
                if result.get("error_code") == "ALREADY_PARTICIPATING":
                    error_msg = (
                        "❌ *Zaten Bu Challenge'a Katıldınız*\n\n"
                        "Aynı challenge'a iki kez katılamazsınız."
                    )
                elif result.get("error_code") == "TEAM_FULL":
                    error_msg = "❌ Bu challenge'ın takımı dolmuş."
                elif result.get("error_code") == "USER_HAS_ACTIVE_CHALLENGE":
                    error_msg = "❌ Zaten aktif bir challenge'ınız var. Önce onu tamamlayın."
                
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text=error_msg
                )
        
        asyncio.run(process_join())
