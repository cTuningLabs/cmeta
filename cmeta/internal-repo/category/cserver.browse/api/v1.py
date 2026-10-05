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
    Values with * or ? are fnmatch patterns: repo:ctuninglabs@*, tag:sla*.

    cx cserver.browse query "sla tag:report after:2026-09-01"      the same in a terminal (--as_json for JSON)
    ?native_action=search&q=...                                    the JSON the page renders (GET or POST)

The graph (?native_action=graph, the Graph tab) draws the results of the query, or - with focus=<artifact> and
depth=N - everything within N connections of one artifact (the query words are then not applied; the
repository and category pickers still are, as a scope):
    categories=1          each artifact hangs off its category node (that is the layout); 0 = artifacts only
    core=1                the cMeta node in the middle, joined to every category
    isolated=1            with categories off, also draw the artifacts that connect to nothing drawn
    neighbors=1           add what the results connect to, and what connects to them (one hop, in the scope)
    max_nodes=300         a cap; over it, a sample spread evenly across categories, best connected first
Connections come from each _desc's `connections` (both ways) and `uses` (one way: a task and the tasks it
runs). A background thread reads every _desc once into a connection index (seconds on thousands of artifacts,
started when the page opens; after an index change or a reload it re-reads only the _desc files that changed);
the graph waits for a build that runs, and the detail lists what connects INTO an artifact from it. Every
answer carries its timings: catalog, connections, selection, graph.

The detail of an artifact can list its files and show one (text inline, images and PDFs as they are): only to
a browser on the server's own machine, unless browse_files says otherwise; never key-like files, never
dot-files, never outside the artifact's own folder.

On a shared server these keys of the cserver config apply:
    hide_repos                repositories left out (aliases or fnmatch patterns) - the same key as /projects
    browse_hide_categories    categories left out; by default anything matching *crypt*, *secret* or
                              *credential*, so that key bundles never show; "none" shows every category
    browse_files              yes = the file browser for everyone; no = for no one; default: a browser on the
                              server's own machine only (the real peer address, no proxy header)
"""

import base64
import datetime
import fnmatch
import html
import itertools
import json
import os
import re
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from cmeta.category import InitCategory

CATEGORY_UID = 'dd9ea50e7f76467f'
SECRET_CATEGORIES = ['*crypt*', '*secret*', '*credential*']
PAGE_DEFAULT = 50
LIMIT_MAX = 1000
GRAPH_DEFAULT = 300
GRAPH_MAX = 1000
DEPTH_MAX = 12
DESC_MAX_BYTES = 400000          # a larger _desc is summarised, not sent

# What the URL of the page keeps: the query, the view, the open artifact and the graph controls
STATE_KEYS = ('q', 'repos', 'cats', 'after', 'before', 'view', 'sort', 'dir', 'uid',
              'focus', 'depth', 'max_nodes', 'categories', 'core', 'isolated', 'neighbors', 'labels', 'links')

UID_RE = re.compile(r'^[0-9a-fA-F]{16}$')
KEY_RE = re.compile(r'^[A-Za-z_][\w.\-]*$')
TOKEN_RE = re.compile(r'-?[^\s"]*"[^"]*"|\S+')
USES_RE = re.compile(r'^(.+),([0-9a-fA-F]{16})$')      # a `uses:` value: <alias>,<UID>

# The file browser: what it never shows - folders named like a key store, files that look like key material
SECRET_DIR_RE = re.compile(r'crypt|secret|credential', re.I)
SECRET_FILE_RE = re.compile(
    r'^id_|_(rsa|dsa|ecdsa|ed25519)$'                                      # SSH key pairs
    r'|\.(pem|key|p12|pfx|ppk|jks|keystore|kdbx|gpg|pgp|asc|ovpn)$'       # keys, keystores, vaults
    r'|^(known_hosts|authorized_keys)'
    r'|(^|[._-])(tokens?|secrets?)(\.[a-z0-9]+)?$|passw(or)?d|credential',  # api_token.txt, not tokenizer.json
    re.I)
TEXT_EXT = {'.md', '.txt', '.yaml', '.yml', '.json', '.py', '.js', '.html', '.htm', '.css', '.csv', '.tsv', '.log',
            '.toml', '.ini', '.cfg', '.sh', '.bat', '.ps1', '.xml', '.rst', '.tex', '.bib', '.svg', '.sql', '.r',
            '.c', '.h', '.cpp', '.java', '.ts', '.tsx', '.jsx', '.go', '.rs', '.jsonl'}
BINARY_MIME = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
               '.gif': 'image/gif', '.webp': 'image/webp'}
META_FILES = ('_cmeta.yaml', '_cmeta.json', '_desc.yaml', '_desc.json')
TEXT_CAP = 512 * 1024
BINARY_CAP = 12 * 1024 * 1024
FILES_DEFAULT = 200
FILES_SCAN_MAX = 20000           # a listing stops counting there (a dataset can hold millions of files)
INDEX_WAIT = 120                 # seconds the graph waits for a running build of the connection index
ARTIFACT_WAIT = 10               # ... and the detail of one artifact, when there is no index yet
INCOMING_MAX = 300               # incoming connections listed in the detail of one artifact

# One catalog per process: rebuilt when the index changes (its files' mtimes and count)
_lock = threading.Lock()
_catalog = {'stamp': None, 'items': [], 'by_uid': {}, 'by_key': {}, 'built': '', 'ms': 0}
_desc_cache = {}                 # path of _desc -> (mtime, data)

# The connection index: what every artifact connects to (`connections`, both ways) and runs (`uses`, one way),
# read from all _desc files in a background thread; kept per process, rebuilt when the catalog changes or a
# reload asks for it. _links_cache keeps what each _desc declared, by mtime, so a rebuild re-reads only edits.
_conn_lock = threading.Lock()
_conn = {'stamp': None, 'want': 0, 'ready': False, 'building': False, 'thread': None, 'done': 0, 'total': 0,
         'ms': 0, 'built': '', 'error': '', 'out': {}, 'uses': {}, 'inn': {}, 'adj': {}, 'links': 0, 'uses_n': 0}
_links_cache = {}                # path of _desc -> ((mtime, size), connections, uses)


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


def _flag(value, default):
    """A switch from the query: '' or absent -> the default; 0, false, no, off -> False; anything else -> True."""
    if value is None or str(value).strip() == '':
        return default
    return str(value).strip().lower() not in ('0', 'false', 'no', 'off')


def _load(f):
    """A JSON or YAML file (the C YAML loader when there is one: thousands of _desc files are read)."""
    with open(f, encoding='utf-8') as fh:
        if f.endswith('.json'):
            return json.load(fh)
        import yaml
        return yaml.load(fh, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))


def _desc_file(path):
    """The _desc file of an artifact folder and its stat: (file, stat) or ('', None)."""
    for fn in ('_desc.json', '_desc.yaml'):
        f = os.path.join(path, fn)
        try:
            return f, os.stat(f)
        except OSError:
            continue
    return '', None


def _read_desc(path):
    """The _desc of an artifact folder, cached by mtime: (data, file name, size) or (None, '', 0)."""
    f, st = _desc_file(path)
    if not f:
        return None, '', 0
    fn = os.path.basename(f)
    hit = _desc_cache.get(f)
    if hit and hit[0] == st.st_mtime:
        return hit[1], fn, st.st_size
    try:
        data = _load(f)
    except Exception as e:
        data = {'_error': '%s: %s' % (type(e).__name__, e)}
    if not isinstance(data, dict):
        data = {'_value': data}
    _desc_cache[f] = (st.st_mtime, data)
    return data, fn, st.st_size


def _cref_uid(cref):
    """The artifact of a cRef like 'cat,UID::alias,UID' -> (its UID or '', its alias or '')."""
    _cat, _cat_uid, alias, uid = _parse_cref(cref)
    return uid, alias


def _parse_cref(cref):
    """'cat,UID::alias,UID' (or 'cat::alias', 'alias,UID', a bare alias or UID) -> (cat, cat UID, alias, UID);
    the UIDs lower-cased, '' for what is missing."""
    s = str(cref or '').strip()
    left, sep, right = s.partition('::')
    if not sep:
        left, right = '', s
    cat, _, cat_uid = left.partition(',')
    parts = [p.strip() for p in right.split(',') if p.strip()]
    uid = next((p.lower() for p in reversed(parts) if UID_RE.match(p)), '')
    alias = next((p for p in parts if not UID_RE.match(p)), '')
    return cat.strip(), cat_uid.strip().lower(), alias, uid


def _connections(desc, meta):
    """The cRefs an artifact connects to: _desc connections (or legacy meta connections)."""
    out = []
    for src in ((desc or {}).get('connections'), (meta or {}).get('connections')):
        if isinstance(src, list):
            out.extend(str(x) for x in src if x)
    return out


def _uses_refs(desc):
    """What an artifact runs, from the `uses:` list of its _desc: [(category, alias, UID)]. An entry mixes one
    reference (the value shaped <alias>,<UID>) with parameters: `- task: setup,a2f9b61079ce4333`."""
    out = []
    for entry in (desc or {}).get('uses') or []:
        if isinstance(entry, dict):
            for k, v in entry.items():
                m = USES_RE.match(v.strip()) if isinstance(v, str) else None
                if m:
                    out.append((str(k).strip(), m.group(1).strip(), m.group(2).lower()))
    return out


def _ai_uses_refs(desc):
    """Whose memory and skills an artifact's AI sessions read, from the `ai_uses:` list of its _desc - the directed
    counterpart of `connections`, in the spirit of `uses`: parsed cRefs. An entry is a cRef string
    "category,UID::artifact,UID" or a dict with "cref"."""
    out = []
    for entry in (desc or {}).get('ai_uses') or []:
        c = entry.get('cref') if isinstance(entry, dict) else entry
        if isinstance(c, str) and '::' in c:
            out.append(_parse_cref(c))
    return out


def _resolve(ref, by_uid, by_key):
    """A parsed reference (cat, cat UID, alias, UID) -> the UID of a catalog artifact, or ''. The UID decides when
    there is one; a reference by alias alone needs its category."""
    cat, cat_uid, alias, uid = ref
    if uid:
        return uid if uid in by_uid else ''
    if alias and (cat or cat_uid):
        a = alias.lower()
        return by_key.get((cat_uid, a)) or by_key.get((cat.lower(), a)) or ''
    return ''


def _links_raw(path):
    """What the _desc of an artifact folder declares, unresolved: (connections as parsed cRefs, uses, ai_uses).
    Cached by the file's mtime and size, so a rebuild of the index re-reads only the _desc files that changed."""
    f, st = _desc_file(path)
    if not f:
        return [], [], []
    key = (st.st_mtime, st.st_size)
    hit = _links_cache.get(f)
    if hit and hit[0] == key:
        return hit[1], hit[2], hit[3]
    try:
        data = _load(f)
    except Exception:
        data = None
    if not isinstance(data, dict):
        data = {}
    conns = [_parse_cref(c) for c in _connections(data, None)]
    uses = _uses_refs(data)
    ai = _ai_uses_refs(data)
    _links_cache[f] = (key, conns, uses, ai)
    return conns, uses, ai


def _conn_compute(items, by_uid, by_key):
    """The connection index of the catalog items: out (connections, as declared), uses (what each runs), ai (whose
    memory each reads: `ai_uses`), inn (who connects to, uses or reads each), adj (every neighbour, either way)."""
    counter = itertools.count(1)

    def read(it):
        try:
            r = _links_raw(it['path'])
        except Exception:
            r = ([], [], [])
        _conn['done'] = next(counter)
        return r

    with ThreadPoolExecutor(max_workers=16) as ex:
        raw = list(ex.map(read, items))
    out, uses, ai, inn, adj = {}, {}, {}, {}, {}
    n_links = n_uses = n_ai = 0
    for it, (conns, us, ais) in zip(items, raw):
        src = it['uid']
        legacy = [_parse_cref(c) for c in _connections(None, it['meta'])]
        o, u, a = [], [], []
        for ref in conns + legacy:
            t = _resolve(ref, by_uid, by_key)
            if t and t != src and t not in o:
                o.append(t)
        for c, al, uid in us:
            t = _resolve((c, '', al, uid), by_uid, by_key)
            if t and t != src and t not in u:
                u.append(t)
        for ref in ais:
            t = _resolve(ref, by_uid, by_key)
            if t and t != src and t not in a:
                a.append(t)
        if o:
            out[src] = o
            n_links += len(o)
        if u:
            uses[src] = u
            n_uses += len(u)
        if a:
            ai[src] = a
            n_ai += len(a)
        for t in o + u + a:
            inn.setdefault(t, set()).add(src)
            adj.setdefault(t, set()).add(src)
            adj.setdefault(src, set()).add(t)
    return {'out': out, 'uses': uses, 'ai': ai, 'inn': inn, 'adj': adj, 'links': n_links, 'uses_n': n_uses, 'ai_n': n_ai}


def _conn_run():
    """The background build of the connection index; it runs again while the catalog changed or a reload asked
    for a newer one during the build."""
    while True:
        with _lock:
            items, by_uid, by_key, stamp = (_catalog['items'], _catalog['by_uid'], _catalog['by_key'],
                                            _catalog['stamp'])
        with _conn_lock:
            want = _conn['want']
            _conn.update(done=0, total=len(items))
        t0 = time.time()
        try:
            res, err = _conn_compute(items, by_uid, by_key), ''
        except Exception as e:
            res, err = None, '%s: %s' % (type(e).__name__, e)
        with _conn_lock:
            if res is not None:
                _conn.update(res)
                _conn.update(ready=True, stamp=stamp, ms=int((time.time() - t0) * 1000),
                             built=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            _conn['error'] = err
            if res is None or (_conn['want'] == want and _catalog['stamp'] == stamp):
                _conn['building'] = False
                return


def _conn_request(force=False):
    """Start a build of the connection index when the catalog changed (or force: a reload), unless one runs;
    a running build picks the request up when it ends. Returns the building thread (None when none is needed)."""
    with _conn_lock:
        if force:
            _conn['want'] += 1
        if (force or _conn['stamp'] != _catalog['stamp']) and not _conn['building']:
            _conn['building'] = True
            t = threading.Thread(target=_conn_run, name='cserver.browse connection index', daemon=True)
            _conn['thread'] = t
            t.start()
        return _conn['thread'] if _conn['building'] else None


def _conn_status():
    return {'ready': _conn['ready'], 'building': _conn['building'], 'done': _conn['done'], 'total': _conn['total'],
            'ms': _conn['ms'], 'built': _conn['built'], 'error': _conn['error'], 'links': _conn['links'],
            'uses': _conn['uses_n'], 'ai_uses': _conn.get('ai_n', 0),
            'stale': bool(_conn['ready'] and _conn['stamp'] != _catalog['stamp'])}


def _fair_sample(uids, items, layer, deg, gdeg, rank, cap):
    """At most cap of the uids, taken layer by layer (the hops from a focus; 0 = the results, 1 = what was added),
    and within a layer round-robin across categories - the best connected first in each - so that one large
    category cannot take the whole budget and leave the others looking empty."""
    layers = {}
    for u in uids:
        layers.setdefault(layer.get(u, 0), []).append(u)
    picked = []
    for d in sorted(layers):
        by_cat = {}
        for u in layers[d]:
            by_cat.setdefault(items[u]['cat'], []).append(u)
        for c in by_cat:
            by_cat[c].sort(key=lambda u: (-deg.get(u, 0), -gdeg.get(u, 0), rank.get(u, 0)))
        order = sorted(by_cat, key=lambda c: (-deg.get(by_cat[c][0], 0), -len(by_cat[c]), c))
        i = 0
        while len(picked) < cap:
            took = False
            for c in order:
                if i < len(by_cat[c]):
                    picked.append(by_cat[c][i])
                    took = True
                    if len(picked) >= cap:
                        break
            if not took:
                break
            i += 1
        if len(picked) >= cap:
            break
    return picked


def _secret_dir(name):
    """A folder the file browser never enters: a dot-folder or one named like a key store."""
    return name.startswith('.') or bool(SECRET_DIR_RE.search(name)) or name in ('__pycache__', 'node_modules')


def _secret_file(name):
    """A file the file browser never lists or shows: a dot-file or one that looks like key material."""
    return name.startswith('.') or bool(SECRET_FILE_RE.search(name))


def _file_kind(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in TEXT_EXT or name in META_FILES or name.upper().startswith('README'):
        return 'text'
    return 'binary' if ext in BINARY_MIME else 'other'


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
            items, by_uid, by_key = [], {}, {}
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
                    by_key[(it['cat'].lower(), it['alias_l'])] = it['uid']          # cat::alias references
                    by_key[(it['cat_uid'].lower(), it['alias_l'])] = it['uid']
            _catalog.update({'stamp': stamp, 'items': items, 'by_uid': by_uid, 'by_key': by_key, 'skipped': skipped,
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

    def _item(self, uid):
        """A catalog item this server shows, by UID (None when it is unknown or hidden)."""
        it = self._catalog()['by_uid'].get(str(uid or '').strip().lower())
        if it is None:
            return None
        return it if any(x is it for x in self._visible()) else None

    def _artifact(self, uid, local, files_on):
        """One artifact: its meta, its _desc, what it connects to and what it uses (resolved to the catalog), what
        connects to it (from the connection index), and its commands."""
        cat = self._catalog()
        it = self._item(uid)
        if it is None:
            return {'error': 'artifact %s is not in the index of this server' % uid}
        by_uid, by_key = cat['by_uid'], cat['by_key']
        shown = set(x['uid'] for x in self._visible())
        desc, desc_file, size = _read_desc(it['path'])
        desc_out = desc
        if desc is not None and size > DESC_MAX_BYTES:
            desc_out = {'_note': '%s is %d bytes; only its keys are shown' % (desc_file, size),
                        '_keys': sorted(desc.keys())}
        links = []
        for cref in _connections(desc, it['meta']):
            ref = _parse_cref(cref)
            tuid = _resolve(ref, by_uid, by_key)
            t = by_uid.get(tuid) if tuid in shown else None
            links.append({'cref': cref, 'uid': tuid if t else ref[3], 'alias': t['alias'] if t else ref[2],
                          'cat': t['cat'] if t else '', 'found': t is not None})
        uses, seen = [], set()
        for c, a, u in _uses_refs(desc):
            if u in seen:
                continue
            seen.add(u)
            t = by_uid.get(u) if u in shown else None
            uses.append({'ref': '%s: %s,%s' % (c, a, u), 'uid': u, 'alias': t['alias'] if t else a,
                         'cat': t['cat'] if t else c, 'found': t is not None})
        ai_uses = []
        for ref in _ai_uses_refs(desc):
            tuid = _resolve(ref, by_uid, by_key)
            t = by_uid.get(tuid) if tuid in shown else None
            ai_uses.append({'cref': '%s,%s::%s,%s' % ref, 'uid': tuid if t else ref[3], 'alias': t['alias'] if t else ref[2],
                            'cat': t['cat'] if t else ref[0], 'found': t is not None})
        incoming, n_in = [], 0
        if _conn['ready']:
            with _conn_lock:
                srcs, used_by, read_by = _conn['inn'].get(it['uid'], ()), _conn['uses'], _conn.get('ai', {})
                rows = [{'uid': s, 'alias': by_uid[s]['alias'], 'cat': by_uid[s]['cat'],
                         'uses': it['uid'] in used_by.get(s, ()), 'ai': it['uid'] in read_by.get(s, ())} for s in srcs if s in shown]
            rows.sort(key=lambda x: (x['cat'].lower(), x['alias'].lower()))
            n_in, incoming = len(rows), rows[:INCOMING_MAX]
        mig = it['meta'].get('migrated_to')
        mig_uid = _cref_uid(mig)[0] if mig else ''
        ref = '%s,%s' % (it['alias'], it['uid'])
        cmd_cat = it['cat'] or 'category'
        out = {'row': _row(it), 'repo_uid': it['repo_uid'], 'meta': it['meta'], 'desc': desc_out,
               'desc_file': desc_file, 'connections': links, 'uses': uses, 'ai_uses': ai_uses, 'incoming': incoming,
               'incoming_total': n_in, 'index': _conn_status(),
               'files': bool(files_on) and not SECRET_DIR_RE.search(it['cat']),
               'cref': '%s,%s::%s' % (it['cat'], it['cat_uid'], ref),
               'migrated_to_uid': mig_uid if mig_uid in shown else '',
               'commands': ['cx %s find %s' % (cmd_cat, ref),
                            'cx %s info %s' % (cmd_cat, ref),
                            'cx %s read %s' % (cmd_cat, ref),
                            'cx %s tags %s --add=<tag> --remove=<tag>' % (cmd_cat, ref),
                            'cx %s update %s --meta.<key>=<value>' % (cmd_cat, ref)]}
        if local:
            out['path'] = it['path']
        return out

    @staticmethod
    def _find_one(ref, scope):
        """The UID of the artifact a focus names - a UID, alias,UID, a cRef, or an alias (the first one in the
        scope) - or '' when the scope has no such artifact."""
        cat, cat_uid, alias, uid = _parse_cref(ref)
        if uid:
            return uid if uid in scope else ''
        a = alias.lower()
        for u, it in scope.items():
            if it['alias_l'] == a and (not (cat or cat_uid) or _name_matches(it['cat'], it['cat_uid'],
                                                                               cat_uid or cat)):
                return u
        return ''

    def _graph(self, params):
        """The graph of the query, or of everything within depth hops of a focus: the artifacts (a fair sample
        when there are more than max_nodes), their categories, the cMeta node, and the connections and uses
        between what is drawn - with the notices and the timings of every stage."""
        T, t0 = {}, time.time()
        cat = self._catalog()
        T['catalog'] = int((time.time() - t0) * 1000)

        t1 = time.time()
        th = _conn_request()
        if th is not None:                           # a build runs (the first, or after an index change or a
            th.join(INDEX_WAIT)                      # reload): wait for it - later ones re-read only edits
        T['index'] = int((time.time() - t1) * 1000)
        if not _conn['ready']:
            return {'error': 'the connections are still being read (%d of %d artifacts) - try again in a moment'
                             % (_conn['done'], _conn['total']), 'index': _conn_status()}
        with _conn_lock:
            out, uses, ai, adj = _conn['out'], _conn['uses'], _conn.get('ai', {}), _conn['adj']

        t2 = time.time()
        by_uid = cat['by_uid']
        vis = self._visible()
        ui_repos, ui_cats = _list(params.get('repos')), _list(params.get('cats'))
        scope = {it['uid']: it for it in vis
                 if (not ui_repos or any(_name_matches(it['repo'], it['repo_uid'], w) for w in ui_repos))
                 and (not ui_cats or any(_name_matches(it['cat'], it['cat_uid'], w) for w in ui_cats))}
        show_cats = _flag(params.get('categories'), True)
        show_core = show_cats and _flag(params.get('core'), False)
        show_iso = _flag(params.get('isolated'), False)
        grow = _flag(params.get('neighbors'), False)
        max_nodes = _int(params.get('max_nodes'), GRAPH_DEFAULT, 10, GRAPH_MAX)
        depth = _int(params.get('depth'), 2, 1, DEPTH_MAX)
        focus = str(params.get('focus') or '').strip()

        layer, rank, notices = {}, {}, []
        start, focus_next, grown = '', 0, 0
        if focus:
            start = self._find_one(focus, scope)
            if start:
                layer[start] = 0
                frontier = [start]
                for d in range(1, depth + 1):
                    nxt = []
                    for u in frontier:
                        for v in adj.get(u, ()):
                            if v in scope and v not in layer:
                                layer[v] = d
                                nxt.append(v)
                    frontier = nxt
                    if not nxt:
                        break
                focus_next = len({v for u in frontier for v in adj.get(u, ()) if v in scope and v not in layer})
            cand = sorted(layer, key=lambda u: layer[u])
        else:
            r = self._search(dict(params, limit=1, offset=0, facets='0'), items=vis)
            cand = [it['uid'] for it in r['_found']]
            rank = {u: i for i, u in enumerate(cand)}
            if grow and len(cand) < len(scope):
                chosen = set(cand)
                for u in list(cand):
                    for v in adj.get(u, ()):
                        if v in scope and v not in chosen:
                            chosen.add(v)
                            layer[v] = 1                   # sampled after the results themselves
                            cand.append(v)
                            grown += 1
        matched = len(cand) - grown
        T['select'] = int((time.time() - t2) * 1000)

        t3 = time.time()
        cset = set(cand)
        deg = {u: sum(1 for v in adj.get(u, ()) if v in cset) for u in cand}
        iso_hidden = 0
        if not show_cats and not show_iso:                 # nothing to hang an unconnected artifact on
            keep = [u for u in cand if deg[u] or u == start]
            iso_hidden, cand = len(cand) - len(keep), keep
        capped = 0
        if len(cand) > max_nodes:
            gdeg = {u: len(adj.get(u, ())) for u in cand}
            picked = _fair_sample(cand, by_uid, layer, deg, gdeg, rank, max_nodes)
            capped = len(cand) - len(picked)
        else:
            picked = cand

        drawn = set(picked)
        links, pairs = [], set()
        for u in picked:                                   # uses: directed, drawn once with an arrow
            for v in uses.get(u, ()):
                if v in drawn:
                    links.append({'s': u, 't': v, 'k': 'uses'})
                    pairs.add((u, v) if u < v else (v, u))
        for u in picked:                                   # ai_uses: directed too (whose memory an artifact reads)
            for v in ai.get(u, ()):
                if v in drawn:
                    links.append({'s': u, 't': v, 'k': 'ai'})
                    pairs.add((u, v) if u < v else (v, u))
        for u in picked:
            for v in out.get(u, ()):
                p = (u, v) if u < v else (v, u)
                if v in drawn and p not in pairs:
                    pairs.add(p)
                    links.append({'s': u, 't': v, 'k': 'link'})
        n_uses = sum(1 for x in links if x['k'] == 'uses')
        n_ai = sum(1 for x in links if x['k'] == 'ai')
        n_links = len(links) - n_uses - n_ai
        ddeg = Counter()
        for x in links:
            ddeg[x['s']] += 1
            ddeg[x['t']] += 1

        nodes = []
        if show_core:
            nodes.append({'id': '__cmeta__', 'kind': 'core', 'label': 'cMeta'})
        per_cat, cat_alias = Counter(), {}
        for u in picked:
            cuid = by_uid[u]['cat_uid'].lower()
            per_cat[cuid] += 1
            cat_alias[cuid] = by_uid[u]['cat']
        if show_cats:
            in_scope = Counter(it['cat_uid'].lower() for it in scope.values())
            shown = set(it['uid'] for it in vis)           # a category node opens the category artifact
            for cuid, n in per_cat.most_common():
                nodes.append({'id': '__cat__' + cuid, 'kind': 'category', 'label': cat_alias[cuid],
                              'cat': cat_alias[cuid], 'uid': cuid if cuid in shown else '',
                              'n': n, 'total': in_scope[cuid]})
                if show_core:
                    links.append({'s': '__cmeta__', 't': '__cat__' + cuid, 'k': 'core'})
        for u in picked:
            it = by_uid[u]
            n = {'id': u, 'kind': 'artifact', 'label': it['alias'], 'cat': it['cat'], 'repo': it['repo'],
                 'deg': ddeg[u]}
            if it['name'] and it['name'] != it['alias']:
                n['name'] = it['name']
            if focus and u in layer:
                n['hop'] = layer[u]
            elif u in layer:
                n['added'] = 1
            nodes.append(n)
            if show_cats:
                links.append({'s': '__cat__' + it['cat_uid'].lower(), 't': u, 'k': 'member'})
        T['graph'] = int((time.time() - t3) * 1000)

        n_drawn = len(picked)
        if focus and not start:
            notices.append('Nothing to focus on: "%s" is not an artifact this page shows (hidden, outside the '
                           'pickers, or not in the index).' % focus)
        elif start:
            notices.append('Focused on %s: %d artifact%s within %d hop%s. %s The query words are not applied '
                           'while focused; the pickers are.' %
                           (by_uid[start]['alias'], len(layer), '' if len(layer) == 1 else 's', depth,
                            '' if depth == 1 else 's',
                            ('One more hop would add %d.' % focus_next) if focus_next else
                            'Nothing further is reachable.'))
        elif not matched:
            notices.append('Nothing matches the query.')
        if capped:
            notices.append('Showing %d of %d artifacts: "nodes" is %d. The sample is spread evenly across '
                           'categories, the best connected first - raise "nodes", or narrow the query.'
                           % (n_drawn, n_drawn + capped, max_nodes))
        if iso_hidden and not n_drawn:
            notices.append('Nothing to draw: categories are off and none of the %d artifacts connects to '
                           'another one here. Tick "categories" to group them, or "isolated" to show them as '
                           'dots.' % iso_hidden)
        elif iso_hidden:
            notices.append('%d artifact%s that connect%s to nothing drawn %s hidden - tick "isolated" to show '
                           'them.' % (iso_hidden, '' if iso_hidden == 1 else 's', 's' if iso_hidden == 1 else '',
                                      'is' if iso_hidden == 1 else 'are'))
        status = _conn_status()
        if status['stale']:
            notices.append('The connections are being read again after an index change; these are as of %s.'
                           % status['built'])
        if status['error']:
            notices.append('The connections could not all be read: %s' % status['error'])
        T['server'] = int((time.time() - t0) * 1000)
        return {'nodes': nodes, 'links': links,
                'cats': [[cat_alias[c], n, c] for c, n in per_cat.most_common()],
                'stats': {'matched': matched, 'drawn': n_drawn, 'capped': capped, 'grown': grown,
                          'isolated_hidden': iso_hidden, 'links': n_links, 'uses': n_uses, 'ai_uses': n_ai,
                          'categories': len(per_cat), 'scope': len(scope)},
                'focus': ({'uid': start, 'alias': by_uid[start]['alias'], 'cat': by_uid[start]['cat'],
                           'depth': depth, 'next': focus_next} if start else None),
                'notices': notices, 'timing': T, 'index': status,
                'options': {'categories': show_cats, 'core': show_core, 'isolated': show_iso,
                            'neighbors': grow, 'max_nodes': max_nodes, 'depth': depth}}

    # ------------------------------------------------------------ the file browser
    def _files(self, uid, limit):
        """The files of an artifact folder: _cmeta and _desc first, then READMEs, the top level, the rest."""
        it = self._item(uid)
        if it is None:
            return {'error': 'artifact %s is not in the index of this server' % uid}
        if SECRET_DIR_RE.search(it['cat']):
            return {'error': 'not shown: this artifact is in a category that holds keys or secrets'}
        root = os.path.realpath(it['path'])
        if not os.path.isdir(root):
            return {'error': 'the folder of this artifact is missing'}
        limit = _int(limit, FILES_DEFAULT, 5, 2000)
        rels, more = [], False
        for dp, dns, fns in os.walk(root):
            dns[:] = sorted(d for d in dns if not _secret_dir(d))
            for fn in sorted(fns):
                if not _secret_file(fn):
                    rels.append(os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/'))
            if len(rels) >= FILES_SCAN_MAX:
                more = True
                break

        def order(rel):
            name = rel.rsplit('/', 1)[-1]
            top = '/' not in rel
            return (0 if top and name in META_FILES else 1 if name.upper().startswith('README') else
                    2 if top else 3, rel.lower())

        rels.sort(key=order)
        files = []
        for rel in rels[:limit]:
            try:
                st = os.stat(os.path.join(root, *rel.split('/')))
            except OSError:
                continue
            files.append({'rel': rel, 'size': st.st_size, 'kind': _file_kind(rel.rsplit('/', 1)[-1]),
                          'mtime': time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))})
        return {'uid': it['uid'], 'total': len(rels), 'more': more, 'limit': limit, 'files': files}

    def _file(self, uid, rel):
        """One file of an artifact folder: text inline (the first 512 KB), a PDF or an image as base64."""
        it = self._item(uid)
        if it is None:
            return {'error': 'artifact %s is not in the index of this server' % uid}
        if SECRET_DIR_RE.search(it['cat']):
            return {'error': 'not shown: this artifact is in a category that holds keys or secrets'}
        rel = str(rel or '').replace('\\', '/')
        parts = rel.split('/')
        if not rel or rel.startswith('/') or ':' in rel or any(p in ('', '.', '..') for p in parts):
            return {'error': 'rel must be a path inside the folder of the artifact'}
        if any(_secret_dir(p) for p in parts[:-1]) or _secret_file(parts[-1]):
            return {'error': 'not shown: the file looks like a key or a secret'}
        root = os.path.realpath(it['path'])
        full = os.path.realpath(os.path.join(root, *parts))
        if not os.path.normcase(full).startswith(os.path.normcase(root.rstrip('\\/') + os.sep)) \
                or not os.path.isfile(full):
            return {'error': 'no such file in this artifact'}
        size = os.path.getsize(full)
        ext = os.path.splitext(full)[1].lower()
        if ext in BINARY_MIME:
            if size > BINARY_CAP:
                return {'rel': rel, 'kind': 'other', 'size': size,
                        'note': 'over %d MB - open it on the machine itself' % (BINARY_CAP // (1024 * 1024))}
            with open(full, 'rb') as f:
                data = f.read()
            return {'rel': rel, 'kind': 'binary', 'mime': BINARY_MIME[ext], 'size': size,
                    'b64': base64.b64encode(data).decode('ascii')}
        with open(full, 'rb') as f:
            raw = f.read(TEXT_CAP + 1)
        truncated, raw = len(raw) > TEXT_CAP, raw[:TEXT_CAP]
        if b'\x00' in raw[:4096] and ext not in TEXT_EXT:
            return {'rel': rel, 'kind': 'other', 'size': size,
                    'note': 'a binary file (%s); not shown' % (ext or 'no extension')}
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        return {'rel': rel, 'kind': 'text', 'size': size, 'truncated': truncated, 'text': text}

    @staticmethod
    def _client_local(misc):
        """True when the request came straight from the server's own machine: the engine cserver says so in
        misc (the real peer address, and no proxy header - a Host header proves nothing)."""
        return bool((misc or {}).get('client_local'))

    def _files_on(self, misc, cfg):
        v = str(cfg.get('browse_files') or '').strip().lower()
        if v in ('yes', 'on', 'true', '1', 'all'):
            return True
        if v in ('no', 'off', 'false', '0', 'none'):
            return False
        return self._client_local(misc)

    # ------------------------------------------------------------ web
    def web_(self, ctx, urls, query={}, misc={}):
        """Render the page (command web) or answer ?native_action=... with JSON."""
        query = query or {}
        local = self._client_local(misc)
        na = query.get('native_action', '')
        if na:
            try:
                if na == 'search':
                    out = self._search(query)
                    out.pop('_found', None)
                elif na == 'options':
                    out = self._options()
                    _conn_request()                    # start reading the connections as the page opens
                    out['index'] = _conn_status()
                elif na == 'reload':
                    self._catalog(force=True)
                    _desc_cache.clear()
                    out = self._options()
                    _conn_request(force=True)          # re-reads only the _desc files that changed
                    out['index'] = _conn_status()
                elif na == 'index':
                    self._catalog()
                    _conn_request()
                    out = _conn_status()
                elif na == 'artifact':
                    th = _conn_request()
                    if th is not None and not _conn['ready']:
                        th.join(ARTIFACT_WAIT)         # a fresh worker process: what connects to it comes soon
                    out = self._artifact(query.get('uid'), local, self._files_on(misc, self._cserver_config()))
                elif na == 'graph':
                    out = self._graph(query)
                elif na in ('files', 'file'):
                    if not self._files_on(misc, self._cserver_config()):
                        out = {'error': 'the file browser is off here: it is for a browser on the server\'s own '
                                        'machine (browse_files in the cserver config changes that)'}
                    elif na == 'files':
                        out = self._files(query.get('uid'), query.get('limit'))
                    else:
                        out = self._file(query.get('uid'), query.get('rel'))
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
            state = {k: str(query.get(k) or '') for k in STATE_KEYS}
            config = {'api_url': urls.get('url', '?'), 'url_server': urls.get('url_server') or '/',
                      'dark_mode': bool(dark), 'version': version, 'local': local,
                      'files': self._files_on(misc, self._cserver_config()),
                      'graph': {'max_nodes': GRAPH_DEFAULT, 'max': GRAPH_MAX, 'depth_max': DEPTH_MAX},
                      'state': state}
            with open(os.path.join(path_to_files, 'index.html'), encoding='utf-8') as f:
                body = f.read()
            body = body.replace('%%CONFIG%%', _js(config)).replace('%%VERSION%%', _esc(version))
            head = (
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +   # phones: no 980px page
                '<link rel="stylesheet" href="%s">\n' % _asset(path_to_files, url_files, 'css/browse.css') +
                '<script src="%s" defer></script>\n' % _asset(path_to_files, url_files, 'js/graph.js') +
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
