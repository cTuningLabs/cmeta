"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.browse - search, browse and graph the artifacts of every plugged repository.

    cx app run cserver      ->  http://127.0.0.1:8004/browse

Three views of one query:
    Search   the results as a list, best matches first
    Browse   a sortable table with facets: repositories, categories, tags, years, generators
    Graph    the results as nodes, joined by the connections in their _desc

Everything is read from the index (every artifact's _cmeta with its repository and category), so a search over
ten thousand artifacts takes milliseconds once the index is loaded (a few seconds, once per server start, and
again only when the index changes). Only the detail of one artifact and the graph read _desc files.

Query syntax (one box; everything must hold):
    word  "a phrase"       in the alias, UID, tags or any value of the meta (case-insensitive)
    -word                  not in them
    repo:<name>            repository alias or UID; the part after "@" is enough (several repo: = any of them)
    cat:<name>             category alias or UID (also category:); several cat: = any of them
    tag:<tag>              has this tag (each tag: must hold); -tag:<tag> has not
    uid:<prefix>           the UID starts with it
    after:YYYY-MM-DD       created on or after (a year or a year-month works too); before: created before
    has:<key>              the meta has the key (dotted: generator.method); -has:<key> has not
    <key>:<value>          a meta value contains it (dotted keys; any item of a list)
    <cat>::<artifact>      a cRef: that category, and the artifact's alias or UID
    Values with * or ? are fnmatch patterns: repo:dappledev@*, tag:sla*.

    cx cserver.browse query "sla tag:report after:2026-09-01"      the same in a terminal (--as_json for JSON)
    ?native_action=search&q=...                                    the JSON the page renders (GET or POST)

On a shared server two keys of the cserver config apply:
    hide_repos                repositories left out (aliases or fnmatch patterns) - the same key as /projects
    browse_hide_categories    categories left out; by default anything matching *crypt*, *secret* or
                              *credential*, so that key bundles never show; "none" shows every category
"""

import datetime
import fnmatch
import html
import json
import os
import re
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from cmeta.category import InitCategory

CATEGORY_UID = 'dd9ea50e7f76467f'
SECRET_CATEGORIES = ['*crypt*', '*secret*', '*credential*']
PAGE_DEFAULT = 50
LIMIT_MAX = 1000
GRAPH_DEFAULT = 150
GRAPH_MAX = 600
DESC_MAX_BYTES = 400000          # a larger _desc is summarised, not sent

UID_RE = re.compile(r'^[0-9a-fA-F]{16}$')
KEY_RE = re.compile(r'^[A-Za-z_][\w.\-]*$')
TOKEN_RE = re.compile(r'-?[^\s"]*"[^"]*"|\S+')

# One catalog per process: rebuilt when the index changes (its files' mtimes and count)
_lock = threading.Lock()
_catalog = {'stamp': None, 'items': [], 'by_uid': {}, 'built': '', 'ms': 0}
_desc_cache = {}                 # path of _desc -> (mtime, data)


# ---------------------------------------------------------------------- helpers
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


def _patterns(value):
    """Aliases or fnmatch patterns, from a list or a comma-separated string, lower-cased."""
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(',')
    return [str(v).strip().lower() for v in value if str(v).strip()]


def _matches_any(text, patterns):
    text = (text or '').lower()
    return any(fnmatch.fnmatchcase(text, p) for p in patterns)


def _wild(v):
    return '*' in v or '?' in v or '[' in v


def _list(value):
    """A list from a list, or a comma-separated string ('' -> [])."""
    if value is None or value == '':
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(',') if v.strip()]


def _int(value, default, low=1, high=None):
    try:
        v = int(value)
    except Exception:
        return default
    v = max(low, v)
    return min(v, high) if high else v


def _stamp(ts):
    """'2026-10-02T09:12:11.39+00:00' -> '2026-10-02 09:12' ('' when missing or unreadable)."""
    if not ts or not isinstance(ts, str) or len(ts) < 10:
        return ''
    return ts[:16].replace('T', ' ')


def _dotted(meta, key):
    """The value at a dotted key of the meta (None when missing)."""
    cur = meta
    for part in key.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _value_matches(value, want):
    """A meta value against a wanted text: fnmatch with wildcards, else a case-insensitive substring;
    a list matches when any item does; a dict is matched on its JSON."""
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(_value_matches(v, want) for v in value)
    text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, dict) else str(value)
    text = text.lower()
    return fnmatch.fnmatchcase(text, want) if _wild(want) else want in text


def _name_matches(alias, uid, want):
    """A repository or category given as alias, UID, alias,UID, the part after "@", or a pattern."""
    want = want.lower()
    if want == '(registry)':                       # the repo artifacts themselves belong to no repository
        return not alias
    if ',' in want:
        want = want.split(',')[-1].strip()
    alias = (alias or '').lower()
    uid = (uid or '').lower()
    if _wild(want):
        return fnmatch.fnmatchcase(alias, want) or fnmatch.fnmatchcase(uid, want)
    return want in (alias, uid) or ('@' in alias and alias.split('@', 1)[1] == want)


def parse_query(q):
    """The query text -> {'words', 'not_words', 'repos', 'cats', 'tags', 'not_tags', 'uids', 'after', 'before',
    'has', 'not_has', 'fields': [(key, value, negated)], 'aliases'}."""
    out = {'words': [], 'not_words': [], 'repos': [], 'cats': [], 'tags': [], 'not_tags': [], 'uids': [],
           'after': '', 'before': '', 'has': [], 'not_has': [], 'fields': [], 'aliases': []}
    for tok in TOKEN_RE.findall(q or ''):
        neg = tok.startswith('-') and len(tok) > 1
        t = tok[1:] if neg else tok

        if '::' in t and not t.startswith('"'):            # a cRef: category::artifact
            cat, art = t.split('::', 1)
            if cat:
                out['cats'].append(cat)
            if art:
                art = art.split(',')
                if len(art) > 1 and UID_RE.match(art[-1].strip()):
                    out['uids'].append(art[-1].strip().lower())
                else:
                    out['aliases'].append(art[0].strip().lower())
            continue

        key, sep, value = t.partition(':')
        if sep and KEY_RE.match(key) and not t.startswith('"'):
            key = key.lower()
            value = value.strip()
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1]
            if value == '':
                continue
            if key == 'repo':
                out['repos'].append(value)
            elif key in ('cat', 'category'):
                out['cats'].append(value)
            elif key == 'tag':
                out['not_tags' if neg else 'tags'].append(value.lower())
            elif key == 'uid':
                out['uids'].append(value.lower())
            elif key in ('after', 'since'):
                out['after'] = value
            elif key in ('before', 'until'):
                out['before'] = value
            elif key == 'has':
                out['not_has' if neg else 'has'].append(value)
            else:
                out['fields'].append((key, value.lower(), neg))
            continue

        word = t[1:-1] if len(t) >= 2 and t[0] == '"' and t[-1] == '"' else t
        word = word.lower().strip()
        if word:
            out['not_words' if neg else 'words'].append(word)
    return out


def _item_matches(it, pq, ui_repos, ui_cats, after, before):
    """True when the catalog item holds everything the parsed query and the pickers ask for."""
    if ui_repos and not any(_name_matches(it['repo'], it['repo_uid'], w) for w in ui_repos):
        return False
    if ui_cats and not any(_name_matches(it['cat'], it['cat_uid'], w) for w in ui_cats):
        return False
    if pq['repos'] and not any(_name_matches(it['repo'], it['repo_uid'], w) for w in pq['repos']):
        return False
    if pq['cats'] and not any(_name_matches(it['cat'], it['cat_uid'], w) for w in pq['cats']):
        return False
    if pq['uids'] and not any(it['uid'].startswith(u) for u in pq['uids']):
        return False
    if pq['aliases'] and not any(fnmatch.fnmatchcase(it['alias_l'], a) if _wild(a) else it['alias_l'] == a
                                 for a in pq['aliases']):
        return False
    tags = it['tags_l']
    for t in pq['tags']:
        if not any(fnmatch.fnmatchcase(x, t) for x in tags) if _wild(t) else t not in tags:
            return False
    for t in pq['not_tags']:
        if any(fnmatch.fnmatchcase(x, t) for x in tags) if _wild(t) else t in tags:
            return False
    if after or before:
        c = it['created']
        if not c or (after and c < after) or (before and c >= before):
            return False
    for k in pq['has']:
        if _dotted(it['meta'], k) is None:
            return False
    for k in pq['not_has']:
        if _dotted(it['meta'], k) is not None:
            return False
    for key, value, neg in pq['fields']:
        if _value_matches(_dotted(it['meta'], key), value) == neg:
            return False
    hay = it['hay']
    for w in pq['words']:
        if w not in hay:
            return False
    for w in pq['not_words']:
        if w in hay:
            return False
    return True


def _score(it, words):
    s = 0
    alias = it['alias_l']
    for w in words:
        if w == alias or w == it['uid']:
            s += 8
        elif w in alias:
            s += 4
        elif any(w in t for t in it['tags_l']):
            s += 2
        elif w in (it['name_l'] or ''):
            s += 2
        else:
            s += 1
    return s


def _snippet(it, words):
    """Where the first word that is not in the alias was found: 'key: ...text...' (or '')."""
    for w in words:
        if w in it['alias_l']:
            continue
        stack = [('', it['meta'])]
        while stack:
            prefix, cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    stack.append(((prefix + '.' if prefix else '') + str(k), v))
            elif isinstance(cur, (list, tuple)):
                for v in cur:
                    stack.append((prefix, v))
            else:
                text = str(cur)
                i = text.lower().find(w)
                if i >= 0:
                    start = max(0, i - 40)
                    return '%s: %s%s%s' % (prefix, '...' if start else '', text[start:i + len(w) + 60],
                                           '...' if i + len(w) + 60 < len(text) else '')
    return ''


def _row(it, words=None):
    """What the page shows of an item (no meta, no haystack)."""
    r = {'uid': it['uid'], 'alias': it['alias'], 'name': it['name'], 'cat': it['cat'], 'cat_uid': it['cat_uid'],
         'repo': it['repo'], 'created': _stamp(it['created_full']), 'updated': _stamp(it['updated_full']),
         'tags': it['tags'][:12], 'migrated_to': it['meta'].get('migrated_to') or ''}
    if words:
        r['snippet'] = _snippet(it, words)
    return r


def _sort(items, sort, desc, words):
    if sort == 'relevance' and words:
        return sorted(items, key=lambda it: (_score(it, words), it['updated_full'] or it['created_full']),
                      reverse=True)
    keys = {
        'alias': lambda it: it['alias_l'],
        'cat': lambda it: (it['cat'].lower(), it['alias_l']),
        'repo': lambda it: (it['repo'].lower(), it['cat'].lower(), it['alias_l']),
        'created': lambda it: it['created_full'] or '',
        'updated': lambda it: it['updated_full'] or it['created_full'] or '',
        'uid': lambda it: it['uid'],
    }
    return sorted(items, key=keys.get(sort, keys['updated']), reverse=desc)


def _facets(items):
    repos, cats, tags, years, gens = Counter(), Counter(), Counter(), Counter(), Counter()
    for it in items:
        repos[it['repo'] or '(registry)'] += 1
        cats[it['cat']] += 1
        tags.update(it['tags'])
        years[it['created'][:4] or '(no date)'] += 1
        g = it['meta'].get('generator')
        gens[(g.get('method') if isinstance(g, dict) else None) or '(none)'] += 1
    return {'repo': repos.most_common(), 'cat': cats.most_common(), 'tag': tags.most_common(30),
            'year': sorted(years.items(), reverse=True), 'generator': gens.most_common()}


def _read_desc(path):
    """The _desc of an artifact folder, cached by mtime: (data, file name, size) or (None, '', 0)."""
    for fn in ('_desc.json', '_desc.yaml'):
        f = os.path.join(path, fn)
        try:
            st = os.stat(f)
        except OSError:
            continue
        hit = _desc_cache.get(f)
        if hit and hit[0] == st.st_mtime:
            return hit[1], fn, st.st_size
        try:
            with open(f, encoding='utf-8') as fh:
                if fn.endswith('.json'):
                    data = json.load(fh)
                else:
                    import yaml
                    data = yaml.safe_load(fh)
        except Exception as e:
            data = {'_error': '%s: %s' % (type(e).__name__, e)}
        if not isinstance(data, dict):
            data = {'_value': data}
        _desc_cache[f] = (st.st_mtime, data)
        return data, fn, st.st_size
    return None, '', 0


def _cref_uid(cref):
    """The artifact of a cRef like 'cat,UID::alias,UID' -> (its UID or '', its alias or '')."""
    s = str(cref or '')
    art = s.split('::', 1)[1] if '::' in s else s
    parts = [p.strip() for p in art.split(',') if p.strip()]
    uid = next((p.lower() for p in reversed(parts) if UID_RE.match(p)), '')
    alias = next((p for p in parts if not UID_RE.match(p)), '')
    return uid, alias


def _connections(desc, meta):
    """The cRefs an artifact connects to: _desc connections (or legacy meta connections)."""
    out = []
    for src in ((desc or {}).get('connections'), (meta or {}).get('connections')):
        if isinstance(src, list):
            out.extend(str(x) for x in src if x)
    return out


# ---------------------------------------------------------------------- the category
class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def _uses(self, key, default):
        return ((self.cmeta or {}).get('uses_categories', {}) or {}).get(key, default)

    def _cserver_config(self):
        """The cserver config, read on every request ({} when it cannot be read)."""
        r = self.cm.access({'category': self._uses('config', 'config,cc6bfe174be847ed'), 'command': 'get',
                            'arg1': 'cserver', 'con': False})
        if r.get('return', 1) > 0:
            return {}
        return r.get('config_cmeta') or {}

    # ------------------------------------------------------------ the catalog
    def _index_stamp(self):
        """Count and newest mtime of the index files: changes whenever the index does."""
        path = getattr(self.cm.repos, 'index_path', '')
        newest, count = 0.0, 0
        try:
            with os.scandir(path) as it:
                for e in it:
                    if e.is_file():
                        count += 1
                        newest = max(newest, e.stat().st_mtime)
        except OSError:
            pass
        return (path, count, newest)

    def _catalog(self, force=False):
        """Every artifact of every indexed category, with what search needs precomputed. Cached per process."""
        stamp = self._index_stamp()
        if not force and _catalog['stamp'] == stamp:
            return _catalog
        with _lock:
            if not force and _catalog['stamp'] == stamp:
                return _catalog
            t0 = time.time()
            items, by_uid = [], {}
            r = self.cm.repos.find_in_index('category', CATEGORY_UID)
            cats = r.get('artifacts', []) if r.get('return', 1) == 0 else []
            skipped = []
            for c in cats:
                cp = c['cmeta_ref_parts']
                if (c.get('cmeta') or {}).get('no_index'):
                    skipped.append(cp.get('artifact_alias', ''))
                    continue
                rr = self.cm.repos.find_in_index(cp.get('artifact_alias', ''), cp['artifact_uid'])
                if rr.get('return', 1) > 0:
                    continue
                for a in rr.get('artifacts', []):
                    p = a['cmeta_ref_parts']
                    meta = a.get('cmeta') or {}
                    alias = p.get('artifact_alias') or p['artifact_uid']
                    tags = [str(t) for t in (meta.get('tags') or []) if t is not None] \
                        if isinstance(meta.get('tags'), list) else []
                    created = meta.get('creation_timestamp') or ''
                    updated = meta.get('last_update_timestamp') or ''
                    name = meta.get('name') if isinstance(meta.get('name'), str) else ''
                    it = {'uid': p['artifact_uid'].lower(), 'alias': alias, 'alias_l': alias.lower(),
                          'name': name, 'name_l': name.lower(),
                          'cat': cp.get('artifact_alias', ''), 'cat_uid': cp['artifact_uid'],
                          'repo': p.get('repo_alias') or '', 'repo_uid': p.get('repo_uid') or '',
                          'path': a.get('path', ''), 'meta': meta, 'tags': tags,
                          'tags_l': [t.lower() for t in tags],
                          'created': created[:10] if isinstance(created, str) else '',
                          'created_full': created if isinstance(created, str) else '',
                          'updated_full': updated if isinstance(updated, str) else ''}
                    it['hay'] = ' '.join([alias, it['uid'], it['cat'], it['repo'],
                                          json.dumps(meta, ensure_ascii=False, default=str)]).lower()
                    items.append(it)
                    by_uid[it['uid']] = it
            _catalog.update({'stamp': stamp, 'items': items, 'by_uid': by_uid, 'skipped': skipped,
                             'built': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                             'ms': int((time.time() - t0) * 1000), 'categories': len(cats)})
            return _catalog

    def _visible(self, cfg=None):
        """The catalog items a viewer may see: hide_repos and browse_hide_categories applied."""
        cat = self._catalog()
        cfg = self._cserver_config() if cfg is None else cfg
        hide_repos = _patterns(cfg.get('hide_repos'))
        raw = cfg.get('browse_hide_categories')
        if raw is None or str(raw).strip() == '':
            hide_cats = SECRET_CATEGORIES                  # the default: key bundles never show
        elif str(raw).strip().lower() in ('none', 'off', 'no'):
            hide_cats = []
        else:
            hide_cats = _patterns(raw)
        if not hide_repos and not hide_cats:
            return cat['items']
        return [it for it in cat['items']
                if not (hide_repos and it['repo'] and _matches_any(it['repo'], hide_repos))
                and not (hide_cats and _matches_any(it['cat'], hide_cats))]

    # ------------------------------------------------------------ actions
    def _search(self, params, items=None):
        """The query, the pickers and the dates -> one page of rows, the total, the facets and the timing."""
        t0 = time.time()
        params = params or {}
        items = self._visible() if items is None else items
        pq = parse_query(params.get('q', ''))
        ui_repos = _list(params.get('repos'))
        ui_cats = _list(params.get('cats'))
        after = str(params.get('after') or pq['after'] or '').strip()
        before = str(params.get('before') or pq['before'] or '').strip()
        found = [it for it in items if _item_matches(it, pq, ui_repos, ui_cats, after, before)]
        sort = str(params.get('sort') or ('relevance' if pq['words'] else 'updated'))
        desc = str(params.get('dir') or ('asc' if sort in ('alias', 'cat', 'repo', 'uid') else 'desc')) == 'desc'
        found = _sort(found, sort, desc, pq['words'])
        limit = _int(params.get('limit'), PAGE_DEFAULT, 1, LIMIT_MAX)
        offset = _int(params.get('offset'), 0, 0)
        page = found[offset:offset + limit]
        out = {'total': len(found), 'offset': offset, 'limit': limit, 'sort': sort,
               'dir': 'desc' if desc else 'asc', 'rows': [_row(it, pq['words']) for it in page],
               'of': len(items), 'ms': int((time.time() - t0) * 1000), 'catalog': self._catalog_info()}
        if str(params.get('facets', '1')).lower() not in ('0', 'no', 'false'):
            out['facets'] = _facets(found)
        out['_found'] = found
        return out

    def _catalog_info(self):
        return {'artifacts': len(_catalog['items']), 'built': _catalog['built'], 'ms': _catalog['ms'],
                'categories': _catalog.get('categories', 0)}

    def _options(self):
        """The repositories and categories for the pickers, with counts (visible items only)."""
        items = self._visible()
        repos, cats = Counter(), Counter()
        for it in items:
            repos[it['repo'] or '(registry)'] += 1
            cats[it['cat']] += 1
        return {'repos': sorted(repos.items(), key=lambda x: x[0].lower()),
                'cats': sorted(cats.items(), key=lambda x: x[0].lower()),
                'total': len(items), 'catalog': self._catalog_info()}

    def _artifact(self, uid, local):
        """One artifact: its meta, its _desc, its connections resolved to the catalog, and its commands."""
        cat = self._catalog()
        uid = str(uid or '').strip().lower()
        it = cat['by_uid'].get(uid)
        if it is None or id(it) not in set(id(x) for x in self._visible()):
            return {'error': 'artifact %s is not in the index of this server' % uid}
        desc, desc_file, size = _read_desc(it['path'])
        desc_out = desc
        if desc is not None and size > DESC_MAX_BYTES:
            desc_out = {'_note': '%s is %d bytes; only its keys are shown' % (desc_file, size),
                        '_keys': sorted(desc.keys())}
        links = []
        for cref in _connections(desc, it['meta']):
            tuid, talias = _cref_uid(cref)
            t = cat['by_uid'].get(tuid) if tuid else None
            links.append({'cref': cref, 'uid': tuid, 'alias': t['alias'] if t else talias,
                          'cat': t['cat'] if t else '', 'found': t is not None})
        mig = it['meta'].get('migrated_to')
        mig_uid = _cref_uid(mig)[0] if mig else ''
        ref = '%s,%s' % (it['alias'], it['uid'])
        cmd_cat = it['cat'] or 'category'
        out = {'row': _row(it), 'repo_uid': it['repo_uid'], 'meta': it['meta'], 'desc': desc_out,
               'desc_file': desc_file, 'connections': links,
               'cref': '%s,%s::%s' % (it['cat'], it['cat_uid'], ref),
               'migrated_to_uid': mig_uid if mig_uid in cat['by_uid'] else '',
               'commands': ['cx %s find %s' % (cmd_cat, ref),
                            'cx %s info %s' % (cmd_cat, ref),
                            'cx %s read %s' % (cmd_cat, ref),
                            'cx %s tags %s --add=<tag> --remove=<tag>' % (cmd_cat, ref),
                            'cx %s update %s --meta.<key>=<value>' % (cmd_cat, ref)]}
        if local:
            out['path'] = it['path']
        return out

    def _graph(self, params):
        """The results as nodes (up to max_nodes) and the connections between them as links; with
        neighbors, the artifacts the results connect to join too (within the same limit)."""
        t0 = time.time()
        cat = self._catalog()
        max_nodes = _int(params.get('max_nodes'), GRAPH_DEFAULT, 1, GRAPH_MAX)
        r = self._search(dict(params, limit=max_nodes, offset=0, facets='0'))
        found = r['_found']
        visible = set(id(it) for it in self._visible()) if cat['items'] else set()
        nodes = list(found[:max_nodes])
        ids = set(it['uid'] for it in nodes)

        def descs(chunk):
            with ThreadPoolExecutor(max_workers=16) as ex:
                return list(ex.map(lambda it: _read_desc(it['path'])[0], chunk))

        out_links = {}
        for it, d in zip(nodes, descs(nodes)):
            out_links[it['uid']] = [u for u in (_cref_uid(c)[0] for c in _connections(d, it['meta'])) if u]
        neighbors = str(params.get('neighbors', '')).lower() in ('1', 'yes', 'true', 'on')
        extra = []
        if neighbors:
            for it in list(nodes):
                for u in out_links.get(it['uid'], []):
                    t = cat['by_uid'].get(u)
                    if t is not None and u not in ids and id(t) in visible and len(nodes) + len(extra) < max_nodes:
                        ids.add(u)
                        extra.append(t)
            for it, d in zip(extra, descs(extra)):
                out_links[it['uid']] = [u for u in (_cref_uid(c)[0] for c in _connections(d, it['meta'])) if u]
        links, seen = [], set()
        for src, targets in out_links.items():
            for t in targets:
                if t in ids and t != src and (src, t) not in seen:
                    seen.add((src, t))
                    links.append({'source': src, 'target': t})
        rows = [dict(_row(it), neighbor=False) for it in nodes] + [dict(_row(it), neighbor=True) for it in extra]
        cats = Counter(x['cat'] for x in rows)
        return {'nodes': rows, 'links': links, 'total': r['total'], 'shown': len(rows),
                'truncated': r['total'] > len(nodes), 'cats': cats.most_common(),
                'ms': int((time.time() - t0) * 1000)}

    @staticmethod
    def _is_local(urls):
        host = (urlparse((urls or {}).get('url_server') or '').hostname or '').lower()
        return host in ('127.0.0.1', 'localhost', '::1')

    # ------------------------------------------------------------ web
    def web_(self, ctx, urls, query={}, misc={}):
        """Render the page (command web) or answer ?native_action=... with JSON."""
        query = query or {}
        na = query.get('native_action', '')
        if na:
            try:
                if na == 'search':
                    out = self._search(query)
                    out.pop('_found', None)
                elif na == 'options':
                    out = self._options()
                elif na == 'reload':
                    self._catalog(force=True)
                    _desc_cache.clear()
                    out = self._options()
                elif na == 'artifact':
                    out = self._artifact(query.get('uid'), self._is_local(urls))
                elif na == 'graph':
                    out = self._graph(query)
                else:
                    out = {'error': 'unknown native_action %r' % na}
                return {'return': 0, 'json': out}
            except Exception as e:
                print('cserver.browse: native_action %r failed: %s\n%s' % (na, e, traceback.format_exc()))
                return {'return': 0, 'json': {'error': '%s: %s' % (type(e).__name__, e)}}

        try:
            path_to_files = os.path.join(self.path, 'files')
            url_files = urls.get('url_files') or ''
            theme = (misc or {}).get('theme', '')
            dark = theme == 'dark' or str(query.get('dark', '')).lower() in ('1', 'true', 'yes')
            version = getattr(self.cm, '__version__', '')
            state = {k: str(query.get(k) or '') for k in ('q', 'repos', 'cats', 'after', 'before', 'view',
                                                         'sort', 'dir', 'uid')}
            config = {'api_url': urls.get('url', '?'), 'url_server': urls.get('url_server') or '/',
                      'dark_mode': bool(dark), 'version': version, 'local': self._is_local(urls),
                      'state': state}
            with open(os.path.join(path_to_files, 'index.html'), encoding='utf-8') as f:
                body = f.read()
            body = body.replace('%%CONFIG%%', _js(config)).replace('%%VERSION%%', _esc(version))
            head = (
                '<link rel="stylesheet" href="%s">\n' % _asset(path_to_files, url_files, 'css/browse.css') +
                '<script src="%s" defer></script>\n' % _asset(path_to_files, url_files, 'js/browse.js')
            )
            return {'return': 0, 'html_meta': {'html': body, 'page_title': 'cMeta browse',
                                                'page_extra_style': head}}
        except Exception as e:
            return self.cm.error('cserver.browse: %s: %s' % (type(e).__name__, e))

    # ------------------------------------------------------------ cli
    def query_(self, ctx, arg1='', q='', repos='', cats='', after='', before='', sort='', dir='', limit=20,
               as_json=False):
        """Search the artifacts of every plugged repository, as the /browse page does ("search" itself is
        a global alias of find, so this command is called query).

        Args:
            arg1: the query (the first word after the command; or --q=...)
            q: the query: words, "phrases", repo:, cat:, tag:, -tag:, uid:, after:, before:, has:, <key>:<value>
            repos: repositories, comma-separated (aliases, UIDs or patterns)
            cats: categories, comma-separated (aliases, UIDs or patterns)
            after: created on or after YYYY-MM-DD
            before: created before YYYY-MM-DD
            sort: relevance, updated, created, alias, cat, repo or uid
            dir: asc or desc
            limit: how many rows to print (default 20)
            as_json: print the JSON the page reads instead of a table
        """
        r = self._search({'q': q or arg1 or '', 'repos': repos, 'cats': cats, 'after': after, 'before': before,
                          'sort': sort, 'dir': dir, 'limit': limit, 'facets': '1' if as_json else '0'})
        r.pop('_found', None)
        if as_json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return {'return': 0, 'result': r}
        rows = r['rows']
        if rows:
            w_alias = min(48, max(len(x['alias']) for x in rows))
            w_cat = min(30, max(len(x['cat']) for x in rows))
            for x in rows:
                print('%-*s  %-*s  %-16s  %s' % (w_alias, x['alias'][:w_alias], w_cat, x['cat'][:w_cat],
                                                 x['updated'] or x['created'], x['repo']))
        print('\n%d of %d artifacts match (%d ms); %d shown, sorted by %s' %
              (r['total'], r['of'], r['ms'], len(rows), r['sort']))
        return {'return': 0, 'total': r['total'], 'rows': rows}
