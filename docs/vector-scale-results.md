# MariaDB vector-index scale probe

This scratch-table experiment repeats the canonical 3,940-vector corpus without changing production tables, then rebuilds the same `M=8` cosine `VECTOR INDEX`. It measures index build cost and indexed top-5 query latency while recording the server's configured HNSW cache ceiling.

- Source vectors: **3,940**
- `mhnsw_max_cache_size`: **16.0 MiB** (16,777,216 bytes)
- MariaDB: **11.8.9-MariaDB-ubu2404**
- OS/architecture: **Darwin / arm64**

| Corpus multiple | Rows | Raw vector payload | Index build | Mean query | P95 query |
|---:|---:|---:|---:|---:|---:|
| 1× | 3,940 | 5.8 MiB | 0.309 s | 0.418 ms | 0.493 ms |
| 5× | 19,700 | 28.9 MiB | 2.292 s | 0.543 ms | 0.986 ms |
| 10× | 39,400 | 57.7 MiB | 5.372 s | 0.584 ms | 0.754 ms |
| 25× | 98,500 | 144.3 MiB | 16.044 s | 0.660 ms | 0.863 ms |

The repeated vectors make this a **server/index scaling probe**, not a retrieval-quality benchmark. Recall/MRR continue to come from the real 40-question corpus harnesses. The scratch table is dropped after the run.

MariaDB 11.8 does not expose a reliable per-index resident-memory figure through the metadata path used by this harness. In particular, ordinary `information_schema.TABLES.INDEX_LENGTH` is not treated as HNSW memory. The experiment therefore reports the configured `mhnsw_max_cache_size` ceiling and raw vector payload, but does not invent a per-index memory value.

Machine-readable artifact: `experiments/results/vector_scale_20261018T134924Z.json`
