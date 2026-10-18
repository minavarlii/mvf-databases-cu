import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]

MAC_ARTIFACT = ROOT / "experiments/results/vector_cache_sweep_20261018T143927Z.json"
UBUNTU_ARTIFACT = (
    ROOT / "experiments/results/ubuntu/vector_cache_sweep_20261018T163108Z.json"
)

README = ROOT / "README.md"
DOCS = ROOT / "docs/vector-cache-sweep-results.md"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)


def _result_by_cache(
    payload: dict[str, Any],
    cache_mib: int,
) -> dict[str, Any]:
    results = cast(list[dict[str, Any]], payload["results"])

    for result in results:
        if cast(int, result["cache_mib"]) == cache_mib:
            return result

    raise AssertionError(f"Missing cache setting: {cache_mib} MiB")


def _assert_documented_values(
    text: str,
    payload: dict[str, Any],
) -> None:
    for cache_mib in (4, 16, 64):
        result = _result_by_cache(payload, cache_mib)

        build_mean_ms = cast(float, result["build_mean_ms"])
        query_mean_ms = cast(float, result["query_mean_ms"])
        overlap = cast(
            float,
            result["within_setting_pairwise_top5_overlap"],
        )

        build_seconds = build_mean_ms / 1000
        overlap_percent = overlap * 100

        assert f"{build_seconds:.3f}" in text
        assert f"{query_mean_ms:.3f}" in text
        assert f"{overlap_percent:.1f}%" in text


def test_cache_sweep_documentation_matches_committed_artifacts() -> None:
    mac = _load(MAC_ARTIFACT)
    ubuntu = _load(UBUNTU_ARTIFACT)

    readme = README.read_text(encoding="utf-8")
    docs = DOCS.read_text(encoding="utf-8")

    _assert_documented_values(readme, ubuntu)

    _assert_documented_values(docs, mac)
    _assert_documented_values(docs, ubuntu)

    assert MAC_ARTIFACT.name in docs
    assert (f"experiments/results/ubuntu/{UBUNTU_ARTIFACT.name}") in docs
    assert UBUNTU_ARTIFACT.name in readme
