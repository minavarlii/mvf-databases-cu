# MariaDB `mhnsw_max_cache_size` sweep

This experiment rebuilds the same large scratch `M=8` cosine vector index once per cache setting. It changes the MariaDB GLOBAL `mhnsw_max_cache_size`, measures build/search latency, checks top-5 stability, then restores the original server value.

- Scratch corpus multiplier: **25×**
- Original cache setting: **16.0 MiB**

| Cache | Rows | Index build | Mean query | P95 query | Top-5 stable |
|---:|---:|---:|---:|---:|:---:|
| 4 MiB | 98,500 | 22.202 s | 0.630 ms | 0.741 ms | yes |
| 16 MiB | 98,500 | 16.301 s | 0.662 ms | 0.899 ms | no |
| 64 MiB | 98,500 | 10.338 s | 0.635 ms | 0.721 ms | no |

The cache setting is a server-level limit, not an estimate of resident index memory. Results therefore report only the configured limit and observed build/search behavior.

Machine-readable artifact: `experiments/results/vector_cache_sweep_20261018T140036Z.json`
