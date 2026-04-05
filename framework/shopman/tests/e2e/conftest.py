"""
Playwright E2E — Pytest fixtures.

Requires:
  pip install pytest-playwright
  playwright install chromium

Run:
  make run  # in another terminal (server must be up)
  pytest tests/e2e/ --base-url=http://localhost:8000
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        action="store",
        default="http://localhost:8000",
        help="Base URL of the running Django server",
    )


@pytest.fixture
def base_url(request):
    return request.config.getoption("--base-url")
