import os
import pandas as pd
from docx import Document
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from src.core.logger import logger
from src.clients import VectorClient, GroqClient

class KnowledgeService:
    """
    Cemil'in 'Bilgi Küpü' (RAG). Dökümanları işler ve soruları yanıtlar.
    Tamamen ücretsiz ve limit-free yapıdadır.
    """

    def __init__(self, vector_client: VectorClient, groq_client: GroqClient):
        self.vector = vector_client
        self.groq = groq_client
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=700,
            chunk_overlap=100
        )

    async def process_knowledge_base(self, folder_path: str = "knowledge_base"):
        """Belirtilen klasördeki dökümanları okur ve indekse ekler."""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            logger.warning(f"[!] {folder_path} bulunamadı, boş bir tane oluşturuldu.")
            return

        all_texts = []
        all_metadata = []

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            text = ""
            
            try:
                # PDF İşleme
                if filename.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                
                # TXT ve Markdown İşleme
                elif filename.endswith((".txt", ".md")):
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()

                # DOCX (Word) İşleme
                elif filename.endswith(".docx"):
                    doc = Document(file_path)
                    text = "\n".join([para.text for para in doc.paragraphs])

                # Excel ve CSV İşleme (Tablosal)
                elif filename.endswith((".csv", ".xlsx", ".xls")):
                    if filename.endswith(".csv"):
                        df = pd.read_csv(file_path)
                    else:
                        df = pd.read_excel(file_path)
                    
                    # Her satırı bir metin parçasına dönüştür
                    rows_text = []
                    for idx, row in df.iterrows():
                        row_str = ", ".join([f"{col}: {row[col]}" for col in df.columns])
                        rows_text.append(row_str)
                    text = "\n".join(rows_text)
                
                if text.strip():
                    chunks = self.splitter.split_text(text)
                    all_texts.extend(chunks)
                    all_metadata.extend([{"source": filename}] * len(chunks))
                    logger.info(f"[+] İşlendi: {filename} ({len(chunks)} parça)")

            except Exception as e:
                logger.error(f"[X] {filename} işlenirken hata: {e}")

        if all_texts:
            self.vector.add_texts(all_texts, all_metadata)
            logger.info(f"[!] {len(all_texts)} parça ile Bilgi Küpü güncellendi.")

    async def ask_question(self, question: str) -> str:
        """Kullanıcının sorusunu dökümanlara göre yanıtlar."""
        try:
            # 1. Benzer metin parçalarını bul (threshold ile filtrele)
            context_docs = self.model_search_context(question)
            
            if not context_docs:
                logger.info(f"[i] Soru için dökümanlarda eşleşme bulunamadı: {question}")
                return "Üzgünüm, bilgi küpümde bu soruyla eşleşen herhangi bir döküman veya bilgi bulunamadı. 😔"

            # 2. Bağlamı (Context) hazırla
            context_text = "\n\n".join([
                f"--- Kaynak: {doc['metadata'].get('source', 'Bilinmiyor')} ---\n{doc['text']}" 
                for doc in context_docs
            ])

            # 3. LLM'e (Groq) sor - Sıkı Kurallar Altında
            system_prompt = (
                "Sen Cemil'sin, sadece sana verilen dökümanlara (BAĞLAM) dayanarak cevap veren bir asistansın. "
                "Şu kurallara KESİNLİKLE uy:\n"
                "1. Sadece sana verilen BAĞLAM içindeki bilgileri kullan.\n"
                "2. Bağlam dışındaki genel kültürünü veya dış bilgileri KESİNLİKLE kullanma.\n"
                "3. Eğer cevabı bağlamda açıkça göremiyorsan, tahmin yürütme; 'Bu konuda dökümanlarımda bilgi bulamadım' de.\n"
                "4. Cevabı uydurma, manipüle etme veya varsayımlarda bulunma.\n"
                "5. Yanıtlarında hiçbir emoji veya ASCII olmayan karakter kullanma (sadece ASCII).\n"
                "6. Yanıtların öz, net ve samimi olsun."
            )
            
            user_prompt = f"BAĞLAM:\n{context_text}\n\nSORU: {question}"
            
            answer = await self.groq.quick_ask(system_prompt, user_prompt)
            
            # 4. Kaynakları Ekle
            unique_sources = list(set([doc['metadata'].get('source', 'Bilinmiyor') for doc in context_docs]))
            if unique_sources:
                answer += f"\n\n[Kaynaklar: {', '.join(unique_sources)}]"
            
            return answer

        except Exception as e:
            logger.error(f"[X] KnowledgeService.ask_question hatası: {e}")
            return "Şu an hafızamı toparlamakta zorlanıyorum, birazdan tekrar sorar mısın? 🧠✨"

    def model_search_context(self, question: str) -> List[Dict]:
        """Vektör veritabanından bağlamı çeker."""
        return self.vector.search(question, top_k=4, threshold=0.6)
