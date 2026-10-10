"""Sequential, offline-only ChatProvider transport for the synthetic supplement."""
import copy
import json
import urllib.error
import urllib.request
from unittest.mock import patch

from quant_rsi.harness.agent_workflow import digest
from quant_rsi.harness.providers import ChatProvider
from quant_rsi.harness.supplement_tasks import static_answer
from quant_rsi.harness.workflow_chat import MockResponse, messages


def next_tool(context):
    observed = {o['tool'] for o in context['observations'] if o['ok']}
    task_id = context['task']['task_id']
    if task_id == 'Q-AT-02' and 'inspect_versions' in observed:
        first = next(o for o in context['observations'] if o['tool'] == 'inspect_versions' and o['ok'])
        branch = 'read_eligible_version' if first['result']['eligible'] else 'inspect_backup'
        return None if branch in observed else branch
    return next((name for name in context['allowed_tools'] if name not in observed), None)


def decide(context, profile):
    observations = context['observations']
    refs = [o['observation_id'] for o in observations]
    if profile == 'illegal_tool':
        return dict(action='TOOL_CALL', tool='shell', arguments={'observations': refs})
    if profile == 'wrong_arguments':
        return dict(action='TOOL_CALL', tool=list(context['allowed_tools'])[0],
                    arguments={'observations': refs, 'run_id': 'RESET'})
    if profile == 'repeat_tool':
        return dict(action='TOOL_CALL', tool=context['allowed_tools'][0], arguments={'observations': refs})
    if profile == 'tool_failure_claim' and any(not o['ok'] for o in observations):
        return dict(action='FINAL', conclusion={'status': 'SUCCESS'}, evidence=refs)
    tool = next_tool(context)
    if profile == 'suboptimal' and observations and not any(o['tool'] == 'audit_rejected_versions' for o in observations):
        tool = 'audit_rejected_versions'
    if profile == 'redundant' and len(observations) == 1:
        tool = observations[0]['tool']
    if tool and profile != 'early_final':
        return dict(action='TOOL_CALL', tool=tool, arguments={'observations': refs})
    if context['task']['kind'] == 'STRUCTURED':
        conclusion = static_answer(context['task'])
        refs = context['input_sources']
    else:
        conclusion = copy.deepcopy(observations[-1]['result']) if observations else {}
    if profile == 'wrong_final' and conclusion:
        field = next(iter(context['conclusion_contract']['fields']))
        value = conclusion[field]
        conclusion[field] = not value if type(value) is bool else 'CONTROLLED_WRONG'
    if profile == 'wrong_reference':
        refs = ['OBS-invented']
    if profile == 'future_claim':
        conclusion.update(selected_vintage='v2', value=12, verdict='PASS')
    return dict(action='FINAL', conclusion=conclusion, evidence=refs)


class ControlledTransport:
    """Test policy sees only public HTTP messages, never TASKS/reference/fixture."""
    def __init__(self, profile='correct', fault=None):
        self.profile, self.fault = profile, fault
        self.model_id = 'supplement-mock-' + profile + ('-' + fault if fault else '')
        self.calls = 0

    def open(self, request, timeout):
        if request.full_url != 'https://offline.invalid/v1/chat/completions':
            raise ValueError('NETWORK_DISABLED')
        self.calls += 1
        body = json.loads(request.data)
        initial = json.loads(body['messages'][1]['content'])
        context = {**initial, 'observations': [], 'history': []}
        for item in body['messages'][2:]:
            value = json.loads(item['content'])
            if item['role'] == 'assistant':
                context['history'].append(value)
            else:
                context['observations'].append(value['untrusted_tool_observation'])
        action = decide(context, self.profile)
        text = json.dumps(action)
        payload = dict(model=self.model_id, choices=[dict(message=dict(content=text), finish_reason='stop')],
                       usage=dict(prompt_tokens=max(1, len(request.data)//4),
                                  completion_tokens=160, completion_tokens_details=dict(reasoning_tokens=40)))
        if self.fault == 'http':
            raise urllib.error.HTTPError(request.full_url, 429, 'controlled', {}, None)
        if self.fault == 'timeout':
            raise TimeoutError('CONTROLLED_TIMEOUT')
        if self.fault == 'business':
            payload = {'error': {'code': 'controlled'}}
        elif self.fault == 'empty':
            payload['choices'][0]['message']['content'] = ''
        elif self.fault == 'truncated':
            payload['choices'][0]['finish_reason'] = 'length'
        elif self.fault == 'json':
            payload['choices'][0]['message']['content'] = '{bad'
        elif self.fault == 'action':
            payload['choices'][0]['message']['content'] = '{"action":"RESET"}'
        elif self.fault == 'usage_missing':
            payload.pop('usage')
        elif self.fault == 'usage_breach':
            payload['usage']['completion_tokens'] = 2049
        elif self.fault == 'model_mismatch':
            payload['model'] = 'OTHER_MODEL'
        elif self.fault == 'native_reasoning':
            payload['usage'].pop('completion_tokens_details')
            payload['usage']['reasoning_tokens'] = 40
        return MockResponse(payload)


class SupplementChatAdapter:
    provider_id = 'supplement-controlled-chat'

    def __init__(self, transport):
        if type(transport) is not ControlledTransport:
            raise ValueError('CONTROLLED_OFFLINE_TRANSPORT_REQUIRED')
        self.transport = transport
        self.model_id = transport.model_id
        self.last_exchange = None
        self.client = ChatProvider(self.provider_id, self.model_id, 'https://offline.invalid/v1',
            'UNUSED', timeout_s=30, max_tokens=2048, _key='synthetic-placeholder')

    def step(self, request, context):
        if request.prompt_hash != digest(context) or request.model_id != self.model_id or request.provider != self.provider_id:
            raise ValueError('CHAT_REQUEST_BINDING_MISMATCH')
        transcript = messages(context)
        exchange = dict(messages=transcript, messages_hash=digest(transcript), request_body=None, response=None)
        def controlled_open(original, timeout):
            body = json.loads(original.data)
            body['messages'] = transcript
            exchange['request_body'] = copy.deepcopy(body)
            # No header or credential is ever persisted.
            revised = urllib.request.Request(original.full_url, data=json.dumps(body).encode(),
                                             headers=dict(original.header_items()), method='POST')
            response = self.transport.open(revised, timeout)
            exchange['response'] = copy.deepcopy(response.payload)
            return response
        try:
            with patch('quant_rsi.harness.providers.urllib.request.urlopen', controlled_open):
                return self.client.reply(request.run_id, json.dumps(context))
        finally:
            self.last_exchange = exchange
