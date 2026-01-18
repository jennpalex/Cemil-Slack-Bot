from typing import List, Optional, Dict, Any, Union
from src.core.logger import logger
from src.core.exceptions import SlackClientError

class ChatManager:
    """
    Slack Mesajlaşma (Chat) işlemlerini merkezi olarak yöneten sınıf.
    Dökümantasyon: https://api.slack.com/methods?filter=chat
    """

    def __init__(self, client, user_client=None):
        self.client = client  # Bot token client
        self.user_client = user_client  # User token client (opsiyonel, user token ile oluşturulan kanallar için)

    def post_message(self, channel: str, text: str, blocks: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        """
        Kanala mesaj gönderir (chat.postMessage).
        Mesajlar her zaman bot token ile gönderilir (bot olarak görünür).
        """
        # Mesajlar her zaman bot token ile gönderilir
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks,
                **kwargs
            )
            if response["ok"]:
                logger.info(f"[+] Mesaj gönderildi (Kanal: {channel}) - bot token kullanıldı")
                return response
            else:
                raise SlackClientError(f"Mesaj gönderilemedi: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.postMessage hatası: {e}")
            raise SlackClientError(str(e))

    def post_ephemeral(self, channel: str, user: str, text: str, blocks: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        """
        Sadece belirli bir kullanıcıya görünen gizli mesaj gönderir (chat.postEphemeral).
        Eğer channel_not_found hatası alınırsa (DM'lerde veya erişilemeyen kanallarda),
        otomatik olarak kullanıcıya DM gönderir.
        """
        try:
            response = self.client.chat_postEphemeral(
                channel=channel,
                user=user,
                text=text,
                blocks=blocks,
                **kwargs
            )
            if response["ok"]:
                logger.info(f"[i] Ephemeral mesaj gönderildi (Kullanıcı: {user})")
                return response
            else:
                error = response.get("error", "unknown_error")
                # channel_not_found hatası durumunda DM gönder
                if error == "channel_not_found":
                    logger.warning(f"[!] Ephemeral mesaj gönderilemedi (channel_not_found), DM deneniyor | Kanal: {channel} | Kullanıcı: {user}")
                    return self._send_dm_fallback(user, text, blocks)
                else:
                    raise SlackClientError(f"Ephemeral mesaj gönderilemedi: {error}")
        except SlackClientError:
            raise
        except Exception as e:
            error_str = str(e)
            # channel_not_found hatası exception içinde de olabilir
            if "channel_not_found" in error_str.lower():
                logger.warning(f"[!] Ephemeral mesaj hatası (channel_not_found), DM deneniyor | Kanal: {channel} | Kullanıcı: {user}")
                return self._send_dm_fallback(user, text, blocks)
            else:
                logger.error(f"[X] chat.postEphemeral hatası: {e}")
                raise SlackClientError(str(e))
    
    def _send_dm_fallback(self, user: str, text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Ephemeral mesaj gönderilemediğinde DM olarak gönderir (fallback).
        """
        try:
            # DM kanalını aç
            from src.commands import ConversationManager
            conv_manager = ConversationManager(self.client)
            dm_channel = conv_manager.open_conversation(users=[user])
            dm_channel_id = dm_channel["id"]
            
            # DM olarak gönder
            response = self.client.chat_postMessage(
                channel=dm_channel_id,
                text=text,
                blocks=blocks
            )
            if response["ok"]:
                logger.info(f"[i] Ephemeral yerine DM gönderildi (Kullanıcı: {user})")
                return response
            else:
                raise SlackClientError(f"DM gönderilemedi: {response['error']}")
        except Exception as e:
            logger.error(f"[X] DM fallback hatası: {e}")
            raise SlackClientError(f"Mesaj gönderilemedi (ephemeral ve DM denendi): {str(e)}")

    def update_message(self, channel: str, ts: str, text: str, blocks: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        """
        Mevcut bir mesajı günceller (chat.update).
        """
        try:
            response = self.client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                blocks=blocks,
                **kwargs
            )
            if response["ok"]:
                logger.info(f"[+] Mesaj güncellendi: {ts}")
                return response
            else:
                raise SlackClientError(f"Mesaj güncellenemedi: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.update hatası: {e}")
            raise SlackClientError(str(e))

    def delete_message(self, channel: str, ts: str, as_user: bool = False) -> bool:
        """
        Bir mesajı siler (chat.delete).
        """
        try:
            response = self.client.chat_delete(channel=channel, ts=ts, as_user=as_user)
            if response["ok"]:
                logger.info(f"[-] Mesaj silindi: {ts}")
                return True
            else:
                raise SlackClientError(f"Mesaj silinemedi: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.delete hatası: {e}")
            raise SlackClientError(str(e))

    def schedule_message(self, channel: str, post_at: Union[int, str], text: str, **kwargs) -> Dict[str, Any]:
        """
        İleri tarihli bir mesaj planlar (chat.scheduleMessage).
        post_at: Unix timestamp
        """
        try:
            response = self.client.chat_scheduleMessage(
                channel=channel,
                post_at=post_at,
                text=text,
                **kwargs
            )
            if response["ok"]:
                logger.info(f"[+] Mesaj planlandı: {response['scheduled_message_id']}")
                return response
            else:
                raise SlackClientError(f"Mesaj planlanamadı: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.scheduleMessage hatası: {e}")
            raise SlackClientError(str(e))

    def delete_scheduled_message(self, channel: str, scheduled_message_id: str) -> bool:
        """
        Planlanmış bir mesajı kuyruktan siler (chat.deleteScheduledMessage).
        """
        try:
            response = self.client.chat_deleteScheduledMessage(
                channel=channel,
                scheduled_message_id=scheduled_message_id
            )
            if response["ok"]:
                logger.info(f"[-] Planlanmış mesaj iptal edildi: {scheduled_message_id}")
                return True
            else:
                raise SlackClientError(f"Planlanmış mesaj silinemedi: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.deleteScheduledMessage hatası: {e}")
            raise SlackClientError(str(e))

    def list_scheduled_messages(self, channel: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Planlanmış mesajları listeler (chat.scheduledMessages.list).
        """
        try:
            response = self.client.chat_scheduledMessages_list(channel=channel, **kwargs)
            if response["ok"]:
                messages = response.get("scheduled_messages", [])
                logger.info(f"[i] Planlanmış mesajlar listelendi: {len(messages)} adet")
                return messages
            else:
                raise SlackClientError(f"Planlanmış mesaj listesi alınamadı: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.scheduledMessages.list hatası: {e}")
            raise SlackClientError(str(e))

    def get_permalink(self, channel: str, message_ts: str) -> str:
        """
        Bir mesajın kalıcı bağlantısını (URL) getirir (chat.getPermalink).
        """
        try:
            response = self.client.chat_getPermalink(channel=channel, message_ts=message_ts)
            if response["ok"]:
                return response["permalink"]
            else:
                raise SlackClientError(f"Permalink alınamadı: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.getPermalink hatası: {e}")
            raise SlackClientError(str(e))

    def me_message(self, channel: str, text: str) -> Dict[str, Any]:
        """
        Bir 'me message' (italik bot mesajı) gönderir (chat.meMessage).
        """
        try:
            response = self.client.chat_meMessage(channel=channel, text=text)
            if response["ok"]:
                return response
            else:
                raise SlackClientError(f"Me message gönderilemedi: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.meMessage hatası: {e}")
            raise SlackClientError(str(e))

    def unfurl_links(self, channel: str, ts: str, unfurls: Dict[str, Any], **kwargs) -> bool:
        """
        Linklerin önizlemesini (unfurl) özelleştirir (chat.unfurl).
        """
        try:
            response = self.client.chat_unfurl(channel=channel, ts=ts, unfurls=unfurls, **kwargs)
            if response["ok"]:
                logger.info(f"[+] Link önizleme güncellendi (TS: {ts})")
                return True
            else:
                raise SlackClientError(f"Link unfurl başarısız: {response['error']}")
        except Exception as e:
            logger.error(f"[X] chat.unfurl hatası: {e}")
            raise SlackClientError(str(e))

    # Akış (Streaming) Metodları (Beta/Özel kullanım durumları için)
    def start_stream(self, channel: str, text: str, **kwargs) -> Dict[str, Any]:
        """Akışlı (Streaming) bir konuşma başlatır."""
        try:
            response = self.client.chat_startStream(channel=channel, text=text, **kwargs)
            if response["ok"]:
                logger.info(f"[>] Stream başlatıldı: {response.get('stream_id')}")
                return response
            raise SlackClientError(response['error'])
        except Exception as e:
            logger.error(f"[X] chat.startStream hatası: {e}")
            raise SlackClientError(str(e))

    def append_stream(self, channel: str, stream_id: str, text: str, **kwargs) -> bool:
        """Mevcut bir akışa text ekler."""
        try:
            response = self.client.chat_appendStream(channel=channel, stream_id=stream_id, text=text, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] chat.appendStream hatası: {e}")
            return False

    def stop_stream(self, channel: str, stream_id: str, **kwargs) -> bool:
        """Akışı durdurur."""
        try:
            response = self.client.chat_stopStream(channel=channel, stream_id=stream_id, **kwargs)
            return response["ok"]
        except Exception as e:
            logger.error(f"[X] chat.stopStream hatası: {e}")
            return False
