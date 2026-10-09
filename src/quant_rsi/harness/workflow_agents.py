"""Observation-dependent scripted policies, never prewritten multi-step transcripts."""
import json
from typing import Protocol

from quant_rsi.agents.worker import WorkerRequest
from quant_rsi.harness.providers import ProviderReply


class AgentStepProvider(Protocol):
    provider_id: str
    model_id: str

    def step(self, request: WorkerRequest, context: dict) -> ProviderReply: ...


def tool(name, **arguments):
    return {'action': 'TOOL_CALL', 'tool': name, 'arguments': arguments}


def final(conclusion, observations):
    return {'action': 'FINAL', 'conclusion': conclusion,
            'evidence': [o['observation_id'] for o in observations if o['ok']]}


class ScriptedAgent:
    provider_id = 'scripted-offline'

    def __init__(self, wrong=False):
        self.wrong = wrong
        self.model_id = 'scripted-wrong-v01' if wrong else 'scripted-correct-v01'

    def step(self, request, context):
        action = self.decide(context)
        return ProviderReply(True, json.dumps(action), None, None, 0, 0, 0, 1,
                             finish_reason='stop', observed_model=self.model_id)

    def decide(self, context):
        observations = context['observations']
        seen = {o['tool']: o for o in observations if o['ok']}
        workflow = context['task']['workflow_id']
        if workflow == 'WFA-01':
            if 'read_fixture' not in seen:
                return tool('read_fixture', fixture_id='response')
            ref = seen['read_fixture']['observation_id']
            if 'inspect_response' not in seen:
                return tool('inspect_response', response_ref=ref)
            if 'validate_rows' not in seen:
                return tool('validate_rows', response_ref=ref)
            checked, inspected = seen['validate_rows']['result'], seen['inspect_response']['result']
            conclusion = {'verdict': 'ACCEPT' if inspected['metadata_consistent'] else 'ACCEPT_WITH_WARNING',
                          'effective_rows': checked['effective_rows'],
                          'accepted_row_ids': checked['accepted_row_ids'],
                          'metadata_consistent': inspected['metadata_consistent']}
            if self.wrong:
                conclusion.update(verdict='REFUSE', effective_rows=0, accepted_row_ids=[])
        elif workflow == 'WFA-02':
            if 'list_vintages' not in seen:
                return tool('list_vintages')
            ids = [v['vintage_id'] for v in seen['list_vintages']['result']['vintages']]
            if 'check_asof_eligibility' not in seen:
                return tool('check_asof_eligibility', vintage_ids=ids)
            checks = seen['check_asof_eligibility']['result']['checks']
            eligible = [v for v in checks if v['eligible']]
            selected = max(eligible, key=lambda v: v['available_at']) if eligible else None
            if 'read_vintage' not in seen:
                return tool('read_vintage', vintage_id=selected['vintage_id'] if selected else ids[0])
            read = seen['read_vintage']['result']
            conclusion = {'verdict': 'SELECT_VINTAGE' if selected else 'REFUSE',
                'selected_vintage': read['vintage_id'] if selected else None,
                'published_at': read['published_at'] if selected else None,
                'available_at': read['available_at'] if selected else None,
                'event_effective_date': read['event_effective_date'] if selected else None,
                'decision_asof': context['task']['decision_asof'],
                'future_rejected': all(not v['eligible'] for v in checks if v['available_at'] > context['task']['decision_asof'])}
            if self.wrong:
                conclusion.update(verdict='SELECT_VINTAGE', selected_vintage=ids[-1], future_rejected=False)
        else:
            if 'inspect_budget' not in seen:
                return tool('inspect_budget')
            remaining = seen['inspect_budget']['result']['remaining_trials']
            if remaining:
                if 'reserve_trial' not in seen:
                    return tool('reserve_trial')
                trial = seen['reserve_trial']['result']['trial_ref']
                if 'run_synthetic_trial' not in seen:
                    return tool('run_synthetic_trial', trial_ref=trial)
                if 'settle_trial' not in seen:
                    return tool('settle_trial', trial_ref=trial)
            budget = seen.get('settle_trial', seen['inspect_budget'])['result']
            sufficient = seen['run_synthetic_trial']['result']['evidence_sufficient'] if remaining else False
            conclusion = {'verdict': 'REFUSE_INSUFFICIENT_EVIDENCE', 'used_trials': budget['used_trials'],
                          'remaining_trials': budget['remaining_trials'],
                          'new_trials': int('settle_trial' in seen), 'evidence_sufficient': sufficient,
                          'strategy_scientific_pass': False}
            if self.wrong:
                conclusion.update(verdict='ACCEPT_STRATEGY', strategy_scientific_pass=True)
        return final(conclusion, observations)


class ChatWorkflowAdapter:
    """Documented future seam: same WorkerRequest/context and ProviderReply.

    Real transport is deliberately disabled in this offline version. A future
    separately authorized adapter must replace the static SYSTEM_PROMPT with the
    public action contract, retain context observations, and reserve token usage.
    """
    def __init__(self, chat_provider):
        self.chat_provider = chat_provider
        self.provider_id = chat_provider.provider_id
        self.model_id = chat_provider.model_id

    def step(self, request, context):
        raise RuntimeError('REAL_AGENT_WORKFLOW_NOT_AUTHORIZED')
