INSERT INTO articles (
    id,
    wikipedia_page_id,
    revision_id,
    title,
    url,
    summary,
    content,
    word_count
)
VALUES
    (
        1,
        1001,
        1,
        'Machine learning',
        'https://en.wikipedia.org/wiki/Machine_learning',
        'Study of algorithms that improve through data.',
        'Machine learning uses data and algorithms to learn patterns.',
        10
    ),
    (
        2,
        1002,
        1,
        '80 Million Tiny Images',
        'https://en.wikipedia.org/wiki/80_Million_Tiny_Images',
        'A large computer vision image dataset.',
        '80 Million Tiny Images is a large image dataset used in computer vision research.',
        14
    ),
    (
        3,
        1003,
        1,
        'Federated learning',
        'https://en.wikipedia.org/wiki/Federated_learning',
        'Distributed machine learning without centralizing data.',
        'Federated learning trains models across distributed devices while keeping data local.',
        13
    );


INSERT INTO categories (
    id,
    name
)
VALUES
    (
        1,
        'Machine learning'
    ),
    (
        2,
        'Datasets in computer vision'
    );


INSERT INTO article_categories (
    article_id,
    category_id
)
VALUES
    (
        1,
        1
    ),
    (
        2,
        2
    ),
    (
        3,
        1
    );


INSERT INTO article_links (
    source_article_id,
    target_article_id
)
VALUES
    (
        1,
        2
    ),
    (
        1,
        3
    );


INSERT INTO chunks (
    id,
    article_id,
    chunk_index,
    content,
    token_count,
    embedding
)
VALUES
    (
        1,
        1,
        0,
        'Machine learning uses data and algorithms to learn patterns.',
        10,
        VEC_FromText(
            CONCAT(
                '[',
                REPEAT('0.05103103630798288,', 383),
                '0.05103103630798288]'
            )
        )
    ),
    (
        2,
        2,
        0,
        '80 Million Tiny Images is a large image dataset used in computer vision research.',
        14,
        VEC_FromText(
            CONCAT(
                '[',
                REPEAT('0.05103103630798288,', 383),
                '0.05103103630798288]'
            )
        )
    ),
    (
        3,
        3,
        0,
        'Federated learning trains models across distributed devices while keeping data local.',
        13,
        VEC_FromText(
            CONCAT(
                '[',
                REPEAT('0.05103103630798288,', 383),
                '0.05103103630798288]'
            )
        )
    );


ANALYZE TABLE
    articles,
    chunks,
    article_categories,
    categories,
    article_links;