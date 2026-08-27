"""Deliberately failing test to verify CI catches breakage. Will be deleted."""


def test_canary_must_fail():
    assert 1 + 1 == 3, "canary: CI must turn red on this"
