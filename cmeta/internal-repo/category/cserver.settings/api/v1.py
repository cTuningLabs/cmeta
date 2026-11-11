"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.settings - the settings of this machine in one list, as a browser's settings page: every config artifact
(cx config set <name> --meta.<key>=<value>) and every key the plugged artifacts read from it, as /cmeta.configs knows
them (its scan: declared in a "configs" block of an artifact's _desc.yaml, read by its code, shown in its docs) - what
each key does, its type and default, who reads it, its value here -, one search box that prunes them, and a field or
a switch per key to change it in place.

    cx app run cserver      ->  http://127.0.0.1:8004/settings

A change is the engine's own `cx config set <name> --meta.<key>=<value>`, made by the page: the value typed as the key
is - the kind of the value it replaces (a number stays a number, yes/no stays yes/no, a list stays a list) or, for a
key not set yet, the type the key is declared with (number, yes/no, list; else a text) -, a dotted key nested
(param.port), the file written under the engine's lock. Reset is `cx config unset`. Undo in the message puts the old
value back. A secret (a password, a token, a key: /cmeta.configs' rule) is never shown - it can be set and reset. A
mapping is not changed here (its keys are: param.port).

    ?native_action=settings      the JSON the page renders (the groups: one per config artifact, its keys)
    ?native_action=set           set a key (config, key, value) -> {config, key, value, old, was_set, changed}
    ?native_action=unset         take a key out (config, key) -> the same
    cx cserver.settings list ["<words>"] [--show=set|unset]     the keys and their values in a terminal

Who may see the values: as /cmeta.configs (configs_values of the cserver config: yes = everyone the server lets in,
no = no one; unset = a browser on the server's own machine or one past its password). Who may change them: a browser
on the server's own machine or one past its password, from a page of this server; never through the cTuning platform
(the configs are the machine's). The repositories hide_repos leaves out, and a host's only_repos, apply through
/cmeta.configs.
"""

import html
import json
import os
import re
import time

from cmeta.category import InitCategory

CONFIGS_PAGE = 'cserver.cmeta.configs,cc8dd8bdf9fe4132'     # what is listed, and who may see the values: its rules
CONFIG = 'config,cc6bfe174be847ed'                         # the config artifacts
WRITES = {'set': ('config', 'key', 'value'), 'unset': ('config', 'key')}
SHOWS = ('', 'set', 'unset')
KEY_RE = re.compile(r'^[A-Za-z_][\w\-]*(?:\.[A-Za-z_][\w\-]*)*$')
NAME_RE = re.compile(r'^[A-Za-z0-9][\w.\-@]*$')
YES = ('yes', 'true', 'on', '1')
NO = ('no', 'false', 'off', '0')
VALUE_MAX = 4000


def _asset(path_to_files, url_files, rel):
    """A versioned URL for a file under files/ (mtime -> a new URL per edit, so no host serves a stale copy)."""
    url = url_files + rel
    try:
        return '%s?v=%d' % (url, int(os.path.getmtime(os.path.join(path_to_files, *rel.split('/')))))
    except Exception:
        return url


def _esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def _js(obj):
    """A JSON literal safe to embed inside a <script> tag."""
    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')


def _nested(parts, value):
    """{'a': {'b': value}} for the parts of a dotted key."""
    out = value
    for p in reversed(parts):
        out = {p: out}
    return out


def _walk(data, parts):
    """The value under a dotted key of a config's data -> (found, value)."""
    cur = data
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return False, None
        cur = cur[p]
    return True, cur


def _typed(text, kind, current, was_set):
    """The value to store for what was typed: the kind of the value it replaces, else the declared type, else a text
    -> (value, '' or why not)."""
    text = '' if text is None else str(text)
    t = text.strip()
    if was_set and isinstance(current, bool):
        if t.lower() in YES:
            return True, ''
        if t.lower() in NO:
            return False, ''
        return None, 'yes or no is expected (the key holds a yes/no)'
    if was_set and isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(t), ''
        except ValueError:
            return None, 'a whole number is expected (the key holds one)'
    if was_set and isinstance(current, float):
        try:
            return float(t), ''
        except ValueError:
            return None, 'a number is expected (the key holds one)'
    if was_set and isinstance(current, list):
        return [x.strip() for x in t.split(',') if x.strip()], ''
    if was_set and isinstance(current, dict):
        return None, 'a mapping: change its keys one by one (<key>.<sub>), or with cx config set'
    kind = str(kind or '').strip().lower()
    if kind in ('number', 'int', 'integer', 'float'):
        try:
            return (float(t) if ('.' in t or 'e' in t.lower()) and kind != 'int' else int(t)), ''
        except ValueError:
            return None, 'a number is expected'
    if kind in ('yes/no', 'bool', 'boolean'):
        if t.lower() in YES + NO:
            return t.lower() if t.lower() in ('yes', 'no', 'true', 'false') else ('yes' if t.lower() in YES else 'no'), ''
        return None, 'yes or no is expected'
    if kind == 'list':
        return [x.strip() for x in t.split(',') if x.strip()], ''
    if kind in ('dict', 'mapping'):
        return None, 'a mapping: change its keys one by one (<key>.<sub>), or with cx config set'
    return text, ''


class Category(InitCategory):
    """
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def _uses(self, key, default):
        return ((self.cmeta or {}).get('uses_categories', {}) or {}).get(key, default)

    @staticmethod
    def _may_write(misc):
        """Who may change a setting: a browser on this machine, or one that passed the server's password; never the
        cTuning platform -> (ok, why not)."""
        misc = misc or {}
        if misc.get('ctuning_server'):
            return False, 'the settings are changed on the cMeta server of their machine, not here'
        if not (misc.get('client_local') or misc.get('password_gate')):
            return False, ('changing a setting is for a browser on the server\'s own machine, or one that signed in to it '
                           'with its password')
        return True, ''

    # ------------------------------------------------------------------ what is listed
    def _configs(self, misc):
        """The JSON of /cmeta.configs for this viewer (its scan, its rules on the values and the repositories)."""
        r = self.cm.access({'category': self._uses('cserver.cmeta.configs', CONFIGS_PAGE), 'command': 'web', 'con': False,
                            'urls': {}, 'query': {'native_action': 'configs'}, 'misc': dict(misc or {})})
        if r.get('return', 1) > 0:
            raise RuntimeError('the configs page (cserver.cmeta.configs): %s' % r.get('error', 'no answer'))
        out = r.get('json') or {}
        if out.get('error'):
            raise RuntimeError('the configs page (cserver.cmeta.configs): %s' % out['error'])
        return out

    def _payload(self, misc):
        """What the page renders: one group per config artifact (the placeholders of dynamic names - <alias>,
        task-<alias> - left out), its keys with what each does, its type and default, who reads it, whether it is set
        here and its value (a secret: never), then the keys set here that no plugged artifact reads."""
        t0 = time.monotonic()
        j = self._configs(misc)
        arts = j.get('artifacts') or {}
        if isinstance(arts, list):
            arts = {a[0]: a[1] for a in arts if isinstance(a, (list, tuple)) and len(a) == 2}

        def who(aids):
            out = []
            for aid in aids:
                a = arts.get(aid) or {}
                name = a.get('alias') or aid
                if a.get('cat') and a['cat'] != 'category':
                    name = '%s::%s' % (a['cat'], name)
                if name not in out:
                    out.append(name)
            return out

        values = bool(j.get('values'))
        groups = []
        for c in j.get('configs') or []:
            name = str(c.get('name') or '')
            if not name or name.startswith('<') or '<' in name:
                continue                                    # a pattern of dynamic names, not a config of this machine
            # the values as the config artifact holds them (typed: a number, a yes/no, a list), for a viewer who may see
            # them - the configs page shows them as text
            data = self._data(name) if values and c.get('data_file') else {}
            keys = []
            for k in c.get('keys') or []:
                if '<' in k['key']:
                    continue                                # a pattern of keys (<category>_create_repo), not a key
                found, value = _walk(data, k['key'].split('.')) if data else (False, None)
                secret = bool(k.get('secret'))
                keys.append({'key': k['key'], 'desc': k.get('desc') or '', 'type': k.get('type') or '',
                             'default': (k.get('defaults') or [''])[0], 'examples': [e.get('value') for e in (k.get('examples') or [])][:3],
                             'secret': secret, 'list': bool(k.get('list')) or isinstance(value, list),
                             'set': found if values else bool(k.get('set')), 'value': None if secret or not found else value,
                             'readers': who([x['aid'] for x in (k.get('readers') or []) + (k.get('declared') or [])]),
                             'unread': False})
            for u in c.get('unread') or []:
                if isinstance(u, dict):
                    key, secret = str(u.get('key') or ''), bool(u.get('secret'))
                else:
                    key, secret = str(u), False
                found, value = _walk(data, key.split('.')) if (key and data) else (False, None)
                if key and not any(x['key'] == key for x in keys):
                    keys.append({'key': key, 'desc': 'set here; no plugged artifact reads it', 'type': '', 'default': '',
                                 'examples': [], 'secret': secret, 'list': isinstance(value, list), 'set': True,
                                 'value': None if secret or not found else value, 'readers': [], 'unread': True})
            keys.sort(key=lambda k: k['key'].lower())
            groups.append({'name': name, 'desc': c.get('desc') or '', 'readers': who([r['aid'] for r in c.get('readers') or []]),
                           'here': bool(c.get('data_file')), 'set_count': sum(1 for k in keys if k['set']), 'keys': keys})
        groups.sort(key=lambda g: (not g['here'], g['name'].lower()))
        return {'groups': groups, 'values': bool(j.get('values')), 'stats': j.get('stats') or {}, 'built': j.get('built'),
                'ms': int((time.monotonic() - t0) * 1000)}

    # ------------------------------------------------------------------ a change
    def _key_of(self, misc, name, key):
        """The entry of a key as the page lists it (for its type, whether it is set, its value) -> (entry, group)."""
        for g in self._payload(misc)['groups']:
            if g['name'] == name:
                for k in g['keys']:
                    if k['key'] == key:
                        return k, g
                return None, g
        return None, None

    def _data(self, name):
        """What a config artifact of this machine holds (its data.json, read as cx config read reads it), or {}."""
        r = self.cm.access({'category': self._uses('config', CONFIG), 'command': 'read', 'arg1': name, 'con': False})
        if r.get('return', 1) > 0:
            return {}
        data = r.get('config_cmeta')
        return data if isinstance(data, dict) else {}

    def _current(self, name, key):
        """The value of a key in a config artifact of this machine -> (set, value)."""
        return _walk(self._data(name), key.split('.'))

    def _change(self, query, misc, unset=False):
        """A key set (the value typed as the key is) or taken out, by the engine's config set / unset, in the config
        artifact named (made when it is not there yet) -> {'config', 'key', 'value', 'old', 'was_set', 'set',
        'changed'} or {'error'}; the value and the old one are None for a secret."""
        name = str(query.get('config') or '').strip()
        key = str(query.get('key') or '').strip()
        if not NAME_RE.match(name):
            return {'error': 'config: the name of a config artifact is expected (cserver, default, task-run-ai ...)'}
        if not KEY_RE.match(key):
            return {'error': 'key: a key is expected (letters, digits, _ -; dots between the levels: param.port)'}
        entry, group = self._key_of(misc, name, key)
        if group is None:
            return {'error': 'there is no config %s on this machine, and no plugged artifact reads one' % name}
        if entry is None and not unset:
            return {'error': 'no plugged artifact reads the key %s of %s (a new key is set with cx config set %s --meta.%s=...)' %
                             (key, name, name, key)}
        secret = bool(entry and entry['secret'])
        was_set, old = self._current(name, key)
        parts = key.split('.')

        if unset:
            if not was_set:
                return {'config': name, 'key': key, 'value': None, 'old': None, 'was_set': False, 'set': False, 'changed': False}
            r = self.cm.access({'category': self._uses('config', CONFIG), 'command': 'set', 'arg1': name, 'con': False,
                                'meta': _nested(parts, ''), 'unset': True})
            if r.get('return', 1) > 0:
                return {'error': '%s: %s' % (name, r.get('error', 'not changed'))}
            print('cMeta info: cserver.settings: %s.%s unset' % (name, key))
            return {'config': name, 'key': key, 'value': None, 'old': None if secret else old, 'was_set': True, 'set': False,
                    'changed': True}

        text = query.get('value')
        if isinstance(text, (list, dict)):
            text = json.dumps(text)
        text = '' if text is None else str(text)
        if len(text) > VALUE_MAX:
            return {'error': 'the value is too long (%d characters at most)' % VALUE_MAX}
        value, why = _typed(text, entry['type'], old, was_set)
        if why:
            return {'error': '%s: %s' % (key, why)}
        if was_set and old == value:
            return {'config': name, 'key': key, 'value': None if secret else value, 'old': None if secret else old,
                    'was_set': True, 'set': True, 'changed': False}
        r = self.cm.access({'category': self._uses('config', CONFIG), 'command': 'set', 'arg1': name, 'con': False,
                            'meta': _nested(parts, value)})
        if r.get('return', 1) > 0:
            return {'error': '%s: %s' % (name, r.get('error', 'not changed'))}
        now_set, now = self._current(name, key)
        if not now_set or now != value:
            return {'error': '%s.%s: the value was not saved as given (the file holds %r)' % (name, key, now)}
        print('cMeta info: cserver.settings: %s.%s set%s' % (name, key, '' if secret else ' to %r' % (value,)))
        return {'config': name, 'key': key, 'value': None if secret else value, 'old': None if secret else old,
                'was_set': was_set, 'set': True, 'changed': True}

    # ------------------------------------------------------------------ web
    def web_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        urls,  # The host's URLs: url (this page), url_files (files/ of this category), url_server.
        query = {},  # GET and POST parameters.
        misc = {},  # Session bits (client_local, same_origin, password_gate on the engine cserver; theme, ctuning_server on cPlatform).
    ):
        """
        The settings page (command web), or ?native_action=settings | set | unset as JSON.
        """
        query = query or {}
        misc = misc or {}
        na = query.get('native_action', '')
        if na:
            t0 = time.monotonic()
            try:
                if na == 'settings':
                    out = self._payload(misc)
                    out['edit'] = self._may_write(misc)[0]
                elif na in WRITES:
                    ok, why = self._may_write(misc)
                    if not ok:
                        out = {'error': why}
                    elif not misc.get('same_origin'):
                        out = {'error': 'refused: the request did not come from a page of this server'}
                    else:
                        out = self._change({k: query.get(k) for k in WRITES[na]}, misc, unset=(na == 'unset'))
                else:
                    out = {'error': 'unknown native_action %r' % na}
            except Exception as e:
                print('cMeta warning: cserver.settings: native_action %r failed: %s: %s' % (na, type(e).__name__, e))
                out = {'error': '%s: %s' % (type(e).__name__, e)}
            if isinstance(out, dict):
                out['server'] = {'pid': os.getpid(), 'ms': int((time.monotonic() - t0) * 1000)}
            return {'return': 0, 'json': out}

        path_to_files = os.path.join(self.path, 'files')
        url_files = urls.get('url_files') or ''
        url_server = urls.get('url_server') or '/'
        platform = bool(misc.get('ctuning_server'))
        dark = misc.get('theme', '') == 'dark' or str(query.get('dark', '')).lower() in ('1', 'true', 'yes')
        config = {'api_url': urls.get('url', '?'), 'url_server': url_server, 'dark_mode': bool(dark), 'hosted': platform,
                  'version': getattr(self.cm, '__version__', ''), 'edit': self._may_write(misc)[0],
                  'state': {'q': str(query.get('q') or ''), 'show': str(query.get('show') or '')},
                  'configs_url': '' if platform else url_server + 'cmeta.configs',
                  'cref_url': '' if platform else url_server + 'cref/'}
        with open(os.path.join(path_to_files, 'index.html'), encoding='utf-8') as f:
            body = f.read()
        body = body.replace('%%CONFIG%%', _js(config)).replace('%%VERSION%%', _esc(config['version']))
        head = ('\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
                '  <link type="text/css" rel="stylesheet" media="all" href="%s">\n'
                '  <script src="%s" defer></script>\n' % (_asset(path_to_files, url_files, 'css/settings.css'),
                                                          _asset(path_to_files, url_files, 'js/settings.js')))
        return {'return': 0, 'html_meta': {'page_title': 'Settings', 'page_extra_style': head, 'html': body}}

    # ------------------------------------------------------------------ cli
    def list_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1 = '',  # Words (the first word after the command): in a key, what it does, its config, who reads it.
        query = '',  # The words, when they are not the first word.
        show = '',  # set = only the keys set here; unset = only those not set.
        as_json = False,  # Print the JSON the page reads instead.
    ):
        """
        The settings of this machine in a terminal, as the page lists them: each config artifact, its keys, their
        values here (secrets hidden).
        """
        if show not in SHOWS:
            return {'return': 1, 'error': 'show: one of %s is expected' % ', '.join(s for s in SHOWS if s)}
        out = self._payload({'cli': True, 'client_local': True})
        words = str(query or arg1 or '').lower().split()
        groups = []
        for g in out['groups']:
            keys = [k for k in g['keys'] if (not show or (show == 'set') == k['set']) and
                    all(w in ' '.join([k['key'], k['desc'], g['name'], ' '.join(k['readers'])]).lower() for w in words)]
            if keys:
                groups.append(dict(g, keys=keys))
        if as_json:
            print(json.dumps(dict(out, groups=groups), indent=2, ensure_ascii=False))
            return {'return': 0, 'groups': groups}
        if ctx.get('control', {}).get('con'):
            for g in groups:
                print('\n%s%s - %s' % (g['name'], '' if g['here'] else ' (not set here)', g['desc'][:100]))
                for k in g['keys']:
                    v = '(hidden)' if k['secret'] and k['set'] else (json.dumps(k['value'], ensure_ascii=False) if k['set'] else '-')
                    print('  %-34s %-28s %s' % (k['key'][:34], v[:28], k['desc'][:70]))
            n = sum(len(g['keys']) for g in groups)
            print('\n%d keys in %d configs, %d set here' % (n, len(groups), sum(1 for g in groups for k in g['keys'] if k['set'])))
        return {'return': 0, 'groups': groups}
