class CemilBotError(Exception):
    """Cemil Bot için temel hata sınıfı."""
    def __init__(self, message="Bot çalışması sırasında bir hata oluştu.", extra=None):
        super().__init__(message)
        self.message = message
        self.extra = extra or {}

class DatabaseError(CemilBotError):
    """Veritabanı işlemleri sırasında oluşan hatalar."""
    pass

class SlackClientError(CemilBotError):
    """Slack API ile iletişim sırasında oluşan hatalar."""
    pass

class GroqClientError(CemilBotError):
    """Groq API ile iletişim sırasında oluşan hatalar."""
    pass

class UserRegistrationError(CemilBotError):
    """Kullanıcı kaydı veya bilgisi güncellenirken oluşan hatalar."""
    pass

class VotingError(CemilBotError):
    """Oylama sistemi ile ilgili hatalar."""
    pass

class CoffeeMatchError(CemilBotError):
    """Kahve eşleşme motorunda oluşan hatalar."""
    pass

class PermissionDeniedError(CemilBotError):
    """Yetkisiz erişim denemelerinde fırlatılan hata."""
    def __init__(self, message="Bu işlem için yetkiniz bulunmuyor.", extra=None):
        super().__init__(message, extra)
