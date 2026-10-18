"""Tests for destructive prebuilt-restore safeguards."""

import pytest

from scripts.restore_prebuilt import validate_restore_request


def test_restore_requires_explicit_confirmation() -> None:
    """Refuse to delete corpus rows without an explicit acknowledgement."""
    with pytest.raises(ValueError, match="--confirm-reset"):
        validate_restore_request(confirm_reset=False, expected_database="mvf")


def test_restore_requires_expected_database_name() -> None:
    """Refuse a destructive restore when the expected database is ambiguous."""
    with pytest.raises(ValueError, match="expected database name is empty"):
        validate_restore_request(confirm_reset=True, expected_database="")


def test_restore_accepts_explicit_safe_request() -> None:
    """Accept a confirmed restore with a non-empty database name."""
    validate_restore_request(confirm_reset=True, expected_database="mvf")
