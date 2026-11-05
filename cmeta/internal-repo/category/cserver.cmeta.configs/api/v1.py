"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.cmeta.configs - every key the artifacts plugged into this machine read from the config artifacts
(cx config set <name> --meta.<key>=<value>), by config artifact: what each key does, who reads it, its value here and
the command that changes it.

    cx app run cserver      ->  http://127.0.0.1:8004/cmeta.configs

Nothing is listed that no plugged artifact knows: a machine with fewer repositories shows fewer configs. A key is known
from three places of the artifacts of the scanned categories (files/configs.yaml: category, task, tool, app, program
...):

    declared   the "configs" block of an artifact's _desc.yaml - the config artifacts it reads and, for each key, what
               it does, its type, its default, an example, whether it is a secret
    code       its Python files, parsed: a call of the config category (get, read, show, set ...) and what the code
               then takes from the answer - cfg.get('key', default), cfg['a']['b'] - through variables, attributes
               of self, module globals, the functions of the file (what they return, the configs and keys they get
               as parameters) and the helper modules it imports from next to it
    docs       the lines "cx config set <name> --meta.<key>=<value>  # what it does" of its READMEs, comments, strings
               and _desc, and the Markdown tables with the columns Key and Meaning (or Description, What it does);
               the README and docs/ of every plugged repository too

They are joined with the config artifacts of this machine: the value of each key - never the value of a key that looks
like a secret (files/configs.yaml: secret_keys) -, the keys set here that no plugged artifact reads (a typo, a
leftover, a key of an artifact that is not plugged here), the config artifacts nothing reads.

The page shows it both ways: a map of the artifacts that use configs and the configs, a line from each artifact to
each config it uses (the JSON's `uses`: per artifact, per config, how many keys it reads, declares and shows, their
names and what it does with the config as a whole), a click on either side showing only that.

A "configs" block in a _desc.yaml (the artifact that reads the keys declares them):

    configs:
      cserver:                                  # the config artifact: cx config set cserver --meta.<key>=<value>
        desc: the engine's web server           # one line about it (optional)
        keys:
          browse_files:                         # a nested key is dotted: test_session.max_keep_mib
            desc: yes = the file browser for everyone; no = for no one
            type: yes/no                        # text, number, yes/no, list, dict, path, url ... (optional)
            default: a browser on the server's own machine only
            example: 'yes'
            secret: false                       # true: its value is never shown
          hide_repos: repositories left out     # a text alone is what it does

What the code, the docs and the _desc of each file say is kept by file (its time and size) in the cache artifact
cache::cserver--cmeta-configs (local repository): a new server process reads again only the files that changed, and a
request looks at the files again at most every REFRESH_AFTER seconds.

    cx cserver.cmeta.configs list ["<query>"] [--as_json]   the keys in a terminal, with the search of the page
    cx cserver.cmeta.configs artifacts ["<query>"]          the other way round: each artifact and the configs it uses
    cx cserver.cmeta.configs scan [--force]                 look at the files again (--force: read every one again)
    ?native_action=configs                                  the JSON the page renders (refresh=1: look again now)

The keys, what they do and who reads them are for everyone the server lets in; the hide_repos of the server and of the
request leave the artifacts and the config artifacts of those repositories out, and a host may name the only
repositories shown in its call (only_repos - the cPlatform's project pointer: "only_repos": "internal,ctuninglabs@
cmeta-aops" in cmeta_params_for_html shows the engine's and cMeta AOps' keys on a public site). The values set here are for a browser
on the server's own machine, or one past the server's password - configs_values in the cserver config says otherwise
(yes: everyone the server lets in; no: no one) -, never through the cPlatform.
"""

import ast
import fnmatch
import hashlib
import json
import os
import re
import sys
import threading
import time
import warnings

import yaml

from cmeta.category import InitCategory

CATEGORY_UID = 'dd9ea50e7f76467f'
CONFIG_UID = 'cc6bfe174be847ed'
CONFIG_CATEGORY = 'config,' + CONFIG_UID
REPO_UID = 'f4f792ab40c7498f'

SETTINGS_FILE = 'configs.yaml'          # under files/: what is scanned, which values are never shown
DESC_FILES = ('_desc.yaml', '_desc.json')
REFRESH_AFTER = 30                      # seconds: a request after that looks at the files again (their times only)

# The cache artifact of this page: cache::cserver--cmeta-configs in the local repository, created on first use
CACHE_CATEGORY = 'cache,1ebdcc1cc30c4022'
CACHE_ALIAS = 'cserver--cmeta-configs'
CACHE_TAGS = ['cserver.cmeta.configs', 'cc8dd8bdf9fe4132']
CACHE_NAME = 'cserver.cmeta.configs: what the code, docs and _desc of each scanned file say of the config artifacts'
CACHE_GENERATOR = {'method': 'script', 'script': 'cserver.cmeta.configs (the /cmeta.configs page of the cMeta engine)'}
CACHE_FILE = 'scan.json'
CACHE_FORMAT = 1                        # a file of another format is ignored and rewritten


def _fingerprint():
    """The scanner that wrote a cache: this file's own bytes - a scan made by another version of the code is read
    again."""
    try:
        with open(__file__, 'rb') as f:
            return '%d-%s' % (CACHE_FORMAT, hashlib.sha1(f.read()).hexdigest()[:16])
    except OSError:
        return str(CACHE_FORMAT)


SCANNER = _fingerprint()

WRITES = ('set', 'unset')

# Where an answer of the config category holds the data of the config artifact
DATA_PATHS = {('config_cmeta',), ('artifact', 'cmeta'), ('meta',), ('loaded_files', 'data.json', 'data')}

# What a description of a key is taken from first (a lower rank wins)
RANKS = {'declared': 0, 'table': 1, 'cmd': 2, 'const': 3, 'line': 4, 'above': 5}

# Modules never looked for next to an artifact (a helper module is: from _lib import graph)
SKIP_MODULES = set(getattr(sys, 'stdlib_module_names', ())) | {'cmeta', 'yaml', 'requests', 'fastapi', 'pytest'}

DEFAULTS = {
    'title': 'cMeta configs', 'subtitle': '',
    'code_categories': ['category', 'task', 'tool', 'app', 'program'],
    'code_files': ['*.py'], 'doc_files': ['*.md', '_desc.yaml', '_desc.json'],
    'max_depth': 2, 'skip_dirs': ['.git', '__pycache__', 'node_modules', '.venv', 'tests'],
    'repo_docs': ['README.md', 'docs'], 'max_file_bytes': 1000000, 'routes': {},
    'secret_keys': ['password', '*_password', '*password_sha256*', '*secret*', '*token*', '*api_key*', '*_key',
                    '*_keys', 'key', 'keys'],
    'config_descs': {},
}

# The keys of a config artifact's meta that are its identity and record, not settings (a config may keep its settings
# in its meta instead of data.json)
META_OWN = {'artifact', 'category', 'alias', 'uid', 'authors', 'author', 'copyright', 'license', 'creation_timestamp',
            'last_update_timestamp', 'generator', 'last_generator', 'tags', 'name', 'desc', 'permanent', 'priority',
            'sort', 'last_api_version', 'base_category_default_api_versions'}

# "cx config set <name> --meta.<key>=<value>  # what it does" in a text
CMD_RE = re.compile(r'''\bcx\s+config\s+(set|unset)\s+["']?([A-Za-z0-9_.@:,+-]+)["']?''')
META_RE = re.compile(r'''--meta\.([^\s=`"']+?)(,?)(?:=("[^"]*"|'[^']*'|[^\s`"']*))?(?=[\s`"')]|$)''')
ANGLE_RE = re.compile(r'<([^<>\n]{1,60})>')
BRACE_RE = re.compile(r'\{([^{}\n]{1,40})\}')
SEP_RE = re.compile(r'^\|?\s*:?-{2,}')
KEY_RE = re.compile(r'^[A-Za-z_<][\w.<>*,@-]*$')
NAME_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.@+-]*$')

# The columns of a Markdown table of keys (the header, lower case)
TABLE_COLS = {'config': ('config', 'config artifact', 'artifact'), 'key': ('key', 'keys', 'config key'),
              'desc': ('meaning', 'description', 'what it does', 'what', 'desc'), 'default': ('default',),
              'by': ('read by',)}

# What one server process knows: the scan of each file by path, the joined model, when it was built
_lock = threading.Lock()
_state = {'home': None, 'files': {}, 'model': None, 'built': 0.0, 'dirty': False, 'disk_dir': '',
          'disk_loaded': False, 'resolved': {}, 'routes': {}}


def _yes(value):
    return value in (True, 1) or str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _list(value):
    """A list from a list, or a comma-separated text ('' -> [])."""
    if value is None or value == '':
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(',') if v.strip()]


def _patterns(value):
    return [p.lower() for p in _list(value)]


def _matches_any(text, patterns):
    text = (text or '').lower()
    return any(fnmatch.fnmatchcase(text, p) for p in patterns)


def _fits(name, patterns):
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def _txt(value):
    """A value of a _desc as one line of text."""
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return ' '.join(str(value).split())


def _config_alias(text):
    """A config artifact as the code or a command names it -> its alias: "local:task" -> "task", "x,<UID>" -> "x"."""
    t = str(text or '').strip()
    if ':' in t and '::' not in t:
        t = t.split(':', 1)[1]
    alias, _, uid = t.partition(',')
    return alias.strip() or uid.strip()


def _plain_name(name):
    return bool(NAME_RE.match(name or ''))


def _placeholders(line):
    """<repository alias,UID> -> <repository_alias,UID>, {key} -> <key>: one word each, so a key ends at a space."""
    line = ANGLE_RE.sub(lambda m: '<%s>' % '_'.join(m.group(1).split()), line)
    return BRACE_RE.sub(lambda m: '<%s>' % (re.sub(r'\W+', '_', m.group(1)).strip('_') or 'x'), line)


def _clean_value(value):
    """A value of a command in a text, without its quotes and the punctuation of the sentence around it (a colon
    stays: git@github.com:)."""
    v = (value or '').strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
        v = v[1:-1]
    while v and v[-1] in ',;':
        v = v[:-1]
    while v.endswith(')') and v.count('(') < v.count(')'):
        v = v[:-1]
    return v


def _short(node, n=40):
    try:
        t = ' '.join(ast.unparse(node).split())
    except Exception:
        return 'x'
    return t if len(t) <= n else t[:n - 3] + '...'


# Names that say nothing of a part the code computes (str(cache_repo_key): the key is cache_repo_key)
PLAIN_NAMES = {'str', 'int', 'float', 'repr', 'len', 'self', 'cls', 'dict', 'list', 'tuple', 'lower', 'upper',
               'strip', 'get', 'format', 'join', 'replace', 'cmeta', 'cm', 'os', 'path'}


def _word(node):
    """A name for a part of a key or a config the code computes at run time: the key it is taken by
    (ctx.get('harness') -> harness), else the last name it is made of (str(cache_repo_key) -> cache_repo_key)."""
    key = node.args[0] if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
        node.func.attr == 'get' and node.args else (node.slice if isinstance(node, ast.Subscript) else None)
    if isinstance(key, ast.Constant) and isinstance(key.value, str) and re.match(r'^\w+$', key.value):
        return key.value
    names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id not in PLAIN_NAMES]
    if names:
        return names[-1]
    attrs = [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr not in PLAIN_NAMES]
    if attrs:
        return attrs[-1]
    texts = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return (re.sub(r'\W+', '_', texts[-1]).strip('_')[:20] if texts else '') or 'x'


def _held(sym):
    """Whether a symbol is something of a config: an answer of the config category, the data of a config artifact or
    a parameter that may hold one."""
    return bool(sym) and sym[0] in ('result', 'data', 'param')


def _jsonable(value):
    """A record of a function's reads as JSON keeps it: ('p', name) -> {'p': name}, tuples -> lists."""
    if isinstance(value, tuple) and len(value) == 2 and value[0] == 'p':
        return {'p': value[1]}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _fact(rec):
    """A read of the code -> one fact: a (action), c (config), k (dotted key), l (line), n (a note), nk (where the note
    comes from), d (the default in the code)."""
    path = [str(p) for p in rec.get('path') or ()]
    if rec.get('key') is not None:
        path.append(str(rec['key']))
    f = {'a': rec['a'], 'c': rec['cfg'], 'k': '.'.join(path), 'l': rec.get('l', 0)}
    if rec.get('n'):
        f['n'], f['nk'] = rec['n'][:300], rec.get('nk', '')
    if isinstance(rec.get('dflt'), str):
        f['d'] = rec['dflt']
    return f


# ---------------------------------------------------------------------- the code
class _Code:
    """What one Python file reads from the config artifacts, found in its syntax tree.

    A symbol is what an expression is known to hold: ('result', config, path) an answer of the config category,
    ('data', config, path) the data of a config artifact (path: the keys taken so far), ('param', name, path) a
    parameter of the function being read, ('str', text) a text. A config is its alias, or ('p', name) when a parameter
    names it. The functions of the file are summed up first (ROUNDS times: helpers of helpers): what they return and
    what they read of their parameters; the facts are then collected in one more pass, the summaries applied at each
    call. Calls of functions imported from another module are kept (calls) and resolved once every file is known."""

    ROUNDS = 2

    def __init__(self, text, routes=None):
        # a text with a bad escape ("\!" in a Windows path) makes Python warn when it is parsed (SyntaxWarning): the
        # warning is the file's author's, not the page's - nothing of it reaches the server's output
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.tree = ast.parse(text)
        self.lines = text.splitlines()
        # the dotted paths that carry the keys of a config (global.init -> task): path -> config
        self.routes = {tuple(k.split('.')): v for k, v in (routes or {}).items()}
        self.consts, self.notes = {}, {}        # module and class constants (texts) and the comment of their line
        self.tuples = {}                        # module and class constants that are lists or tuples (loops over keys)
        self.fns, self.summ = [], {}            # every function of the file; their summaries by name
        self.globals, self.attrs = {}, {}       # module variables and attributes of self that hold a config
        self.mods = {}                          # a name of the file -> the module (and name) it was imported as
        self.facts, self.calls = [], []
        self.emit, self.cur, self.stmt = False, None, None
        self.globs, self.locals = set(), set()

    def run(self):
        self._collect()
        for rnd in range(self.ROUNDS + 1):
            self.emit = rnd == self.ROUNDS
            for fn in self.fns:
                self._function(fn)
        self.cur, self.globs, self.locals = None, set(), set()
        self._block(self.tree.body, {})
        return self

    def exports(self):
        """The functions another file may call: those that read a config named or keyed by their parameters."""
        out = {}
        for name, s in self.summ.items():
            reads, seen = [], set()
            for r in s['reads']:
                j = _jsonable(r) if r.get('on') is None else None
                key = json.dumps(j, sort_keys=True) if j else ''
                if j and key not in seen:       # a loop over keys reads the same thing once per key
                    seen.add(key)
                    reads.append(j)
            if reads:
                out[name] = {'params': s['params'], 'reads': reads}
        return out

    # ------------------------------------------------------------ the file
    def _collect(self):
        bodies = [self.tree.body] + [n.body for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        for body in bodies:
            for st in body:
                if not (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)):
                    continue
                if isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                    self.consts[st.targets[0].id] = st.value.value
                    note = self._trailing(st)
                    if note:
                        self.notes[st.targets[0].id] = note
                elif isinstance(st.value, (ast.Tuple, ast.List)):
                    self.tuples[st.targets[0].id] = st.value       # KEYS = ('title', 'subtitle'): for k in KEYS
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.fns.append(n)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    self.mods[a.asname or a.name.split('.')[0]] = a.name.split('.') if a.asname else [a.name.split('.')[0]]
            elif isinstance(n, ast.ImportFrom):
                base = n.module.split('.') if n.module else []
                for a in n.names:
                    if a.name != '*':
                        self.mods[a.asname or a.name] = base + [a.name]

    def _trailing(self, node):
        """The comment at the end of the line a node ends on ('' when a text stands between them)."""
        try:
            line = self.lines[node.end_lineno - 1].encode('utf-8')
        except (IndexError, TypeError, AttributeError):
            return ''
        rest = line[node.end_col_offset:].decode('utf-8', 'replace')
        j = rest.find('#')
        if j < 0 or '"' in rest[:j] or "'" in rest[:j]:
            return ''
        return rest[j + 1:].strip()

    def _above(self, lineno):
        """The comment lines right above a line (three at most)."""
        out, i = [], lineno - 2
        while i >= 0 and len(out) < 3:
            s = self.lines[i].strip() if i < len(self.lines) else ''
            if not s.startswith('#'):
                break
            out.insert(0, s.lstrip('#').strip())
            i -= 1
        return ' '.join(x for x in out if x)

    def _note(self, knode, node):
        """What the code says of a key it reads -> (text, where from): the comment of the constant that names it, the
        comment at the end of its line, the comments above its statement."""
        if isinstance(knode, ast.Name) and knode.id in self.notes:
            return self.notes[knode.id], 'const'
        t = self._trailing(node)
        if t:
            return t, 'line'
        a = self._above(self.stmt.lineno) if self.stmt is not None else ''
        return (a, 'above') if a else ('', '')

    # ------------------------------------------------------------ functions and statements
    def _function(self, fn):
        a = fn.args
        params = [x.arg for x in a.posonlyargs + a.args]
        names = params + [x.arg for x in a.kwonlyargs]
        summ = {'params': params, 'reads': [], 'ret': None}
        saved = (self.cur, self.globs, self.locals, self.stmt)
        self.cur = summ
        self.globs = {n for s in ast.walk(fn) if isinstance(s, ast.Global) for n in s.names}
        self.locals = ({n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)} |
                       set(names)) - self.globs
        self._block(fn.body, {n: ('param', n, ()) for n in names})
        self.cur, self.globs, self.locals, self.stmt = saved
        self.summ[fn.name] = summ

    def _block(self, stmts, env):
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            self.stmt = st
            if isinstance(st, ast.Assign):
                sym = self._ev(st.value, env)
                for t in st.targets:
                    self._bind(t, sym, env)
            elif isinstance(st, ast.AnnAssign):
                self._bind(st.target, self._ev(st.value, env) if st.value is not None else None, env)
            elif isinstance(st, ast.Return):
                sym = self._ev(st.value, env) if st.value is not None else None
                if self.cur is not None and _held(sym):
                    self.cur['ret'] = sym
            elif isinstance(st, (ast.For, ast.AsyncFor)):
                items = self._literal_items(st.iter, env)
                if items is None:
                    self._ev(st.iter, env)
                    self._bind(st.target, None, env)
                    self._block(st.body, env)
                else:
                    for item in items:                  # for key in ('title', 'subtitle'): once per key
                        self._bind_item(st.target, item, env)
                        self._block(st.body, env)
                self._block(st.orelse, env)
            elif isinstance(st, (ast.If, ast.While)):
                self._ev(st.test, env)
                self._block(st.body, env)
                self._block(st.orelse, env)
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                for it in st.items:
                    sym = self._ev(it.context_expr, env)
                    if it.optional_vars is not None:
                        self._bind(it.optional_vars, sym, env)
                self._block(st.body, env)
            elif isinstance(st, ast.Try) or type(st).__name__ == 'TryStar':
                self._block(st.body, env)
                for h in st.handlers:
                    self._block(h.body, env)
                self._block(st.orelse, env)
                self._block(st.finalbody, env)
            else:
                for child in ast.iter_child_nodes(st):
                    if isinstance(child, ast.expr):
                        self._ev(child, env)
                    elif isinstance(child, ast.stmt):
                        self._block([child], env)

    def _literal_items(self, node, env):
        """What a loop runs over when the code spells it out: a list or tuple of texts, or of tuples of them (also a
        constant of the file holding one) -> [a symbol, or a list of symbols for a tuple], None otherwise."""
        if isinstance(node, ast.Name) and node.id not in env and node.id not in self.locals:
            node = self.tuples.get(node.id, node)
        if not isinstance(node, (ast.Tuple, ast.List, ast.Set)) or not 0 < len(node.elts) <= 50:
            return None
        out = []
        for e in node.elts:
            if isinstance(e, (ast.Tuple, ast.List)):
                out.append([self._ev(x, env) for x in e.elts])
            else:
                s = self._ev(e, env)
                if not (s and s[0] == 'str'):
                    return None
                out.append(s)
        return out

    def _bind_item(self, target, item, env):
        """The variable(s) of a loop bound to one item (a symbol is a tuple itself: a tuple of the loop is a list)."""
        if isinstance(item, list):
            if isinstance(target, (ast.Tuple, ast.List)) and len(item) == len(target.elts):
                for t, s in zip(target.elts, item):
                    self._bind(t, s, env)
            else:
                self._bind(target, None, env)
        else:
            self._bind(target, item, env)

    def _comprehension(self, node, env):
        """A comprehension over a list the code spells out: its expression read once per item (one generator)."""
        gens = node.generators
        items = self._literal_items(gens[0].iter, env) if len(gens) == 1 else None
        if items is None:
            return False
        for item in items:
            inner = dict(env)
            self._bind_item(gens[0].target, item, inner)
            for c in gens[0].ifs:
                self._ev(c, inner)
            for part in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
                self._ev(part, inner)
        return True

    def _bind(self, target, sym, env):
        if isinstance(target, ast.Name):
            if sym is None:
                env.pop(target.id, None)
            else:
                env[target.id] = sym
            if target.id in self.globs and sym and sym[0] in ('result', 'data') and isinstance(sym[1], str):
                self.globals[target.id] = sym
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and \
                target.value.id in ('self', 'cls'):
            if sym and sym[0] in ('result', 'data') and isinstance(sym[1], str):
                self.attrs[target.attr] = sym
        elif isinstance(target, (ast.Tuple, ast.List)):
            for t in target.elts:
                self._bind(t, None, env)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, None, env)

    # ------------------------------------------------------------ expressions
    def _ev(self, node, env):
        """What an expression holds (a symbol or None); the reads inside it are recorded on the way."""
        if node is None:
            return None
        t = type(node)
        if t is ast.Constant:
            return ('str', node.value) if isinstance(node.value, str) else None
        if t is ast.Name:
            if node.id in env:
                return env[node.id]
            if node.id in self.locals:
                return None
            if node.id in self.globals:
                return self.globals[node.id]
            if node.id in self.consts:
                return ('str', self.consts[node.id])
            return None
        if t is ast.Attribute:
            if isinstance(node.value, ast.Name) and node.value.id in ('self', 'cls'):
                return self.attrs.get(node.attr)
            self._ev(node.value, env)
            return None
        if t is ast.Await:
            return self._ev(node.value, env)
        if t is ast.BoolOp:
            syms = [self._ev(v, env) for v in node.values]
            return next((s for s in syms if _held(s)), None)
        if t is ast.IfExp:
            self._ev(node.test, env)
            a, b = self._ev(node.body, env), self._ev(node.orelse, env)
            return a if _held(a) else (b if _held(b) else None)
        if t in (ast.JoinedStr, ast.BinOp):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self._ev(child, env)
            p = self._pattern(node, env)
            return ('str', p) if p is not None else None
        if t is ast.Subscript:
            if isinstance(node.slice, ast.Constant) and node.slice.value == 'config' and \
                    'uses_categories' in _short(node.value, 80):
                return ('str', CONFIG_CATEGORY)         # self.cmeta['uses_categories']['config'], kept in a variable
            base = self._ev(node.value, env)
            if isinstance(node.slice, ast.Slice):
                return None
            return self._take(base, node.slice, None, node, env)
        if t is ast.Call:
            return self._call(node, env)
        if t is ast.Lambda:
            return None
        if t in (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp) and self._comprehension(node, env):
            return None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._ev(child, env)
            elif isinstance(child, ast.comprehension):
                self._ev(child.iter, env)
                for c in child.ifs:
                    self._ev(c, env)
            elif isinstance(child, ast.keyword):
                self._ev(child.value, env)
        return None

    def _pattern(self, node, env, depth=0):
        """A text built by the code, as a pattern: f'{category_alias}_create_cmd' -> '<category_alias>_create_cmd'
        (None for an expression that builds no text)."""
        if depth > 12:
            return None
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.Name):
            s = env.get(node.id) or (('str', self.consts[node.id]) if node.id in self.consts else None)
            return s[1] if s and s[0] == 'str' else '<%s>' % node.id
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                elif isinstance(v, ast.FormattedValue):
                    p = self._pattern(v.value, env, depth + 1)
                    parts.append(p if p is not None else '<%s>' % _word(v.value))
            return ''.join(parts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            if not (self._texty(node.left, env) or self._texty(node.right, env)):
                return None                     # a sum of numbers, not a text
            a, b = self._pattern(node.left, env, depth + 1), self._pattern(node.right, env, depth + 1)
            return a + b if a is not None and b is not None else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and \
                isinstance(node.left.value, str):
            return re.sub(r'%[-0-9.]*[sdrif]', '<x>', node.left.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr in ('replace', 'lower', 'upper', 'strip', 'lstrip', 'rstrip'):
            return self._pattern(node.func.value, env, depth + 1)
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
            return '<%s>' % _word(node)
        return None

    def _texty(self, node, env):
        """Whether an expression is surely a text: a string, an f-string, a name that holds one, a sum with one."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str)
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.Name):
            s = env.get(node.id)
            return (s is not None and s[0] == 'str') or (s is None and node.id in self.consts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._texty(node.left, env) or self._texty(node.right, env)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr in ('replace', 'lower', 'upper', 'strip', 'lstrip', 'rstrip'):
            return self._texty(node.func.value, env)
        return False

    def _key(self, node, env):
        """A key the code takes: its text, ('p', name) when a parameter names it, or a pattern."""
        s = self._ev(node, env)
        if s and s[0] == 'str':
            return s[1]
        if s and s[0] == 'param' and not s[2]:
            return ('p', s[1])
        p = self._pattern(node, env)
        return p if p else '<%s>' % _word(node)

    def _default(self, node, env):
        if node is None:
            return None
        if isinstance(node, ast.Name):
            s = env.get(node.id)
            if s and s[0] == 'param' and not s[2]:
                return ('p', node.id)
            if s and s[0] == 'str':
                return repr(s[1])                      # a loop variable over defaults: (('harness', 'codex'), ...)
            if node.id in self.consts:
                return repr(self.consts[node.id])
        t = _short(node, 80)
        return t

    def _call(self, node, env):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ('access', 'access_sync') and node.args:
            a = node.args[0]
            items = None
            if isinstance(a, ast.Dict):
                items = list(zip(a.keys, a.values))
            elif isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == 'dict' and not a.args:
                items = [(ast.Constant(k.arg), k.value) for k in a.keywords if k.arg]     # dict(category=..., ...)
            if items is not None:
                r = self._access(items, env, node)
                if r is not None:
                    return r
        if isinstance(f, ast.Attribute):
            m = f.attr
            if m == '_uses' and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'config':
                return ('str', CONFIG_CATEGORY)         # self._uses('config', 'config,<UID>')
            base = self._ev(f.value, env)
            if m in ('get', 'setdefault', 'pop') and node.args and \
                    (_held(base) or (self.routes and (base is None or base[0] == 'route'))):
                for a in node.args[1:]:
                    self._ev(a, env)
                return self._take(base, node.args[0], node.args[1] if len(node.args) > 1 else None, node, env)
            if _held(base):
                if m in ('items', 'keys', 'values'):
                    self._every(base, node)
                    return None
                if m == 'copy':
                    return base
            if m == 'update' and node.args:
                arg = self._ev(node.args[0], env)
                if _held(arg):
                    self._every(arg, node)
                return None
            if m in ('deepcopy', 'copy') and isinstance(f.value, ast.Name) and len(node.args) == 1:
                return self._ev(node.args[0], env)
            if isinstance(f.value, ast.Name) and f.value.id in ('self', 'cls') and m in self.summ:
                s = self.summ[m]
                return self._apply(s, node, env, 1 if s['params'][:1] in (['self'], ['cls']) else 0)
            if isinstance(f.value, ast.Name) and f.value.id in self.mods and f.value.id not in env:
                self._call_out(self.mods[f.value.id], m, node, env)
        elif isinstance(f, ast.Name):
            if f.id == 'dict' and len(node.args) == 1 and not node.keywords:
                return self._ev(node.args[0], env)
            if f.id in self.summ and f.id not in env:
                return self._apply(self.summ[f.id], node, env, 0)
            if f.id in self.mods and f.id not in env:
                parts = self.mods[f.id]
                self._call_out(parts[:-1], parts[-1], node, env)
        else:
            self._ev(f, env)
        for a in node.args:
            self._ev(a.value if isinstance(a, ast.Starred) else a, env)
        for k in node.keywords:
            self._ev(k.value, env)
        return None

    def _is_config(self, node, env):
        """Whether the category of an access is the config category ('config', 'config,<UID>', a constant naming
        it, self.cmeta['uses_categories']['config'], self._uses('config', ...))."""
        s = self._ev(node, env)
        if s and s[0] == 'str':
            alias, _, uid = s[1].partition(',')
            return alias.strip().lower() in ('config', CONFIG_UID) or uid.strip().lower() == CONFIG_UID
        t = _short(node, 200)
        return "['config']" in t or "_uses('config'" in t or '_uses("config"' in t or CONFIG_UID in t

    def _config_name(self, node, env):
        if node is None:
            return None
        s = self._ev(node, env)
        if s and s[0] == 'str':
            return _config_alias(s[1]) or None
        if s and s[0] == 'param' and not s[2]:
            return ('p', s[1])
        # self.cmeta['uses_artifacts']['config::ctuning_server']: the meta of the category names it
        if isinstance(node, ast.Subscript):
            k = self._ev(node.slice, env)
            if k and k[0] == 'str' and '::' in k[1]:
                return _config_alias(k[1].split('::', 1)[1]) or None
        t = _short(node, 60)
        if 'default_config_name' in t:
            return 'default'
        p = self._pattern(node, env)
        return p if p and '<' in p else '<%s>' % _word(node)

    def _access(self, items, env, node):
        """A call of the config category (its dict as (key, value) nodes): what it names and does -> the symbol of its
        answer (None: another category)."""
        vals = {}
        for k, v in items:
            ks = self._ev(k, env) if k is not None else None
            if ks and ks[0] == 'str':
                vals[ks[1]] = v
        if 'category' not in vals or not self._is_config(vals['category'], env):
            return None
        cs = self._ev(vals.get('command'), env)
        command = cs[1] if cs and cs[0] == 'str' else ''
        name = self._config_name(vals.get('arg1'), env)
        for k, v in vals.items():
            if k not in ('category', 'command', 'arg1', 'meta'):
                self._ev(v, env)
        if name is None:
            return None
        if command in WRITES:
            meta = vals.get('meta')
            keys = list(_dict_keys(meta)) if isinstance(meta, ast.Dict) else []
            for key in keys or ['']:
                self._record({'a': 'write', 'cfg': name, 'path': (), 'key': key or None, 'l': node.lineno})
        else:
            self._record({'a': 'uses', 'cfg': name, 'path': (), 'key': None, 'l': node.lineno})
        return ('result', name, ())

    def _route(self, base, key):
        """A key taken on the way along a route (ctx['tasks'].get('global').get('init')): the data of its config at the
        end of the route, ('route', path) on the way, None off it."""
        if not self.routes or not isinstance(key, str):
            return None
        if base is None or base[0] == 'route':
            path = (base[1] if base else ()) + (key,)
        elif base[0] == 'param':
            path = tuple(base[2]) + (key,)
        else:
            return None
        for rp, config in self.routes.items():
            if path[-len(rp):] == rp:
                return ('data', config, ())
        if base is None or base[0] == 'route':
            if any(rp[:len(path)] == path for rp in self.routes):
                return ('route', path)
        return None

    def _take(self, base, knode, dnode, node, env):
        """A key taken from what an expression holds (x[key], x.get(key, default)) -> what it holds then."""
        key = self._key(knode, env)
        if not _held(base):
            return self._route(base if base and base[0] == 'route' else None, key)
        if base[0] == 'param':
            routed = self._route(base, key)
            if routed:
                return routed
        if base[0] == 'result':
            if not isinstance(key, str):
                return None
            path = base[2] + (key,)
            if path in DATA_PATHS:
                return ('data', base[1], ())
            return ('result', base[1], path) if len(path) < 3 else None
        note, nk = self._note(knode, node)
        rec = {'a': 'read', 'path': base[2], 'key': key, 'dflt': self._default(dnode, env), 'l': node.lineno,
               'n': note, 'nk': nk}
        if base[0] == 'data':
            rec['cfg'] = base[1]
        else:
            rec['on'] = base[1]
        self._record(rec)
        return (base[0], base[1], base[2] + (key if isinstance(key, str) else '<%s>' % key[1],))

    def _every(self, base, node):
        """Every key of a config (or of a part of it) taken: cfg.items(), result.update(cfg)."""
        if base[0] == 'result':
            return
        rec = {'a': 'every', 'path': base[2], 'key': None, 'l': node.lineno}
        if base[0] == 'data':
            rec['cfg'] = base[1]
        else:
            rec['on'] = base[1]
        self._record(rec)

    def _record(self, rec):
        """A read known whole is a fact (in the last pass); one that depends on a parameter of the function goes into
        its summary, to be completed at each call."""
        cfg, key = rec.get('cfg'), rec.get('key')
        if rec.get('on') is None and isinstance(cfg, str) and not isinstance(key, tuple):
            if self.emit:
                self.facts.append(_fact(rec))
        elif self.cur is not None:
            self.cur['reads'].append(rec)

    def _apply(self, summ, node, env, offset):
        """A call of a function of this file: its summary completed with the arguments of the call -> what it
        returns."""
        params = summ['params'][offset:]
        args = {}
        for i, a in enumerate(node.args):
            if isinstance(a, ast.Starred):
                break
            if i < len(params):
                args[params[i]] = a
        for k in node.keywords:
            if k.arg:
                args[k.arg] = k.value
        syms = {n: self._ev(a, env) for n, a in args.items()}
        for a in node.args[len(params):]:
            self._ev(a.value if isinstance(a, ast.Starred) else a, env)

        for rec in summ['reads']:
            r = dict(rec, l=node.lineno)
            if rec.get('on') is not None:
                s = syms.get(rec['on'])
                if not s or s[0] not in ('data', 'param'):
                    continue
                del r['on']
                if s[0] == 'data':
                    r['cfg'] = s[1]
                else:
                    r['on'] = s[1]
                r['path'] = tuple(s[2]) + tuple(rec['path'])
            elif isinstance(rec.get('cfg'), tuple):
                s = syms.get(rec['cfg'][1])
                if s and s[0] == 'str':
                    r['cfg'] = _config_alias(s[1])
                elif s and s[0] == 'param' and not s[2]:
                    r['cfg'] = ('p', s[1])
                else:
                    r['cfg'] = '<%s>' % rec['cfg'][1]
            if isinstance(rec.get('key'), tuple):
                s = syms.get(rec['key'][1])
                if s and s[0] == 'str':
                    r['key'] = s[1]
                elif s and s[0] == 'param' and not s[2]:
                    r['key'] = ('p', s[1])
                else:
                    r['key'] = '<%s>' % rec['key'][1]
                # the key comes from this call: what is said here of it, not what the helper says of itself
                knode = args.get(rec['key'][1])
                note, nk = self._note(knode, node)
                r['n'], r['nk'] = note, nk
            if isinstance(rec.get('dflt'), tuple):
                a = args.get(rec['dflt'][1])
                r['dflt'] = self._default(a, env) if a is not None else None
            self._record(r)

        ret = summ.get('ret')
        if not _held(ret):
            return None
        if ret[0] == 'param':
            s = syms.get(ret[1])
            return (s[0], s[1], tuple(s[2]) + tuple(ret[2])) if _held(s) else None
        if isinstance(ret[1], tuple):
            s = syms.get(ret[1][1])
            if s and s[0] == 'str':
                return (ret[0], _config_alias(s[1]), ret[2])
            return None
        return ret

    def _call_out(self, module, name, node, env):
        """A call of a function imported from another module, kept with its arguments (texts and the configs they
        hold) to be completed when every file is known."""
        if not self.emit or not module or module[0] in SKIP_MODULES:
            return
        args = [self._spec(a, env) for a in node.args if not isinstance(a, ast.Starred)]
        kw = {k.arg: self._spec(k.value, env) for k in node.keywords if k.arg}
        if not any(a and a.get('s') is not None for a in args + list(kw.values())):
            return
        note, nk = self._note(None, node)
        call = {'m': module, 'f': name, 'args': args, 'l': node.lineno}
        if kw:
            call['kw'] = kw
        if note:
            call['n'], call['nk'] = note[:300], nk
        self.calls.append(call)

    def _spec(self, node, env):
        s = self._ev(node, env)
        out = {'t': _short(node, 80)}
        if s and s[0] == 'str':
            out['s'] = s[1]
        return out


def _dict_keys(node, prefix=''):
    """The dotted keys of a dict literal (meta={'a': {'b': 1}} -> a.b)."""
    for k, v in zip(node.keys, node.values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            continue
        key = prefix + k.value
        if isinstance(v, ast.Dict) and v.keys:
            yield from _dict_keys(v, key + '.')
        else:
            yield key


# ---------------------------------------------------------------------- the docs
def _doc_lines(text):
    """The "cx config set <name> --meta.<key>=<value>" commands of a text -> facts (a: doc): the config, the key, the
    value as an example, the comment after "#" on that line as what the key does."""
    out = []
    if 'config' not in text:
        return out
    for i, line in enumerate(text.splitlines(), 1):
        if '--meta.' not in line or 'config' not in line:
            continue
        line = _placeholders(line)
        for m in CMD_RE.finditer(line):
            name = _config_alias(m.group(2))
            if not _plain_name(name):
                continue
            rest = line[m.end():]
            stop = len(rest)
            for mark in ('`', ' #', '\t#', ' |', '&&', ' >', ' 2>', '\\n'):
                j = rest.find(mark)
                if j >= 0:
                    stop = min(stop, j)
            args, after = rest[:stop], rest[stop:]
            j = after.find('#')
            note = after[j + 1:].strip().strip('`').strip() if j >= 0 else ''
            for km in META_RE.finditer(args):
                key, listy, value = km.group(1).strip('.'), km.group(2), km.group(3)
                if key.endswith('-') and value is None:
                    key, value = key[:-1], 'false'
                elif value is None:
                    value = '' if m.group(1) == 'unset' else 'true'
                if not key or key.startswith('<') or not KEY_RE.match(key):
                    continue
                f = {'a': 'doc', 'c': name, 'k': key, 'l': i, 'cmd': m.group(1), 'ctx': line.strip()[:240]}
                if m.group(1) == 'set':
                    f['x'] = _clean_value(value)
                if listy:
                    f['list'] = 1
                if note and m.group(1) == 'set':        # after an unset, the comment is of the removal ("off again")
                    f['n'], f['nk'] = note[:300], 'cmd'
                out.append(f)
    return out


def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def _md_plain(text):
    return re.sub(r'[`*]', '', text or '').strip()


def _doc_tables(text, cmd_facts):
    """The Markdown tables of keys: a header with a column Key and one Meaning (Description, What it does); the config
    from a column Config (or Artifact), else the config of the last "cx config set" line in the 60 lines above."""
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:
        if not (lines[i].lstrip().startswith('|') and SEP_RE.match(lines[i + 1].strip())):
            i += 1
            continue
        cols = [_md_plain(c).lower() for c in _cells(lines[i])]
        col = {k: next((n for n, c in enumerate(cols) if c in names), None) for k, names in TABLE_COLS.items()}
        j = i + 2
        if col['key'] is None or col['desc'] is None:
            i = j
            continue
        before = [f['c'] for f in cmd_facts if i + 1 - 60 <= f['l'] <= i + 1]
        context = before[-1] if before else ''
        while j < len(lines) and lines[j].lstrip().startswith('|'):
            cells = _cells(lines[j])

            def cell(what):
                n = col[what]
                return cells[n] if n is not None and n < len(cells) else ''

            if col['config'] is not None:
                names = re.findall(r'`([^`]+)`', cell('config'))
                name = _config_alias(names[0] if names else _md_plain(cell('config')))
            else:
                name = context
            keys = [k.strip() for k in re.findall(r'`([^`]+)`', cell('key'))] or [_md_plain(cell('key'))]
            dflts = [d.strip().strip('`') for d in cell('default').split(',')] if cell('default') else []
            desc = ' '.join(cell('desc').split())
            for n, k in enumerate(keys):
                if not (name and _plain_name(name) and KEY_RE.match(k)):
                    continue
                f = {'a': 'doc', 'c': name, 'k': k, 'l': j + 1, 'n': desc[:400], 'nk': 'table'}
                d = dflts[n] if len(dflts) == len(keys) else (dflts[0] if len(keys) == 1 and dflts else '')
                if d and d not in ('-', '—', '–'):
                    f['d'] = d
                if cell('by'):
                    f['by'] = ' '.join(cell('by').split())[:160]
                out.append(f)
            j += 1
        i = j
    return out


def _declared(data, text):
    """The "configs" block of a _desc -> facts (a: declare): each config with what it is, its keys with what they do,
    their type, default, example and whether they are secret."""
    block = data.get('configs') if isinstance(data, dict) else None
    if isinstance(block, list):
        items = [(x.get('name') or x.get('config'), x) for x in block if isinstance(x, dict)]
    elif isinstance(block, dict):
        items = list(block.items())
    else:
        return []

    lines = text.splitlines()
    start = next((n for n, line in enumerate(lines) if re.match(r'^\s*["\']?configs["\']?\s*:', line)), 0)

    def line_of(word, after):
        pat = re.compile(r'^\s*(?:-\s*)?(?:name:\s*)?["\']?%s["\']?(?:\s*:|\s*$)' % re.escape(str(word)))
        return next((n + 1 for n in range(max(0, after), len(lines)) if pat.match(lines[n])), after + 1)

    out = []
    for name, spec in items:
        name = _config_alias(str(name or ''))
        if not name:
            continue
        if isinstance(spec, str):
            spec = {'desc': spec}
        if not isinstance(spec, dict):
            continue
        at = line_of(name, start)
        f = {'a': 'declare', 'c': name, 'k': '', 'l': at}
        if spec.get('desc'):
            f['n'], f['nk'] = _txt(spec['desc'])[:400], 'declared'
        out.append(f)
        keys = spec.get('keys') or {}
        if isinstance(keys, list):
            keys = {(k.get('key') if isinstance(k, dict) else k): k for k in keys}
        if not isinstance(keys, dict):
            continue
        for key, ks in keys.items():
            if not key:
                continue
            ks = {'desc': ks} if isinstance(ks, str) else (ks if isinstance(ks, dict) else {})
            f = {'a': 'declare', 'c': name, 'k': str(key), 'l': line_of(key, at)}
            if ks.get('desc'):
                f['n'], f['nk'] = _txt(ks['desc'])[:600], 'declared'
            for src, dst in (('type', 't'), ('default', 'd'), ('example', 'x')):
                if ks.get(src) not in (None, ''):
                    f[dst] = _txt(ks[src])
            if _yes(ks.get('secret')):
                f['s'] = 1
            out.append(f)
    return out


def _template_reads(text, routes):
    """The keys a template takes along a route ({{global.init.<key>}} in a _desc) -> facts (a: read)."""
    out = []
    for route, config in (routes or {}).items():
        if '{{' not in text or route not in text:
            continue
        rx = re.compile(r'\{\{\s*' + re.escape(route) + r'\.([A-Za-z_][\w.-]*)')
        for i, line in enumerate(text.splitlines(), 1):
            for m in rx.finditer(line):
                out.append({'a': 'read', 'c': config, 'k': m.group(1).rstrip('.'), 'l': i})
    return out


def _scan_text(text, kind, stats, routes=None):
    """What one file says of the config artifacts -> {'facts', 'exports', 'calls', 'error'}."""
    if kind == 'py':
        res = {'facts': _doc_lines(text)}
        if 'config' not in text.lower() and not any("'%s'" % r.split('.')[0] in text for r in routes or {}):
            return res
        stats['parsed'] += 1
        try:
            code = _Code(text, routes).run()
        except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
            stats['errors'] += 1
            res['error'] = '%s: %s' % (type(e).__name__, str(e)[:200])
            return res
        seen = set()
        for f in code.facts:                   # an expression read twice on the way gives the same fact twice
            k = (f['a'], f['c'], f['k'], f['l'])
            if k not in seen:
                seen.add(k)
                res['facts'].append(f)
        ex = code.exports()
        if ex:
            res['exports'] = ex
        if code.calls:
            res['calls'] = code.calls
        return res

    if kind == 'desc':
        res = {'facts': _doc_lines(text) + _template_reads(text, routes)}
        try:
            data = json.loads(text) if text.lstrip().startswith('{') else \
                yaml.load(text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
        except Exception as e:
            res['error'] = '%s: %s' % (type(e).__name__, str(e)[:200])
            return res
        res['facts'] += _declared(data, text)
        return res

    cmd = _doc_lines(text)
    return {'facts': cmd + _doc_tables(text, cmd)}


def _walk(root, settings, max_depth=None):
    """The files of a folder that are scanned -> [(path, relative path, kind, [mtime_ns, size])]."""
    out = []
    code, docs = settings['code_files'], settings['doc_files']
    skip = set(settings['skip_dirs'])
    deepest = settings['max_depth'] if max_depth is None else max_depth
    limit = settings['max_file_bytes']
    stack = [(root, '', 0)]
    while stack:
        folder, rel, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if depth < deepest and e.name not in skip and not e.name.startswith('.'):
                        stack.append((e.path, rel + e.name + '/', depth + 1))
                    continue
                name = e.name
                kind = 'desc' if name in DESC_FILES else \
                    ('py' if _fits(name, code) else ('md' if _fits(name, docs) else ''))
                if not kind:
                    continue
                st = e.stat()
                if st.st_size <= limit:
                    out.append((e.path, rel + name, kind, [st.st_mtime_ns, st.st_size]))
            except OSError:
                continue
    return out


def _resolve(call, summ):
    """A call of a function of another module, completed with that function's summary -> facts."""
    params = summ.get('params') or []
    if params[:1] in (['self'], ['cls']):
        params = params[1:]
    args = dict(zip(params, call.get('args') or []))
    args.update(call.get('kw') or {})
    out = []
    for rec in summ.get('reads') or []:
        r = dict(rec, l=call['l'])
        for what in ('cfg', 'key'):
            v = rec.get(what)
            if isinstance(v, dict):
                a = args.get(v.get('p')) or {}
                r[what] = a['s'] if a.get('s') is not None else '<%s>' % v.get('p')
        if isinstance(r.get('cfg'), str):
            r['cfg'] = _config_alias(r['cfg'])
        d = rec.get('dflt')
        if isinstance(d, dict):
            a = args.get(d.get('p'))
            r['dflt'] = a.get('t') if a else None
        if isinstance(rec.get('key'), dict):
            r['n'], r['nk'] = call.get('n', ''), call.get('nk', '')
        if isinstance(r.get('cfg'), str) and not isinstance(r.get('key'), dict):
            out.append(_fact(r))
    return out


def _pattern_re(key):
    """A key with parts the code names at run time as a regular expression of the keys it stands for: <x> one part
    of a dotted key, * anything (test_session.prices.*: every key under it)."""
    out = []
    for part in re.split(r'(<[^<>]*>|\*)', key):
        if not part:
            continue
        out.append(r'.+' if part == '*' else (r'[^.]+' if part.startswith('<') else re.escape(part)))
    return re.compile('^' + ''.join(out) + '$')


def _merge_key(dst, src):
    """One key of a config joined into another (two names the code and the docs give the same key)."""
    dst['sources'] |= src['sources']
    for what in ('readers', 'docs', 'declared'):
        for aid, refs in src[what].items():
            dst[what].setdefault(aid, []).extend(refs)
    for what in ('descs', 'types', 'examples'):
        dst[what] += src[what]
    dst['defaults'] += [d for d in src['defaults'] if d not in dst['defaults']]
    dst['secret'] = dst['secret'] or src['secret']
    dst['list'] = dst['list'] or src['list']


def _flatten(data, prefix=''):
    """The data of a config artifact as dotted keys -> {key: value} (a dict is entered, anything else is a value)."""
    out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            key = prefix + str(k)
            if isinstance(v, dict) and v:
                out.update(_flatten(v, key + '.'))
            else:
                out[key] = v
    return out


def _value_text(value):
    if isinstance(value, str):
        text = value
    elif isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
        text = ','.join(str(v) for v in value)
    else:
        text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 300 else text[:297] + '...'


def _type_of(default):
    """The type of a key from a default the code gives it."""
    d = (default or '').strip()
    if d in ('True', 'False'):
        return 'yes/no'
    if re.match(r'^-?\d+(\.\d+)?$', d):
        return 'number'
    if d.startswith('[') or d.startswith('('):
        return 'list'
    if d.startswith('{'):
        return 'dict'
    if d[:1] in ('"', "'"):
        return 'text'
    return ''


def _js(obj):
    """A JSON literal safe inside a <script> tag."""
    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')


def _esc(s):
    return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _asset(path_to_files, url_files, rel):
    """A new URL for every edit of a file under files/ (the hosts send no Cache-Control for them)."""
    try:
        return '%s%s?v=%d' % (url_files, rel, int(os.path.getmtime(os.path.join(path_to_files, *rel.split('/')))))
    except OSError:
        return url_files + rel


# ---------------------------------------------------------------------- the search
def _terms(query):
    """A query -> [(negated, field, value)]: words, "a phrase", -word, config: (cfg:), key:, art: (artifact:), repo:,
    cat:, is:."""
    out = []
    for m in re.finditer(r'(-?)(?:(\w+):)?("([^"]*)"|\S+)', query or ''):
        neg, field, raw, quoted = m.group(1) == '-', (m.group(2) or '').lower(), m.group(3), m.group(4)
        value = (quoted if quoted is not None else raw).lower()
        field = {'cfg': 'config', 'artifact': 'art'}.get(field, field)
        if field and field not in ('config', 'key', 'art', 'repo', 'cat', 'is'):
            value, field = (field + ':' + value), ''
        if value:
            out.append((neg, field, value))
    return out


def _row_matches(row, terms):
    """Whether a key (a row of the page) holds every term of a query - the search of the page, in Python."""
    for neg, field, value in terms:
        if field == 'config':
            hit = fnmatch.fnmatchcase(row['config'].lower(), value) if any(c in value for c in '*?[') else \
                value in row['config'].lower()
        elif field == 'key':
            hit = value in row['key'].lower()
        elif field == 'art':
            hit = any(value in a for a in row['arts'])
        elif field == 'repo':
            hit = any(value in r for r in row['repos'])
        elif field == 'cat':
            hit = any(value in c for c in row['cats'])
        elif field == 'is':
            hit = value in row['is']
        else:
            hit = value in row['hay']
        if hit == neg:
            return False
    return True


def _related(c, k):
    """The artifacts a key is related to: those that read it, declare it or show it in their docs, and those that read
    every key of its whole config -> [aid]."""
    aids = [x['aid'] for x in k.get('readers', []) + k.get('declared', []) + k.get('docs', [])]
    return aids + [r['aid'] for r in c.get('readers') or [] if '' in (r.get('every') or []) and r['aid'] not in aids]


def _rows(payload):
    """The keys of a payload as rows of the search: what a word may be found in, and what is: says of them."""
    arts = payload['artifacts']
    rows = []
    for c in payload['configs']:
        for k in c['keys']:
            who = [arts.get(aid, {}) for aid in _related(c, k)]
            flags = set(k['sources'])
            flags.add('set' if k.get('set') else 'unset')
            if k.get('secret'):
                flags.add('secret')
            if not k.get('desc'):
                flags.add('undocumented')
            if '<' in k['key'] or '*' in k['key']:
                flags.add('dynamic')
            hay = ' '.join([c['name'], k['key'], k.get('desc') or '', k.get('type') or '',
                            ' '.join(k.get('defaults') or []), '' if k.get('secret') else str(k.get('value') or '')] +
                           ['%s::%s %s' % (a.get('cat', ''), a.get('alias', ''), a.get('repo', '')) for a in who]).lower()
            rows.append({'config': c['name'], 'key': k['key'], 'hay': hay, 'is': flags,
                         'repos': {a.get('repo', '').lower() for a in who},
                         'cats': {a.get('cat', '').lower() for a in who},
                         'arts': {('%s::%s' % (a.get('cat', ''), a.get('alias', ''))).lower() for a in who},
                         'k': k, 'c': c})
        for u in c.get('unread') or []:
            hay = ' '.join([c['name'], u['key'], '' if u.get('secret') else str(u.get('value') or '')]).lower()
            rows.append({'config': c['name'], 'key': u['key'], 'hay': hay, 'is': {'set', 'unread'}, 'repos': set(),
                         'cats': set(), 'arts': set(), 'k': dict(u, unread=True), 'c': c})
    return rows


def _uses_of(configs):
    """Every artifact and the configs it uses, from the configs of a payload -> {aid: {config: {'reads', 'declares',
    'docs' (how many of its keys), 'keys' (their names), 'how' (what it does with the config as a whole: reads, every
    key, run time, write, declared)}}} - the page's map and its terminal command read it."""
    uses = {}

    def use(aid, name):
        return uses.setdefault(aid, {}).setdefault(name, {'reads': 0, 'declares': 0, 'docs': 0, 'keys': [], 'how': []})

    for c in configs:
        for r in c['readers']:
            u = use(r['aid'], c['name'])
            u['how'] = sorted(set(u['how']) | set(r['how']) | ({'every key'} if '' in (r.get('every') or []) else set()))
        for k in c['keys']:
            for what, lst in (('reads', k['readers']), ('declares', k['declared']), ('docs', k['docs'])):
                for x in lst:
                    u = use(x['aid'], c['name'])
                    u[what] += 1
                    if k['key'] not in u['keys']:
                        u['keys'].append(k['key'])
    for per in uses.values():
        for u in per.values():
            u['keys'].sort(key=str.lower)
    return uses


# ---------------------------------------------------------------------- the category
class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def _uses(self, key, default):
        return ((self.cmeta or {}).get('uses_categories', {}) or {}).get(key, default)

    def _settings(self):
        """files/configs.yaml over the defaults -> (the settings, the problems found)."""
        out = {k: (list(v) if isinstance(v, list) else (dict(v) if isinstance(v, dict) else v))
               for k, v in DEFAULTS.items()}
        path = os.path.join(self.path, 'files', SETTINGS_FILE)
        try:
            with open(path, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            return out, ['%s is missing: the defaults are used' % SETTINGS_FILE]
        except yaml.YAMLError as e:
            return out, ['%s: %s' % (SETTINGS_FILE, e)]
        if not isinstance(data, dict):
            return out, ['%s: a mapping is expected' % SETTINGS_FILE]
        problems = []
        for k in ('title', 'subtitle'):
            if data.get(k):
                out[k] = ' '.join(str(data[k]).split())
        for k in ('code_categories', 'code_files', 'doc_files', 'skip_dirs', 'repo_docs', 'secret_keys'):
            if k in data:
                out[k] = _list(data.get(k))
        for k in ('max_depth', 'max_file_bytes'):
            if k in data:
                try:
                    out[k] = max(0, int(data[k]))
                except (TypeError, ValueError):
                    problems.append('%s: %s is a number' % (SETTINGS_FILE, k))
        if isinstance(data.get('config_descs'), dict):
            out['config_descs'] = {str(k): _txt(v) for k, v in data['config_descs'].items() if v}
        if isinstance(data.get('routes'), dict):
            out['routes'] = {str(k).strip('.'): _config_alias(v) for k, v in data['routes'].items() if k and v}
        elif data.get('routes') is not None:
            problems.append('%s: routes is a mapping of dotted paths to config artifacts (global.init: task)' %
                            SETTINGS_FILE)
        return out, problems

    def _cserver_config(self):
        """The cserver config, read (never created) on every request ({} when there is none)."""
        r = self.cm.access({'category': self._uses('config', CONFIG_CATEGORY), 'command': 'read', 'arg1': 'cserver',
                            'con': False})
        cfg = r.get('config_cmeta') if r.get('return', 1) == 0 else None
        return cfg if isinstance(cfg, dict) else {}

    def _lookup(self, alias, uid):
        """The index of one category, whatever the scope of the request (it is applied to what is shown): an engine
        core older than this page has no scope."""
        try:
            return self.cm.repos.find_in_index(alias, uid, scope=False)
        except TypeError as e:
            if 'scope' not in str(e):
                raise
            return self.cm.repos.find_in_index(alias, uid)

    @staticmethod
    def _art(cat, cat_uid, a):
        p = a.get('cmeta_ref_parts') or {}
        meta = a.get('cmeta') or {}
        uid = str(p.get('artifact_uid') or '').lower()
        alias = p.get('artifact_alias') or uid
        # a repository is in no repository: its docs belong to itself (hide_repos hides them with it)
        own = cat == 'repo'
        return {'aid': cat_uid.lower() + '::' + uid, 'cat': cat, 'cat_uid': cat_uid.lower(), 'alias': alias, 'uid': uid,
                'repo': alias if own else (p.get('repo_alias') or ''),
                'repo_uid': uid if own else str(p.get('repo_uid') or '').lower(), 'path': a.get('path') or '',
                'name': meta.get('name') if isinstance(meta.get('name'), str) else ''}

    def _artifacts(self, settings):
        """The artifacts of the scanned categories and the plugged repositories, from the index (every repository:
        the scope of a request is applied to what is shown)."""
        r = self._lookup('category', CATEGORY_UID)
        pats = [p.lower() for p in settings['code_categories']]
        arts = []
        for c in (r.get('artifacts') or []) if r.get('return', 1) == 0 else []:
            cp = c.get('cmeta_ref_parts') or {}
            alias = cp.get('artifact_alias') or ''
            if not alias or not any(fnmatch.fnmatchcase(alias.lower(), p) for p in pats):
                continue
            rr = self._lookup(alias, cp['artifact_uid'])
            for a in (rr.get('artifacts') or []) if rr.get('return', 1) == 0 else []:
                arts.append(self._art(alias, cp['artifact_uid'], a))
        rr = self._lookup('repo', REPO_UID)
        repos = [self._art('repo', REPO_UID, a) for a in ((rr.get('artifacts') or []) if rr.get('return', 1) == 0 else [])]
        return arts, repos

    # ------------------------------------------------------------ the cache artifact
    def _cache_dir(self):
        """The folder of cache::cserver--cmeta-configs (local repository), created on first use: '' when it cannot
        be had."""
        if _state['disk_dir'] and os.path.isdir(_state['disk_dir']):
            return _state['disk_dir']
        try:
            r = self.cm.access({'category': self._uses('cache', CACHE_CATEGORY), 'command': 'get', 'arg1': CACHE_ALIAS,
                                'tags': list(CACHE_TAGS), 'con': False,
                                'meta': {'name': CACHE_NAME, 'generator': dict(CACHE_GENERATOR)}})
            path = (r.get('artifact') or {}).get('path', '') if r.get('return', 1) == 0 else ''
        except Exception:
            path = ''
        _state['disk_dir'] = path if path and os.path.isdir(path) else ''
        return _state['disk_dir']

    def _load_disk(self):
        if _state['disk_loaded']:
            return
        _state['disk_loaded'] = True
        folder = self._cache_dir()
        if not folder:
            return
        try:
            with open(os.path.join(folder, CACHE_FILE), encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        # a scan made along other routes says other things of the code: read every file again
        if not isinstance(data, dict) or data.get('format') != SCANNER or data.get('routes') != _state['routes']:
            return
        for path, item in (data.get('files') or {}).items():
            if isinstance(item, list) and len(item) == 2 and path not in _state['files']:
                _state['files'][path] = {'st': item[0], 'r': item[1]}

    def _save_disk(self):
        """The scan of every file into the cache artifact: a temporary file replaced, a few tries on Windows (another
        worker may be reading it); a failure costs one more full read next time, nothing else."""
        if not _state['dirty']:
            return
        folder = self._cache_dir()
        if not folder:
            return
        path = os.path.join(folder, CACHE_FILE)
        tmp = '%s.%d.tmp' % (path, os.getpid())
        data = {'format': SCANNER, 'routes': _state['routes'],
                'files': {p: [v['st'], v['r']] for p, v in _state['files'].items()}}
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            for n in range(5):
                try:
                    os.replace(tmp, path)
                    _state['dirty'] = False
                    break
                except PermissionError:
                    time.sleep(0.05 * (n + 1))
        except OSError as e:
            print('cMeta warning: cserver.cmeta.configs: %s not written: %s' % (path, e))
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ------------------------------------------------------------ the scan
    def _file(self, path, kind, st, stats, force):
        """What a file says, from what this process (or the cache artifact) knows of it while it keeps its time and
        size; else read and scanned."""
        hit = _state['files'].get(path)
        if hit and hit['st'] == st and not force:
            return hit['r']
        stats['read'] += 1
        try:
            with open(path, 'rb') as f:
                text = f.read().decode('utf-8-sig', errors='replace')
            res = _scan_text(text, kind, stats, _state['routes'])
        except OSError as e:
            res = {'facts': [], 'error': str(e)}
        _state['files'][path] = {'st': st, 'r': res}
        _state['dirty'] = True
        return res

    def _helper(self, art, path, call, stats, force):
        """The file of the module a call names, looked for next to the file that calls it, in its artifact and in
        the folder of its category (from _lib import graph: task/_lib/graph.py) -> its path or ''."""
        bases = [os.path.dirname(path), art['path'], os.path.dirname(art['path'])]
        module = [str(m) for m in call.get('m') or [] if m]
        for base in bases:
            key = (base, tuple(module))
            if key not in _state['resolved']:
                found = ''
                for cand in (os.path.join(base, *module) + '.py', os.path.join(base, *module, '__init__.py')):
                    if os.path.isfile(cand):
                        found = cand
                        break
                _state['resolved'][key] = found
            if _state['resolved'][key]:
                return _state['resolved'][key]
        return ''

    def _scan(self, force=False, refresh=False):
        """The model of every key known here (no scope, no values): built again when REFRESH_AFTER seconds have passed,
        on refresh, or with force (every file read again). It serves every viewer of this process, so it is built
        outside the scope of the request that asks for it (hide_repos: its cache artifact lives in the local
        repository); the scope is applied to what is shown."""
        repos = self.cm.repos
        if not getattr(repos, 'hidden_repos', ()) or not hasattr(repos, 'pop_hidden_repos'):
            return self._scan_all(force, refresh)
        saved = repos.push_hidden_repos(None)              # None: no change - what is hidden now, to put back
        repos.pop_hidden_repos(((), frozenset(), ()))
        try:
            return self._scan_all(force, refresh)
        finally:
            repos.pop_hidden_repos(saved)

    def _scan_all(self, force, refresh):
        home = getattr(self.cm.repos, 'index_path', '')
        with _lock:
            if _state['home'] != home:
                _state.update(home=home, files={}, model=None, built=0.0, dirty=False, disk_dir='',
                              disk_loaded=False, resolved={}, routes={})
            if not force and not refresh and _state['model'] is not None and \
                    time.monotonic() - _state['built'] < REFRESH_AFTER:
                return _state['model']

            t0 = time.monotonic()
            settings, problems = self._settings()
            if settings['routes'] != _state['routes']:
                # other routes: what this process knows of the code was read along the old ones
                _state.update(routes=dict(settings['routes']), files={}, disk_loaded=False, dirty=True)
            self._load_disk()
            arts, repos = self._artifacts(settings)
            stats = {'artifacts': len(arts), 'files': 0, 'read': 0, 'parsed': 0, 'errors': 0}
            _state['resolved'] = {}
            seen, results, errors = set(), [], []

            for art in arts:
                for path, rel, kind, st in _walk(art['path'], settings):
                    seen.add(path)
                    results.append((art, rel, path, self._file(path, kind, st, stats, force)))
            for repo in repos:
                root = repo['path']
                for item in settings['repo_docs']:
                    target = os.path.join(root, *item.split('/'))
                    if os.path.isdir(target):
                        for path, rel, kind, st in _walk(target, settings):
                            if kind != 'py':
                                seen.add(path)
                                results.append((repo, item.rstrip('/') + '/' + rel, path,
                                                self._file(path, kind, st, stats, force)))
                    elif os.path.isfile(target) and _fits(os.path.basename(target), settings['doc_files']):
                        try:
                            s = os.stat(target)
                        except OSError:
                            continue
                        seen.add(target)
                        results.append((repo, item, target, self._file(target, 'md', [s.st_mtime_ns, s.st_size],
                                                                       stats, force)))

            # the calls of functions of helper modules (from _lib import graph): those modules read and the calls
            # completed with what their functions read
            extra = []
            for art, rel, path, res in results:
                for call in res.get('calls') or []:
                    hp = self._helper(art, path, call, stats, force)
                    if not hp:
                        continue
                    try:
                        s = os.stat(hp)
                    except OSError:
                        continue
                    seen.add(hp)
                    summ = (self._file(hp, 'py', [s.st_mtime_ns, s.st_size], stats, force).get('exports') or {}) \
                        .get(call.get('f'))
                    if summ:
                        extra.append((art, rel, path, {'facts': _resolve(call, summ)}))
            results += extra

            stats['files'] = len(seen)
            for gone in [p for p in _state['files'] if p not in seen]:
                del _state['files'][gone]
                _state['dirty'] = True
            for art, rel, path, res in results:
                if res.get('error'):
                    errors.append('%s::%s/%s: %s' % (art['cat'], art['alias'], rel, res['error']))
            self._save_disk()

            model = self._join(results, arts + repos, settings)
            stats['ms'] = int((time.monotonic() - t0) * 1000)
            model.update(settings=settings, problems=problems, errors=errors, stats=stats,
                         built=time.strftime('%Y-%m-%d %H:%M:%S'))
            _state['model'] = model
            _state['built'] = time.monotonic()
            return model

    @staticmethod
    def _join(results, arts, settings):
        """The facts of every file joined by config artifact and key: who reads, declares and documents each key,
        what it does (the best description first), its type, defaults and examples."""
        configs = {}

        def config(name):
            return configs.setdefault(name, {'name': name, 'descs': [], 'keys': {}, 'readers': {}})

        def key_of(c, key):
            return c['keys'].setdefault(key, {'key': key, 'descs': [], 'types': [], 'defaults': [], 'examples': [],
                                              'secret': False, 'list': False, 'readers': {}, 'docs': {},
                                              'declared': {}, 'sources': set()})

        for art, rel, path, res in results:
            for f in res.get('facts') or []:
                name = f.get('c')
                if not isinstance(name, str) or not name:
                    continue
                c = config(name)
                a, key, line = f['a'], f.get('k') or '', f.get('l', 0)
                where = [art['aid'], rel, line]
                if a in ('uses', 'every', 'write') or (a == 'declare' and not key):
                    r = c['readers'].setdefault(art['aid'], {'how': set(), 'every': set(), 'refs': []})
                    r['how'].add('declared' if a == 'declare' else ('reads' if a == 'uses' else a))
                    if a == 'every':
                        r['every'].add(key)
                    r['refs'].append([rel, line, a, key])
                    if a == 'declare' and f.get('n'):
                        c['descs'].append([0, f['n'], 'declared', art['aid'], rel, line])
                    if not (a == 'write' and key):
                        continue
                if not key:
                    continue
                k = key_of(c, key)
                if a in ('read', 'write'):
                    k['sources'].add('code')
                    k['readers'].setdefault(art['aid'], []).append([rel, line, a])
                    c['readers'].setdefault(art['aid'], {'how': set(), 'every': set(), 'refs': []})['how'].add('reads')
                elif a == 'declare':
                    k['sources'].add('declared')
                    k['declared'].setdefault(art['aid'], []).append([rel, line])
                    c['readers'].setdefault(art['aid'], {'how': set(), 'every': set(), 'refs': []})['how'].add('declared')
                else:
                    k['sources'].add('docs')
                    k['docs'].setdefault(art['aid'], []).append([rel, line])
                if f.get('n'):
                    k['descs'].append([RANKS.get(f.get('nk'), 6), f['n'], f.get('nk') or 'code'] + where)
                if f.get('t'):
                    k['types'].append(f['t'])
                d = f.get('d')
                if d is not None and d not in k['defaults'] and d not in ('None', "''", '""'):
                    k['defaults'].append(d)
                if f.get('x') not in (None, ''):
                    k['examples'].append([f['x']] + where)
                if f.get('s'):
                    k['secret'] = True
                if f.get('list'):
                    k['list'] = True

        for name, desc in (settings.get('config_descs') or {}).items():
            if name in configs:
                configs[name]['descs'].append([9, desc, 'settings', '', SETTINGS_FILE, 0])

        for c in configs.values():
            def reader(aid):
                return c['readers'].setdefault(aid, {'how': set(), 'every': set(), 'refs': []})

            # a key the code names whole at run time (cfg.get(key) with a key of its own choosing): no row, a word
            # on its reader
            for key in [k for k in c['keys'] if re.match(r'^<[^<>]*>$', k)]:
                for aid, refs in c['keys'].pop(key)['readers'].items():
                    reader(aid)['how'].add('run time')
                    reader(aid)['refs'] += [[r[0], r[1], 'run time', key] for r in refs]

            # a key only the docs show, inside a key the code or a _desc knows (an entry of a dict: local_ai_uses.<x>,
            # use.python.tool_path): an example of that key, not a row of its own
            coded = {n for n, k in c['keys'].items() if k['sources'] & {'code', 'declared'}}
            for key in list(c['keys']):
                k = c['keys'][key]
                if k['sources'] != {'docs'}:
                    continue
                parents = [p for p in coded if key.startswith(p + '.') and
                           not any(o != p and o.startswith(p + '.') for o in coded)]
                if not parents:
                    continue
                p = c['keys'][max(parents, key=len)]
                sub = key[len(p['key']) + 1:]
                p['sources'].add('docs')
                for aid, refs in k['docs'].items():
                    p['docs'].setdefault(aid, []).extend(refs)
                p['examples'] += [x[:4] + [sub] for x in k['examples']]
                p['descs'] += [[d[0] + 1] + d[1:] for d in k['descs']]
                del c['keys'][key]

            # one key under two names with parts named at run time (cache_repos.<key> in the docs,
            # cache_repos.<cache_repo_key> in the code): one row, under the name a _desc or the docs give
            by_rx = {}
            for name in sorted((n for n in c['keys'] if '<' in n or '*' in n),
                               key=lambda n: ('declared' not in c['keys'][n]['sources'],
                                              'docs' not in c['keys'][n]['sources'], n)):
                rx = _pattern_re(name).pattern
                if rx in by_rx:
                    _merge_key(c['keys'][by_rx[rx]], c['keys'].pop(name))
                else:
                    by_rx[rx] = name

            # a key the docs or a _desc show that a key the code names at run time stands for
            # (run_ai_gateway_codex, run_ai_gateway_<harness>): read by the same code
            patterns = [(k, _pattern_re(n)) for n, k in c['keys'].items() if ('<' in n or '*' in n) and k['readers']]
            for key, k in c['keys'].items():
                if k['readers'] or '<' in key or '*' in key:
                    continue
                for pk, rx in patterns:
                    if rx.match(key):
                        k['sources'].add('code')
                        for aid, refs in pk['readers'].items():
                            k['readers'].setdefault(aid, []).extend(refs)

            # a key the code only takes on the way to its parts (cfg.get('test_session', {}).get('repo')) is no row
            names = list(c['keys'])
            for key in names:
                k = c['keys'][key]
                if k['sources'] == {'code'} and not k['descs'] and any(o.startswith(key + '.') for o in names):
                    for aid in k['readers']:
                        reader(aid)['how'].add('reads')
                    del c['keys'][key]
        return {'configs': configs, 'arts': {a['aid']: a for a in arts}}

    # ------------------------------------------------------------ what a viewer sees
    def _values_on(self, misc, cfg):
        """Whether this viewer sees the values set here (configs_values: yes / no; else this machine's browser or one
        past the password; never through the cPlatform)."""
        if misc.get('ctuning_server'):
            return False
        v = cfg.get('configs_values')
        if v not in (None, ''):
            return _yes(v)
        return bool(misc.get('client_local') or misc.get('password_gate') or misc.get('cli'))

    def _hidden(self, cfg, only_repos=''):
        """The repositories this viewer must not see: the server's hide_repos, the scope of the request, and every
        repository but those of only_repos when a host names them (a page on a public site shows its public
        repositories alone)."""
        pats = _patterns(cfg.get('hide_repos'))
        allow = _patterns(only_repos)
        repos = self.cm.repos
        scoped = bool(getattr(repos, 'hidden_repos', ()))

        def hidden(alias, uid):
            if allow and not (_matches_any(alias, allow) or (uid and uid.lower() in allow)):
                return True
            if pats and alias and _matches_any(alias, pats):
                return True
            return bool(scoped and uid and repos.repo_hidden(None, alias=alias, uid=uid))
        return hidden

    def _config_artifacts(self, hidden):
        """The config artifacts of this machine the viewer may see -> {alias: [{repo, uid, path, data}]} (the local
        repository first)."""
        out = {}
        r = self._lookup('config', CONFIG_UID)
        for a in (r.get('artifacts') or []) if r.get('return', 1) == 0 else []:
            art = self._art('config', CONFIG_UID, a)
            if hidden(art['repo'], art['repo_uid']):
                continue
            data = {}
            try:
                with open(os.path.join(art['path'], 'data.json'), encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                pass
            art['data'] = data if isinstance(data, dict) else {}
            art['kept_in'] = 'data.json'
            if not art['data']:
                # a config that keeps its settings in its meta (what "config read" answers as artifact.cmeta)
                extra = {k: v for k, v in (a.get('cmeta') or {}).items() if k not in META_OWN}
                if extra:
                    art['data'], art['kept_in'] = extra, '_cmeta'
            try:
                art['files'] = sorted(n for n in os.listdir(art['path']) if not n.startswith(('.', '_cmeta')) and
                                      n != 'data.json' and not n.endswith(('.lock', '.tmp')))[:20]
            except OSError:
                art['files'] = []
            out.setdefault(art['alias'], []).append(art)
        for v in out.values():
            v.sort(key=lambda x: (x['repo'] != 'local', x['repo']))
        return out

    def _payload(self, misc, refresh=False, force=False, only_repos=''):
        """What the page renders: every config artifact known here with its keys, as this viewer may see them."""
        t0 = time.monotonic()
        model = self._scan(force=force, refresh=refresh)
        settings = model['settings']
        cfg = self._cserver_config()
        hidden = self._hidden(cfg, only_repos)
        values = self._values_on(misc, cfg)
        secret = [p.lower() for p in settings['secret_keys']]

        def is_secret(key):
            parts = key.lower().split('.')
            return any(fnmatch.fnmatchcase(key.lower(), p) or fnmatch.fnmatchcase(part, p)
                       for p in secret for part in parts)

        seen_arts = {aid: a for aid, a in model['arts'].items() if not hidden(a['repo'], a['repo_uid'])}
        # what is set on this machine - even which configs it holds - is for a viewer who may see the values; the
        # others see the keys the artifacts know, and who reads them
        here = self._config_artifacts(hidden) if values else {}
        used = set()
        out = []

        for name in sorted(set(model['configs']) | set(here), key=lambda n: (n.startswith('<'), n.lower())):
            c = model['configs'].get(name) or {'descs': [], 'keys': {}, 'readers': {}}
            readers = [{'aid': aid, 'how': sorted(r['how']), 'every': sorted(r['every']),
                        'refs': [x for x in r['refs'] if x[2] != 'declare'][:20]}
                       for aid, r in c['readers'].items() if aid in seen_arts]
            keys = []
            for key, k in c['keys'].items():
                rd = [{'aid': aid, 'refs': refs[:10]} for aid, refs in k['readers'].items() if aid in seen_arts]
                dc = [{'aid': aid, 'refs': refs[:5]} for aid, refs in k['declared'].items() if aid in seen_arts]
                do = [{'aid': aid, 'refs': refs[:5]} for aid, refs in k['docs'].items() if aid in seen_arts]
                if not (rd or dc or do):
                    continue
                visible = {x['aid'] for x in rd + dc + do}
                descs = sorted([d for d in k['descs'] if d[3] in visible], key=lambda d: d[0])
                texts, uniq = [], []
                for d in descs:
                    if d[1] not in texts:
                        texts.append(d[1])
                        uniq.append({'text': d[1], 'from': d[2], 'aid': d[3], 'file': d[4], 'line': d[5]})
                types = k['types'] or [t for t in (_type_of(d) for d in k['defaults']) if t]
                examples = []
                for x in k['examples']:
                    sub = x[4] if len(x) > 4 else ''           # an entry under the key (local_ai_uses.<x>=<cRef>)
                    if x[1] in visible and (sub, x[0]) not in [(e['sub'], e['value']) for e in examples]:
                        examples.append({'value': x[0], 'sub': sub, 'aid': x[1], 'file': x[2], 'line': x[3]})
                sec = k['secret'] or is_secret(key)
                keys.append({'key': key, 'desc': uniq[0]['text'] if uniq else '',
                             'desc_from': uniq[0]['from'] if uniq else '',
                             'descs': uniq[:6], 'type': types[0] if types else '',
                             'defaults': [d for d in k['defaults'] if d not in ('{}', '[]', '()')][:4],
                             'examples': [] if sec else examples[:4], 'secret': sec,
                             'list': k['list'] or (types[:1] == ['list']),
                             # where this viewer can see it known from
                             'sources': [s for s, there in (('declared', dc), ('code', rd), ('docs', do)) if there],
                             'readers': rd, 'declared': dc, 'docs': do, 'set': False, 'value': None})
            if not keys and not readers and name not in here:
                continue

            descs = sorted([d for d in c['descs'] if d[3] in seen_arts or d[2] == 'settings'], key=lambda d: d[0])
            entry = {'name': name, 'dynamic': '<' in name, 'desc': descs[0][1] if descs else '',
                     'desc_from': descs[0][2] if descs else '', 'readers': readers, 'keys': keys,
                     'artifacts': [], 'unread': [], 'set_count': 0}

            # the values of this machine: each set key to its key, to the part of a key it is under, or to a key the
            # code names at run time; the others are read by no plugged artifact
            if name in here:
                used.add(name)
                arts = here[name]
                entry['artifacts'] = [{'repo': a['repo'], 'uid': a['uid'], 'alias': a['alias'],
                                       'keys': len(_flatten(a['data'])), 'kept_in': a['kept_in'],
                                       'files': a['files']} for a in arts]
                if values:
                    flat = _flatten(arts[0]['data'])
                    by_key = {k['key']: k for k in keys}
                    patterns = [(k, _pattern_re(k['key'])) for k in keys if '<' in k['key'] or '*' in k['key']]
                    # a reader that takes every key of the whole config (not of one dict in it) may pass them on
                    every = any('' in r['every'] for r in readers)
                    for skey, val in flat.items():
                        k = by_key.get(skey)
                        if k is None:
                            parents = [p for p in by_key if skey.startswith(p + '.')]
                            k = by_key[max(parents, key=len)] if parents else None
                        if k is None:
                            k = next((kk for kk, rx in sorted(patterns, key=lambda x: -len(x[0]['key']))
                                      if rx.match(skey)), None)
                        sec = is_secret(skey) or (k is not None and k['secret'])
                        shown = None if sec else _value_text(val)
                        if k is None:
                            entry['unread'].append({'key': skey, 'value': shown, 'secret': sec, 'every': every})
                            continue
                        entry['set_count'] += 1
                        if k['key'] == skey:
                            k['set'], k['value'] = True, shown
                        else:
                            k['set'] = True
                            k.setdefault('children', []).append({'key': skey, 'value': shown, 'secret': sec})
                    # where its values are: its data.json, or (settings in its meta) the artifact itself
                    entry['data_file'] = {'alias': arts[0]['alias'], 'uid': arts[0]['uid'],
                                          'file': 'data.json' if arts[0]['kept_in'] == 'data.json' else ''}
            keys.sort(key=lambda k: (('<' in k['key'] or '*' in k['key']), k['key'].lower()))
            out.append(entry)

        aids = {r['aid'] for c in out for r in c['readers']} | \
            {x['aid'] for c in out for k in c['keys'] for x in k['readers'] + k['declared'] + k['docs']} | \
            {d['aid'] for c in out for k in c['keys'] for d in k['descs'] if d['aid']}
        artifacts = {aid: {k: a[k] for k in ('cat', 'cat_uid', 'alias', 'uid', 'repo', 'name')}
                     for aid, a in seen_arts.items() if aid in aids}
        repos = {}
        for a in artifacts.values():
            repos[a['repo']] = repos.get(a['repo'], 0) + 1

        named = [c for c in out if not c['dynamic']]
        stats = dict(model['stats'])
        stats.update(configs=len(named), keys=sum(len(c['keys']) for c in named),
                     set=sum(1 for c in named for k in c['keys'] if k.get('set')),
                     unread=sum(len(c['unread']) for c in out), readers=len(artifacts), repos=len(repos),
                     here=len(used), dynamic=len(out) - len(named), ms_view=int((time.monotonic() - t0) * 1000))
        # the files that could not be parsed, by name, for a viewer who may see this machine's state (an error of a
        # file may carry its local path); the count for the others
        errors = model['errors'][:50] if values else ['%d file(s)' % len(model['errors'])] if model['errors'] else []
        return {'configs': out, 'artifacts': artifacts, 'repos': sorted(repos.items(), key=lambda x: x[0].lower()),
                # the other way round: every artifact and the configs it uses (the map of the page)
                'uses': _uses_of(out),
                'values': values, 'stats': stats, 'built': model['built'], 'problems': model['problems'],
                'errors': errors, 'title': settings['title']}

    ############################################################
    def web_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        urls,  # The host's URLs: url (this page), url_files (files/ of this category), url_server.
        query = {},  # GET and POST parameters.
        misc = {},  # Session bits (client_local, password_gate on the engine cserver; theme, ctuning_server on cPlatform).
        only_repos = '',  # The repositories shown (aliases, UIDs or patterns): set by a host in the call - a project
                          # pointer of the cPlatform -, never by the address; '' = every repository the viewer may see.
    ):
        """
        The configs page (command web), or ?native_action=configs as JSON.
        """
        query = query or {}
        misc = misc or {}

        na = query.get('native_action', '')
        if na:
            t0 = time.monotonic()
            try:
                if na == 'configs':
                    out = self._payload(misc, refresh=_yes(query.get('refresh')), only_repos=only_repos)
                else:
                    out = {'error': 'unknown native_action %r' % na}
            except Exception as e:
                print('cMeta warning: cserver.cmeta.configs: native_action %r failed: %s: %s' % (na, type(e).__name__, e))
                out = {'error': '%s: %s' % (type(e).__name__, e)}
            out['server'] = {'pid': os.getpid(), 'ms': int((time.monotonic() - t0) * 1000)}
            return {'return': 0, 'json': out}

        settings, problems = self._settings()
        path_to_files = os.path.join(self.path, 'files')
        url_files = urls.get('url_files') or ''
        url_server = urls.get('url_server') or '/'
        platform = bool(misc.get('ctuning_server'))
        dark = misc.get('theme', '') == 'dark' or str(query.get('dark', '')).lower() in ('1', 'true', 'yes')
        version = getattr(self.cm, '__version__', '')

        state = {k: str(query.get(k) or '') for k in ('q', 'view', 'show', 'repo', 'open', 'art', 'cfg')}
        config = {'api_url': urls.get('url', '?'), 'url_server': url_server, 'dark_mode': bool(dark),
                  # inside the cPlatform's shell (its top bar, its menu, its theme): the page paints nothing past its box
                  'hosted': platform, 'version': version, 'title': settings['title'], 'state': state,
                  # the page of one artifact: a host's /cref/ (the engine cserver has one; a host may name its own)
                  'cref_url': str(misc.get('cref_url') or ('' if platform else url_server + 'cref/')),
                  'settings_url': '' if platform else url_server + 'cref/category::cserver.cmeta.configs,%s/files/%s' %
                                                      (self.cmeta.get('artifact', 'cc8dd8bdf9fe4132'), SETTINGS_FILE),
                  'problems': problems}

        with open(os.path.join(path_to_files, 'index.html'), encoding='utf-8') as f:
            body = f.read()
        body = (body.replace('%%CONFIG%%', _js(config)).replace('%%TITLE%%', _esc(settings['title']))
                .replace('%%SUBTITLE%%', _esc(settings['subtitle'])).replace('%%VERSION%%', _esc(version)))
        head = ('\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
                '  <link type="text/css" rel="stylesheet" media="all" href="%s">\n'
                '  <script src="%s" defer></script>\n' % (_asset(path_to_files, url_files, 'css/configs.css'),
                                                          _asset(path_to_files, url_files, 'js/configs.js')))
        return {'return': 0, 'html_meta': {'page_title': settings['title'], 'page_extra_style': head, 'html': body}}

    ############################################################
    def list_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1 = '',  # The query (the first word after the command), in the syntax of the search box of the page.
        query = '',  # The query, when it is not the first word.
        limit = 0,  # The keys printed per config (0: all).
        as_json: bool = False,  # Print the JSON the page reads instead.
    ):
        """
        The config artifacts and their keys in a terminal, as the page lists them: what each key does, its value
        here (secrets hidden), who reads it; then the keys set here that no plugged artifact reads.
        """
        payload = self._payload({'cli': True})
        q = str(query or arg1 or '').strip()
        terms = _terms(q)
        rows = [r for r in _rows(payload) if _row_matches(r, terms)]

        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return {'return': 0, 'result': payload}

        for p in payload['problems']:
            print('cMeta warning: %s' % p)
        arts = payload['artifacts']
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 0

        by_config = {}
        for r in rows:
            by_config.setdefault(r['config'], []).append(r)
        for c in payload['configs']:
            mine = by_config.get(c['name'])
            if not mine and (terms or c['keys'] or c['unread']):
                continue
            where = ', '.join('%s (%d keys)' % (a['repo'], a['keys']) for a in c['artifacts']) or 'not set here'
            print('\nconfig::%s - %s' % (c['name'], c['desc'] or 'no description'))
            print('  set here: %s; read by %d artifact(s)' % (where, len(c['readers'])))
            for r in (mine or [])[:limit or None]:
                k = r['k']
                if k.get('unread'):
                    print('  ? %-34s = %-24s set here, read by no plugged artifact' %
                          (k['key'], '(hidden)' if k.get('secret') else k.get('value')))
                    continue
                value = '(hidden)' if k['secret'] and k.get('set') else (k.get('value') if k.get('set') else '')
                if k.get('children') and not k.get('value'):
                    value = '%d set under it' % len(k['children'])
                who = ', '.join(sorted({'%s::%s' % (arts[x['aid']]['cat'], arts[x['aid']]['alias'])
                                        for x in k['readers'] + k['declared'] if x['aid'] in arts}))
                print('  %s %-34s = %-24s %s%s' % ('*' if k.get('set') else ' ', k['key'], str(value or '')[:24],
                                                   (k['desc'] or '')[:90], ('  [%s]' % who[:80]) if who else ''))
            if limit and mine and len(mine) > limit:
                print('  ... %d more (--limit=0: all)' % (len(mine) - limit))

        s = payload['stats']
        print('\n%d config artifacts, %d keys (%d set here), %d set here but read by no plugged artifact; read by %d '
              'artifacts of %d repositories; %d files looked at, %d read, %d parsed in %d ms' %
              (s['configs'], s['keys'], s['set'], s['unread'], s['readers'], s['repos'], s['files'], s['read'],
               s['parsed'], s['ms']))
        print('* = set here.  cx config set <name> --meta.<key>=<value> changes a key; cx config show <name> lists them.')
        return {'return': 0, 'configs': len(payload['configs']), 'rows': len(rows)}

    ############################################################
    def artifacts_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1 = '',  # The query (the first word after the command): words, art:, cat:, repo:, config:.
        query = '',  # The query, when it is not the first word.
        as_json: bool = False,  # Print the JSON instead: {aid: {config: {reads, declares, docs, keys, how}}}.
    ):
        """
        The other way round: every artifact that reads, declares or shows config keys, with the configs it uses and
        their keys - the map of the page, from the artifacts' side.
        """
        payload = self._payload({'cli': True})
        arts, uses = payload['artifacts'], payload['uses']
        terms = _terms(str(query or arg1 or '').strip())

        def fits(aid):
            a = arts.get(aid) or {}
            name = ('%s::%s' % (a.get('cat', ''), a.get('alias', ''))).lower()
            configs = [c.lower() for c in uses.get(aid) or {}]
            hay = ' '.join([name, a.get('repo', ''), a.get('name', '')] + configs).lower()
            for neg, field, value in terms:
                hit = (value in name if field == 'art' else value in (a.get('cat') or '').lower() if field == 'cat' else
                       value in (a.get('repo') or '').lower() if field == 'repo' else
                       any(value in c for c in configs) if field == 'config' else value in hay)
                if hit == neg:
                    return False
            return True

        shown = sorted((aid for aid in uses if aid in arts and fits(aid)),
                       key=lambda aid: (arts[aid]['cat'].lower(), arts[aid]['alias'].lower()))
        if as_json:
            out = {'%s::%s' % (arts[aid]['cat'], arts[aid]['alias']): uses[aid] for aid in shown}
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return {'return': 0, 'result': out}

        for aid in shown:
            a = arts[aid]
            print('\n%s::%s  (%s)%s' % (a['cat'], a['alias'], a['repo'], ('  ' + a['name'][:70]) if a.get('name') else ''))
            for name in sorted(uses[aid], key=lambda n: (n.startswith('<'), n.lower())):
                u = uses[aid][name]
                what = [('reads %d' % u['reads']) if u['reads'] else '', ('declares %d' % u['declares']) if u['declares'] else '',
                        ('shows %d' % u['docs']) if u['docs'] else '']
                what += [h for h in u['how'] if h in ('every key', 'run time', 'write')]
                keys = ', '.join(u['keys'][:8]) + (' ...' if len(u['keys']) > 8 else '')
                print('    %-28s %-28s %s' % (name, ', '.join(w for w in what if w) or 'reads it', keys))
        print('\n%d artifact(s) use config artifacts%s. cx cserver.cmeta.configs list "art:<name>" lists the keys of one.' %
              (len(shown), '' if not terms else ' and hold the query'))
        return {'return': 0, 'artifacts': len(shown)}

    ############################################################
    def scan_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        force: bool = False,  # Read and parse every file again, whatever the cache artifact knows of it.
    ):
        """
        Look at the files of the scanned artifacts again and say what was found and what it cost.
        """
        t0 = time.monotonic()
        model = self._scan(force=force, refresh=True)
        s = model['stats']
        for p in model['problems']:
            print('cMeta warning: %s' % p)
        print('%d artifacts, %d files looked at, %d read, %d parsed (%d could not be parsed) in %.2f s' %
              (s['artifacts'], s['files'], s['read'], s['parsed'], s['errors'], time.monotonic() - t0))
        print('%d config artifacts named, %d named at run time' %
              (sum(1 for n in model['configs'] if '<' not in n), sum(1 for n in model['configs'] if '<' in n)))
        for e in model['errors'][:20]:
            print('cMeta info: not parsed: %s' % e)
        cache = _state['disk_dir']
        if cache:
            print('cache: %s' % os.path.join(cache, CACHE_FILE))
        return {'return': 0, 'stats': s, 'errors': model['errors']}
