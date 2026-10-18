# MariaDB `mhnsw_max_cache_size` repeated-build sweep

This experiment uses a deterministic perturbed scratch corpus: each copy is a tiny norm-preserving rotation of a real stored vector, so the 98,500-row workload does not contain exact duplicated vectors.

- Source vectors: **3,940**
- Scratch corpus multiplier: **25×**
- Ground-truth query vectors: **20**
- Independent index rebuilds per cache setting: **3**
- Original cache setting: **16.0 MiB**

## macOS / Apple M4 Pro

| Cache | Rows | Build mean | Build stddev | Build min–max | Query mean | Query P95 | Within-setting pairwise top-5 overlap |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 MiB | 98,500 | 20.823 s | 0.333 s | 20.493–21.160 s | 0.646 ms | 0.824 ms | 75.0% |
| 16 MiB | 98,500 | 14.809 s | 0.097 s | 14.697–14.867 s | 0.640 ms | 0.807 ms | 67.7% |
| 64 MiB | 98,500 | 8.794 s | 0.126 s | 8.690–8.934 s | 0.710 ms | 0.886 ms | 71.3% |

Across repeated rebuilds, the fastest mean build occurred at 64 MiB and the slowest at 4 MiB (**2.37× apart**). Mean query latency varied by only **0.069 ms** across cache settings. The minimum within-setting pairwise top-5 overlap was **67.7%**.

### macOS across-cache first-rebuild comparison

This table is intentionally separate from the within-setting pairwise metric above. It compares only the first rebuild from each setting against the 4 MiB first rebuild.

| Cache | First rebuild top-5 overlap vs baseline |
|---:|---:|
| 4 MiB | reference |
| 16 MiB | 79.0% |
| 64 MiB | 78.0% |

Machine-readable artifact:
`experiments/results/vector_cache_sweep_20261018T143927Z.json`

## Ubuntu / GitHub Actions x86_64

Runner metadata recorded by the benchmark:

- OS: **Linux 6.17.0-1022-azure**
- Architecture: **x86_64**
- Python: **3.12.15**
- MariaDB: **11.8.9-MariaDB-ubu2404**
- Machine model: **Microsoft Corporation Virtual Machine**
- CPU: **AMD EPYC 9V45 96-Core Processor**
- Memory: **15.61 GiB**

| Cache | Rows | Build mean | Build stddev | Build min–max | Query mean | Query P95 | Within-setting pairwise top-5 overlap |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 MiB | 98,500 | 37.482 s | 0.767 s | 36.779–38.300 s | 0.509 ms | 0.645 ms | 63.0% |
| 16 MiB | 98,500 | 28.292 s | 0.484 s | 27.937–28.844 s | 0.373 ms | 0.450 ms | 63.0% |
| 64 MiB | 98,500 | 19.848 s | 0.107 s | 19.760–19.967 s | 0.392 ms | 0.455 ms | 77.0% |

Across repeated rebuilds, the fastest mean build again occurred at 64 MiB and the slowest at 4 MiB (**1.89× apart**). Mean query latency varied by only **0.136 ms** across cache settings. The minimum within-setting pairwise top-5 overlap was **63.0%**.

### Ubuntu across-cache first-rebuild comparison

As above, this comparison is descriptive only and uses the first rebuild from each cache setting.

| Cache | First rebuild top-5 overlap vs baseline |
|---:|---:|
| 4 MiB | reference |
| 16 MiB | 57.0% |
| 64 MiB | 58.0% |

Machine-readable artifact:
`experiments/results/ubuntu/vector_cache_sweep_20261018T160756Z.json`

## Cross-machine interpretation

The repeated-build finding reproduced on both machines: increasing `mhnsw_max_cache_size` substantially reduced HNSW index-build time, while query latency remained comparatively flat.

The within-setting top-5 overlap does **not** move monotonically with cache size across environments:

- macOS: **75.0% / 67.7% / 71.3%** for 4 / 16 / 64 MiB;
- Ubuntu: **63.0% / 63.0% / 77.0%** for 4 / 16 / 64 MiB.

That non-monotonic pattern supports treating the ranking differences as **ANN rebuild variability**, not as evidence that a larger cache deterministically improves retrieval quality. The across-cache first-rebuild comparison is therefore kept separate and descriptive rather than interpreted causally.

The cache setting is a **server-level limit**, not an estimate of resident index memory. Build conclusions use repeated rebuilds and their variance rather than one build per setting, and absolute build times are not compared directly across machines because the hardware differs.
