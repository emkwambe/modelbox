"""Throwaway: fails on purpose to show a red required check blocks merging into main.

Never merged; the pull request carrying it is closed and its branch deleted.
"""


def test_deliberately_fails() -> None:
    raise AssertionError("throwaway: this test fails on purpose")
