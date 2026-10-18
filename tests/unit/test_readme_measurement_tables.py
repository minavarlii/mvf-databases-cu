import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

MAC_MULTI_MODE = ROOT / "experiments/results/multi_mode_latency_20261018T115413Z.json"
MAC_CONCURRENCY = ROOT / "experiments/results/vector_concurrency_20261018T115420Z.json"
M_GROUND_TRUTH = (
    ROOT / "experiments/results/vector_index_m_ground_truth_20261018T112918Z.json"
)
EF_SEARCH = ROOT / "experiments/results/vector_ef_search_20261018T111327Z.json"
GROUND_TRUTH_LATENCY = (
    ROOT / "experiments/results/ground_truth_latency_20261018T112857Z.json"
)
INDEX_VS_BRUTE = ROOT / "experiments/results/index_vs_bruteforce_20261018T112952Z.json"
HYBRID_INDEX = ROOT / "experiments/results/hybrid_index_probe_20261018T111312Z.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_cell(cell: str) -> str:
    return cell.strip().replace("**", "").replace("`", "")


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []

    for line in text.splitlines():
        if not line.startswith("|"):
            continue

        cells = [_clean_cell(cell) for cell in line.strip("|").split("|")]

        if cells and not all(set(cell) <= {"-", ":"} for cell in cells):
            rows.append(cells)

    return rows


def _find_row(
    text: str,
    prefix: tuple[str, ...],
) -> list[str]:
    matches = [row for row in _table_rows(text) if tuple(row[: len(prefix)]) == prefix]

    assert len(matches) == 1, (
        f"Expected exactly one row starting with {prefix!r}, found {len(matches)}"
    )

    return matches[0]


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        found.append(mapping)

        for child in mapping.values():
            found.extend(_walk_dicts(child))

    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))

    return found


def _number(
    mapping: dict[str, Any],
    *keys: str,
) -> float:
    for key in keys:
        value = mapping.get(key)

        if isinstance(value, int | float):
            return float(value)

    raise AssertionError(
        f"None of the numeric keys {keys!r} found in {mapping.keys()!r}"
    )


def _mapping_for_setting(
    payload: Any,
    setting: int,
    keys: tuple[str, ...],
) -> dict[str, Any]:
    for mapping in _walk_dicts(payload):
        for key in keys:
            value = mapping.get(key)

            if isinstance(value, int | float) and int(value) == setting:
                return mapping

    raise AssertionError(f"Could not find setting {setting} using keys {keys!r}")


def _format_build_ms(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.3f} s"
    return f"{value:.3f} ms"


def _all_numbers(value: Any) -> list[float]:
    numbers: list[float] = []

    if isinstance(value, bool):
        return numbers

    if isinstance(value, int | float):
        numbers.append(float(value))

    elif isinstance(value, dict):
        for child in cast(dict[str, Any], value).values():
            numbers.extend(_all_numbers(child))

    elif isinstance(value, list):
        for child in value:
            numbers.extend(_all_numbers(child))

    return numbers


def _artifact_contains_number(
    payload: Any,
    expected: float,
    tolerance: float = 0.005,
) -> bool:
    return any(abs(value - expected) <= tolerance for value in _all_numbers(payload))


def test_results_at_a_glance_rows_come_from_artifacts() -> None:
    readme = README.read_text(encoding="utf-8")

    start = readme.index("## Results at a glance")
    end = readme.index("### Contents", start)
    section = readme[start:end]

    latency = _load(GROUND_TRUTH_LATENCY)
    index_vs_brute = _load(INDEX_VS_BRUTE)
    hybrid = _load(HYBRID_INDEX)

    semantic_row = _find_row(
        section,
        ("40-question semantic mean",),
    )
    semantic_mean = float(semantic_row[1].removesuffix(" ms"))
    assert _artifact_contains_number(
        latency,
        semantic_mean,
        tolerance=0.001,
    )

    index_row = _find_row(
        section,
        ("Native VECTOR INDEX vs brute force",),
    )
    index_speedup = float(index_row[1].removesuffix("×"))
    assert _artifact_contains_number(
        index_vs_brute,
        index_speedup,
        tolerance=0.01,
    )

    hybrid_row = _find_row(
        section,
        ("Filtered ANN speedup",),
    )
    hybrid_speedup = float(hybrid_row[1].removesuffix("×"))
    assert _artifact_contains_number(
        hybrid,
        hybrid_speedup,
        tolerance=0.01,
    )

    assert (
        _find_row(
            section,
            ("Backend pytest cases",),
        )[1]
        == "46 passed"
    )

    assert (
        _find_row(
            section,
            ("Frontend Vitest cases",),
        )[1]
        == "60 passed"
    )


def test_mac_multi_mode_rows_match_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = cast(dict[str, Any], _load(MAC_MULTI_MODE))

    for key, label in (
        ("semantic", "Semantic"),
        ("hybrid", "Hybrid"),
        ("linked", "Linked"),
    ):
        values = cast(dict[str, Any], payload[key])

        row = _find_row(
            readme,
            ("Apple M4 Pro / macOS", label),
        )

        assert row[2] == (f"{_number(values, 'aggregate_mean_ms'):.3f} ms")
        assert row[3] == (f"{_number(values, 'aggregate_p95_ms'):.3f} ms")
        assert row[4] == (f"{_number(values, 'between_pass_mean_stddev_ms'):.3f} ms")
        assert row[5] == (f"{_number(values, 'nonempty_result_rate') * 100:.0f}%")


def test_mac_concurrency_row_matches_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = cast(dict[str, Any], _load(MAC_CONCURRENCY))

    start = readme.index("### Concurrent writers and ANN stability")
    end = readme.index("Artifacts:", start)
    section = readme[start:end]

    row = _find_row(
        section,
        ("Apple M4 Pro / macOS",),
    )

    assert row[1] == str(int(_number(payload, "write_failures")))
    assert row[2] == str(int(_number(payload, "query_failures")))
    assert row[3] == (f"{_number(payload, 'commit_mean_ms'):.3f} ms")
    assert row[4] == (f"{_number(payload, 'commit_p95_ms'):.3f} ms")

    baseline = cast(
        dict[str, Any],
        payload["baseline_quality"],
    )
    inserted = cast(
        dict[str, Any],
        payload["post_insert_quality"],
    )
    cleaned = cast(
        dict[str, Any],
        payload["post_delete_quality"],
    )

    expected_recall = (
        f"{_number(baseline, 'recall_at_10') * 100:.1f}% → "
        f"{_number(inserted, 'recall_at_10') * 100:.1f}% → "
        f"{_number(cleaned, 'recall_at_10') * 100:.1f}%"
    )

    assert row[5] == expected_recall
    assert row[6] == str(
        int(
            _number(
                payload,
                "orphan_chunks_after_cleanup",
            )
        )
    )


def test_m_ground_truth_table_matches_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = _load(M_GROUND_TRUTH)

    start = readme.index("### Vector-index `M` study")
    end = readme.index(
        "A separate single-query exact-top-5 probe",
        start,
    )
    section = readme[start:end]

    for m_value in (4, 8, 16, 32):
        values = _mapping_for_setting(
            payload,
            m_value,
            ("m", "M"),
        )

        row = _find_row(section, (str(m_value),))

        build_ms = _number(
            values,
            "build_time_ms",
            "build_ms",
            "index_build_ms",
        )
        mean_ms = _number(
            values,
            "mean_query_ms",
        )
        median_ms = _number(
            values,
            "median_query_ms",
        )
        p95_ms = _number(
            values,
            "p95_query_ms",
        )
        stddev_ms = _number(
            values,
            "between_pass_mean_stddev_ms",
        )
        recall = _number(
            values,
            "recall_at_10",
            "recall@10",
        )
        mrr = _number(values, "mrr", "MRR")

        assert row[1] == _format_build_ms(build_ms)
        assert row[2] == f"{mean_ms:.3f} ms"
        assert row[3] == f"{median_ms:.3f} ms"
        assert row[4] == f"{p95_ms:.3f} ms"
        assert row[5] == f"{stddev_ms:.3f} ms"
        assert row[6] == f"{recall * 100:.1f}%"
        assert row[7] == f"{mrr:.3f}"


def test_ef_search_table_matches_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = _load(EF_SEARCH)

    start = readme.index("### Runtime HNSW `mhnsw_ef_search` study")
    end = readme.index(
        "### Multi-query ground-truth latency",
        start,
    )
    section = readme[start:end]

    for ef_value in (200, 400, 800, 1600):
        values = _mapping_for_setting(
            payload,
            ef_value,
            (
                "ef_search",
                "mhnsw_ef_search",
                "ef",
            ),
        )

        row = _find_row(section, (str(ef_value),))

        mean_ms = _number(
            values,
            "aggregate_mean_query_ms",
        )
        p95_ms = _number(
            values,
            "aggregate_p95_query_ms",
        )
        stddev_ms = _number(
            values,
            "aggregate_stddev_query_ms",
        )
        recall = _number(
            values,
            "mean_recall_at_10",
        )
        mrr = _number(values, "mean_mrr")

        assert row[1] == f"{mean_ms:.3f} ms"
        assert row[2] == f"{p95_ms:.3f} ms"
        assert row[3] == f"{stddev_ms:.3f} ms"
        assert row[4] == f"{recall * 100:.1f}%"
        assert row[5] == f"{mrr:.3f}"
