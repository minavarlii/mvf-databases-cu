-- MVF: MariaDB-native vector search examples.
-- Run after the schema, corpus and embeddings have been loaded.
--
-- The examples intentionally use an embedding already stored in the corpus as
-- the query vector, so this file is pasteable without generating a 384-number
-- vector by hand. Application queries use the same shapes with a bound
-- :embedding parameter produced by sentence-transformers.

SET @query_embedding = (
    SELECT VEC_ToText(embedding)
    FROM chunks
    ORDER BY id
    LIMIT 1
);

SET @result_limit = 5;
SET @category = 'Machine learning';
SET @source_title = 'Machine learning';

-- 1) Native semantic nearest-neighbour search.
SELECT
    c.id AS chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM chunks AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
ORDER BY distance ASC
LIMIT 5;

-- 2) Same vector ranking, constrained by an ordinary relational category
-- predicate in the same SQL statement.
SELECT
    c.id AS chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM chunks AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
WHERE c.article_id IN (
    SELECT ac.article_id
    FROM article_categories AS ac
    INNER JOIN categories AS cat
        ON cat.id = ac.category_id
    WHERE cat.name = @category
)
ORDER BY distance ASC
LIMIT 5;

-- 3) Graph-constrained vector ranking. MariaDB first follows the local
-- Wikipedia link graph and then ranks only chunks belonging to linked targets.
SELECT
    c.id AS chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM article_links AS al
INNER JOIN articles AS source
    ON source.id = al.source_article_id
INNER JOIN articles AS target
    ON target.id = al.target_article_id
INNER JOIN chunks AS c
    ON c.article_id = target.id
WHERE source.title = @source_title
ORDER BY distance ASC
LIMIT 5;

-- 4) Inspect whether MariaDB chooses the native vector index for semantic
-- retrieval.
EXPLAIN
SELECT
    c.id,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM chunks AS c
ORDER BY distance ASC
LIMIT 5;

-- 5) Inspect the mixed relational/vector hybrid plan.
EXPLAIN
SELECT
    c.id,
    c.article_id,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM chunks AS c
WHERE c.article_id IN (
    SELECT ac.article_id
    FROM article_categories AS ac
    INNER JOIN categories AS cat
        ON cat.id = ac.category_id
    WHERE cat.name = @category
)
ORDER BY distance ASC
LIMIT 5;

-- 6) Ordinary relational predicate: only articles above a minimum word count.
SET @min_word_count = 1000;

SELECT
    c.id AS chunk_id,
    c.article_id,
    a.title AS article_title,
    a.word_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM chunks AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
WHERE a.word_count >= @min_word_count
ORDER BY distance ASC
LIMIT 5;

-- 7) Ordinary temporal predicate: rank vectors only from rows edited since a
-- chosen timestamp.
SET @edited_since = '2026-01-01 00:00:00';

SELECT
    c.id AS chunk_id,
    c.article_id,
    a.title AS article_title,
    a.updated_at,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@query_embedding)
    ) AS distance
FROM chunks AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
WHERE a.updated_at >= @edited_since
ORDER BY distance ASC
LIMIT 5;

