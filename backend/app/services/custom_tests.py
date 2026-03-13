from __future__ import annotations

from typing import Final

# Backward compatibility:
# some historical teacher-authored records stored duration in minutes
# instead of seconds. We normalize those legacy values at read-time.
_LEGACY_MINUTE_VALUES: Final[set[int]] = {5, 10, 15, 20, 30, 45, 60, 90, 120}
_DEFAULT_SECONDS: Final[int] = 5 * 60


def normalize_custom_test_time_limit_seconds(raw_value: int | None) -> int:
    if raw_value is None:
        return _DEFAULT_SECONDS

    raw = int(raw_value)
    if raw <= 0:
        return _DEFAULT_SECONDS

    if raw in _LEGACY_MINUTE_VALUES:
        return raw * 60

    return raw


def custom_test_duration_minutes(raw_value: int | None) -> int:
    normalized_seconds = normalize_custom_test_time_limit_seconds(raw_value)
    return max(1, normalized_seconds // 60)

