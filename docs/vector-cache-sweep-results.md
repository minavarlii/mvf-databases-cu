# MariaDB `mhnsw_max_cache_size` repeated-build sweep

This experiment uses a deterministic perturbed scratch corpus: each copy is a tiny norm-preserving rotation of a real stored vector, so the 98,500-row workload does not contain exact duplicated vectors.

- Source vectors: **3,940**
- Scratch corpus multiplier: **25×**
- Ground-truth query vectors: **20**
- Independent index rebuilds per cache setting: **3**
- Original cache setting: **16.0 MiB**

| Cache | Rows | Build mean | Build stddev | Build min–max | Query mean | Query P95 | Within-setting pairwise top-5 overlap |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 MiB | 98,500 | 37.023 s | 0.664 s | 36.536–37.779 s | 0.523 ms | 1.353 ms | 59.0% |
| 16 MiB | 98,500 | 29.556 s | 0.473 s | 29.068–30.013 s | 0.377 ms | 0.458 ms | 61.3% |
| 64 MiB | 98,500 | 19.550 s | 0.339 s | 19.265–19.925 s | 0.373 ms | 0.451 ms | 66.3% |

## Interpretation

Across repeated rebuilds, the fastest mean build occurred at 64 MiB and the slowest at 4 MiB (1.89× apart). Mean query latency varied by only 0.150 ms across cache settings. The minimum within-setting pairwise top-5 overlap was 59.0%. Because exact duplicate vectors were removed, any remaining ordering differences are treated as ANN rebuild variability rather than duplicate ties; this experiment does not claim that cache size deterministically changes retrieval quality.

## Across-cache first-rebuild comparison

This table is intentionally separate from the within-setting pairwise metric above. It compares only the first rebuild from each setting against the 4 MiB first rebuild.

| Cache | First rebuild top-5 overlap vs baseline |
|---:|---:|
| 4 MiB | reference |
| 16 MiB | 50.0% |
| 64 MiB | 67.0% |

Across-cache overlap is descriptive only: changing cache size also requires a fresh ANN rebuild, so it is not interpreted as a causal retrieval-quality effect of the cache setting.

The cache setting is a server-level limit, not an estimate of resident index memory. Build conclusions use repeated rebuilds and their variance rather than one build per setting.

Machine-readable artifact: `experiments/results/vector_cache_sweep_20261018T163108Z.json`
