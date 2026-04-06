-- Footfall counting mode: line vs zone (PostgreSQL)
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS footfall_mode VARCHAR(16) NOT NULL DEFAULT 'line';
