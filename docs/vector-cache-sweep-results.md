# MariaDB `mhnsw_max_cache_size` repeated-build sweep

This experiment uses a deterministic perturbed scratch corpus: each copy is a tiny norm-preserving rotation of a real stored vector, so the 98,500-row workload does not contain exact duplicated vectors.

- Source vectors: **3,940**
- Scratch corpus multiplier: **25×**
- Ground-truth query vectors: **20**
- Independent index rebuilds per cache setting: **3**
- Original cache setting: **16.0 MiB**

| Cache | Rows | Build mean | Build stddev | Build min–max | Query mean | Query P95 | Mean top-5 overlap |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 MiB | 98,500 | 20.718 s | 0.237 s | 20.482–20.956 s | 0.748 ms | 1.002 ms | 67.7% |
| 16 MiB | 98,500 | 15.043 s | 0.115 s | 14.970–15.175 s | 0.722 ms | 0.892 ms | 60.7% |
| 64 MiB | 98,500 | 8.785 s | 0.024 s | 8.767–8.813 s | 0.730 ms | 0.864 ms | 56.7% |

## Interpretation

Across repeated rebuilds, the fastest mean build occurred at 64 MiB and the slowest at 4 MiB (2.36× apart). Mean query latency varied by only 0.025 ms across cache settings. The minimum mean top-5 overlap with the first rebuild was 56.7%. Because exact duplicate vectors were removed, any remaining ordering differences are treated as ANN rebuild variability rather than duplicate ties; this experiment does not claim that cache size deterministically changes retrieval quality.

The cache setting is a server-level limit, not an estimate of resident index memory. Build conclusions use repeated rebuilds and their variance rather than one build per setting.

Machine-readable artifact: `experiments/results/vector_cache_sweep_20261018T141922Z.json`
