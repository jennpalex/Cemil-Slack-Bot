-- Migration: Canvas ve özet mesaj desteği için yeni alanlar
-- Date: 2026-01-27
-- Description: Challenge'lar için canvas/özet mesajı ve proje bilgilerini tutacak kolonlar

-- Challenge hub için yeni alanlar
ALTER TABLE challenge_hubs ADD COLUMN project_name TEXT;
ALTER TABLE challenge_hubs ADD COLUMN project_description TEXT;
ALTER TABLE challenge_hubs ADD COLUMN summary_message_ts TEXT;
ALTER TABLE challenge_hubs ADD COLUMN summary_message_channel_id TEXT;
ALTER TABLE challenge_hubs ADD COLUMN ended_at TIMESTAMP;
