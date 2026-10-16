"""Compatibility entry point for revision-scoped startup diagnostics."""

from .ai_diagnostics import MAX_BYTES, MAX_PODS, observe_failure_signals


def observe_startup_failure(runtime, project, component, revision, *, api=None):
    return observe_failure_signals(runtime, project, component, revision, api=api,
                                   require_nonzero_exit=True, startup_only=True)
