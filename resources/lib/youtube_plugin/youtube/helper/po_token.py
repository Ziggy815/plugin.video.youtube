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
    from urllib.error import URLError
except ImportError:
    from urllib import unquote
    from urllib2 import Request, urlopen, URLError

from ...kodion import logging

_LOG = logging.getLogger(__name__)

# Cache im RAM (/tmp auf LibreELEC/Linux), Fallback auf System-Temp
if os.path.isdir('/tmp') and os.access('/tmp', os.W_OK):
    _POT_CACHE_FILE = '/tmp/yt_pot_cache.json'
else:
    _POT_CACHE_FILE = os.path.join(tempfile.gettempdir(), 'yt_pot_cache.json')

_DEFAULT_PROVIDER_URL = 'http://192.168.11.170:4416/get_pot'
_POT_TTL = 12000  # ~3.3 Stunden (Token im Container gilt ~4 Stunden)


def get_cached_po_token(provider_url=None, content_binding=None):
    """
    Holt (visitor_data, po_token) aus /tmp oder fragt den PO-Token-Container ab.
    Wird content_binding übergeben, antwortet der Container in ~10ms statt 10s.
    """
    now = time.time()
    if os.path.exists(_POT_CACHE_FILE):
        try:
            with open(_POT_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cached_ts = data.get('ts', 0)
            visitor_data = data.get('visitor_data')
            po_token = data.get('po_token')
            if visitor_data and po_token and (now - cached_ts < _POT_TTL):
                if not content_binding or content_binding == visitor_data:
                    return unquote(visitor_data), po_token
        except Exception as exc:
            _LOG.debug('Failed to read PO token cache: %r', exc)

    url = provider_url or _DEFAULT_PROVIDER_URL
    if not url:
        return None, None

    try:
        payload = {}
        if content_binding:
            payload['content_binding'] = content_binding

        req = Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
            if hasattr(content, 'decode'):
                content = content.decode('utf-8')
            res = json.loads(content)
            raw_visitor = res.get('contentBinding')
            visitor_data = unquote(raw_visitor) if raw_visitor else None
            po_token = res.get('poToken')
            if visitor_data and po_token:
                try:
                    with open(_POT_CACHE_FILE, 'w', encoding='utf-8') as f:
                        json.dump({
                            'ts': now,
                            'visitor_data': visitor_data,
                            'po_token': po_token,
                        }, f)
                except Exception as exc:
                    _LOG.debug('Failed to write PO token cache: %r', exc)
                return visitor_data, po_token
    except Exception as exc:
        _LOG.warning('Failed to retrieve PO token from %s: %r', url, exc)

    return None, None
