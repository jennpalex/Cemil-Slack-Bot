import os
from typing import List, Dict, Any, Optional
from groq import Groq
from src.core.logger import logger
from src.core.exceptions import GroqClientError

class GroqClient:
    """
    Groq Cloud API için merkezi istemci sınıfı.
    Yüksek hızlı LLM çıkarımı sağlar.
    """

    def __init__(self, api_key: Optional[str] = None, default_model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            logger.error("[X] GROQ_API_KEY bulunamadı! Lütfen .env dosyasını kontrol edin.")
            raise GroqClientError("Groq API Key eksik.")
        
        try:
            self.client = Groq(api_key=self.api_key)
            self.default_model = default_model
            logger.info(f"[i] Groq İstemcisi hazırlandı. Varsayılan Model: {default_model}")
        except Exception as e:
            logger.error(f"[X] Groq İstemcisi başlatılırken hata: {e}")
            raise GroqClientError(str(e))

    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False
    ) -> str:
        """
        Groq üzerinden bir sohbet yanıtı (completion) döndürür.
        """
        target_model = model or self.default_model
        try:
            logger.info(f"[>] Groq sorgusu gönderiliyor ({target_model})...")
            completion = self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
            
            # Yanıtı al
            response_text = completion.choices[0].message.content
            logger.info("[+] Groq yanıtı başarıyla alındı.")
            return response_text

        except Exception as e:
            logger.error(f"[X] Groq Chat Completion hatası: {e}")
            raise GroqClientError(f"Groq yanıt üretemedi: {str(e)}")

    def quick_ask(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        """
        Hızlı bir soru-cevap işlemi için kolaylaştırıcı metod.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "human", "content": user_prompt}
        ]
        return self.chat_completion(messages, model=model)
