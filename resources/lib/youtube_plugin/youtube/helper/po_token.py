# -*- coding: utf-8 -*-
"""
    Copyright (C) 2014-2016 bromix (plugin.video.youtube)
    Copyright (C) 2016-2026 plugin.video.youtube

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only for more information.
"""

from __future__ import absolute_import, division, unicode_literals

import json
import os
import tempfile
import time

try:
    from urllib.parse import unquote
    from urllib.request import Request, urlopen
except ImportError:
    from urllib import unquote
    from urllib2 import Request, urlopen

from ...kodion import logging

_LOG = logging.getLogger(__name__)

# Cache in RAM (/tmp on LibreELEC/Linux), fall back to the system temp dir
if os.path.isdir('/tmp') and os.access('/tmp', os.W_OK):
    _POT_CACHE_FILE = '/tmp/yt_pot_cache.json'
else:
    _POT_CACHE_FILE = os.path.join(tempfile.gettempdir(), 'yt_pot_cache.json')

# Tokens served by the provider are valid for ~4 hours, refresh after ~3.3 h
_POT_TTL = 12000
# Do not query a failing provider again for this many seconds
_FAILURE_BACKOFF = 60
_REQUEST_TIMEOUT = 15

_last_failure = {}


def _read_cache(provider_url, content_binding, now):
    if not os.path.exists(_POT_CACHE_FILE):
        return None, None
    try:
        with open(_POT_CACHE_FILE, 'r') as f:
            data = json.load(f)
        visitor_data = data.get('visitor_data')
        po_token = data.get('po_token')
        if (data.get('provider_url') == provider_url
                and visitor_data
                and po_token
                and now - data.get('ts', 0) < _POT_TTL
                and (not content_binding or content_binding == visitor_data)):
            return unquote(visitor_data), po_token
    except Exception as exc:
        _LOG.debug('Failed to read PO token cache: %r', exc)
    return None, None


def _write_cache(provider_url, visitor_data, po_token, now):
    try:
        with open(_POT_CACHE_FILE, 'w') as f:
            json.dump({
                'ts': now,
                'provider_url': provider_url,
                'visitor_data': visitor_data,
                'po_token': po_token,
            }, f)
    except Exception as exc:
        _LOG.debug('Failed to write PO token cache: %r', exc)


def get_cached_po_token(provider_url, content_binding=None):
    """
    Get (visitor_data, po_token) from the cache or query the PO token provider.

    If content_binding is given the provider answers in ~10ms instead of ~10s.
    Returns (None, None) if no provider URL is configured or the provider
    is unavailable.
    """
    if not provider_url:
        return None, None

    now = time.time()

    visitor_data, po_token = _read_cache(provider_url, content_binding, now)
    if po_token:
        return visitor_data, po_token

    if now - _last_failure.get(provider_url, 0) < _FAILURE_BACKOFF:
        return None, None

    try:
        payload = {}
        if content_binding:
            payload['content_binding'] = content_binding

        req = Request(
            provider_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        resp = urlopen(req, timeout=_REQUEST_TIMEOUT)
        try:
            content = resp.read()
        finally:
            resp.close()
        if hasattr(content, 'decode'):
            content = content.decode('utf-8')
        res = json.loads(content)
        raw_visitor = res.get('contentBinding')
        visitor_data = unquote(raw_visitor) if raw_visitor else None
        po_token = res.get('poToken')
        if visitor_data and po_token:
            _last_failure.pop(provider_url, None)
            _write_cache(provider_url, visitor_data, po_token, now)
            return visitor_data, po_token
        _LOG.warning('Invalid PO token response from %s', provider_url)
    except Exception as exc:
        _LOG.warning('Failed to retrieve PO token from %s: %r',
                     provider_url, exc)

    _last_failure[provider_url] = now
    return None, None
