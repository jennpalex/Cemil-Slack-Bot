from typing import List, Optional, Dict, Any, Union
from src.core.logger import logger
from src.core.exceptions import SlackClientError

class ConversationManager:
    """
    Slack Konuşma/Kanal (Conversations) işlemlerini merkezi olarak yöneten sınıf.
    Dökümantasyon: https://api.slack.com/methods?filter=conversations
    """

    def __init__(self, client, user_client=None):
        self.client = client  # Bot token client
        self.user_client = user_client  # User token client (opsiyonel, kanal oluşturma için)

    def create_channel(self, name: str, is_private: bool = False, **kwargs) -> Dict[str, Any]:
        """Yeni bir kanal oluşturur (conversations.create). User token varsa onu kullanır."""
        # User token varsa onu kullan (workspace kısıtlamalarını bypass eder)
        client_to_use = self.user_client if self.user_client else self.client
        
        try:
            response = client_to_use.conversations_create(name=name, is_private=is_private, **kwargs)
            if response["ok"]:
                channel = response["channel"]
                token_type = "user token" if self.user_client else "bot token"
                logger.info(f"[+] Kanal oluşturuldu: #{name} (ID: {channel['id']}) - {token_type} kullanıldı")
                return channel
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.create hatası: {e}")
            raise SlackClientError(str(e))

    def get_info(self, channel_id: str, **kwargs) -> Dict[str, Any]:
        """Kanal hakkında bilgi getirir (conversations.info). User token varsa onu kullanır."""
        # User token varsa onu kullan (user token ile oluşturulan kanalları görebilmek için)
        client_to_use = self.user_client if self.user_client else self.client
        try:
            response = client_to_use.conversations_info(channel=channel_id, **kwargs)
            if response["ok"]:
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.info hatası: {e}")
            raise SlackClientError(str(e))

    def list_channels(self, types: str = "public_channel,private_channel", limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """Workspace'teki kanalları listeler (conversations.list)."""
        try:
            response = self.client.conversations_list(types=types, limit=limit, **kwargs)
            if response["ok"]:
                channels = response.get("channels", [])
                logger.info(f"[i] Kanallar listelendi: {len(channels)} adet")
                return channels
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.list hatası: {e}")
            raise SlackClientError(str(e))

    def join_channel(self, channel_id: str) -> Dict[str, Any]:
        """Mevcut bir kanala katılır (conversations.join)."""
        try:
            response = self.client.conversations_join(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanala katılım başarılı: {channel_id}")
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.join hatası: {e}")
            raise SlackClientError(str(e))

    def invite_users(self, channel_id: str, user_ids: List[str], include_bot: bool = True) -> Dict[str, Any]:
        """
        Kanala kullanıcıları davet eder (conversations.invite). 
        User token varsa onu kullanır (workspace owner olarak işlem yapar).
        include_bot=True ise bot'u da davet listesine ekler (bot token ile mesaj gönderebilmek için).
        
        Not: User token ile oluşturulan kanallarda, kanalı oluşturan kişi zaten kanalda olduğu için
        davet listesinden çıkarılır.
        """
        # User token varsa onu kullan (workspace owner olarak işlem yapar)
        client_to_use = self.user_client if self.user_client else self.client
        
        # Kanalın mevcut üyelerini al (zaten kanalda olanları davet etmemek için)
        existing_members = set()
        try:
            members = self.get_members(channel_id)  # get_members artık user token kullanıyor
            existing_members = set(members)
            logger.debug(f"[i] Kanal mevcut üyeleri: {len(existing_members)} kişi")
        except Exception as e:
            logger.warning(f"[!] Kanal üyeleri alınamadı, devam ediliyor: {e}")
        
        # User token sahibini davet listesinden çıkar (zaten kanalda - user token ile oluşturulan kanallarda otomatik eklenir)
        user_token_owner_id = None
        if self.user_client:
            try:
                user_info = self.user_client.auth_test()
                if user_info["ok"]:
                    user_token_owner_id = user_info["user_id"]
                    existing_members.add(user_token_owner_id)  # User token sahibi her zaman kanalda
                    logger.debug(f"[i] User token sahibi zaten kanalda: {user_token_owner_id}")
            except Exception as e:
                logger.warning(f"[!] User token sahibi bilgisi alınamadı: {e}")
        
        # Zaten kanalda olanları davet listesinden çıkar
        final_user_ids = [uid for uid in user_ids if uid not in existing_members]
        
        # Bot'u mutlaka davet listesine ekle (bot token ile mesaj gönderebilmek için)
        bot_user_id = None
        if include_bot:
            try:
                # Bot'un user ID'sini al
                bot_info = self.client.auth_test()
                if bot_info["ok"]:
                    bot_user_id = bot_info["user_id"]
                    # Bot zaten kanalda değilse ekle
                    if bot_user_id not in existing_members:
                        final_user_ids.append(bot_user_id)
                        logger.debug(f"[i] Bot user ID eklendi: {bot_user_id}")
                    else:
                        logger.debug(f"[i] Bot zaten kanalda: {bot_user_id}")
            except Exception as e:
                logger.warning(f"[!] Bot user ID alınamadı: {e}")
        
        # Eğer davet edilecek kimse yoksa, başarılı dön (zaten hepsi kanalda)
        if not final_user_ids:
            logger.info(f"[i] Tüm kullanıcılar zaten kanalda, davet gerekmiyor (Kanal: {channel_id})")
            try:
                # Kanal bilgisini döndür
                channel_info = self.get_info(channel_id)
                return channel_info
            except Exception:
                # Fallback: boş dict döndür
                return {"id": channel_id}
        
        # Bot'u ayrı davet et (bot mutlaka kanalda olmalı)
        bot_invited = False
        if include_bot and bot_user_id and bot_user_id not in existing_members:
            try:
                bot_response = client_to_use.conversations_invite(channel=channel_id, users=[bot_user_id])
                if bot_response["ok"]:
                    bot_invited = True
                    logger.info(f"[+] Bot kanala davet edildi: {bot_user_id}")
                else:
                    # Bot zaten kanalda olabilir
                    if bot_response.get("error") in ["already_in_channel", "cant_invite_self"]:
                        bot_invited = True
                        logger.debug(f"[i] Bot zaten kanalda: {bot_user_id}")
            except Exception as e:
                error_str = str(e)
                if "already_in_channel" in error_str or "cant_invite_self" in error_str:
                    bot_invited = True
                    logger.debug(f"[i] Bot zaten kanalda (hata mesajından): {bot_user_id}")
                else:
                    logger.warning(f"[!] Bot davet edilemedi: {e}")
        
        # Diğer kullanıcıları davet et
        if final_user_ids and bot_user_id in final_user_ids:
            # Bot'u final_user_ids'den çıkar (zaten davet ettik)
            final_user_ids = [uid for uid in final_user_ids if uid != bot_user_id]
        
        if not final_user_ids:
            # Sadece bot davet edildi, diğer kullanıcılar zaten kanalda
            logger.info(f"[i] Tüm kullanıcılar zaten kanalda (Kanal: {channel_id})")
            try:
                channel_info = self.get_info(channel_id)
                return channel_info
            except Exception:
                return {"id": channel_id}
        
        try:
            response = client_to_use.conversations_invite(channel=channel_id, users=final_user_ids)
            if response["ok"]:
                token_type = "user token" if self.user_client else "bot token"
                logger.info(f"[+] Davet gönderildi: {len(final_user_ids)} kullanıcı (Kanal: {channel_id}) - {token_type} kullanıldı")
                try:
                    return self.get_info(channel_id)
                except Exception:
                    return {"id": channel_id}
            
            # Kısmi başarı durumunu kontrol et (bazı kullanıcılar zaten kanalda olabilir)
            if "errors" in response:
                # Sadece 'cant_invite_self' veya 'already_in_channel' hataları varsa, kısmi başarı sayılabilir
                non_critical_errors = ["cant_invite_self", "already_in_channel"]
                critical_errors = [err for err in response.get("errors", []) 
                                if err.get("error") not in non_critical_errors]
                
                if not critical_errors:
                    # Bazı kullanıcılar davet edildi, bazıları zaten kanaldaydı - bu başarı sayılır
                    logger.info(f"[i] Kısmi başarı: Bazı kullanıcılar zaten kanalda (Kanal: {channel_id})")
                    try:
                        channel_info = self.get_info(channel_id)
                        return channel_info
                    except Exception:
                        return {"id": channel_id}
            
            raise SlackClientError(response.get('error', 'Bilinmeyen hata'))
        except SlackClientError:
            raise
        except Exception as e:
            error_str = str(e)
            # 'cant_invite_self' veya 'already_in_channel' hatalarını yumuşak handle et
            if "cant_invite_self" in error_str or "already_in_channel" in error_str:
                logger.warning(f"[!] Bazı kullanıcılar zaten kanalda, devam ediliyor: {e}")
                try:
                    channel_info = self.get_info(channel_id)
                    return channel_info
                except Exception:
                    return {"id": channel_id}
            logger.error(f"[X] conversations.invite hatası: {e}")
            raise SlackClientError(str(e))

    def kick_user(self, channel_id: str, user_id: str, max_retries: int = 3) -> bool:
        """
        Kullanıcıyı kanaldan çıkarır (conversations.kick). 
        User token varsa onu kullanır (workspace owner olarak işlem yapar).
        Rate limit hatalarında otomatik retry yapar.
        """
        import time
        
        # User token varsa onu kullan (workspace owner olarak işlem yapar)
        client_to_use = self.user_client if self.user_client else self.client
        token_type = "user token" if self.user_client else "bot token"
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[>] conversations.kick çağrılıyor (deneme {attempt + 1}/{max_retries}) | Kullanıcı: {user_id} | Kanal: {channel_id} | Token: {token_type}")
                response = client_to_use.conversations_kick(channel=channel_id, user=user_id)
                
                if response["ok"]:
                    logger.info(f"[+] Kullanıcı çıkarıldı: {user_id} (Kanal: {channel_id}) - {token_type} kullanıldı")
                    return True
                
                # Hata durumunda detaylı log
                error = response.get('error', 'unknown_error')
                error_detail = response.get('response_metadata', {}).get('messages', [])
                
                logger.error(f"[X] conversations.kick hatası: {error} | Kullanıcı: {user_id} | Kanal: {channel_id} | Token: {token_type}")
                if error_detail:
                    logger.error(f"[X] Hata detayları: {error_detail}")
                
                # Bazı hatalar non-critical olabilir
                if error in ["user_not_found", "channel_not_found", "not_in_channel"]:
                    logger.warning(f"[!] conversations.kick non-critical hata: {error}")
                    return False
                
                raise SlackClientError(f"conversations.kick failed: {error}")
            except SlackClientError:
                raise
            except Exception as e:
                error_str = str(e).lower()
                
                # Rate limit hatası kontrolü
                if "rate_limited" in error_str or "ratelimited" in error_str or "429" in error_str:
                    # Slack'in önerdiği bekleme süresini al
                    retry_after = 60  # Varsayılan: 60 saniye
                    
                    # Response'dan Retry-After header'ını almaya çalış
                    try:
                        if hasattr(e, 'response') and e.response:
                            retry_after = int(e.response.get('headers', {}).get('Retry-After', 60))
                    except:
                        pass
                    
                    if attempt < max_retries - 1:
                        logger.warning(f"[!] Rate limit hatası! {retry_after} saniye bekleniyor... (deneme {attempt + 1}/{max_retries}) | Kullanıcı: {user_id}")
                        time.sleep(retry_after)
                        continue  # Tekrar dene
                    else:
                        logger.error(f"[X] Rate limit hatası! Max retry sayısına ulaşıldı | Kullanıcı: {user_id}")
                        raise SlackClientError(f"Rate limit exceeded after {max_retries} retries")
                
                logger.error(f"[X] conversations.kick exception: {e} | Kullanıcı: {user_id} | Kanal: {channel_id}", exc_info=True)
                raise SlackClientError(str(e))
        
        # Buraya gelmemeli ama yine de
        return False

    def leave_channel(self, channel_id: str) -> bool:
        """Kanaldan veya grup DM'den ayrılır (conversations.leave)."""
        try:
            response = self.client.conversations_leave(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanaldan ayrıldı: {channel_id}")
                return True
            else:
                error = response.get("error", "Bilinmeyen hata")
                logger.warning(f"[!] Kanaldan ayrılamadı: {channel_id} | Hata: {error}")
                return False
        except Exception as e:
            logger.error(f"[X] conversations.leave hatası: {channel_id} | {e}")
            return False

    def archive_channel(self, channel_id: str) -> bool:
        """Kanalı arşivler (conversations.archive). User token varsa onu kullanır (workspace owner olarak işlem yapar)."""
        # User token varsa onu kullan (workspace owner olarak işlem yapar)
        client_to_use = self.user_client if self.user_client else self.client
        
        try:
            response = client_to_use.conversations_archive(channel=channel_id)
            if response["ok"]:
                token_type = "user token" if self.user_client else "bot token"
                logger.info(f"[-] Kanal arşivlendi: {channel_id} - {token_type} kullanıldı")
                return True
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.archive hatası: {e}")
            raise SlackClientError(str(e))

    def unarchive_channel(self, channel_id: str) -> bool:
        """Kanal arşivini geri alır (conversations.unarchive)."""
        try:
            response = self.client.conversations_unarchive(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanal arşivi kaldırıldı: {channel_id}")
                return True
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.unarchive hatası: {e}")
            raise SlackClientError(str(e))

    def rename_channel(self, channel_id: str, name: str) -> Dict[str, Any]:
        """Kanalı yeniden adlandırır (conversations.rename)."""
        try:
            response = self.client.conversations_rename(channel=channel_id, name=name)
            if response["ok"]:
                logger.info(f"[+] Kanal adı güncellendi: #{name}")
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.rename hatası: {e}")
            raise SlackClientError(str(e))

    def set_topic(self, channel_id: str, topic: str) -> bool:
        """Kanal konusunu ayarlar (conversations.setTopic)."""
        try:
            response = self.client.conversations_setTopic(channel=channel_id, topic=topic)
            if not response["ok"]:
                error = response.get("error", "unknown_error")
                # channel_not_found gibi hatalar non-critical, warning olarak logla
                if error in ["channel_not_found", "not_in_channel", "missing_scope"]:
                    logger.warning(f"[!] conversations.setTopic hatası (non-critical): {error} | Kanal: {channel_id}")
                else:
                    logger.error(f"[X] conversations.setTopic hatası: {error} | Kanal: {channel_id}")
                return False
            return True
        except Exception as e:
            logger.warning(f"[!] conversations.setTopic exception (non-critical): {e}")
            return False

    def set_purpose(self, channel_id: str, purpose: str) -> bool:
        """Kanal amacını/açıklamasını ayarlar (conversations.setPurpose)."""
        try:
            response = self.client.conversations_setPurpose(channel=channel_id, purpose=purpose)
            if not response["ok"]:
                error = response.get("error", "unknown_error")
                # channel_not_found gibi hatalar non-critical, warning olarak logla
                if error in ["channel_not_found", "not_in_channel", "missing_scope"]:
                    logger.warning(f"[!] conversations.setPurpose hatası (non-critical): {error} | Kanal: {channel_id}")
                else:
                    logger.error(f"[X] conversations.setPurpose hatası: {error} | Kanal: {channel_id}")
                return False
            return True
        except Exception as e:
            logger.warning(f"[!] conversations.setPurpose exception (non-critical): {e}")
            return False

    def get_history(self, channel_id: str, limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """Kanal geçmişini getirir (conversations.history)."""
        try:
            response = self.client.conversations_history(channel=channel_id, limit=limit, **kwargs)
            if response["ok"]:
                return response.get("messages", [])
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.history hatası: {e}")
            raise SlackClientError(str(e))

    def get_replies(self, channel_id: str, ts: str, **kwargs) -> List[Dict[str, Any]]:
        """Bir mesaj dizisindeki (thread) cevapları getirir (conversations.replies)."""
        try:
            response = self.client.conversations_replies(channel=channel_id, ts=ts, **kwargs)
            if response["ok"]:
                return response.get("messages", [])
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.replies hatası: {e}")
            raise SlackClientError(str(e))

    def get_members(self, channel_id: str, limit: int = 100, **kwargs) -> List[str]:
        """Kanal üyelerinin ID listesini getirir (conversations.members). User token varsa onu kullanır."""
        # User token varsa onu kullan (user token ile oluşturulan kanalları görebilmek için)
        client_to_use = self.user_client if self.user_client else self.client
        try:
            response = client_to_use.conversations_members(channel=channel_id, limit=limit, **kwargs)
            if response["ok"]:
                return response.get("members", [])
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.members hatası: {e}")
            raise SlackClientError(str(e))

    def open_conversation(self, users: List[str], **kwargs) -> Dict[str, Any]:
        """DM veya grup DM başlatır (conversations.open)."""
        try:
            response = self.client.conversations_open(users=users, **kwargs)
            if response["ok"]:
                return response["channel"]
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.open hatası: {e}")
            raise SlackClientError(str(e))

    def close_conversation(self, channel_id: str) -> bool:
        """DM veya grup DM'i kapatır (conversations.close)."""
        try:
            response = self.client.conversations_close(channel=channel_id)
            if response["ok"]:
                logger.info(f"[+] Konuşma kapatıldı: {channel_id}")
                return True
            else:
                error = response.get("error", "Bilinmeyen hata")
                logger.warning(f"[!] Konuşma kapatılamadı: {channel_id} | Hata: {error}")
                # Bazı durumlarda (örneğin grup DM'ler) kapatılamayabilir
                return False
        except Exception as e:
            logger.error(f"[X] conversations.close hatası: {channel_id} | {e}")
            return False

    def mark_read(self, channel_id: str, ts: str) -> bool:
        """Kanalda okunma imlecini ayarlar (conversations.mark)."""
        try:
            response = self.client.conversations_mark(channel=channel_id, ts=ts)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.mark hatası: {e}")
            return False

    # Slack Connect / Paylaşılan Kanal Metodları
    def accept_shared_invite(self, invite_id: str, channel_name: str, **kwargs) -> bool:
        """Slack Connect davetini kabul eder (conversations.acceptSharedInvite)."""
        try:
            response = self.client.conversations_acceptSharedInvite(invite_id=invite_id, channel_name=channel_name, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.acceptSharedInvite hatası: {e}")
            return False

    def approve_shared_invite(self, invite_id: str, **kwargs) -> bool:
        """Slack Connect davetini onaylar (conversations.approveSharedInvite)."""
        try:
            response = self.client.conversations_approveSharedInvite(invite_id=invite_id, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.approveSharedInvite hatası: {e}")
            return False

    def decline_shared_invite(self, invite_id: str, **kwargs) -> bool:
        """Slack Connect davetini reddeder (conversations.declineSharedInvite)."""
        try:
            response = self.client.conversations_declineSharedInvite(invite_id=invite_id, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.declineSharedInvite hatası: {e}")
            return False

    def invite_shared_channel(self, channel_id: str, emails: Optional[List[str]] = None, user_ids: Optional[List[str]] = None, **kwargs) -> bool:
        """Paylaşılan kanal daveti gönderir (conversations.inviteShared)."""
        try:
            response = self.client.conversations_inviteShared(channel=channel_id, emails=emails, user_ids=user_ids, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] conversations.inviteShared hatası: {e}")
            return False

    # Canvas (Kanal Bazlı)
    def create_channel_canvas(self, channel_id: str) -> Dict[str, Any]:
        """Kanal için canvas oluşturur (conversations.canvases.create)."""
        try:
            response = self.client.conversations_canvases_create(channel_id=channel_id)
            if response["ok"]:
                logger.info(f"[+] Kanal canvas'ı oluşturuldu (Kanal: {channel_id})")
                return response
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] conversations.canvases.create hatası: {e}")
            raise SlackClientError(str(e))
