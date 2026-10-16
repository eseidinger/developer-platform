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
