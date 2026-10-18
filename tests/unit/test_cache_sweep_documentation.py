import json
import re
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]

MAC_CACHE_ARTIFACT = (
    ROOT / "experiments/results/vector_cache_sweep_20261018T143927Z.json"
)
UBUNTU_CACHE_ARTIFACT = (
    ROOT / "experiments/results/ubuntu/vector_cache_sweep_20261018T163108Z.json"
)
UBUNTU_MULTI_MODE_ARTIFACT = (
    ROOT / "experiments/results/ubuntu/multi_mode_latency_20261018T162532Z.json"
)
UBUNTU_CONCURRENCY_ARTIFACT = (
    ROOT / "experiments/results/ubuntu/vector_concurrency_20261018T162542Z.json"
)

README = ROOT / "README.md"
DOCS = ROOT / "docs/vector-cache-sweep-results.md"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)


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
    for row in _table_rows(text):
        if tuple(row[: len(prefix)]) == prefix:
            return row

    raise AssertionError(f"Missing markdown row beginning with {prefix!r}")


def _section(
    text: str,
    heading: str,
    next_heading: str | None,
) -> str:
    start = text.index(heading)

    if next_heading is None:
        return text[start:]

    end = text.index(next_heading, start + len(heading))
    return text[start:end]


def _cache_result(
    payload: dict[str, Any],
    cache_mib: int,
) -> dict[str, Any]:
    results = cast(list[dict[str, Any]], payload["results"])

    for result in results:
        if cast(int, result["cache_mib"]) == cache_mib:
            return result

    raise AssertionError(f"Missing cache setting {cache_mib} MiB")


def _assert_cache_section_matches(
    section: str,
    payload: dict[str, Any],
) -> None:
    for cache_mib in (4, 16, 64):
        result = _cache_result(payload, cache_mib)
        row = _find_row(section, (f"{cache_mib} MiB",))

        expected_build = f"{cast(float, result['build_mean_ms']) / 1000:.3f} s"
        expected_query = f"{cast(float, result['query_mean_ms']):.3f} ms"
        expected_overlap = (
            f"{cast(float, result['within_setting_pairwise_top5_overlap']) * 100:.1f}%"
        )

        assert row[2] == expected_build
        assert row[5] == expected_query
        assert row[7] == expected_overlap


def test_cache_sweep_docs_match_each_artifact_by_row() -> None:
    docs = DOCS.read_text(encoding="utf-8")

    mac_section = _section(
        docs,
        "## macOS / Apple M4 Pro",
        "## Ubuntu / GitHub Actions x86_64",
    )
    ubuntu_section = _section(
        docs,
        "## Ubuntu / GitHub Actions x86_64",
        "## Cross-machine interpretation",
    )

    _assert_cache_section_matches(
        mac_section,
        _load(MAC_CACHE_ARTIFACT),
    )
    _assert_cache_section_matches(
        ubuntu_section,
        _load(UBUNTU_CACHE_ARTIFACT),
    )

    assert MAC_CACHE_ARTIFACT.name in mac_section
    assert (
        f"experiments/results/ubuntu/{UBUNTU_CACHE_ARTIFACT.name}"
    ) in ubuntu_section


def test_readme_ubuntu_cache_paragraph_matches_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = _load(UBUNTU_CACHE_ARTIFACT)

    match = re.search(
        rf"The same repeated cache-sweep workload.*?"
        rf"{re.escape(UBUNTU_CACHE_ARTIFACT.name)}.*?"
        rf"(?=\n---|\n## )",
        readme,
        flags=re.DOTALL,
    )
    assert match is not None

    paragraph = match.group(0)

    for cache_mib in (4, 16, 64):
        result = _cache_result(payload, cache_mib)

        build = cast(float, result["build_mean_ms"]) / 1000
        query = cast(float, result["query_mean_ms"])
        overlap = cast(
            float,
            result["within_setting_pairwise_top5_overlap"],
        )

        assert f"{build:.3f}" in paragraph
        assert f"{query:.3f}" in paragraph
        assert f"{overlap * 100:.1f}%" in paragraph


def test_readme_ubuntu_multi_mode_rows_match_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = _load(UBUNTU_MULTI_MODE_ARTIFACT)

    for mode, label in (
        ("semantic", "Semantic"),
        ("hybrid", "Hybrid"),
        ("linked", "Linked"),
    ):
        values = cast(dict[str, Any], payload[mode])

        row = _find_row(
            readme,
            ("GitHub Actions / Ubuntu", label),
        )

        assert row[2] == (f"{cast(float, values['aggregate_mean_ms']):.3f} ms")
        assert row[3] == (f"{cast(float, values['aggregate_p95_ms']):.3f} ms")
        assert row[4] == (
            f"{cast(float, values['between_pass_mean_stddev_ms']):.3f} ms"
        )
        assert row[5] == (f"{cast(float, values['nonempty_result_rate']) * 100:.0f}%")


def test_readme_ubuntu_concurrency_row_matches_artifact() -> None:
    readme = README.read_text(encoding="utf-8")
    payload = _load(UBUNTU_CONCURRENCY_ARTIFACT)

    row = _find_row(
        readme,
        ("GitHub Actions / Ubuntu",),
    )

    # There are multiple Ubuntu rows in README. Select the concurrency-shaped one.
    concurrency_rows = [
        candidate
        for candidate in _table_rows(readme)
        if candidate
        and candidate[0] == "GitHub Actions / Ubuntu"
        and len(candidate) == 7
        and "→" in candidate[5]
    ]

    assert len(concurrency_rows) == 1
    row = concurrency_rows[0]

    assert row[1] == str(cast(int, payload["write_failures"]))
    assert row[2] == str(cast(int, payload["query_failures"]))
    assert row[3] == f"{cast(float, payload['commit_mean_ms']):.3f} ms"
    assert row[4] == f"{cast(float, payload['commit_p95_ms']):.3f} ms"

    baseline = cast(
        dict[str, Any],
        payload["baseline_quality"],
    )
    post_insert = cast(
        dict[str, Any],
        payload["post_insert_quality"],
    )
    post_delete = cast(
        dict[str, Any],
        payload["post_delete_quality"],
    )

    expected_recall = (
        f"{cast(float, baseline['recall_at_10']) * 100:.1f}% → "
        f"{cast(float, post_insert['recall_at_10']) * 100:.1f}% → "
        f"{cast(float, post_delete['recall_at_10']) * 100:.1f}%"
    )

    assert row[5] == expected_recall
    assert row[6] == str(cast(int, payload["orphan_chunks_after_cleanup"]))
