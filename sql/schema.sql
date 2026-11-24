CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS diary (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
  ganji_year TEXT NOT NULL, lunar_year INT NOT NULL, lunar_month INT NOT NULL,
  is_leap BOOLEAN NOT NULL, lunar_day INT NOT NULL, day_ganji TEXT,
  solar_date DATE NOT NULL, ganji_mismatch BOOLEAN NOT NULL, label TEXT NOT NULL,
  original TEXT NOT NULL, translation TEXT NOT NULL,
  emotion TEXT NOT NULL CHECK (emotion IN ('일상','유머·불평','분노','비통')),
  intro TEXT NOT NULL, questions JSONB NOT NULL, embedding vector(1024) NOT NULL);
CREATE INDEX IF NOT EXISTS diary_embedding_hnsw ON diary USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS diary_solar_date ON diary (solar_date);
