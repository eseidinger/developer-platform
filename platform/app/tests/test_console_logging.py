import logging
import unittest

from app.console_logging import ConsoleFormatter


class SharedLogBoundaryTests(unittest.TestCase):
    def test_shared_console_omits_project_arguments_and_exception_messages(self):
        try:
            raise ValueError("private-project-and-password")
        except ValueError:
            import sys

            record = logging.LogRecord(
                "app.lifecycle",
                logging.ERROR,
                __file__,
                10,
                "Project %s failed",
                ("private-project",),
                sys.exc_info(),
                func="execute",
            )
        text = ConsoleFormatter().format(record)
        self.assertNotIn("private-project", text)
        self.assertIn("ValueError", text)
        self.assertIn("execute", text)
