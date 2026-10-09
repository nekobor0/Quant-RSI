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

    @property
    def truncated(self):
        """True when the model hit the token ceiling instead of finishing.

        A reasoning model that exhausts max_tokens can return HTTP 200 with no
        content at all, which would otherwise be scored as a malformed answer
        and understate capability.
        """
        return self.finish_reason == 'length' or (
            self.text is None and self.output_tokens is not None)


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
    "Do not report a value as UNKNOWN or null for something the input states."
)


def build_prompt(task_id, public_input_obj, required_keys=None):
    """Deterministic user message; byte-stable so its hash is reproducible.

    The required report keys are published here. Scoring tests whether the right
    facts were established, not whether the model guessed an unstated schema, so
    the facts to report are declared while their correct values are not.
    """
    payload = json.dumps(public_input_obj, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True)
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

    def reply(self, task_id, prompt):
        started = time.perf_counter()
        if task_id == _MOCK_MALFORMED:
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
    # On truncation, retry once with this larger ceiling before giving up. A model
    # that simply thought for a long time should not be scored as incapable.
    retry_max_tokens: int = 64000
    temperature: float = 0.0
    max_retries: int = 1
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

        last_error = None
        # Up to (max_retries + 1) transport attempts; the final attempt may raise
        # the token ceiling once if the model was cut off rather than finished.
        for attempt in range(1, self.max_retries + 2):
            limit = self.max_tokens
            escalated = False
            while True:
                body = {'model': self.model_id, 'messages': messages,
                        'temperature': self.temperature, 'max_tokens': limit,
                        'stream': False}
                raw = json.dumps(body).encode()
                started = time.perf_counter()
                request = urllib.request.Request(url, data=raw, headers=headers, method='POST')
                try:
                    with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                        status = response.status
                        payload = json.loads(response.read().decode('utf-8'))
                    wall = max(1, int((time.perf_counter() - started) * 1000))
                    choices = payload.get('choices') or []
                    message = (choices[0].get('message') or {}) if choices else {}
                    text = message.get('content')
                    if text is not None and not str(text).strip():
                        text = None  # whitespace-only must not count as an answer
                    reasoning = message.get('reasoning_content') or ''
                    finish = choices[0].get('finish_reason') if choices else None
                    usage = payload.get('usage') or {}
                    reply = ProviderReply(True, text, status, None,
                                          usage.get('prompt_tokens'),
                                          usage.get('completion_tokens'),
                                          wall, attempt, finish_reason=finish,
                                          reasoning_chars=len(reasoning))
                    # Cut off by the ceiling: retry once with a larger one instead
                    # of reporting a truncated answer as a capability failure.
                    if (reply.truncated and not escalated
                            and limit < self.retry_max_tokens):
                        escalated = True
                        limit = self.retry_max_tokens
                        continue
                    return reply
                except urllib.error.HTTPError as exc:
                    wall = max(1, int((time.perf_counter() - started) * 1000))
                    detail = ''
                    try:
                        detail = exc.read().decode('utf-8', 'replace')[:400]
                    except Exception:
                        pass
                    last_error = ProviderReply(False, None, exc.code,
                                               f'HTTPError {exc.code}: {detail}', None, None,
                                               wall, attempt)
                    if exc.code != 429 and exc.code < 500:
                        return last_error
                    break
                except Exception as exc:  # transport, DNS, TLS, timeout
                    wall = max(1, int((time.perf_counter() - started) * 1000))
                    last_error = ProviderReply(False, None, None,
                                               f'{type(exc).__name__}: {exc}', None, None,
                                               wall, attempt)
                    break
            if attempt <= self.max_retries:
                time.sleep(min(2.0 * attempt, 5.0))
        return last_error


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
