from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


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


def test_results_at_a_glance_rows() -> None:
    readme = README.read_text(encoding="utf-8")

    start = readme.index("## Results at a glance")
    end = readme.index("### Contents", start)
    section = readme[start:end]

    expected = {
        "Corpus": "285 articles / 3,940 vectors",
        "Recall@10": "92.5%",
        "MRR": "0.782",
        "40-question semantic mean": "15.442 ms",
        "Native VECTOR INDEX vs brute force": "169.33×",
        "Filtered ANN speedup": "93.22×",
        "Backend pytest cases": "46 passed",
        "Frontend Vitest cases": "60 passed",
    }

    for label, value in expected.items():
        row = _find_row(section, (label,))
        assert row[1] == value


def test_mac_multi_mode_rows() -> None:
    readme = README.read_text(encoding="utf-8")

    expected = {
        "Semantic": ("1.292 ms", "1.490 ms", "0.146 ms", "100%"),
        "Hybrid": ("2.610 ms", "3.164 ms", "0.459 ms", "100%"),
        "Linked": ("86.949 ms", "88.778 ms", "0.408 ms", "100%"),
    }

    for mode, values in expected.items():
        row = _find_row(
            readme,
            ("Apple M4 Pro / macOS", mode),
        )

        assert tuple(row[2:6]) == values


def test_mac_concurrency_row() -> None:
    readme = README.read_text(encoding="utf-8")

    matches = [
        row
        for row in _table_rows(readme)
        if row and row[0] == "Apple M4 Pro / macOS" and len(row) == 7 and "→" in row[5]
    ]

    assert len(matches) == 1
    row = matches[0]

    assert row[1] == "0"
    assert row[2] == "0"
    assert row[3] == "0.934 ms"
    assert row[4] == "1.279 ms"
    assert row[5] == "92.5% → 92.5% → 92.5%"
    assert row[6] == "0"


def test_m_ground_truth_table() -> None:
    readme = README.read_text(encoding="utf-8")

    expected = {
        "4": (
            "168.898 ms",
            "15.429 ms",
            "15.417 ms",
            "16.675 ms",
            "0.110 ms",
            "92.5%",
            "0.782",
        ),
        "8": (
            "341.078 ms",
            "15.686 ms",
            "15.534 ms",
            "17.669 ms",
            "0.012 ms",
            "92.5%",
            "0.782",
        ),
        "16": (
            "1.035 s",
            "15.736 ms",
            "15.681 ms",
            "17.079 ms",
            "0.113 ms",
            "92.5%",
            "0.782",
        ),
        "32": (
            "3.850 s",
            "16.706 ms",
            "15.827 ms",
            "18.525 ms",
            "1.327 ms",
            "92.5%",
            "0.782",
        ),
    }

    for m_value, values in expected.items():
        candidates = [
            row
            for row in _table_rows(readme)
            if row and row[0] == m_value and len(row) == 8
        ]

        assert len(candidates) == 1
        assert tuple(candidates[0][1:]) == values


def test_ef_search_table() -> None:
    readme = README.read_text(encoding="utf-8")

    expected = {
        "200": (
            "15.523 ms",
            "17.069 ms",
            "0.363 ms",
            "92.5%",
            "0.782",
        ),
        "400": (
            "16.088 ms",
            "17.483 ms",
            "0.123 ms",
            "92.5%",
            "0.782",
        ),
        "800": (
            "15.834 ms",
            "17.257 ms",
            "0.228 ms",
            "92.5%",
            "0.782",
        ),
        "1600": (
            "16.993 ms",
            "18.117 ms",
            "1.383 ms",
            "92.5%",
            "0.782",
        ),
    }

    for ef_value, values in expected.items():
        row = _find_row(readme, (ef_value,))
        assert tuple(row[1:6]) == values
