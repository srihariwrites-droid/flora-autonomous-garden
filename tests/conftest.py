"""Pytest configuration: ensure e2e tests run last.

Playwright's session-scoped browser fixture keeps the asyncio event loop
active while it's alive. Running e2e tests before other async tests causes
"Runner.run() cannot be called from a running event loop" errors because
the session loop is still in use during teardown. Moving them to the end
avoids this clash.
"""


def pytest_collection_modifyitems(items: list) -> None:
    e2e = [i for i in items if "test_dashboard_e2e" in i.nodeid]
    rest = [i for i in items if "test_dashboard_e2e" not in i.nodeid]
    items[:] = rest + e2e
