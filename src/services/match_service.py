import os
import asyncio
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from src.core.logger import logger
from src.core.exceptions import CemilBotError
from src.commands import ChatManager, ConversationManager
from src.clients import GroqClient, CronClient
from src.repositories import MatchRepository

class CoffeeMatchService:
    """
    Kullanıcılar arasında kahve eşleşmesi ve moderasyonunu yöneten servis.
    Bekleme havuzu (waiting pool) sistemi ile akıllı eşleştirme yapar.
    """

    def __init__(
        self, 
        chat_manager: ChatManager, 
        conv_manager: ConversationManager, 
        groq_client: GroqClient, 
        cron_client: CronClient,
        match_repo: MatchRepository
    ):
        self.chat = chat_manager
        self.conv = conv_manager
        self.groq = groq_client
        self.cron = cron_client
        self.match_repo = match_repo
        self.admin_channel = os.environ.get("ADMIN_CHANNEL_ID")
        
        # Bekleme Havuzu ve Rate Limiting
        self.waiting_pool: List[str] = []  # Bekleyen kullanıcı ID'leri
        self.last_request_time: Dict[str, datetime] = {}  # user_id -> son istek zamanı
        self.pool_timeout_jobs: Dict[str, str] = {}  # user_id -> cron job_id

    def can_request_coffee(self, user_id: str) -> tuple[bool, Optional[str]]:
        """
        Kullanıcının kahve isteği yapıp yapamayacağını kontrol eder.
        Returns: (izin_var_mı, hata_mesajı)
        """
        # Rate limiting: 5 dakikada bir istek
        if user_id in self.last_request_time:
            elapsed = datetime.now() - self.last_request_time[user_id]
            if elapsed < timedelta(minutes=5):
                remaining = 5 - int(elapsed.total_seconds() / 60)
                return False, f"⏳ Bir sonraki kahve isteğinizi {remaining} dakika sonra yapabilirsiniz."
        
        # Zaten havuzda mı?
        if user_id in self.waiting_pool:
            return False, "⏳ Zaten kahve havuzunda bekliyorsunuz. Eşleşme için sabırlı olun!"
        
        return True, None

    async def request_coffee(self, user_id: str, channel_id: str, user_name: str = None) -> str:
        """
        Kullanıcının kahve isteğini işler.
        Returns: Kullanıcıya gösterilecek mesaj
        """
        if not user_name:
            user_name = user_id
        
        # İzin kontrolü
        can_request, error_msg = self.can_request_coffee(user_id)
        if not can_request:
            logger.info(f"[!] Kahve isteği reddedildi | Kullanıcı: {user_name} ({user_id}) | Sebep: {error_msg}")
            return error_msg
        
        # Son istek zamanını kaydet
        self.last_request_time[user_id] = datetime.now()
        
        # CRITICAL: Önce havuzda olup olmadığını tekrar kontrol et (race condition önleme)
        if user_id in self.waiting_pool:
            logger.warning(f"[!] Kullanıcı zaten havuzda | Kullanıcı: {user_name} ({user_id})")
            return "⏳ Zaten kahve havuzunda bekliyorsunuz. Eşleşme için sabırlı olun!"
        
        # Havuzda başka biri var mı?
        if self.waiting_pool:
            # Eşleşme yap!
            partner_id = self.waiting_pool.pop(0)
            
            # Partner'ın timeout job'ını iptal et
            if partner_id in self.pool_timeout_jobs:
                removed = self.cron.remove_job(self.pool_timeout_jobs[partner_id])
                if removed:
                    logger.info(f"[i] Partner timeout job iptal edildi | Partner: {partner_id}")
                del self.pool_timeout_jobs[partner_id]
            
            # Partner ismini al
            try:
                partner_info = self.chat.client.users_info(user=partner_id)
                partner_name = partner_info.get("user", {}).get("real_name", partner_id) if partner_info.get("ok") else partner_id
            except Exception as e:
                logger.warning(f"[!] Partner ismi alınamadı: {e}")
                partner_name = partner_id
            
            # Eşleşmeyi başlat
            await self.start_match(user_id, partner_id, user_name, partner_name)
            
            logger.info(f"[<>] KAHVE EŞLEŞMESİ | {user_name} ({user_id}) <-> {partner_name} ({partner_id})")
            return f"✅ Harika! Bir kahve arkadaşı bulduk. Özel sohbet kanalınız açılıyor... ☕"
        
        else:
            # Havuza ekle (tekrar kontrol ile - race condition önleme)
            if user_id not in self.waiting_pool:
                self.waiting_pool.append(user_id)
                
                # 5 dakika sonra havuzdan çıkar
                job_id = f"coffee_timeout_{user_id}"
                self.cron.add_once_job(
                    func=self._timeout_user,
                    delay_minutes=5,
                    job_id=job_id,
                    args=[user_id]
                )
                self.pool_timeout_jobs[user_id] = job_id
                
                logger.info(f"[i] Kullanıcı kahve havuzuna eklendi | Kullanıcı: {user_name} ({user_id}) | Bekleyen: {len(self.waiting_pool)} kişi")
                return (
                    "☕ Kahve isteğiniz alındı! \\n\\n"
                    "5 dakika içinde başka biri de kahve isterse eşleşeceksiniz. \\n"
                    "Eğer kimse çıkmazsa istek otomatik olarak iptal edilecek. ⏳"
                )
            else:
                logger.warning(f"[!] Kullanıcı zaten havuzda (race condition) | Kullanıcı: {user_name} ({user_id})")
                return "⏳ Zaten kahve havuzunda bekliyorsunuz. Eşleşme için sabırlı olun!"

    def _timeout_user(self, user_id: str):
        """5 dakika içinde eşleşme olmayan kullanıcıyı havuzdan çıkarır."""
        # Önce havuzda olup olmadığını kontrol et
        if user_id not in self.waiting_pool:
            logger.debug(f"[i] Kullanıcı zaten havuzda değil (muhtemelen eşleşti) | Kullanıcı: {user_id}")
            # Cleanup yap
            if user_id in self.pool_timeout_jobs:
                del self.pool_timeout_jobs[user_id]
            if user_id in self.last_request_time:
                del self.last_request_time[user_id]
            return
        
        # Havuzdan çıkar
        self.waiting_pool.remove(user_id)
        
        # Kullanıcı ismini al
        try:
            user_info = self.chat.client.users_info(user=user_id)
            user_name = user_info.get("user", {}).get("real_name", user_id) if user_info.get("ok") else user_id
        except Exception as e:
            logger.warning(f"[!] Kullanıcı ismi alınamadı: {e}")
            user_name = user_id
        
        logger.info(f"[!] Kahve isteği zaman aşımı | Kullanıcı: {user_name} ({user_id}) | 5 dakika içinde eşleşme bulunamadı")
        
        # ÖNEMLİ: Timeout olduğunda last_request_time'ı temizle
        # Böylece kullanıcı hemen tekrar deneyebilir (rate limiting engellemesin)
        if user_id in self.last_request_time:
            del self.last_request_time[user_id]
            logger.info(f"[i] Rate limiting temizlendi | Kullanıcı: {user_name} ({user_id}) | Tekrar deneyebilir")
        
        # Kullanıcıya bilgi mesajı gönder
        try:
            dm_channel = self.conv.open_conversation(users=[user_id])
            self.chat.post_message(
                channel=dm_channel["id"],
                text="⏰ Kahve isteğiniz zaman aşımına uğradı. 5 dakika içinde eşleşme bulunamadı. Tekrar denemek isterseniz `/kahve` yazabilirsiniz!"
            )
            logger.debug(f"[i] Timeout mesajı gönderildi | Kullanıcı: {user_name} ({user_id})")
        except Exception as e:
            logger.error(f"[X] Timeout mesajı gönderilemedi: {e}")
        
        # Cleanup
        if user_id in self.pool_timeout_jobs:
            del self.pool_timeout_jobs[user_id]

    async def start_match(self, user_id1: str, user_id2: str, user_name1: str = None, user_name2: str = None):
        """
        İki kullanıcıyı eşleştirir, grup açar ve buzları eritir.
        """
        try:
            # Kullanıcı isimlerini al
            if not user_name1:
                try:
                    user_info1 = self.chat.client.users_info(user=user_id1)
                    user_name1 = user_info1.get("user", {}).get("real_name", user_id1) if user_info1.get("ok") else user_id1
                except:
                    user_name1 = user_id1
            
            if not user_name2:
                try:
                    user_info2 = self.chat.client.users_info(user=user_id2)
                    user_name2 = user_info2.get("user", {}).get("real_name", user_id2) if user_info2.get("ok") else user_id2
                except:
                    user_name2 = user_id2
            
            logger.info(f"[>] Kahve eşleşmesi başlatılıyor | {user_name1} ({user_id1}) <-> {user_name2} ({user_id2})")
            
            # 1. Grup konuşması aç
            channel = self.conv.open_conversation(users=[user_id1, user_id2])
            channel_id = channel["id"]
            logger.info(f"[+] Özel grup oluşturuldu | Kanal: {channel_id} | {user_name1} & {user_name2}")

            # 2. Veritabanına kaydet
            match_id = self.match_repo.create({
                "channel_id": channel_id,
                "user1_id": user_id1,
                "user2_id": user_id2,
                "status": "active"
            })

            # 3. Ice Breaker mesajı oluştur
            system_prompt = (
                "Sen Cemil'sin, bir topluluk asistanısın. Görevin birbiriyle eşleşen iki iş arkadaşı için "
                "kısa, eğlenceli ve samimi bir tanışma mesajı yazmak. "
                "ÖNEMLİ: Hiçbir emoji veya ASCII olmayan karakter kullanma. "
                "Sadece ASCII (Harfler, sayılar ve [i], [c], [>], == gibi işaretler) kullan."
            )
            user_prompt = f"Şu iki kullanıcı az önce kahve için eşleşti: <@{user_id1}> ve <@{user_id2}>. Onlara güzel bir selam ver."
            
            ice_breaker = await self.groq.quick_ask(system_prompt, user_prompt)

            # 4. Mesajı kanala gönder
            self.chat.post_message(
                channel=channel_id,
                text=ice_breaker,
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"[c] *Kahve Eşleşmesi:* \n\n{ice_breaker}"}
                    },
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "[i] Bu kanal 5 dakika sonra otomatik olarak kapatılacaktır."}]
                    }
                ]
            )

            # 5. 5 dakika sonra kapatma görevi planla
            self.cron.add_once_job(
                func=self.close_match,
                delay_minutes=5,
                job_id=f"close_match_{channel_id}",
                args=[channel_id, match_id]
            )
            logger.info(f"[i] 5 dakika sonra kapatma görevi planlandı | Kanal: {channel_id} | {user_name1} & {user_name2}")

        except Exception as e:
            logger.error(f"[X] CoffeeMatchService.start_match hatası: {e}")
            raise CemilBotError(f"Eşleşme başlatılamadı: {e}")

    async def close_match(self, channel_id: str, match_id: str):
        """Sohbet özetini çıkarır, admini bilgilendirir ve grubu kapatır."""
        try:
            # Kullanıcı isimlerini al
            match_data = self.match_repo.get(match_id)
            try:
                user_info1 = self.chat.client.users_info(user=match_data['user1_id'])
                user_name1 = user_info1.get("user", {}).get("real_name", match_data['user1_id']) if user_info1.get("ok") else match_data['user1_id']
            except:
                user_name1 = match_data['user1_id']
            try:
                user_info2 = self.chat.client.users_info(user=match_data['user2_id'])
                user_name2 = user_info2.get("user", {}).get("real_name", match_data['user2_id']) if user_info2.get("ok") else match_data['user2_id']
            except:
                user_name2 = match_data['user2_id']
            
            logger.info(f"[>] Eşleşme grubu kapatılıyor | Kanal: {channel_id} | {user_name1} ({match_data['user1_id']}) & {user_name2} ({match_data['user2_id']})")
            
            # 1. Sohbet geçmişini al
            messages = self.conv.get_history(channel_id=channel_id, limit=50)
            
            # 2. Mesajları temizle
            user_messages = []
            for msg in messages:
                if not msg.get("bot_id") and msg.get("type") == "message":
                    user_text = msg.get("text", "")
                    user_messages.append(f"Kullanıcı: {user_text}")

            conversation_text = "\n".join(user_messages) if user_messages else "Konuşma yapılmadı."

            # 3. LLM ile Özet Çıkar
            summary = "Eşleşme süresince herhangi bir konuşma gerçekleşmedi."
            if user_messages:
                system_prompt = "Sen bir analiz asistanısın. Sana sunulan sohbet geçmişini analiz et ve konuşulan konuları bir cümleyle özetle. Sadece ASCII karakterler kullan."
                summary = await self.groq.quick_ask(system_prompt, f"Sohbet Geçmişi:\n{conversation_text}")

            # 4. Veritabanını Güncelle
            self.match_repo.update(match_id, {
                "status": "closed",
                "summary": summary
            })

            # 5. Admin Kanalını Bilgilendir
            if self.admin_channel:
                match_data = self.match_repo.get(match_id)
                admin_msg = (
                    f"[!] *EŞLEŞME ÖZETİ RAPORU*\n"
                    f"== Kanal: {channel_id}\n"
                    f"== Katılımcılar: <@{match_data['user1_id']}> & <@{match_data['user2_id']}>\n"
                    f"== Özet: {summary}"
                )
                self.chat.post_message(channel=self.admin_channel, text=admin_msg)

            # 6. Kapanış mesajı gönder (grup DM'de)
            self.chat.post_message(
                channel=channel_id,
                text=(
                    "[>] *Süremiz doldu. Bu sohbet sona erdi. Görüşmek üzere!*\n\n"
                    "ℹ️ *Önemli:* Bu grup DM'den çıkmak için:\n"
                    "1. Sol menüde bu konuşmayı bulun\n"
                    "2. Sağ tıklayın ve 'Leave conversation' seçeneğini seçin\n"
                    "3. Veya mobilde konuşma ayarlarından 'Leave' butonuna tıklayın"
                )
            )
            
            # 7. Her kullanıcıya ayrı DM gönder (grup DM'den çıkmaları için)
            try:
                # Kullanıcı 1'e DM gönder
                dm_channel1 = self.conv.open_conversation(users=[match_data['user1_id']])
                self.chat.post_message(
                    channel=dm_channel1["id"],
                    text=(
                        f"☕ *Kahve Eşleşmesi Sonlandı*\n\n"
                        f"<@{match_data['user1_id']}> ve <@{match_data['user2_id']}> arasındaki eşleşme süresi doldu.\n\n"
                        f"💡 *Grup DM'den çıkmak için:*\n"
                        f"• Sol menüde grup DM'i bulun\n"
                        f"• Sağ tıklayın → 'Leave conversation'\n"
                        f"• Veya mobilde konuşma ayarlarından 'Leave' butonuna tıklayın\n\n"
                        f"Yeni bir eşleşme için `/kahve` komutunu kullanabilirsiniz! ☕"
                    )
                )
                logger.debug(f"[i] Kapanış DM'i gönderildi | Kullanıcı: {user_name1} ({match_data['user1_id']})")
            except Exception as e:
                logger.warning(f"[!] Kullanıcı 1'e DM gönderilemedi: {e}")
            
            try:
                # Kullanıcı 2'ye DM gönder
                dm_channel2 = self.conv.open_conversation(users=[match_data['user2_id']])
                self.chat.post_message(
                    channel=dm_channel2["id"],
                    text=(
                        f"☕ *Kahve Eşleşmesi Sonlandı*\n\n"
                        f"<@{match_data['user1_id']}> ve <@{match_data['user2_id']}> arasındaki eşleşme süresi doldu.\n\n"
                        f"💡 *Grup DM'den çıkmak için:*\n"
                        f"• Sol menüde grup DM'i bulun\n"
                        f"• Sağ tıklayın → 'Leave conversation'\n"
                        f"• Veya mobilde konuşma ayarlarından 'Leave' butonuna tıklayın\n\n"
                        f"Yeni bir eşleşme için `/kahve` komutunu kullanabilirsiniz! ☕"
                    )
                )
                logger.debug(f"[i] Kapanış DM'i gönderildi | Kullanıcı: {user_name2} ({match_data['user2_id']})")
            except Exception as e:
                logger.warning(f"[!] Kullanıcı 2'ye DM gönderilemedi: {e}")
            
            # Kapanış mesajının gönderilmesi için kısa bir bekleme
            await asyncio.sleep(2)
            
            # Önce conversations.close dene (1-on-1 DM için)
            close_success = self.conv.close_conversation(channel_id=channel_id)
            
            # Eğer başarısız olursa (grup DM ise), kullanıcıları çıkarmayı dene
            if not close_success:
                logger.info(f"[i] Grup DM tespit edildi | Kanal: {channel_id}")
                
                # Önce kullanıcıları gruptan çıkarmayı dene (conversations.kick)
                # Not: Grup DM'lerde bu genellikle çalışmaz (Slack API kısıtlaması), ama deneyelim
                user1_kicked = False
                user2_kicked = False
                
                try:
                    if self.conv.kick_user(channel_id, match_data['user1_id']):
                        user1_kicked = True
                        logger.info(f"[+] Kullanıcı 1 gruptan çıkarıldı | {user_name1} ({match_data['user1_id']})")
                except Exception as e:
                    logger.warning(f"[!] Kullanıcı 1 çıkarılamadı (Slack API kısıtlaması - grup DM'lerde genellikle çalışmaz): {e}")
                
                try:
                    if self.conv.kick_user(channel_id, match_data['user2_id']):
                        user2_kicked = True
                        logger.info(f"[+] Kullanıcı 2 gruptan çıkarıldı | {user_name2} ({match_data['user2_id']})")
                except Exception as e:
                    logger.warning(f"[!] Kullanıcı 2 çıkarılamadı (Slack API kısıtlaması - grup DM'lerde genellikle çalışmaz): {e}")
                
                # Eğer kullanıcılar çıkarılamadıysa, bot'u gruptan çıkar
                if not user1_kicked or not user2_kicked:
                    logger.info(f"[i] Kullanıcılar otomatik çıkarılamadı, bot gruptan çıkıyor | Kanal: {channel_id}")
                    leave_success = self.conv.leave_channel(channel_id)
                    if leave_success:
                        logger.info(f"[+] Bot başarıyla kanaldan çıkarıldı | Kanal: {channel_id} | Not: Kullanıcılar manuel olarak çıkmalı")
                    else:
                        logger.warning(f"[!] Bot kanaldan çıkarılamadı (Slack API kısıtlaması) | Kanal: {channel_id}")
                        logger.info(f"[i] Kullanıcılar manuel olarak kanaldan çıkabilir")
                else:
                    # Kullanıcılar çıkarıldı, bot da çıksın
                    logger.info(f"[+] Tüm kullanıcılar gruptan çıkarıldı, bot da çıkıyor | Kanal: {channel_id}")
                    leave_success = self.conv.leave_channel(channel_id)
                    if leave_success:
                        logger.info(f"[+] Bot başarıyla kanaldan çıkarıldı | Kanal: {channel_id}")
                    else:
                        logger.warning(f"[!] Bot kanaldan çıkarılamadı | Kanal: {channel_id}")
            else:
                logger.info(f"[+] 1-on-1 DM başarıyla kapatıldı | Kanal: {channel_id}")
            
            logger.info(f"[+] Eşleşme raporlandı | Kanal: {channel_id} | Özet: {summary[:50]}...")

        except Exception as e:
            logger.error(f"[X] CoffeeMatchService.close_match hatası: {e}")
