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

| Cache | First rebuild top-5 overlap vs baseline |
|---:|---:|
| 4 MiB | reference |
| 16 MiB | 79.0% |
| 64 MiB | 78.0% |

Machine-readable artifact: `experiments/results/vector_cache_sweep_20261018T143927Z.json`

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
| 4 MiB | 98,500 | 37.023 s | 0.664 s | 36.536–37.779 s | 0.523 ms | 1.353 ms | 59.0% |
| 16 MiB | 98,500 | 29.556 s | 0.473 s | 29.068–30.013 s | 0.377 ms | 0.458 ms | 61.3% |
| 64 MiB | 98,500 | 19.550 s | 0.339 s | 19.265–19.925 s | 0.373 ms | 0.451 ms | 66.3% |

Across repeated rebuilds, the fastest mean build again occurred at 64 MiB and the slowest at 4 MiB (**1.89× apart**). Mean query latency varied by **0.150 ms** across cache settings. The minimum within-setting pairwise top-5 overlap was **59.0%**.

### Ubuntu across-cache first-rebuild comparison

| Cache | First rebuild top-5 overlap vs baseline |
|---:|---:|
| 4 MiB | reference |
| 16 MiB | 50.0% |
| 64 MiB | 67.0% |

Machine-readable artifact: `experiments/results/ubuntu/vector_cache_sweep_20261018T163108Z.json`

## Cross-machine interpretation

The repeated-build finding reproduced on both machines: increasing `mhnsw_max_cache_size` substantially reduced HNSW index-build time, while query latency remained comparatively small.

The within-setting top-5 overlap does not follow the same pattern across environments: macOS measured **75.0% / 67.7% / 71.3%**, while Ubuntu measured **59.0% / 61.3% / 66.3%** for 4 / 16 / 64 MiB. This supports treating ranking changes as **ANN rebuild variability**, not as evidence that cache size deterministically improves retrieval quality. Across-cache first-rebuild comparisons are therefore reported separately and descriptively rather than interpreted causally.

Independent GitHub-hosted Ubuntu runs also showed noticeable absolute timing drift on the shared runner while preserving the same qualitative cache-size trend. Cross-machine CI measurements are therefore used to reproduce behavior and directionality, not as hardware-normalized latency comparisons.

The cache setting is a **server-level limit**, not an estimate of resident index memory. Build conclusions use repeated rebuilds and their variance rather than one build per setting.
