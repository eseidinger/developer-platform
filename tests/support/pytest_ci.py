"""Make missing integration prerequisites visible instead of accepting skips."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--fail-on-skip", action="store_true", help="Fail if a required test is skipped"
    )


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption("--fail-on-skip"):
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter and reporter.stats.get("skipped"):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
