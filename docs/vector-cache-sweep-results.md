# MariaDB `mhnsw_max_cache_size` repeated-build sweep

This experiment uses a deterministic perturbed scratch corpus: each copy is a tiny norm-preserving rotation of a real stored vector, so the 98,500-row workload does not contain exact duplicated vectors.

- Source vectors: **3,940**
- Scratch corpus multiplier: **25×**
- Ground-truth query vectors: **20**
- Independent index rebuilds per cache setting: **3**
- Original cache setting: **16.0 MiB**

| Cache | Rows | Build mean | Build stddev | Build min–max | Query mean | Query P95 | Within-setting pairwise top-5 overlap |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 MiB | 98,500 | 20.823 s | 0.333 s | 20.493–21.160 s | 0.646 ms | 0.824 ms | 75.0% |
| 16 MiB | 98,500 | 14.809 s | 0.097 s | 14.697–14.867 s | 0.640 ms | 0.807 ms | 67.7% |
| 64 MiB | 98,500 | 8.794 s | 0.126 s | 8.690–8.934 s | 0.710 ms | 0.886 ms | 71.3% |

## Interpretation

Across repeated rebuilds, the fastest mean build occurred at 64 MiB and the slowest at 4 MiB (2.37× apart). Mean query latency varied by only 0.069 ms across cache settings. The minimum within-setting pairwise top-5 overlap was 67.7%. Because exact duplicate vectors were removed, any remaining ordering differences are treated as ANN rebuild variability rather than duplicate ties; this experiment does not claim that cache size deterministically changes retrieval quality.

## Across-cache first-rebuild comparison

This table is intentionally separate from the within-setting pairwise metric above. It compares only the first rebuild from each setting against the 4 MiB first rebuild.

| Cache | First rebuild top-5 overlap vs baseline |
|---:|---:|
| 4 MiB | reference |
| 16 MiB | 79.0% |
| 64 MiB | 78.0% |

Across-cache overlap is descriptive only: changing cache size also requires a fresh ANN rebuild, so it is not interpreted as a causal retrieval-quality effect of the cache setting.

The cache setting is a server-level limit, not an estimate of resident index memory. Build conclusions use repeated rebuilds and their variance rather than one build per setting.

Machine-readable artifact: `experiments/results/vector_cache_sweep_20261018T143927Z.json`
