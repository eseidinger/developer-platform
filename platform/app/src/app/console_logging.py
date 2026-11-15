"""Console records contain event locations, never project payloads or identifiers.

Project detail belongs in the scoped API, audit and telemetry stores, where the
purge lifecycle can erase it. Docker's shared append-only stdout cannot provide
safe per-project deletion, so exception messages and interpolated arguments are
intentionally excluded from this shared transport.
"""

import json
import logging


class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        result = {
            "level": record.levelname.lower(),
            "event": record.name + "." + record.funcName,
        }
        if record.exc_info and record.exc_info[0]:
            result["error_type"] = record.exc_info[0].__name__
        return json.dumps(result, separators=(",", ":"))
