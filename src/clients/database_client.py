import sqlite3
import uuid
import os
from typing import List, Dict, Any, Optional
from src.core.logger import logger
from src.core.exceptions import DatabaseError
from src.core.singleton import SingletonMeta

class DatabaseClient(metaclass=SingletonMeta):
    """
    Cemil Bot için merkezi veritabanı yönetim sınıfı.
    SQLite bağlantı yönetiminden sorumludur.
    """

    def __init__(self, db_path: str = "data/cemil_bot.db"):
        self.db_path = db_path
        # Klasör yoksa oluştur
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_db()

    def get_connection(self):
        """SQLite bağlantısı döndürür."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Dict benzeri erişim için
            # FOREIGN KEY desteğini etkinleştir (her connection için zorunlu)
            conn.execute("PRAGMA foreign_keys = ON")
            # Foreign key'lerin açık olduğunu doğrula
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            if result and result[0] == 0:
                logger.warning("[!] Foreign key'ler açılamadı, tekrar deniyor...")
                conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except sqlite3.Error as e:
            logger.error(f"[X] Veritabanı bağlantı hatası: {e}")
            raise DatabaseError(f"Veritabanına bağlanılamadı: {e}")

    def init_db(self):
        """Temel tabloları hazırlar (Gerekirse)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Foreign key'leri aç (tüm tablolar için)
                cursor.execute("PRAGMA foreign_keys = ON")
                
                # Kullanıcılar Tablosu (Users)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        slack_id TEXT UNIQUE,
                        first_name TEXT,
                        middle_name TEXT,
                        surname TEXT,
                        full_name TEXT,
                        birthday TEXT,
                        cohort TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Migration: Gereksiz kolonları kaldır ve sadece gerekli kolonları bırak
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                required_columns = ['id', 'slack_id', 'first_name', 'middle_name', 'surname', 'full_name', 'birthday', 'cohort', 'created_at', 'updated_at']
                has_unnecessary_columns = any(col not in required_columns for col in columns)
                missing_cohort = 'cohort' not in columns
                missing_middle_name = 'middle_name' not in columns
                has_department = 'department' in columns
                
                # Eğer middle_name kolonu yoksa ekle
                if missing_middle_name:
                    logger.info("[i] middle_name kolonu ekleniyor...")
                    cursor.execute("ALTER TABLE users ADD COLUMN middle_name TEXT")
                    logger.info("[+] middle_name kolonu eklendi.")
                
                if has_unnecessary_columns or missing_cohort or has_department or missing_middle_name:
                    logger.info("[i] Veritabanı şeması güncelleniyor...")
                    # Yeni temiz tablo oluştur
                    cursor.execute("DROP TABLE IF EXISTS users_new")
                    cursor.execute("""
                        CREATE TABLE users_new (
                            id TEXT PRIMARY KEY,
                            slack_id TEXT UNIQUE,
                            first_name TEXT,
                            middle_name TEXT,
                            surname TEXT,
                            full_name TEXT,
                            birthday TEXT,
                            cohort TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Mevcut verileri kopyala (sadece mevcut kolonlar varsa)
                    if 'id' in columns and 'slack_id' in columns:
                        # Department varsa cohort'a çevir, yoksa boş bırak
                        if has_department:
                            cursor.execute("""
                                INSERT INTO users_new (id, slack_id, first_name, middle_name, surname, full_name, birthday, cohort, created_at, updated_at)
                                SELECT 
                                    id, 
                                    slack_id, 
                                    COALESCE(first_name, '') as first_name,
                                    COALESCE(middle_name, '') as middle_name,
                                    COALESCE(surname, '') as surname,
                                    COALESCE(full_name, '') as full_name,
                                    birthday,
                                    COALESCE(department, '') as cohort,
                                    COALESCE(created_at, CURRENT_TIMESTAMP) as created_at,
                                    COALESCE(updated_at, CURRENT_TIMESTAMP) as updated_at
                                FROM users
                            """)
                        else:
                            cursor.execute("""
                                INSERT INTO users_new (id, slack_id, first_name, middle_name, surname, full_name, birthday, cohort, created_at, updated_at)
                                SELECT 
                                    id, 
                                    slack_id, 
                                    COALESCE(first_name, '') as first_name,
                                    COALESCE(middle_name, '') as middle_name,
                                    COALESCE(surname, '') as surname,
                                    COALESCE(full_name, '') as full_name,
                                    birthday,
                                    COALESCE(cohort, '') as cohort,
                                    COALESCE(created_at, CURRENT_TIMESTAMP) as created_at,
                                    COALESCE(updated_at, CURRENT_TIMESTAMP) as updated_at
                                FROM users
                            """)
                    
                    # Eski tabloyu sil ve yenisini yeniden adlandır
                    cursor.execute("DROP TABLE users")
                    cursor.execute("ALTER TABLE users_new RENAME TO users")
                    logger.info("[+] Veritabanı şeması temizlendi: Sadece gerekli kolonlar kaldı (id, slack_id, first_name, middle_name, surname, full_name, birthday, cohort).")

                # Eşleşme Takip Tablosu (Matches)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS matches (
                        id TEXT PRIMARY KEY,
                        channel_id TEXT,
                        coffee_channel_id TEXT,
                        user1_id TEXT,
                        user2_id TEXT,
                        status TEXT DEFAULT 'active',
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user1_id) REFERENCES users(id) ON DELETE SET NULL,
                        FOREIGN KEY (user2_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                """)
                
                # Migration: coffee_channel_id ve updated_at kolonları yoksa ekle
                cursor.execute("PRAGMA table_info(matches)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'coffee_channel_id' not in columns:
                    logger.info("[i] coffee_channel_id kolonu ekleniyor...")
                    cursor.execute("ALTER TABLE matches ADD COLUMN coffee_channel_id TEXT")
                    logger.info("[+] coffee_channel_id kolonu eklendi.")
                if 'updated_at' not in columns:
                    logger.info("[i] matches tablosuna updated_at kolonu ekleniyor...")
                    # SQLite'da ALTER TABLE ile DEFAULT CURRENT_TIMESTAMP kullanılamaz, NULL ile ekle
                    cursor.execute("ALTER TABLE matches ADD COLUMN updated_at TIMESTAMP")
                    logger.info("[+] matches.updated_at kolonu eklendi.")

                # Oylama Başlıkları Tablosu (Polls)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS polls (
                        id TEXT PRIMARY KEY,
                        topic TEXT,
                        options TEXT, -- JSON formatında seçenekler
                        result_summary TEXT, -- Oylama bittiğinde LLM özeti veya ham sonuç
                        creator_id TEXT,
                        allow_multiple INTEGER DEFAULT 0, -- Çoklu oy opsiyonu
                        is_closed INTEGER DEFAULT 0,
                        expires_at TIMESTAMP,
                        message_ts TEXT, -- Oylama mesajının timestamp'i (güncelleme için)
                        message_channel TEXT, -- Oylama mesajının kanalı
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Migration: Eğer message_ts ve message_channel kolonları yoksa ekle
                cursor.execute("PRAGMA table_info(polls)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'message_ts' not in columns:
                    cursor.execute("ALTER TABLE polls ADD COLUMN message_ts TEXT")
                    logger.info("[i] polls tablosuna message_ts kolonu eklendi.")
                if 'message_channel' not in columns:
                    cursor.execute("ALTER TABLE polls ADD COLUMN message_channel TEXT")
                    logger.info("[i] polls tablosuna message_channel kolonu eklendi.")

                # Oylar Tablosu (Votes) - User & Poll Ara Tablo
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS votes (
                        id TEXT PRIMARY KEY,
                        poll_id TEXT,
                        user_id TEXT,
                        option_index INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(poll_id, user_id, option_index),
                        FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)

                # Anonim Geri Bildirim Tablosu (Feedbacks)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS feedbacks (
                        id TEXT PRIMARY KEY,
                        content TEXT,
                        category TEXT DEFAULT 'general',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Yardım İstekleri Tablosu (Help Requests)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS help_requests (
                        id TEXT PRIMARY KEY,
                        requester_id TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        description TEXT NOT NULL,
                        status TEXT DEFAULT 'open',
                        helper_id TEXT,
                        channel_id TEXT,
                        help_channel_id TEXT,
                        message_ts TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (helper_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                """)
                
                # Migration: help_channel_id ve updated_at kolonları yoksa ekle
                cursor.execute("PRAGMA table_info(help_requests)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'help_channel_id' not in columns:
                    logger.info("[i] help_channel_id kolonu ekleniyor...")
                    cursor.execute("ALTER TABLE help_requests ADD COLUMN help_channel_id TEXT")
                    logger.info("[+] help_channel_id kolonu eklendi.")
                if 'updated_at' not in columns:
                    logger.info("[i] help_requests tablosuna updated_at kolonu ekleniyor...")
                    # SQLite'da ALTER TABLE ile DEFAULT CURRENT_TIMESTAMP kullanılamaz, NULL ile ekle
                    cursor.execute("ALTER TABLE help_requests ADD COLUMN updated_at TIMESTAMP")
                    logger.info("[+] help_requests.updated_at kolonu eklendi.")
                
                # Challenge Hub Tabloları
                # Foreign key'leri aç (challenge tabloları için)
                cursor.execute("PRAGMA foreign_keys = ON")
                
                # Challenge tablolarını DROP edip yeniden oluştur (foreign key düzeltmeleri için)
                # NOT: Challenge verileri startup'ta temizleniyor, bu yüzden güvenli
                logger.info("[i] Challenge tabloları foreign key düzeltmeleri için yeniden oluşturuluyor...")
                cursor.execute("DROP TABLE IF EXISTS challenge_submissions")
                cursor.execute("DROP TABLE IF EXISTS challenge_participants")
                cursor.execute("DROP TABLE IF EXISTS challenge_hubs")
                cursor.execute("DROP TABLE IF EXISTS user_challenge_stats")
                # challenge_themes ve challenge_projects'i DROP etme (seed data var)
                
                # Challenge Themes (Temalar)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_themes (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        icon TEXT,
                        difficulty_range TEXT,
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Challenge Projects (Proje Şablonları)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_projects (
                        id TEXT PRIMARY KEY,
                        theme TEXT NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT,
                        objectives TEXT,
                        deliverables TEXT,
                        tasks TEXT,
                        difficulty_level TEXT DEFAULT 'intermediate',
                        estimated_hours INTEGER DEFAULT 48,
                        min_team_size INTEGER DEFAULT 2,
                        max_team_size INTEGER DEFAULT 6,
                        learning_objectives TEXT,
                        skills_required TEXT,
                        skills_developed TEXT,
                        resources TEXT,
                        knowledge_base_refs TEXT,
                        llm_customizable INTEGER DEFAULT 1,
                        llm_enhancement_prompt TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Challenge Hubs (Ana Challenge'lar)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_hubs (
                        id TEXT PRIMARY KEY,
                        creator_id TEXT NOT NULL,
                        theme TEXT NOT NULL,
                        team_size INTEGER NOT NULL,
                        status TEXT DEFAULT 'recruiting',
                        challenge_channel_id TEXT,
                        hub_channel_id TEXT,
                        selected_project_id TEXT,
                        llm_customizations TEXT,
                        deadline_hours INTEGER DEFAULT 48,
                        difficulty TEXT DEFAULT 'intermediate',
                        deadline TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (creator_id) REFERENCES users(slack_id) ON DELETE CASCADE
                    )
                """)
                
                # Migration: updated_at kolonu yoksa ekle
                cursor.execute("PRAGMA table_info(challenge_hubs)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'updated_at' not in columns:
                    logger.info("[i] challenge_hubs tablosuna updated_at kolonu ekleniyor...")
                    # SQLite'da ALTER TABLE ile DEFAULT CURRENT_TIMESTAMP kullanılamaz, NULL ile ekle
                    cursor.execute("ALTER TABLE challenge_hubs ADD COLUMN updated_at TIMESTAMP")
                    logger.info("[+] challenge_hubs.updated_at kolonu eklendi.")
                
                # Challenge Participants (Katılımcılar)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_participants (
                        id TEXT PRIMARY KEY,
                        challenge_hub_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        role TEXT,
                        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        points_earned INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(challenge_hub_id, user_id),
                        FOREIGN KEY (challenge_hub_id) REFERENCES challenge_hubs(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(slack_id) ON DELETE CASCADE
                    )
                """)
                
                # Migration: updated_at kolonu yoksa ekle
                cursor.execute("PRAGMA table_info(challenge_participants)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'updated_at' not in columns:
                    logger.info("[i] challenge_participants tablosuna updated_at kolonu ekleniyor...")
                    # SQLite'da ALTER TABLE ile DEFAULT CURRENT_TIMESTAMP kullanılamaz, NULL ile ekle
                    cursor.execute("ALTER TABLE challenge_participants ADD COLUMN updated_at TIMESTAMP")
                    logger.info("[+] challenge_participants.updated_at kolonu eklendi.")
                
                # Challenge Submissions (Takım Çıktıları)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_submissions (
                        id TEXT PRIMARY KEY,
                        challenge_hub_id TEXT NOT NULL,
                        team_name TEXT,
                        project_name TEXT,
                        solution_summary TEXT,
                        deliverables TEXT,
                        learning_outcomes TEXT,
                        llm_enhanced_features TEXT,
                        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        points_awarded INTEGER DEFAULT 0,
                        creativity_score INTEGER DEFAULT 0,
                        teamwork_score INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (challenge_hub_id) REFERENCES challenge_hubs(id) ON DELETE CASCADE
                    )
                """)
                
                # Migration: updated_at kolonu yoksa ekle
                cursor.execute("PRAGMA table_info(challenge_submissions)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'updated_at' not in columns:
                    logger.info("[i] challenge_submissions tablosuna updated_at kolonu ekleniyor...")
                    # SQLite'da ALTER TABLE ile DEFAULT CURRENT_TIMESTAMP kullanılamaz, NULL ile ekle
                    cursor.execute("ALTER TABLE challenge_submissions ADD COLUMN updated_at TIMESTAMP")
                    logger.info("[+] challenge_submissions.updated_at kolonu eklendi.")
                
                # User Challenge Stats (Kullanıcı İstatistikleri)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_challenge_stats (
                        user_id TEXT PRIMARY KEY,
                        total_challenges INTEGER DEFAULT 0,
                        completed_challenges INTEGER DEFAULT 0,
                        total_points INTEGER DEFAULT 0,
                        creativity_points INTEGER DEFAULT 0,
                        teamwork_points INTEGER DEFAULT 0,
                        favorite_theme TEXT,
                        last_challenge_date DATE,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(slack_id) ON DELETE CASCADE
                    )
                """)
                
                conn.commit()
                logger.debug("[i] Veritabanı tabloları kontrol edildi.")
                
                # Index'leri oluştur (performans için)
                self._create_indexes(cursor)
                conn.commit()
                
                # Seed data: Temalar ve Projeler
                self._seed_challenge_data(cursor)
                conn.commit()
                
        except sqlite3.Error as e:
            logger.error(f"[X] Veritabanı ilklendirme hatası: {e}")
            raise DatabaseError(f"Tablolar oluşturulamadı: {e}")
    
    def _seed_challenge_data(self, cursor):
        """Challenge temaları ve projeler için seed data ekler. Açılışta kontrol eder, yoksa ekler."""
        try:
            # Mobile App temasını ve projelerini temizle (artık kullanılmıyor)
            cursor.execute("DELETE FROM challenge_projects WHERE theme = 'Mobile App'")
            deleted_projects = cursor.rowcount
            if deleted_projects > 0:
                logger.info(f"[i] {deleted_projects} Mobile App projesi temizlendi.")
            
            cursor.execute("DELETE FROM challenge_themes WHERE id = 'theme_mobile_app'")
            if cursor.rowcount > 0:
                logger.info("[i] Mobile App teması temizlendi.")
            
            # Temalar
            themes = [
                ("theme_ai_chatbot", "AI Chatbot", "Yapay zeka destekli chatbot geliştirme", "🤖", "intermediate-advanced", 1),
                ("theme_web_app", "Web App", "Modern web uygulaması geliştirme", "🌐", "intermediate-advanced", 1),
                ("theme_data_analysis", "Data Analysis", "Veri analizi ve görselleştirme projeleri", "📊", "intermediate", 1),
                # Mobile App teması kaldırıldı - sadece AI ve Web App kullanılıyor
                # ("theme_mobile_app", "Mobile App", "Mobil uygulama geliştirme", "📱", "advanced", 0),
                ("theme_automation", "Automation", "İş süreçlerini otomatikleştirme", "⚙️", "intermediate", 1),
            ]
            
            themes_added = 0
            for theme_id, name, desc, icon, diff_range, is_active in themes:
                # Önce kontrol et
                cursor.execute("SELECT id FROM challenge_themes WHERE id = ?", (theme_id,))
                exists = cursor.fetchone()
                
                if not exists:
                    cursor.execute("""
                        INSERT INTO challenge_themes (id, name, description, icon, difficulty_range, is_active)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (theme_id, name, desc, icon, diff_range, is_active))
                    themes_added += 1
                    logger.debug(f"[+] Tema eklendi: {name}")
            
            if themes_added > 0:
                logger.info(f"[+] {themes_added} yeni tema eklendi.")
            else:
                logger.debug("[i] Tüm temalar zaten mevcut.")
            
            # Projeler
            import json
            
            all_projects = [
    {
        "id": "proj_sentiment_analyzer",
        "theme": "AI Chatbot",
        "name": "Basit Duygu Analizi",
        "description": "Kullanıcı yorumlarını pozitif, negatif veya nötr olarak sınıflandıran Python uygulaması",
        "objectives": ["Metin ön işleme", "Duygu sözlüğü oluşturma", "Sınıflandırma mantığı", "Test ve değerlendirme"],
        "deliverables": ["python_script", "sentiment_dictionary", "test_results", "documentation"],
        "tasks": [
            {"title": "Metin Ön İşleme", "description": "Küçük harfe çevirme, noktalama temizleme, Türkçe karakter düzenleme", "estimated_hours": 6},
            {"title": "Duygu Sözlüğü", "description": "Pozitif ve negatif kelime listesi oluştur", "estimated_hours": 6},
            {"title": "Sınıflandırma", "description": "Kelime sayımına göre duygu skoru hesapla", "estimated_hours": 8},
            {"title": "Test", "description": "Örnek metinlerle doğruluk testi yap", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 36,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_text_summarizer",
        "theme": "AI Chatbot",
        "name": "Basit Metin Özetleyici",
        "description": "Uzun metinleri cümle önemine göre özetleyen Python uygulaması",
        "objectives": ["Cümle ayrıştırma", "Kelime frekansı hesaplama", "Önem skoru atama", "Özet oluşturma"],
        "deliverables": ["python_script", "sample_summaries", "usage_guide"],
        "tasks": [
            {"title": "Cümle Ayrıştırma", "description": "Metni cümlelere ayır ve temizle", "estimated_hours": 4},
            {"title": "Kelime Frekansı", "description": "Her kelimenin kaç kez geçtiğini hesapla", "estimated_hours": 4},
            {"title": "Önem Skoru", "description": "Her cümleye puan ver", "estimated_hours": 6},
            {"title": "Özet Oluşturma", "description": "En önemli N cümleyi seç ve sırala", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 28,
        "min_team_size": 2,
        "max_team_size": 3
    },
    {
        "id": "proj_spam_detector",
        "theme": "AI Chatbot",
        "name": "Spam E-posta Dedektörü",
        "description": "E-postaları spam veya normal olarak sınıflandıran kural tabanlı sistem",
        "objectives": ["Spam anahtar kelimeleri belirleme", "Kural motoru oluşturma", "Skor hesaplama", "Test senaryoları"],
        "deliverables": ["python_script", "keyword_list", "test_emails", "accuracy_report"],
        "tasks": [
            {"title": "Anahtar Kelimeler", "description": "Spam göstergesi olan kelimeleri listele", "estimated_hours": 4},
            {"title": "Kural Motoru", "description": "Kurallara göre spam skoru hesaplayan fonksiyon", "estimated_hours": 8},
            {"title": "Eşik Belirleme", "description": "Spam/normal ayrımı için eşik değer belirle", "estimated_hours": 4},
            {"title": "Test", "description": "Örnek e-postalarla test et", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 30,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_recommendation_basic",
        "theme": "AI Chatbot",
        "name": "Basit Film Öneri Sistemi",
        "description": "Kullanıcı tercihlerine göre film öneren basit içerik tabanlı sistem",
        "objectives": ["Film veritabanı oluşturma", "Benzerlik hesaplama", "Öneri algoritması", "Kullanıcı arayüzü"],
        "deliverables": ["python_script", "movie_database", "sample_recommendations"],
        "tasks": [
            {"title": "Film Veritabanı", "description": "Film bilgilerini içeren CSV oluştur", "estimated_hours": 4},
            {"title": "Tür Eşleştirme", "description": "Türlere göre benzerlik hesapla", "estimated_hours": 6},
            {"title": "Öneri Fonksiyonu", "description": "Beğenilen filme göre öneri üret", "estimated_hours": 6},
            {"title": "CLI Arayüzü", "description": "Komut satırı arayüzü oluştur", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 30,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_flask_portfolio",
        "theme": "Web App",
        "name": "Kişisel Portfolyo Sitesi",
        "description": "Flask ile oluşturulan dinamik kişisel portfolyo web sitesi",
        "objectives": ["Flask kurulumu", "Şablon tasarımı", "Proje sayfaları", "İletişim formu"],
        "deliverables": ["flask_app", "html_templates", "css_styles", "deployment_guide"],
        "tasks": [
            {"title": "Flask Kurulum", "description": "Proje yapısını oluştur ve Flask ayarla", "estimated_hours": 4},
            {"title": "Ana Sayfa", "description": "Hakkımda bölümü ile ana sayfa", "estimated_hours": 6},
            {"title": "Proje Galerisi", "description": "Projeleri listeleyen dinamik sayfa", "estimated_hours": 8},
            {"title": "İletişim Formu", "description": "Basit iletişim formu ekle", "estimated_hours": 6}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 36,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_url_shortener",
        "theme": "Web App",
        "name": "URL Kısaltma Servisi",
        "description": "Uzun URL'leri kısaltan ve yönlendiren web uygulaması",
        "objectives": ["URL kısaltma algoritması", "Veritabanı tasarımı", "Yönlendirme sistemi", "İstatistik sayfası"],
        "deliverables": ["flask_app", "sqlite_database", "statistics_page", "documentation"],
        "tasks": [
            {"title": "Kısaltma Algoritması", "description": "Benzersiz kısa kod üreten fonksiyon", "estimated_hours": 4},
            {"title": "Veritabanı", "description": "SQLite ile URL depolama", "estimated_hours": 6},
            {"title": "Web Arayüzü", "description": "URL girişi ve kısaltma sayfası", "estimated_hours": 8},
            {"title": "Yönlendirme", "description": "Kısa URL'den orijinale yönlendirme", "estimated_hours": 6}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 36,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_blog_basic",
        "theme": "Web App",
        "name": "Basit Blog Uygulaması",
        "description": "Yazı ekleme, düzenleme ve listeleme özellikli blog sistemi",
        "objectives": ["CRUD işlemleri", "Şablon sistemi", "Veritabanı entegrasyonu", "Arama özelliği"],
        "deliverables": ["flask_app", "database_schema", "templates", "user_guide"],
        "tasks": [
            {"title": "Veritabanı Tasarımı", "description": "Blog yazıları için SQLite şeması", "estimated_hours": 4},
            {"title": "Yazı CRUD", "description": "Yazı ekleme, düzenleme, silme, listeleme", "estimated_hours": 10},
            {"title": "Şablonlar", "description": "Jinja2 ile HTML şablonları", "estimated_hours": 8},
            {"title": "Arama", "description": "Başlık ve içerikte arama", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 40,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_quiz_app",
        "theme": "Web App",
        "name": "Online Quiz Uygulaması",
        "description": "Çoktan seçmeli sorularla quiz yapan ve skor hesaplayan uygulama",
        "objectives": ["Soru veritabanı", "Quiz mantığı", "Skor hesaplama", "Sonuç sayfası"],
        "deliverables": ["flask_app", "question_database", "score_system", "result_page"],
        "tasks": [
            {"title": "Soru Veritabanı", "description": "JSON formatında soru havuzu oluştur", "estimated_hours": 6},
            {"title": "Quiz Akışı", "description": "Soru gösterme ve cevap alma mantığı", "estimated_hours": 8},
            {"title": "Skor Sistemi", "description": "Doğru/yanlış sayımı ve puan hesaplama", "estimated_hours": 4},
            {"title": "Sonuç Sayfası", "description": "Sonuç ve doğru cevapları göster", "estimated_hours": 6}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 36,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_sales_analysis",
        "theme": "Data Analysis",
        "name": "Satış Verisi Analizi",
        "description": "E-ticaret satış verilerini analiz edip görselleştiren Python projesi",
        "objectives": ["Veri temizleme", "Trend analizi", "Kategori bazlı analiz", "Dashboard oluşturma"],
        "deliverables": ["jupyter_notebook", "visualizations", "analysis_report", "insights_summary"],
        "tasks": [
            {"title": "Veri Temizleme", "description": "Eksik ve hatalı verileri düzelt", "estimated_hours": 6},
            {"title": "Keşifsel Analiz", "description": "Temel istatistikler ve dağılımlar", "estimated_hours": 8},
            {"title": "Trend Analizi", "description": "Aylık/haftalık satış trendleri", "estimated_hours": 8},
            {"title": "Görselleştirme", "description": "Matplotlib/Seaborn ile grafikler", "estimated_hours": 8}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 42,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_weather_analysis",
        "theme": "Data Analysis",
        "name": "Hava Durumu Verisi Analizi",
        "description": "Tarihi hava durumu verilerini analiz eden ve kalıpları bulan proje",
        "objectives": ["Veri toplama", "Mevsimsel analiz", "Korelasyon analizi", "Tahmin denemesi"],
        "deliverables": ["jupyter_notebook", "weather_charts", "correlation_matrix", "findings_report"],
        "tasks": [
            {"title": "Veri Hazırlama", "description": "CSV'den veri okuma ve temizleme", "estimated_hours": 6},
            {"title": "Mevsimsel Analiz", "description": "Mevsim bazlı sıcaklık/yağış analizi", "estimated_hours": 8},
            {"title": "Korelasyon", "description": "Değişkenler arası ilişki analizi", "estimated_hours": 6},
            {"title": "Görselleştirme", "description": "Zaman serisi ve ısı haritaları", "estimated_hours": 6}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 38,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_student_performance",
        "theme": "Data Analysis",
        "name": "Öğrenci Performans Analizi",
        "description": "Öğrenci notlarını analiz edip başarı faktörlerini araştıran proje",
        "objectives": ["Veri keşfi", "İstatistiksel analiz", "Faktör analizi", "Öneriler raporu"],
        "deliverables": ["jupyter_notebook", "statistical_analysis", "factor_charts", "recommendation_report"],
        "tasks": [
            {"title": "Veri Keşfi", "description": "Veri setini tanı ve temizle", "estimated_hours": 6},
            {"title": "Tanımlayıcı İstatistik", "description": "Ortalama, medyan, standart sapma", "estimated_hours": 6},
            {"title": "Faktör Analizi", "description": "Başarıyı etkileyen faktörleri bul", "estimated_hours": 8},
            {"title": "Görselleştirme", "description": "Box plot, scatter plot, histogram", "estimated_hours": 6}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 38,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_covid_tracker",
        "theme": "Data Analysis",
        "name": "Salgın Verisi Takip Sistemi",
        "description": "Açık kaynak salgın verilerini analiz eden ve görselleştiren dashboard",
        "objectives": ["API'den veri çekme", "Zaman serisi analizi", "Ülke karşılaştırması", "İnteraktif grafik"],
        "deliverables": ["python_script", "dashboard", "country_comparison", "trend_analysis"],
        "tasks": [
            {"title": "Veri Çekme", "description": "Açık kaynak API'den veri al", "estimated_hours": 6},
            {"title": "Veri İşleme", "description": "Pandas ile veri düzenleme", "estimated_hours": 6},
            {"title": "Zaman Serisi", "description": "Günlük/haftalık trend analizi", "estimated_hours": 8},
            {"title": "Dashboard", "description": "Plotly ile interaktif görselleştirme", "estimated_hours": 10}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 42,
        "min_team_size": 2,
        "max_team_size": 4
    },
    # Mobile App projeleri kaldırıldı - sadece AI ve Web App kullanılıyor
    # Automation Projeleri
    {
        "id": "proj_file_organizer",
        "theme": "Automation",
        "name": "Dosya Organizasyon Scripti",
        "description": "Belirli klasördeki dosyaları türüne göre otomatik organize eden Python scripti",
        "objectives": ["Dosya türü tespiti", "Klasör oluşturma", "Dosya taşıma", "Log tutma"],
        "deliverables": ["python_script", "config_file", "log_system", "usage_guide"],
        "tasks": [
            {"title": "Dosya Tespiti", "description": "Dosya uzantılarına göre tür belirleme", "estimated_hours": 4},
            {"title": "Klasör Yapısı", "description": "Türlere göre klasör oluşturma", "estimated_hours": 4},
            {"title": "Dosya Taşıma", "description": "Dosyaları ilgili klasöre taşıma", "estimated_hours": 6},
            {"title": "Log Sistemi", "description": "Yapılan işlemleri loglama", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 30,
        "min_team_size": 2,
        "max_team_size": 3
    },
    {
        "id": "proj_email_automation",
        "theme": "Automation",
        "name": "E-posta Otomasyon Scripti",
        "description": "Belirli koşullara göre otomatik e-posta gönderen Python scripti",
        "objectives": ["E-posta şablonları", "Koşul kontrolü", "SMTP entegrasyonu", "Zamanlama"],
        "deliverables": ["python_script", "email_templates", "config_file", "scheduler"],
        "tasks": [
            {"title": "SMTP Ayarları", "description": "E-posta sunucusu bağlantısı", "estimated_hours": 4},
            {"title": "Şablon Sistemi", "description": "Dinamik e-posta şablonları", "estimated_hours": 6},
            {"title": "Koşul Motoru", "description": "Belirli koşullarda e-posta gönderme", "estimated_hours": 6},
            {"title": "Zamanlama", "description": "Schedule ile otomatik çalıştırma", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 32,
        "min_team_size": 2,
        "max_team_size": 4
    },
    {
        "id": "proj_backup_automation",
        "theme": "Automation",
        "name": "Otomatik Yedekleme Scripti",
        "description": "Belirli klasörleri otomatik olarak yedekleyen ve sıkıştıran script",
        "objectives": ["Yedekleme stratejisi", "Sıkıştırma", "Tarih damgası", "Eski yedekleri temizleme"],
        "deliverables": ["python_script", "backup_system", "compression", "cleanup_logic"],
        "tasks": [
            {"title": "Yedekleme Mantığı", "description": "Dosya kopyalama ve tarih damgası", "estimated_hours": 6},
            {"title": "Sıkıştırma", "description": "ZIP formatında sıkıştırma", "estimated_hours": 4},
            {"title": "Temizleme", "description": "Eski yedekleri otomatik silme", "estimated_hours": 4},
            {"title": "Zamanlama", "description": "Cron/schedule ile otomatik çalıştırma", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 30,
        "min_team_size": 2,
        "max_team_size": 3
    },
    {
        "id": "proj_social_media_scheduler",
        "theme": "Automation",
        "name": "Sosyal Medya Zamanlayıcı",
        "description": "Twitter/LinkedIn için otomatik post zamanlayan ve gönderen script",
        "objectives": ["API entegrasyonu", "Zamanlama sistemi", "İçerik yönetimi", "Hata yönetimi"],
        "deliverables": ["python_script", "api_integration", "scheduler", "content_manager"],
        "tasks": [
            {"title": "API Bağlantısı", "description": "Twitter/LinkedIn API entegrasyonu", "estimated_hours": 8},
            {"title": "Zamanlama", "description": "Belirli saatte post gönderme", "estimated_hours": 6},
            {"title": "İçerik Yönetimi", "description": "JSON/CSV'den içerik okuma", "estimated_hours": 4},
            {"title": "Hata Yönetimi", "description": "API hatalarını yönetme", "estimated_hours": 4}
        ],
        "difficulty_level": "beginner",
        "estimated_hours": 36,
        "min_team_size": 2,
        "max_team_size": 4
    }
]
            
            projects_added = 0
            for project in all_projects:
                # Önce kontrol et - proje var mı?
                cursor.execute("SELECT id FROM challenge_projects WHERE id = ?", (project["id"],))
                exists = cursor.fetchone()
                
                if not exists:
                    # objectives ve deliverables JSON formatına çevir
                    objectives_json = json.dumps(project["objectives"], ensure_ascii=False)
                    deliverables_json = json.dumps(project["deliverables"], ensure_ascii=False)
                    tasks_json = json.dumps(project["tasks"], ensure_ascii=False)
                    
                    cursor.execute("""
                        INSERT INTO challenge_projects 
                        (id, theme, name, description, objectives, deliverables, tasks, difficulty_level, estimated_hours, min_team_size, max_team_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        project["id"],
                        project["theme"],
                        project["name"],
                        project["description"],
                        objectives_json,
                        deliverables_json,
                        tasks_json,
                        project["difficulty_level"],
                        project["estimated_hours"],
                        project["min_team_size"],
                        project["max_team_size"]
                    ))
                    projects_added += 1
                    logger.debug(f"[+] Proje eklendi: {project['name']} ({project['theme']})")
            
            if projects_added > 0:
                logger.info(f"[+] {projects_added} yeni proje eklendi.")
            else:
                logger.debug("[i] Tüm projeler zaten mevcut.")
            
            # Toplam istatistik
            cursor.execute("SELECT COUNT(*) FROM challenge_projects")
            total_projects = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM challenge_themes WHERE is_active = 1")
            total_themes = cursor.fetchone()[0]
            
            logger.info(f"[i] Challenge veritabanı durumu: {total_themes} tema, {total_projects} proje mevcut.")
        except Exception as e:
            logger.warning(f"[!] Challenge seed data eklenirken hata: {e}")
    
    def _create_indexes(self, cursor):
        """Performans için index'leri oluşturur."""
        try:
            indexes = [
                # Challenge indexes
                ("idx_challenge_hubs_status", "challenge_hubs", "status"),
                ("idx_challenge_hubs_creator", "challenge_hubs", "creator_id"),
                ("idx_challenge_participants_hub", "challenge_participants", "challenge_hub_id"),
                ("idx_challenge_participants_user", "challenge_participants", "user_id"),
                ("idx_challenge_submissions_hub", "challenge_submissions", "challenge_hub_id"),
                
                # Help indexes
                ("idx_help_requests_status", "help_requests", "status"),
                ("idx_help_requests_requester", "help_requests", "requester_id"),
                ("idx_help_requests_helper", "help_requests", "helper_id"),
                
                # Match indexes
                ("idx_matches_status", "matches", "status"),
                ("idx_matches_user1", "matches", "user1_id"),
                ("idx_matches_user2", "matches", "user2_id"),
                
                # Poll indexes
                ("idx_polls_is_closed", "polls", "is_closed"),
                ("idx_polls_creator", "polls", "creator_id"),
                ("idx_votes_poll", "votes", "poll_id"),
                ("idx_votes_user", "votes", "user_id"),
                
                # User indexes
                ("idx_users_slack_id", "users", "slack_id"),
            ]
            
            for index_name, table_name, column_name in indexes:
                try:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})")
                    logger.debug(f"[+] Index oluşturuldu: {index_name}")
                except sqlite3.Error as e:
                    logger.warning(f"[!] Index oluşturulamadı ({index_name}): {e}")
            
            logger.info("[+] Veritabanı index'leri kontrol edildi.")
        except Exception as e:
            logger.warning(f"[!] Index oluşturulurken hata: {e}")
    
    def clean_challenge_tables(self):
        """Challenge tablolarını temizler (startup için)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Foreign key constraint'leri geçici olarak devre dışı bırak
                cursor.execute("PRAGMA foreign_keys = OFF")
                
                # Sırayla temizle (foreign key bağımlılıklarına göre)
                tables = [
                    "challenge_submissions",
                    "challenge_participants",
                    "challenge_hubs",
                    "user_challenge_stats"
                ]
                
                deleted_counts = {}
                for table in tables:
                    cursor.execute(f"DELETE FROM {table}")
                    deleted_counts[table] = cursor.rowcount
                    logger.debug(f"[+] {table} temizlendi: {cursor.rowcount} kayıt silindi")
                
                # Foreign key constraint'leri tekrar etkinleştir
                cursor.execute("PRAGMA foreign_keys = ON")
                
                conn.commit()
                
                total_deleted = sum(deleted_counts.values())
                if total_deleted > 0:
                    logger.info(f"[+] Challenge tabloları temizlendi: {total_deleted} kayıt silindi")
                else:
                    logger.info("[i] Challenge tabloları zaten temizdi.")
                
                return deleted_counts
        except Exception as e:
            logger.error(f"[X] Challenge tabloları temizlenirken hata: {e}", exc_info=True)
            # Hata durumunda foreign key'leri tekrar etkinleştir
            try:
                with self.get_connection() as conn:
                    conn.execute("PRAGMA foreign_keys = ON")
            except:
                pass
            return {}