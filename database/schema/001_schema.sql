-- MVF core relational schema.
-- MariaDB 11.8+.

CREATE TABLE IF NOT EXISTS articles (
    id BIGINT NOT NULL AUTO_INCREMENT,
    wikipedia_page_id BIGINT NOT NULL,
    revision_id BIGINT NOT NULL,
    title VARCHAR(512) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    summary TEXT NULL,
    content LONGTEXT NOT NULL,
    word_count INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (id),
    UNIQUE KEY uq_articles_wikipedia_page_id (wikipedia_page_id),
    KEY ix_articles_title (title)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS categories (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(512) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (id),
    UNIQUE KEY uq_categories_name (name)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS article_categories (
    article_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,

    PRIMARY KEY (article_id, category_id),

    CONSTRAINT fk_article_categories_article
        FOREIGN KEY (article_id)
        REFERENCES articles (id)
        ON DELETE CASCADE,

    CONSTRAINT fk_article_categories_category
        FOREIGN KEY (category_id)
        REFERENCES categories (id)
        ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS article_links (
    source_article_id BIGINT NOT NULL,
    target_article_id BIGINT NOT NULL,

    PRIMARY KEY (source_article_id, target_article_id),

    CONSTRAINT fk_article_links_source
        FOREIGN KEY (source_article_id)
        REFERENCES articles (id)
        ON DELETE CASCADE,

    CONSTRAINT fk_article_links_target
        FOREIGN KEY (target_article_id)
        REFERENCES articles (id)
        ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS chunks (
    id BIGINT NOT NULL AUTO_INCREMENT,
    article_id BIGINT NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    token_count INT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (id),

    CONSTRAINT uq_chunks_article_chunk_index
        UNIQUE (article_id, chunk_index),

    CONSTRAINT fk_chunks_article
        FOREIGN KEY (article_id)
        REFERENCES articles (id)
        ON DELETE CASCADE,

    KEY ix_chunks_article_id (article_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
  