#!/usr/bin/env python3
"""Human-readable command flow log shared by dashboard and backend."""

import datetime
import json
import os


FLOW_LOG_PATH = os.environ.get('DT4N_FLOW_LOG', 'logs/command_flow.log')


def _ts():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def _compact(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    except Exception:
        return str(value)


def flow_event(source, event, correlation_id=None, subject=None, target=None,
               level='INFO', detail=None, **extra):
    """Append one concise line to logs/command_flow.log.

    Logging is best-effort: it must never break command execution.
    """
    cid = correlation_id or '-'
    subject = subject or '-'
    target = target or '-'
    parts = [
        '[%s]' % _ts(),
        '[%s]' % source,
        '[%s]' % level,
        '[cid=%s]' % cid,
        event,
        'subject=%s' % subject,
        'target=%s' % target,
    ]
    if detail:
        parts.append('detail=%s' % detail)
    for key in sorted(extra):
        value = extra[key]
        if value is not None and value != '':
            parts.append('%s=%s' % (key, _compact(value)))
    line = ' '.join(parts)

    try:
        parent = os.path.dirname(os.path.abspath(FLOW_LOG_PATH))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(FLOW_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        try:
            os.chmod(FLOW_LOG_PATH, 0o666)
        except OSError:
            pass
    except Exception:
        pass
