"""
Smoke test — verifies pytest discovery and project structure are correctly set up.

This test will be replaced by real agent tests as stories are implemented.
"""


def test_project_structure_smoke() -> None:
    """Confirm pytest discovers and runs tests from the correct directory."""
    assert True


def test_package_importable() -> None:
    """Confirm the tiktok_faceless package is importable."""
    import tiktok_faceless  # noqa: F401

    assert tiktok_faceless is not None
