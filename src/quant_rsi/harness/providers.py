"""Model providers for the PUBLIC Track A capability comparison.

One interface serves both the deterministic offline mock and real chat models,
so the scoring path is identical offline and online. Swapping in a real model
changes only the provider object, never the oracle.

Credential handling: the OpenAI-compatible provider reads its key from an
environment variable at call time, keeps it in-process only, and never writes,
echoes or hashes it. No credential value is stored in this module.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderReply:
    ok: bool
    text: str | None
    http_status: int | None
    transport_error: str | None
    input_tokens: int | None
    output_tokens: int | None
    wall_ms: int
    attempts: int
    finish_reason: str | None = None
    reasoning_chars: int | None = None
    reasoning_tokens: int | None = None
    failure_class: str | None = None
    cost: float | None = None
    currency: str | None = None
    observed_model: str | None = None

    @property
    def truncated(self):
        """True when the model hit the token ceiling instead of finishing.

        A reasoning model that exhausts max_tokens can return HTTP 200 with no
        content at all, which would otherwise be scored as a malformed answer
        and understate capability.
        """
        return self.finish_reason == 'length'

    @property
    def failure_type(self):
        if self.failure_class:
            return self.failure_class
        if not self.ok:
            return 'HTTP_ERROR' if self.http_status is not None else 'TRANSPORT_FAILED'
        if self.truncated:
            return 'TOKEN_BUDGET_EXHAUSTED'
        if not isinstance(self.text, str) or not self.text.strip():
            return 'EMPTY_CONTENT'
        return None


class ProviderError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Prompt contract
# --------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an A-share quantitative research agent. You will receive a JSON "
    "object describing a situation. Decide what the evidence actually supports.\n"
    "Reply with ONE JSON object and nothing else. It must have exactly these "
    "three keys:\n"
    '  "verdict": one of "PASS", "REFUSE", "FLAG_INCONSISTENT", "INSUFFICIENT_EVIDENCE"\n'
    '  "reason": a short string justification\n'
    '  "evidence": a JSON object of the specific facts you relied on\n'
    "Use PASS only when the evidence positively supports acting. Use REFUSE when "
    "acting would be unjustified. Use FLAG_INCONSISTENT when the data itself "
    "contradicts itself. Use INSUFFICIENT_EVIDENCE when the data cannot settle "
    "the question. Do not invent facts that are not present in the input.\n"
    "In \"evidence\", report the concrete values you checked, using descriptive "
    "key names, for example counts, booleans, or the exact dates you compared. "
    "Use UNKNOWN only when the input explicitly states it or its contract permits it. "
    "Follow the supplied answer contract, including its reason grammar, fact aliases "
    "and source citation rules. A legal JSON code fence is accepted."
)


def build_prompt(task_id, public_input_obj, required_keys=None, contract=None):
    """Deterministic user message; byte-stable so its hash is reproducible.

    The required report keys are published here. Scoring tests whether the right
    facts were established, not whether the model guessed an unstated schema, so
    the facts to report are declared while their correct values are not.
    """
    payload = json.dumps(public_input_obj, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True)
    if contract is not None:
        return f'task_id: {task_id}\ninput: {payload}\nanswer_contract: ' + json.dumps(
            contract, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    lines = [
        f'task_id: {task_id}',
        f'input: {payload}',
        '',
        'Your evidence object must report the following facts:',
    ]
    if required_keys:
        lines.extend(f'  - {item}' for item in required_keys)
    else:
        lines.append('  - the concrete values you relied on')
    lines.extend([
        '',
        'You may choose any clear key names. Report the exact values you found. '
        'Reply with the raw JSON object only, with no markdown fence and no text '
        'before or after it.',
    ])
    return '\n'.join(lines)


# --------------------------------------------------------------------------
# Deterministic offline mock
# --------------------------------------------------------------------------

_MOCK_REPLIES = {
    # behaves correctly
    'A-META-COUNT-ITEMS': {
        'verdict': 'FLAG_INCONSISTENT',
        'reason': 'declared count is 0 but items holds one well-formed record',
        'evidence': {'items_len': 1, 'declared_count': 0, 'effective_rows': 1},
    },
    'A-PIT-ANNOUNCEMENT-VS-EFFECTIVE': {
        'verdict': 'PASS',
        'reason': 'as-of date is after publication and before termination takes effect',
        'evidence': {'still_listed_on_as_of': True, 'announcement_date': '20170208',
                     'effective_date': '20170214'},
    },
    'A-INSUFFICIENT-SUPPORT': {
        'verdict': 'REFUSE',
        'reason': 'neither candidate reaches the 0.60 minimum support',
        'evidence': {'terminal': 'REFUSE', 'reason_code': 'INSUFFICIENT_SUPPORT'},
    },
    # fails on evidence
    'A-EMPTY-VS-FAILURE': {
        'verdict': 'INSUFFICIENT_EVIDENCE',
        'reason': 'an empty table cannot be distinguished from a swallowed error',
        'evidence': {'missing': ['vendor_error_semantics']},
    },
    'A-DELIST-NOT-SUSPENSION': {
        'verdict': 'PASS',
        'reason': 'zero rows are consistent with the known termination',
        'evidence': {'suspension_conclusion_supported': False,
                     'zero_rows_supports': 'POST_DELISTING_INELIGIBILITY_CONSISTENT_OBSERVATION'},
    },
}

_MOCK_MALFORMED = 'A-BUDGET-ESCAPE'
_MOCK_EMPTY_EVIDENCE = 'A-PIT-BACKFILL-REFUSAL'


@dataclass
class MockProvider:
    """Deterministic, credential-free stand-in with a fixed capability profile."""
    provider_id: str = 'mock'
    model_id: str = 'mock-capability-v1'
    suite: str = '0.1'

    def reply(self, task_id, prompt):
        started = time.perf_counter()
        if self.suite == '0.2':
            from quant_rsi.harness.capability_oracle import V02_PATH
            from pathlib import Path
            samples = json.loads(Path(V02_PATH.with_name('validation_samples_v02.json')).read_text(encoding='utf-8'))
            profile = 'wrong_decision' if self.provider_id == 'mock-b' else 'correct'
            text = json.dumps(samples[task_id][profile], sort_keys=True)
        elif task_id == _MOCK_MALFORMED:
            text = '{"verdict": "REFUSE", "reason": "rename does not reset the root"'  # truncated JSON
        elif task_id == _MOCK_EMPTY_EVIDENCE:
            text = json.dumps({'verdict': 'REFUSE',
                               'reason': 'current snapshot has no as-of availability',
                               'evidence': {'snapshot_is_current_not_as_of': True,
                                            'missing_fields': 'UNKNOWN'}})
        else:
            text = json.dumps(_MOCK_REPLIES[task_id], sort_keys=True)
        wall = max(1, int((time.perf_counter() - started) * 1000))
        return ProviderReply(True, text, None, None, 0, 0, wall, 1)


# --------------------------------------------------------------------------
# Real chat provider (OpenAI-compatible)
# --------------------------------------------------------------------------

@dataclass
class ChatProvider:
    """Minimal stdlib HTTPS OpenAI-compatible chat client.

    No third-party SDK, so the transport stays auditable and dependency-free.
    """
    provider_id: str
    model_id: str
    base_url: str
    api_key_env: str
    timeout_s: int = 300
    # Reasoning models spend this budget on hidden reasoning first. A ceiling the
    # reasoning alone can exhaust yields HTTP 200 with EMPTY content, which reads
    # as a malformed answer unless diagnosed. Measured: deepseek-v4-pro produced
    # 36,120 characters of reasoning on one task and still hit an 8,000 ceiling.
    max_tokens: int = 24000
    temperature: float = 0.0
    extra_headers: dict = field(default_factory=dict)
    _key: str | None = field(default=None, repr=False, compare=False)

    def _resolve_key(self):
        # Read once per process, keep in memory, never persist or echo.
        if self._key is None:
            key = os.environ.get(self.api_key_env)
            if not key:
                raise ProviderError(
                    f'missing credential: environment variable {self.api_key_env} is not set')
            self._key = key
        return self._key

    def reply(self, task_id, prompt):
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt}]
        url = self.base_url.rstrip('/') + '/chat/completions'
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + self._resolve_key(),
                   'Accept': 'application/json'}
        headers.update(self.extra_headers)

        # Exactly one request, no transport retry or post-answer token escalation.
        body = {'model': self.model_id, 'messages': messages,
                'temperature': self.temperature, 'max_tokens': self.max_tokens,
                'stream': False}
        started = time.perf_counter()
        status = None
        request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers=headers, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                status = response.status
                payload = json.loads(response.read().decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('invalid provider envelope')
            if payload.get('error') or payload.get('code') not in (None, 0, '0'):
                return ProviderReply(False, None, status, 'BUSINESS_ERROR', None, None,
                                     max(1, int((time.perf_counter()-started)*1000)), 1,
                                     failure_class='BUSINESS_ERROR')
            choices = payload.get('choices') or []
            message = (choices[0].get('message') or {}) if choices else {}
            text = message.get('content')
            if text is not None and (not isinstance(text, str) or not text.strip()):
                text = None
            usage = payload.get('usage') or {}
            details = usage.get('completion_tokens_details') or {}
            return ProviderReply(True, text, status, None,
                                 usage.get('prompt_tokens'), usage.get('completion_tokens'),
                                 max(1, int((time.perf_counter()-started)*1000)), 1,
                                 finish_reason=choices[0].get('finish_reason') if choices else None,
                                 reasoning_chars=len(message.get('reasoning_content') or ''),
                                 reasoning_tokens=details.get('reasoning_tokens', usage.get('reasoning_tokens')),
                                 observed_model=payload.get('model'))
        except urllib.error.HTTPError as exc:
            # Do not persist arbitrary server bodies or exception strings: they
            # can echo credentials or request headers.
            failure, status = 'HTTP_ERROR', exc.code
        except (TimeoutError,):
            failure = 'TASK_TIMEOUT'
        except urllib.error.URLError as exc:
            failure = 'TASK_TIMEOUT' if isinstance(exc.reason, TimeoutError) else 'TRANSPORT_FAILED'
        except (ValueError, TypeError, KeyError, AttributeError):
            failure = 'PROVIDER_RESPONSE_INVALID'
        except Exception:
            failure = 'TRANSPORT_FAILED'
        return ProviderReply(False, None, status, failure, None, None,
                             max(1, int((time.perf_counter()-started)*1000)), 1,
                             failure_class=failure)


# Registry of the intended comparison pair. No credential is stored here.
#
# Model ids below were read from each provider's /v1/models endpoint on
# 2026-10-08 (both keys valid). Earlier placeholders ('deepseek-chat',
# 'mimo-v2.6-pro' for the batch host) were wrong and are corrected here.
#
#   DeepSeek : deepseek-flash, deepseek-v4-pro
#   Xiaomi   : mimo-v2.5, mimo-v2.5-asr, mimo-v2.5-pro, mimo-v2.5-tts,
#              mimo-v2.5-tts-voiceclone, mimo-v2.5-tts-voicedesign,
#              mimo-v2.6-flash, mimo-v2.6-pro, mimo-v2.6-pro-ultraspeed
#
# Provider ids match the DSH llm-pi-ai registration ('xiaomi') and the official
# DeepSeek provider ('deepseek-official'), so a model chosen here can also be
# named when delegating to a subagent.
def planned_pairs():
    return {
        'deepseek': ChatProvider(
            provider_id='deepseek',
            model_id=os.environ.get('QRSI_DEEPSEEK_MODEL', 'deepseek-v4-pro'),
            base_url=os.environ.get('QRSI_DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1'),
            api_key_env='DEEPSEEK_API_KEY'),
        'xiaomi': ChatProvider(
            provider_id='xiaomi',
            model_id=os.environ.get('QRSI_XIAOMI_MODEL', 'mimo-v2.6-pro'),
            # Corrected after an unauthenticated TLS probe on 2026-10-08:
            #   batch-api-cn.xiaomimimo.com -> 404 on every API path (it is an
            #   openresty batch service, not the chat API).
            #   api.xiaomimimo.com -> 401 on /v1/models, 405 on GET
            #   /v1/chat/completions, i.e. the OpenAI-compatible surface.
            base_url=os.environ.get('QRSI_XIAOMI_BASE_URL',
                                    'https://api.xiaomimimo.com/v1'),
            api_key_env='XIAOMI_API_KEY'),
    }
