"""AI run completion must use the append-only audit contract."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app import main
from app.identity import Principal


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class AIRunAuditTests(unittest.TestCase):
    def test_run_states_use_valid_audit_results_and_preserve_domain_state(self):
        for state in ('completed', 'abstained', 'failed'):
            with self.subTest(state=state), ExitStack() as stack:
                run_id = uuid4()
                outcome = {'state': state, 'result': {}, 'evidence': [], 'tool_calls': 1,
                           'estimated_cost_usd': .001}
                stack.enter_context(patch.object(main, 'require_permission'))
                stack.enter_context(patch.object(main, 'connect', return_value=Connection()))
                stack.enter_context(patch.object(main, 'access_scope', return_value=None))
                stack.enter_context(patch.object(main.ai_store, 'classification', return_value='internal'))
                stack.enter_context(patch.object(main.ai_model, 'configured_model'))
                create = stack.enter_context(patch.object(main.ai_store, 'create_run', return_value=run_id))
                finish = stack.enter_context(patch.object(main.ai_store, 'finish_run'))
                stack.enter_context(patch.object(main.ai_tools, 'make_tools', return_value=[]))
                agent = stack.enter_context(patch.object(main.ai_agent, 'run', return_value=outcome))

                def append(actor, action, target_kind, target_id, result, scope, detail):
                    if result not in {'succeeded', 'failed', 'denied', 'rejected'}:
                        raise ValueError('Audit result violates database constraint')
                    self.assertEqual(result, 'failed' if state == 'failed' else 'succeeded')
                    self.assertEqual(detail['state'], state)
                    self.assertEqual(scope, {'project': 'demo'})
                    self.assertEqual(target_id, str(run_id))
                    return 42

                audit = stack.enter_context(patch.object(main, 'record_event', side_effect=append))
                response = main.create_ai_run('demo', main.AIRunRequest(kind='explain_application'),
                                              Principal('https://issuer.example', 'human', 'Human'))
                self.assertEqual(response['state'], state)
                self.assertEqual(response['run_id'], str(run_id))
                create.assert_called_once()
                agent.assert_called_once()
                finish.assert_called_once()
                audit.assert_called_once()

    def test_required_audit_failure_still_returns_unavailable(self):
        with patch.object(main, 'record_event', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(HTTPException) as error:
                main.required_audit(main.Actor('oidc', 'human'), 'ai.run', 'ai-run', 'run', 'succeeded')
        self.assertEqual(error.exception.status_code, 503)


class RuntimeRollbackCandidateTests(unittest.TestCase):
    def connection(self, revision=2, state='succeeded'):
        from unittest.mock import Mock
        connection = Mock()
        connection.execute.return_value.fetchone.side_effect = [
            (revision, state), (1, {'image': 'good'}), ({'image': 'bad'},)]
        return connection

    def test_applied_runtime_failure_allows_retained_rollback_candidate(self):
        callback = unittest.mock.Mock(return_value=True)
        target, base, previous = main.ai_changes.candidate(self.connection(), 'demo', 2, callback)
        self.assertEqual((target, base, previous), (1, {'image': 'bad'}, {'image': 'good'}))
        callback.assert_called_once_with()

    def test_no_runtime_failure_or_inflight_or_stale_deployment_is_rejected(self):
        for revision, state, confirmed in [(2, 'succeeded', False), (2, 'queued', True),
                                           (2, 'running', True), (3, 'failed', True)]:
            with self.subTest(revision=revision, state=state):
                with self.assertRaises(main.ai_changes.ProposalUnavailable):
                    main.ai_changes.candidate(self.connection(revision, state), 'demo', 2, lambda: confirmed)

    def test_failed_apply_does_not_require_available_runtime(self):
        callback = unittest.mock.Mock(side_effect=AssertionError('Should not query runtime'))
        self.assertEqual(main.ai_changes.candidate(self.connection(state='failed'), 'demo', 2, callback)[0], 1)
        callback.assert_not_called()

    def test_runtime_confirmation_excludes_progressing_healthy_and_missing_states(self):
        spec = {'components': [{'name': 'web', 'type': 'service', 'image': 'image'}]}
        for state in ('ready', 'progressing', 'unknown', 'not_found', 'failed'):
            with self.subTest(state=state), patch.object(main, 'observe_deployment', return_value={'state': state}):
                self.assertEqual(main._ai_runtime_failed('demo', spec), state == 'failed')
        with patch.object(main, 'observe_deployment', side_effect=RuntimeError('Observer unavailable')):
            self.assertFalse(main._ai_runtime_failed('demo', spec))

    def test_a_failed_secondary_service_is_also_observed(self):
        spec = {'components': [{'name': name, 'type': 'service', 'image': 'image'} for name in ('web', 'api')]}
        with patch.object(main, 'observe_deployment', side_effect=[{'state': 'ready'}, {'state': 'failed'}]) as observe:
            self.assertTrue(main._ai_runtime_failed('demo', spec))
        self.assertEqual(observe.call_count, 2)
