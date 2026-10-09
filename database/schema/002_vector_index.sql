-- MVF MariaDB vector index.
-- Cosine distance is used because the vectors represent text embeddings.

CREATE VECTOR INDEX IF NOT EXISTS ix_chunks_embedding
ON chunks (embedding)
M = 8
DISTANCE = cosine;
