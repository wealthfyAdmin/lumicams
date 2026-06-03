-- Run once against your Lumicams database if tables already existed before crowd analytics.
-- PostgreSQL 11+ (IF NOT EXISTS on ADD COLUMN)

ALTER TABLE cameras ADD COLUMN IF NOT EXISTS footfall_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS footfall_line_y DOUBLE PRECISION NOT NULL DEFAULT 0.5;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS heatmap_enabled BOOLEAN NOT NULL DEFAULT TRUE;
