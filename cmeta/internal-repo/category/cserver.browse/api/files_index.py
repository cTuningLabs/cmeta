"""
The file search of /browse (2026-11-12): the names of every file inside the artifacts of the home, and the text of the
kinds Python reads without a library, in one SQLite database with its FTS5 word indexes - so a search finds the artifact
whose files, by their names or their contents, hold the words, with partial words and wildcards.

Where: the result artifact result::local:cserver-browse-files (permanent, as the state of the named syncs is - never a
cache artifact, which may be cleaned), the file files.sqlite (WAL). What: every category of every repository but the keys
and secrets (the categories and folders named like them, the files that look like key material) and the skip lists of
the cserver config (categories of machine output - tmp, cache, log, state, result, website -, folders - .git, .venv,
node_modules, site-packages ...), dot-files and dot-folders never, symlinks never, to a depth. The index lives on this
machine only (local is not synced); each machine builds its own.

How: a background thread of one server process at a time (a lock file beside the database): the first time, the names
(a scandir walk of every artifact, nothing opened), then the texts (each readable file once, its first browse_file_search_max_kb
KB); afterwards a sweep every browse_file_search_refresh minutes - the folders' own times (NTFS, ext4 and APFS change a
folder's time when an entry is added, removed or renamed in it: only a changed folder is listed again), the text files'
times and sizes (a changed file is read again), a folder or an artifact gone dropped - and at once on a reload, through
the command line (cx cserver.browse files --sweep) and for the artifacts cMeta itself changed.

The query: a plain word matches inside longer words - it is looked up in the index's vocabulary (fts5vocab: the distinct
terms; LIKE '%word%', with * and ? as wildcards) and the terms found are searched as one OR query (measured 2026-11-12
on the user's home: exactly what a trigram index finds, at a fifth of its size); a "phrase" is an FTS5 phrase. The
answer is per artifact: the files that matched, a few of them, for the row's second line; the snippet of a hit is read
from the file when the row is shown.
"""

import datetime
import json
import os
import re
import sqlite3
import threading
import time
import zipfile

FORMAT = 1                       # a database of another format is rebuilt
DB_FILE = 'files.sqlite'
LOCK_FILE = 'files.sqlite.building'
RESULT_ALIAS = 'cserver-browse-files'
RESULT_TAGS = ['cserver.browse', 'file-search']
RESULT_NAME = 'cserver.browse: the names and texts of the files inside the artifacts of this machine (the file search of /browse)'

# machine output rather than the user's files; "category" and "config" are the definitions and the settings of cMeta
# itself (a config may hold a key); "repo" is never indexed whatever the list says: a repository is an artifact whose
# folder holds every other artifact (the index walked the whole local repository as one artifact - itself included)
DEFAULT_SKIP_CATEGORIES = ['tmp', 'cache', 'log', 'state', 'result', 'website', 'category', 'config']
NEVER_CATEGORIES = ['repo']
DEFAULT_SKIP_FOLDERS = ['.git', '.venv', 'venv', 'node_modules', '__pycache__', 'site-packages', '.pytest_cache',
                        '.mypy_cache', '.ruff_cache', '.idea', '.vscode', 'dist', 'build']
DEFAULT_TEXT = ['md', 'txt', 'rst', 'yaml', 'yml', 'json', 'csv', 'tsv', 'eml', 'html', 'htm', 'tex', 'py', 'sh', 'bat',
                'ps1', 'ipynb', 'docx', 'pptx', 'xlsx']
DEFAULT_MAX_KB = 256
DEFAULT_DEPTH = 10
DEFAULT_REFRESH = 15             # minutes between two sweeps
LOCK_STALE = 3600                # seconds: a lock its builder has not touched for this long is of a process that died
LOCK_TOUCH = 60                  # seconds between two touches of its lock by a builder at work
VOCAB_MAX = 400                  # the terms one partial word may stand for
PER_ARTIFACT = 5                 # the files named per artifact in an answer
SNIPPET_READ = 262144            # bytes of a file read for a snippet
SNIPPET_LEN = 180
BATCH = 400                      # files per transaction while building

SECRET_DIR_RE = re.compile(r'crypt|secret|credential', re.I)
SECRET_FILE_RE = re.compile(
    r'^id_|_(rsa|dsa|ecdsa|ed25519)$'
    r'|\.(pem|key|p12|pfx|ppk|jks|keystore|kdbx|gpg|pgp|asc|ovpn)$'
    r'|^(known_hosts|authorized_keys)'
    r'|(^|[._-])(tokens?|secrets?)(\.[a-z0-9]+)?$|passw(or)?d|credential',
    re.I)
RESERVED = {'con', 'prn', 'aux', 'nul'} | {'com%d' % i for i in range(1, 10)} | {'lpt%d' % i for i in range(1, 10)}
TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')
OFFICE = {'docx': ('word/document.xml',), 'pptx': ('ppt/slides/',), 'xlsx': ('xl/sharedStrings.xml', 'xl/worksheets/')}
WORD_RE = re.compile(r'[^\W_]+', re.U)           # how unicode61 cuts: letters and digits, the rest separates

_lock = threading.Lock()
_state = {'thread': None, 'building': False, 'want': 0, 'done_want': 0, 'error': '', 'last': 0.0, 'db': '',
          'phase': '', 'done': 0, 'total': 0, 'dirty': set(), 'items': [], 'once': False}


# ------------------------------------------------------------------ the configuration

def settings(cfg):
    """The keys of the cserver config that drive the file search -> a dict, or None when it is off (the default)."""
    on = str(cfg.get('browse_file_search') or '').strip().lower()
    if on not in ('yes', 'true', '1', 'on'):
        return None

    def lst(key, default):
        v = cfg.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            return list(default)
        if isinstance(v, str):
            v = v.split(',')
        if isinstance(v, (list, tuple)):
            out = [str(x).strip() for x in v if str(x).strip()]
            return [] if out and out[0].lower() == 'none' else out
        return list(default)

    def num(key, default, low, high):
        try:
            return min(high, max(low, int(cfg.get(key))))
        except (TypeError, ValueError):
            return default

    # when the index is refreshed by itself (the user, 2026-11-12: "an explicit button refresh ... not every 15
    # minutes - will be too expensive", then "skip automatic reindex when cserver starts for now and add it as a
    # config"): never (default: the Refresh button, the command line, and the artifacts cMeta itself changes), at the
    # server's start, or every so many minutes
    refresh = str(cfg.get('browse_file_search_refresh') or 'never').strip().lower()
    minutes = 0
    if refresh not in ('start', 'never'):
        try:
            minutes = max(1, int(refresh))
            refresh = 'minutes'
        except ValueError:
            refresh = 'never'
    follow = str(cfg.get('browse_file_search_follow') or 'yes').strip().lower() not in ('no', 'false', '0', 'off')
    # the keys and secrets (the categories and folders named like them, the key-like files): never read, unless the
    # machine says yes - a personal machine of one user who wants to find them too (2026-11-13); even then the
    # contents of key-like files are never read, only their names
    secrets = str(cfg.get('browse_file_search_secrets') or 'no').strip().lower() in ('yes', 'on', 'true', '1')
    s = {'skip_cats': [x.lower() for x in lst('browse_file_search_skip_categories', DEFAULT_SKIP_CATEGORIES)],
         'repos': [x.lower() for x in lst('browse_file_search_repos', [])],
         'skip_repos': [x.lower() for x in lst('browse_file_search_skip_repos', [])],
         'secrets': secrets,
         'skip_dirs': [x.lower() for x in lst('browse_file_search_skip_folders', DEFAULT_SKIP_FOLDERS)],
         'text': [x.lower().lstrip('.') for x in lst('browse_file_search_text', DEFAULT_TEXT)],
         'max_kb': num('browse_file_search_max_kb', DEFAULT_MAX_KB, 1, 65536),
         'depth': num('browse_file_search_depth', DEFAULT_DEPTH, 0, 64),
         'refresh': refresh, 'minutes': minutes, 'follow': follow}
    # what changes the files read inside the artifacts rebuilds the index (a refresh lists only changed folders); the
    # repositories do not (a refresh adds and drops whole artifacts); the keys and secrets count only when on, so an
    # index made before them keeps its signature
    keys = ('skip_cats', 'skip_dirs', 'text', 'max_kb', 'depth') + (('secrets',) if secrets else ())
    s['sig'] = json.dumps({k: s[k] for k in keys}, sort_keys=True)
    return s


# ------------------------------------------------------------------ the database

def _connect(path, write=False):
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    con.execute('pragma busy_timeout=30000')
    if write:
        con.execute('pragma journal_mode=wal')
        con.execute('pragma synchronous=normal')
    return con


def _fts_create(con, name, column):
    """A contentless FTS5 table whose rows can be deleted without their text (contentless_delete, SQLite 3.43+); on an
    older SQLite a plain contentless one - its rows of files gone stay until a rebuild, unseen (every answer joins
    the files table)."""
    opts = "content='', tokenize='unicode61 remove_diacritics 2'"
    try:
        con.execute('create virtual table %s using fts5(%s, %s, contentless_delete=1)' % (name, column, opts))
        return True
    except sqlite3.OperationalError:
        con.execute('create virtual table %s using fts5(%s, %s)' % (name, column, opts))
        return False


def _create(path, sig):
    for p in (path, path + '-wal', path + '-shm', path + '-journal'):
        try:
            os.remove(p)
        except OSError:
            pass
    con = _connect(path, write=True)
    con.execute('create table meta(key text primary key, value text)')
    con.execute('create table arts(uid text primary key, cat text, repo text, root text, seen integer)')
    con.execute('create table dirs(id integer primary key, uid text, rel text, mtime_ns integer, seen integer, unique(uid, rel))')
    # AUTOINCREMENT: an id is never given again - on an SQLite without contentless_delete the word rows of a file
    # gone or changed stay behind under its old id, unseen as long as no other file gets that id
    con.execute('create table files(id integer primary key autoincrement, uid text, dir_id integer, rel text, name text, '
                'ext text, size integer, mtime_ns integer, state integer, seen integer, unique(uid, rel))')
    con.execute('create index files_dir on files(dir_id)')
    con.execute('create index files_state on files(state)')
    con.execute('create index files_ext on files(ext)')
    deletable = _fts_create(con, 'names', 'words')
    _fts_create(con, 'texts', 'body')
    con.execute("create virtual table names_v using fts5vocab(names, 'row')")
    con.execute("create virtual table texts_v using fts5vocab(texts, 'row')")
    con.execute('create table vocab(kind text, term text, docs integer)')
    con.execute('create index vocab_kind on vocab(kind, term)')
    # the partial words: a trigram index over the terms themselves (measured 2026-11-12 on 3.7 million terms: 1-2 ms
    # against a 900 ms scan with LIKE), one per index, fed with the new terms after every pass (never emptied: a term
    # whose files are gone finds nothing; a rebuild starts them anew)
    try:
        con.execute("create virtual table vt using fts5(term, tokenize='trigram')")
        con.execute("create virtual table vn using fts5(term, tokenize='trigram')")
        trigram = True
    except sqlite3.OperationalError:                   # an SQLite before 3.34: the LIKE scan of the vocabulary
        trigram = False
    for k, v in (('format', str(FORMAT)), ('sig', sig), ('deletable', '1' if deletable else '0'), ('phase', 'new'),
                 ('trigram', '1' if trigram else '0'), ('sqlite', sqlite3.sqlite_version)):
        con.execute('insert into meta(key, value) values (?, ?)', (k, v))
    con.close()


def _meta(con):
    return dict(con.execute('select key, value from meta').fetchall())


def _set_meta(con, **kw):
    for k, v in kw.items():
        con.execute('insert or replace into meta(key, value) values (?, ?)', (k, str(v)))


def db_path(folder):
    return os.path.join(folder, DB_FILE) if folder else ''


def usable(path, sig=None):
    """Whether the database exists and is of this format (and of these settings, when a signature is given)."""
    if not path or not os.path.isfile(path):
        return False
    try:
        con = _connect(path)
        try:
            m = _meta(con)
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return m.get('format') == str(FORMAT) and (sig is None or m.get('sig') == sig)


# ------------------------------------------------------------------ the lock between processes

def _take_lock(folder):
    """The lock of the building process (a file with its pid and time): True when taken. A stale one - of a process
    that is gone, or not touched for LOCK_STALE (a builder touches its lock as it works: _Build.progress) - is taken
    over; one still being written (no pid in it yet) is judged by its time alone."""
    p = os.path.join(folder, LOCK_FILE)
    for _ in range(2):
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(fd, 'w') as f:
                f.write('%d %d' % (os.getpid(), int(time.time())))
            return True
        except FileExistsError:
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    words = f.read().split()
                alive = _pid_exists(words[0]) if words else True
            except OSError:
                alive = True
            try:
                stale = not alive or time.time() - os.path.getmtime(p) > LOCK_STALE
            except OSError:                             # gone meanwhile: try again
                stale = True
            if not stale:
                return False
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            except OSError:
                return False
    return False


def _drop_lock(folder):
    try:
        os.remove(os.path.join(folder, LOCK_FILE))
    except OSError:
        pass


def _pid_exists(pid):
    """The engine's own check (psutil's rules: a process this one may not look at exists too)."""
    from cmeta.utils.sys import pid_exists
    return pid_exists(pid)


# ------------------------------------------------------------------ the walk

def _ext(name):
    n = name.lower()
    for two in ('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst'):
        if n.endswith(two):
            return two[1:]
    i = n.rfind('.')
    return n[i + 1:] if i > 0 else ''


def _reserved(name):
    return name.split('.')[0].lower() in RESERVED


def _list_dir(folder, skip_dirs, top=False, secrets=False):
    """One folder listed: (files: [(name, size, mtime_ns)], subfolders: [name]) - dot-entries, the skip list and
    symlinks left out, and the folders of keys and secrets and the key-like files unless secrets; at the top of an
    artifact its meta files too (the search of the artifacts reads them already). None when it cannot be read."""
    try:
        with os.scandir(folder) as it:
            entries = list(it)
    except OSError:
        return None
    files, subs = [], []
    for e in entries:
        name = e.name
        if name.startswith('.') or (top and name.lower().startswith(('_cmeta.', '_desc.'))):
            continue
        try:
            if e.is_dir(follow_symlinks=False):
                if name.lower() in skip_dirs or (not secrets and SECRET_DIR_RE.search(name)):
                    continue
                subs.append(name)
                continue
            if not e.is_file(follow_symlinks=False) or (not secrets and SECRET_FILE_RE.search(name)):
                continue
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        files.append((name, int(st.st_size), int(st.st_mtime_ns)))
    return files, subs


def _words_of(rel):
    """The words of a path for the names index: its parts cut as unicode61 cuts them (so "plan-v2_final.md" gives
    plan, v2, final, md and "20250331" stays one word)."""
    return ' '.join(WORD_RE.findall(rel))


class _Build:
    """One pass over the artifacts: the whole walk (first time, a rebuild, a change of settings), else the sweep."""

    def __init__(self, path, items, s, stamp):
        self.path, self.items, self.s, self.stamp = path, items, s, stamp
        self.lock = os.path.join(os.path.dirname(path), LOCK_FILE)
        self.touched = time.monotonic()
        self.con = _connect(path, write=True)
        self.deletable = _meta(self.con).get('deletable') == '1'
        self.text_exts = set(s['text'])
        self.max_bytes = s['max_kb'] * 1024
        self.n_files = self.n_dirs = self.n_read = 0

    def close(self):
        self.con.close()

    def progress(self, phase, done, total):
        with _lock:
            _state.update(phase=phase, done=done, total=total)
        _set_meta(self.con, phase=phase, done=done, total=total)
        if time.monotonic() - self.touched > LOCK_TOUCH:  # the lock kept fresh: a long first build is not "stale"
            self.touched = time.monotonic()
            try:
                os.utime(self.lock)
            except OSError:
                pass

    # -- the names
    def walk_all(self):
        """Every artifact walked whole (the first build, a rebuild)."""
        self.con.execute('begin')
        total = len(self.items)
        for n, it in enumerate(self.items):
            self.walk_artifact(it, whole=True)
            if n % 50 == 0:
                self.con.execute('commit')
                self.progress('names', n, total)
                self.con.execute('begin')
        self.drop_unseen()
        self.con.execute('commit')
        self.progress('names', total, total)

    def sweep(self, dirty_uids, partial=False):
        """The artifacts cMeta changed (dirty_uids), new or moved walked whole and the artifacts gone dropped; then,
        unless partial, the folders whose time changed listed again and the text files whose size or time changed
        marked to read again (partial: what cMeta's own index change touched, nothing else looked at)."""
        known = {r[0]: r for r in self.con.execute('select uid, root from arts')}
        self.con.execute('begin')
        total = len(self.items)
        walked = 0
        for n, it in enumerate(self.items):
            was = known.get(it['uid'])
            if was is None or was[1] != it['path'] or it['uid'] in dirty_uids:
                self.walk_artifact(it, whole=True)
                walked += 1
            else:
                self.con.execute('update arts set seen = ? where uid = ?', (self.stamp, it['uid']))
            if n % 200 == 0:
                self.con.execute('commit')
                self.progress('sweep', n, total)
                self.con.execute('begin')
        self.con.execute('commit')
        self.n_walked = walked
        if partial:
            self.con.execute('begin')
            # the folders of the artifacts kept as they were: seen now, so that nothing of theirs is dropped
            self.con.execute('update dirs set seen = ? where uid in (select uid from arts where seen = ?) and seen != ?',
                             (self.stamp, self.stamp, self.stamp))
            self.drop_unseen()
            self.con.execute('commit')
            return
        # the folders of the artifacts kept: a changed time -> that folder listed again
        rows = self.con.execute('select d.id, d.uid, d.rel, d.mtime_ns, a.root from dirs d join arts a on a.uid = d.uid '
                                'where a.seen = ? and d.seen != ?', (self.stamp, self.stamp)).fetchall()
        self.con.execute('begin')
        for n, (did, uid, rel, mtime_ns, root) in enumerate(rows):
            full = os.path.join(root, *rel.split('/')) if rel else root
            try:
                now = int(os.stat(full).st_mtime_ns)
            except OSError:
                now = None
            if now is None:
                self.drop_dir(did)
            elif now != mtime_ns:
                self.list_into(uid, root, rel, did, depth=rel.count('/') + 1 if rel else 0, whole=False)
            else:
                self.con.execute('update dirs set seen = ? where id = ?', (self.stamp, did))
            if n % 500 == 0:
                self.con.execute('commit')
                self.progress('sweep', n, len(rows))
                self.con.execute('begin')
                time.sleep(0.005)
        self.drop_unseen()
        self.con.execute('commit')
        # the text files: a changed size or time is read again
        rows = self.con.execute('select f.id, f.rel, f.size, f.mtime_ns, a.root from files f join arts a on a.uid = f.uid '
                                'where f.state in (1, 2)').fetchall()
        self.con.execute('begin')
        for n, (fid, rel, size, mtime_ns, root) in enumerate(rows):
            try:
                st = os.stat(os.path.join(root, *rel.split('/')))
                changed = int(st.st_size) != size or int(st.st_mtime_ns) != mtime_ns
            except OSError:
                changed = False                          # gone: the folder's time dropped it above, or will
            if changed:
                fid = self.forget_text(fid)
                self.con.execute('update files set size = ?, mtime_ns = ?, state = 3 where id = ?',
                                 (int(st.st_size), int(st.st_mtime_ns), fid))
            if n % 500 == 0:
                self.con.execute('commit')
                self.con.execute('begin')
                time.sleep(0.005)
        self.con.execute('commit')
        self.progress('sweep', len(rows), len(rows))

    def walk_artifact(self, it, whole):
        self.con.execute('insert or replace into arts(uid, cat, repo, root, seen) values (?, ?, ?, ?, ?)',
                         (it['uid'], it['cat'], it['repo'], it['path'], self.stamp))
        if not os.path.isdir(it['path']):
            return
        self.list_into(it['uid'], it['path'], '', None, 0, whole=True)

    def list_into(self, uid, root, rel, did, depth, whole):
        """A folder (rel inside the artifact) listed into the tables; whole: its subfolders too, recursively."""
        stack = [(rel, did, depth)]
        while stack:
            rel, did, depth = stack.pop()
            full = os.path.join(root, *rel.split('/')) if rel else root
            got = _list_dir(full, self.s['skip_dirs'], top=not rel, secrets=self.s.get('secrets', False))
            if got is None:
                if did is not None:
                    self.drop_dir(did)
                continue
            files, subs = got
            try:
                mtime_ns = int(os.stat(full).st_mtime_ns)
            except OSError:
                mtime_ns = 0
            if did is None:
                self.con.execute('insert or ignore into dirs(uid, rel, mtime_ns, seen) values (?, ?, ?, ?)',
                                 (uid, rel, mtime_ns, self.stamp))
                did = self.con.execute('select id from dirs where uid = ? and rel = ?', (uid, rel)).fetchone()[0]
            self.con.execute('update dirs set mtime_ns = ?, seen = ? where id = ?', (mtime_ns, self.stamp, did))
            self.n_dirs += 1
            # the files of this folder: new ones inserted, known ones kept (a changed text file is read again)
            known = {r[0]: r for r in self.con.execute('select name, id, size, mtime_ns, state from files where dir_id = ?', (did,))}
            seen_names = set()
            for name, size, mtime_ns_f in files:
                seen_names.add(name)
                frel = rel + '/' + name if rel else name
                ext = _ext(name)
                kind = 0 if (ext not in self.text_exts or _reserved(name) or SECRET_FILE_RE.search(name)) else 3
                row = known.get(name)
                if row is None:
                    self.con.execute('insert or replace into files(uid, dir_id, rel, name, ext, size, mtime_ns, state, seen) '
                                     'values (?, ?, ?, ?, ?, ?, ?, ?, ?)', (uid, did, frel, name, ext, size, mtime_ns_f, kind, self.stamp))
                    fid = self.con.execute('select id from files where uid = ? and rel = ?', (uid, frel)).fetchone()[0]
                    self.con.execute('insert into names(rowid, words) values (?, ?)', (fid, _words_of(frel)))
                    self.n_files += 1
                else:
                    fid, old_size, old_mtime, state = row[1], row[2], row[3], row[4]
                    if state in (1, 2) and (old_size != size or old_mtime != mtime_ns_f):
                        fid = self.forget_text(fid)
                        state = 3
                    elif state == 3 and kind == 0:
                        state = 0
                    self.con.execute('update files set size = ?, mtime_ns = ?, state = ?, seen = ? where id = ?',
                                     (size, mtime_ns_f, state, self.stamp, fid))
            for name, row in known.items():
                if name not in seen_names:
                    self.drop_file(row[1])
            # the subfolders: new ones walked whole; known ones only when the whole walk asks
            subs_known = {r[1].rsplit('/', 1)[-1]: r[0] for r in self.con.execute(
                "select id, rel from dirs where uid = ? and rel like ? and rel not like ? and rel != ''",
                (uid, (rel + '/%' if rel else '%'), (rel + '/%/%' if rel else '%/%')))}
            for name in subs:
                srel = rel + '/' + name if rel else name
                sid = subs_known.pop(name, None)
                if depth + 1 > self.s['depth']:
                    continue
                if sid is None or whole:
                    stack.append((srel, sid, depth + 1))
                else:
                    self.con.execute('update dirs set seen = ? where id = ?', (self.stamp, sid))
            for name, sid in subs_known.items():                   # a subfolder gone (or a symlink now)
                self.drop_dir(sid)

    def drop_file(self, fid):
        if self.deletable:                          # a contentless_delete table: a plain delete by rowid
            self.con.execute('delete from texts where rowid = ?', (fid,))
            self.con.execute('delete from names where rowid = ?', (fid,))
        self.con.execute('delete from files where id = ?', (fid,))     # (else its rows stay, unseen: see _create)

    def forget_text(self, fid):
        """The old text of a changed file out of the answers -> the file's id from now on. A contentless_delete table
        deletes its row; an older SQLite cannot delete a contentless row without its text (SQLite before 3.43, the
        Python 3.9 of python.org among them), so the file gets a new id - never given before (AUTOINCREMENT) - and its
        name anew: the old rows stay behind, unseen (every answer joins the files table), until a rebuild."""
        if self.deletable:
            self.con.execute('delete from texts where rowid = ?', (fid,))
            return fid
        row = self.con.execute('select uid, dir_id, rel, name, ext, size, mtime_ns, state, seen from files where id = ?',
                               (fid,)).fetchone()
        if row is None:
            return fid
        self.con.execute('delete from files where id = ?', (fid,))
        new = self.con.execute('insert into files(uid, dir_id, rel, name, ext, size, mtime_ns, state, seen) '
                               'values (?, ?, ?, ?, ?, ?, ?, ?, ?)', row).lastrowid
        self.con.execute('insert into names(rowid, words) values (?, ?)', (new, _words_of(row[2])))
        return new

    def drop_dir(self, did):
        rel = self.con.execute('select uid, rel from dirs where id = ?', (did,)).fetchone()
        if not rel:
            return
        uid, rel = rel
        ids = [r[0] for r in self.con.execute('select id from dirs where uid = ? and (id = ? or rel like ?)',
                                              (uid, did, rel + '/%' if rel else '%'))]
        for d in ids:
            for (fid,) in self.con.execute('select id from files where dir_id = ?', (d,)).fetchall():
                self.drop_file(fid)
            self.con.execute('delete from dirs where id = ?', (d,))

    def drop_unseen(self):
        """The artifacts not in this pass (gone, or in a category now skipped) and their files and folders."""
        for (uid,) in self.con.execute('select uid from arts where seen != ?', (self.stamp,)).fetchall():
            for (fid,) in self.con.execute('select id from files where uid = ?', (uid,)).fetchall():
                self.drop_file(fid)
            self.con.execute('delete from dirs where uid = ?', (uid,))
            self.con.execute('delete from arts where uid = ?', (uid,))
        # folders of kept artifacts the pass did not see (inside a whole walk that lost them)
        for (did,) in self.con.execute('select d.id from dirs d join arts a on a.uid = d.uid where d.seen != ? and a.seen = ?',
                                       (self.stamp, self.stamp)).fetchall():
            self.drop_dir(did)

    # -- the texts
    def read_texts(self):
        """Every file marked to read (state 3): its text into the index."""
        total = self.con.execute('select count(*) from files where state = 3').fetchone()[0]
        done = 0
        self.progress('texts', 0, total)
        while True:
            rows = self.con.execute('select f.id, f.rel, f.ext, a.root from files f join arts a on a.uid = f.uid '
                                    'where f.state = 3 limit ?', (BATCH,)).fetchall()
            if not rows:
                break
            self.con.execute('begin')
            for fid, rel, ext, root in rows:
                text = read_text(os.path.join(root, *rel.split('/')), ext, self.max_bytes)
                if text:
                    self.con.execute('insert into texts(rowid, body) values (?, ?)', (fid, text))
                    self.n_read += 1
                self.con.execute('update files set state = ? where id = ?', (1 if text else 2, fid))
            self.con.execute('commit')
            done += len(rows)
            self.progress('texts', done, total)
            with _lock:
                stop = _state.get('mode') == 'rebuild'
            if stop:
                break                                   # a rebuild was asked meanwhile: this pass ends here
        self.progress('texts', done, total)

    def vocab(self):
        """The vocabulary tables of both indexes copied into one plain table (the terms with how many files hold
        each; a point lookup by term, the LIKE scan of the fallback), and the terms new since the last pass added to
        the trigram indexes (vt for the texts, vn for the names)."""
        trigram = _meta(self.con).get('trigram') == '1'
        self.con.execute('begin')
        self.con.execute('create temp table nv as select term, doc from names_v')
        self.con.execute('create temp table tv as select term, doc from texts_v')
        if trigram:
            self.con.execute("insert into vn(term) select term from nv where term not in (select term from vocab where kind = 'n')")
            self.con.execute("insert into vt(term) select term from tv where term not in (select term from vocab where kind = 't')")
        self.con.execute('delete from vocab')
        self.con.execute("insert into vocab(kind, term, docs) select 'n', term, doc from nv")
        self.con.execute("insert into vocab(kind, term, docs) select 't', term, doc from tv")
        self.con.execute('drop table nv')
        self.con.execute('drop table tv')
        self.con.execute('commit')

    def counts(self):
        f = self.con.execute('select count(*) from files').fetchone()[0]
        d = self.con.execute('select count(*) from dirs').fetchone()[0]
        t = self.con.execute('select count(*) from files where state = 1').fetchone()[0]
        a = self.con.execute('select count(*) from arts').fetchone()[0]
        return f, d, t, a


# ------------------------------------------------------------------ the readers

def read_text(path, ext, max_bytes):
    """The text of a file for the index: '' when it is not readable as text (binary, a reserved name, an error)."""
    name = os.path.basename(path)
    if _reserved(name):
        return ''
    try:
        if ext in OFFICE:
            return _office_text(path, ext, max_bytes)
        with open(path, 'rb') as f:
            raw = f.read(max_bytes)
    except (OSError, ValueError):
        return ''
    if not raw or b'\x00' in raw[:4096]:
        return ''
    text = _decode(raw)
    if ext in ('html', 'htm'):
        text = TAG_RE.sub(' ', text)
    return clean_text(text)


# The tokens that are not words and would only swell the index and its vocabulary (measured 2026-11-12 on the user's
# home: 3.7 million distinct terms, 660,000 of them words - the rest UIDs, hashes, timestamps, base64, glued strings):
# a run of 25 letters or digits and more; a hexadecimal run of 16 and more (a UID, a hash); a number of 9 digits and
# more; a mixed run of letters and digits of 13 and more (an identifier, a timestamp). A date (20250331), a version
# (v2, 3.14), a model (gpt4o) and every word stay. Not applied to the names of the files.
NOISE_RE = re.compile(r'(?<![^\W_])(?:[^\W_]{25,}|[0-9a-fA-F]{16,}|[0-9]{9,}|(?=[^\W_]{13,}(?![^\W_]))[^\W\d_]*\d[^\W_]*)(?![^\W_])')


def clean_text(text):
    """The text without its noise tokens (NOISE_RE), each replaced by a blank."""
    return NOISE_RE.sub(' ', text)


def _decode(raw):
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            return raw.decode('utf-16')
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def _office_text(path, ext, max_bytes):
    """The text of a docx / pptx / xlsx: the XML parts that hold it, their tags dropped (the standard library's
    zipfile; no library for the formats)."""
    out, size = [], 0
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                n = info.filename
                if not any(n == p or (p.endswith('/') and n.startswith(p) and n.endswith('.xml')) for p in OFFICE[ext]):
                    continue
                if n.startswith('ppt/slides/') and not n.startswith('ppt/slides/slide'):
                    continue
                with z.open(info) as f:
                    xml = f.read(max_bytes).decode('utf-8', errors='replace')
                # the texts are what the tags enclose; a space between them keeps the words apart
                text = WS_RE.sub(' ', TAG_RE.sub(' ', xml.replace('</a:p>', '\n').replace('</w:p>', '\n')))
                text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                out.append(text)
                size += len(text)
                if size >= max_bytes:
                    break
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
        return ''
    return clean_text(' '.join(out)[:max_bytes])


# ------------------------------------------------------------------ the build thread

def request(folder, items, s, mode='partial', dirty_uids=None):
    """A pass asked for - 'rebuild' (from nothing), 'sweep' (every folder's time, every text file's size and time:
    the Refresh button, the server's start), 'partial' (the artifacts new, gone, moved or named in dirty_uids: what
    cMeta's own index change touched) - started in a background thread when none runs (and another process does not
    hold the lock); a running one picks the request up when it ends, the strongest mode asked for wins. items: the
    catalog's artifacts (uid, cat, repo, path), without the hidden and skipped categories. Returns the thread (None
    when none could start)."""
    rank = {'partial': 0, 'sweep': 1, 'rebuild': 2}
    with _lock:
        _state['want'] += 1
        if dirty_uids:
            _state['dirty'] |= set(dirty_uids)
        if rank.get(mode, 0) > rank.get(_state.get('mode', 'partial'), 0):
            _state['mode'] = mode
        _state['db'] = db_path(folder)
        _state['items'] = items
        if _state['building']:
            return _state['thread']
        _state['building'] = True
        t = threading.Thread(target=_run, args=(folder, s), name='cserver.browse file index', daemon=True)
        _state['thread'] = t
        t.start()
        return t


def due(s):
    """Whether a routine sweep is due: the refresh setting in minutes, and the last pass older than that."""
    with _lock:
        return (s['refresh'] == 'minutes' and not _state['building']
                and time.monotonic() - _state['last'] > s['minutes'] * 60)


def started_once():
    """Whether this process has run (or started) a pass already: the sweep of the server's start happens once."""
    with _lock:
        return bool(_state.get('once'))


def running():
    """The thread of the pass that runs in this process, or None."""
    with _lock:
        return _state['thread'] if _state['building'] else None


def _run(folder, s):
    try:
        while True:
            with _lock:
                want = _state['want']
                dirty = _state['dirty']
                items = _state['items']
                _state['dirty'] = set()
                mode = _state.pop('mode', 'partial')
                _state['once'] = True
            if not _take_lock(folder):
                with _lock:
                    _state['error'] = 'another server process builds the file index'
                    _state['done_want'] = want
            else:
                try:
                    _pass(folder, items, s, dirty, mode)
                    with _lock:
                        _state['error'] = ''
                except Exception as e:
                    with _lock:
                        _state['error'] = '%s: %s' % (type(e).__name__, e)
                finally:
                    _drop_lock(folder)
                with _lock:
                    _state['done_want'] = want
                    _state['last'] = time.monotonic()
            with _lock:
                if _state['want'] == want:
                    _state['building'] = False
                    _state['phase'] = ''
                    return
    except Exception as e:
        with _lock:
            _state.update(building=False, error='%s: %s' % (type(e).__name__, e))


def _pass(folder, items, s, dirty, mode):
    """One pass of the given mode (a database missing, of another format or of other settings is rebuilt whatever
    the mode); the texts of the files marked to read, then the vocabulary; the meta says what was done."""
    path = db_path(folder)
    fresh = mode == 'rebuild' or not usable(path, s['sig'])
    if fresh:
        _create(path, s['sig'])
    # the stamp of this pass: what it saw; always above the last one (two passes within a second must differ)
    con = _connect(path)
    try:
        last = int(_meta(con).get('stamp') or 0)
    finally:
        con.close()
    stamp = max(int(time.time() * 1000), last + 1)
    b = _Build(path, items, s, stamp)
    _set_meta(b.con, stamp=stamp, mode='rebuild' if fresh else mode)
    try:
        t0 = time.monotonic()
        if fresh or _meta(b.con).get('phase') in ('new', 'names'):
            b.walk_all()
            mode = 'rebuild'
        else:
            b.sweep(dirty, partial=(mode == 'partial'))
        t1 = time.monotonic()
        b.read_texts()
        b.vocab()
        f, d, t, a = b.counts()
        _set_meta(b.con, phase='idle', built=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                  files=f, dirs=d, texts=t, arts=a, names_s=round(t1 - t0, 1), texts_s=round(time.monotonic() - t1, 1),
                  last_mode=mode, last_walked=getattr(b, 'n_walked', a), last_read=b.n_read)
    finally:
        b.close()


def status(folder, s=None):
    """What a page or the command line says of the index: this process's view of the thread and the database's meta
    (written by whichever process builds)."""
    path = db_path(folder)
    with _lock:
        out = {'on': s is not None, 'db': path, 'building': _state['building'], 'phase': _state['phase'],
               'done': _state['done'], 'total': _state['total'], 'error': _state['error']}
    if not path or not os.path.isfile(path):
        out.update(ready=False, files=0, dirs=0, texts=0, arts=0, built='', size=0)
        return out
    try:
        con = _connect(path)
        try:
            m = _meta(con)
        finally:
            con.close()
    except sqlite3.Error as e:
        out.update(ready=False, error=out['error'] or str(e))
        return out
    size = 0
    for p in (path, path + '-wal'):
        try:
            size += os.path.getsize(p)
        except OSError:
            pass
    stale = s is not None and m.get('sig') != s['sig']
    out.update(ready=m.get('format') == str(FORMAT) and m.get('phase') not in ('new', 'names') and not stale,
               files=int(m.get('files') or 0), dirs=int(m.get('dirs') or 0), texts=int(m.get('texts') or 0),
               arts=int(m.get('arts') or 0), built=m.get('built', ''), size=size, settings_changed=stale,
               db_phase=m.get('phase', ''), db_done=int(m.get('done') or 0), db_total=int(m.get('total') or 0),
               names_s=m.get('names_s', ''), texts_s=m.get('texts_s', ''), deletable=m.get('deletable') == '1',
               lock=os.path.isfile(os.path.join(folder, LOCK_FILE)))
    if not out['building'] and out['lock']:
        out['building'] = True                      # another process builds: its progress is in the database
        out['phase'], out['done'], out['total'] = out['db_phase'], out['db_done'], out['db_total']
    return out


def stats(folder, top=40):
    """What the index holds, for the Statistics dialog (the user, 2026-11-12: "a button to show all the current stats
    ... extremely useful"): the totals, the categories by files (artifacts, files, MB, text files, folders, the top
    extensions), the repositories, the extensions by files, the folders with the most files directly in them, the
    !AI parts, the depths - all from the database (no file touched)."""
    path = db_path(folder)
    if not usable(path):
        return {'ready': False}
    con = _connect(path)
    try:
        t0 = time.monotonic()
        m = _meta(con)
        out = {'ready': True, 'built': m.get('built', ''), 'files': int(m.get('files') or 0), 'dirs': int(m.get('dirs') or 0),
               'texts': int(m.get('texts') or 0), 'arts': int(m.get('arts') or 0),
               'bytes': con.execute('select coalesce(sum(size), 0) from files').fetchone()[0]}
        out['categories'] = [{'cat': r[0], 'arts': r[1], 'files': r[2], 'bytes': r[3], 'texts': r[4]} for r in con.execute(
            'select a.cat, count(distinct a.uid), count(f.id), coalesce(sum(f.size), 0), '
            'sum(case when f.state = 1 then 1 else 0 end) from arts a left join files f on f.uid = a.uid '
            'group by a.cat order by count(f.id) desc')]
        out['repos'] = [{'repo': r[0], 'arts': r[1], 'files': r[2], 'bytes': r[3]} for r in con.execute(
            'select a.repo, count(distinct a.uid), count(f.id), coalesce(sum(f.size), 0) from arts a '
            'left join files f on f.uid = a.uid group by a.repo order by count(f.id) desc')]
        out['exts'] = [{'ext': r[0] or '(none)', 'files': r[1], 'bytes': r[2]} for r in con.execute(
            'select ext, count(*), sum(size) from files group by ext order by count(*) desc limit ?', (top,))]
        out['folders'] = [{'cat': r[0], 'alias': os.path.basename(r[1].rstrip('\\/')) or r[1], 'rel': r[2], 'files': r[3]}
                          for r in con.execute(
            'select a.cat, a.root, d.rel, count(f.id) as n from files f join dirs d on d.id = f.dir_id '
            'join arts a on a.uid = d.uid group by f.dir_id order by n desc limit ?', (top // 2,))]
        ai = {}
        for rel, size in con.execute("select rel, size from files where rel like '%!AI/%' or rel like '!AI/%'"):
            after = rel.split('!AI/', 1)[1]
            part = after.split('/', 1)[0] if '/' in after else '(top)'
            if part not in ('memory', 'skills', 'log', 'tmp', 'pending', '(top)'):
                part = 'other'
            c = ai.setdefault(part, [0, 0])
            c[0] += 1
            c[1] += size
        out['ai'] = [{'part': k, 'files': v[0], 'bytes': v[1]} for k, v in sorted(ai.items(), key=lambda x: -x[1][0])]
        out['depths'] = [{'depth': r[0], 'files': r[1]} for r in con.execute(
            "select length(rel) - length(replace(rel, '/', '')) as depth, count(*) from files group by depth order by depth")]
        out['big'] = [{'cat': r[0], 'alias': os.path.basename(r[1].rstrip('\\/')) or r[1], 'rel': r[2], 'bytes': r[3]}
                      for r in con.execute('select a.cat, a.root, f.rel, f.size from files f join arts a on a.uid = f.uid '
                                           'order by f.size desc limit 20')]
        out['ms'] = int((time.monotonic() - t0) * 1000)
        return out
    finally:
        con.close()


def clear(folder):
    """The database and the lock removed: the next start builds anew."""
    path = db_path(folder)
    n = 0
    for p in (path, path + '-wal', path + '-shm', path + '-journal', os.path.join(folder, LOCK_FILE)):
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    return n


# ------------------------------------------------------------------ the query

class Query:
    """The questions of one search, answered from the database: which artifacts hold a word in their files' names
    or texts (and which files), a file by its name or a pattern. Opened once per search; nothing cached between
    searches (the index changes under it)."""

    def __init__(self, folder):
        self.path = db_path(folder)
        self.con = _connect(self.path) if usable(self.path) else None
        self.ms = 0
        self.terms_capped = []                      # the words whose partial match hit the term cap
        self.trigram = bool(self.con is not None and _meta(self.con).get('trigram') == '1')

    def close(self):
        if self.con is not None:
            self.con.close()
            self.con = None

    @property
    def ready(self):
        return self.con is not None

    def terms(self, kind, word):
        """The terms of the vocabulary a partial word stands for - the word inside a term, * and ? as wildcards: the
        trigram index of the terms narrows them (every literal part of three letters or more), LIKE decides; without
        a part of three letters, or on an SQLite without trigram, LIKE alone (a scan). -> the terms (VOCAB_MAX at most,
        the most frequent first)."""
        w = word.lower().replace('%', '').replace('_', ' ')
        pat = '%' + ''.join('%' if c == '*' else '_' if c == '?' else c for c in w).strip('%') + '%'
        if pat == '%%' or pat == '%':
            return []
        parts = [p for p in re.split(r'[*?]', w) if len(p) >= 3]
        table = {'n': 'vn', 't': 'vt'}[kind]
        rows = None
        if parts and self.trigram:
            q = ' AND '.join('"%s"' % p.replace('"', '""') for p in parts)
            try:
                rows = self.con.execute(
                    'select v.term from %s x join vocab v on v.kind = ? and v.term = x.term where x.%s match ? and v.term like ? '
                    'order by v.docs desc limit ?' % (table, table), (kind, q, pat, VOCAB_MAX + 1)).fetchall()
            except sqlite3.OperationalError:
                rows = None
        if rows is None:
            rows = self.con.execute('select term from vocab where kind = ? and term like ? order by docs desc limit ?',
                                    (kind, pat, VOCAB_MAX + 1)).fetchall()
        if len(rows) > VOCAB_MAX:
            self.terms_capped.append(word)
            rows = rows[:VOCAB_MAX]
        return [r[0] for r in rows]

    def _match(self, table, kind, word):
        """The file ids whose names (kind 'n') or texts ('t') hold the word - a phrase (with a blank) as an FTS5
        phrase of whole words, a single word as any term it is part of."""
        t0 = time.monotonic()
        parts = WORD_RE.findall(word) if ' ' in word else [word]
        if len(parts) > 1:
            q = '"' + ' '.join(parts) + '"'
        else:
            terms = self.terms(kind, word)
            if not terms:
                self.ms += int((time.monotonic() - t0) * 1000)
                return set()
            q = ' OR '.join('"%s"' % t.replace('"', '""') for t in terms)
        try:
            ids = {r[0] for r in self.con.execute('select rowid from %s where %s match ?' % (table, table), (q,))}
        except sqlite3.OperationalError:
            ids = set()
        self.ms += int((time.monotonic() - t0) * 1000)
        return ids

    def ids_with(self, word, names=True, texts=True):
        """{file id: 'n' | 't'} of the files whose name ('n' - a name hit wins) or text ('t') holds the word."""
        out = {}
        if self.con is None:
            return out
        if texts:
            for i in self._match('texts', 't', word):
                out[i] = 't'
        if names:
            for i in self._match('names', 'n', word):
                out[i] = 'n'
        return out

    def exact_ids(self, word, names=True, texts=True):
        """(the files whose names, the files whose texts hold the word as a whole word - a phrase: its words in a
        row): what ranks a file above one that holds it only inside a longer word ("vera" in "several"), and a file
        named by the words above one whose text holds them. A word with * or ?: none."""
        out = (set(), set())
        if self.con is None or '*' in word or '?' in word:
            return out
        parts = WORD_RE.findall(word)
        if not parts:
            return out
        q = '"' + ' '.join(parts) + '"'
        for n, (table, on) in enumerate((('names', names), ('texts', texts))):
            if on:
                try:
                    out[n].update(r[0] for r in self.con.execute('select rowid from %s where %s match ?' % (table, table), (q,)))
                except sqlite3.OperationalError:
                    pass
        return out

    def locate(self, ids):
        """{file id: (uid, rel)} of file ids."""
        out = {}
        if self.con is None:
            return out
        ids = sorted(ids)
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            for fid, uid, rel in self.con.execute('select id, uid, rel from files where id in (%s)' % ','.join('?' * len(chunk)), chunk):
                out[fid] = (uid, rel)
        return out

    def uids_with(self, word, names=True, texts=True):
        """{uid: [(rel, kind)]} of the artifacts whose files hold the word, the files named (PER_ARTIFACT per
        artifact, ('', 'more') beyond)."""
        ids = self.ids_with(word, names, texts)
        found = {}
        for fid, (uid, rel) in sorted(self.locate(ids).items(), key=lambda x: x[1][1].lower()):
            lst = found.setdefault(uid, [])
            if len(lst) < PER_ARTIFACT:
                lst.append((rel, ids[fid]))
            elif len(lst) == PER_ARTIFACT:
                lst.append(('', 'more'))
        return found

    def uids_with_file(self, pattern):
        """{uid: [(rel, 'n')]} of the artifacts holding a file whose path matches: a glob (*, ?) on the path inside
        the artifact, else a part of the name or the path."""
        if self.con is None:
            return {}
        p = pattern.lower()
        if '*' in p or '?' in p:
            like = p.replace('%', '').replace('_', ' ').replace('*', '%').replace('?', '_')
            if '/' not in like:
                like = '%' + like
            rows = self.con.execute('select uid, rel from files where lower(rel) like ? limit 20000', (like,))
        else:
            rows = self.con.execute("select uid, rel from files where instr(lower(rel), ?) > 0 limit 20000", (p,))
        found = {}
        for uid, rel in rows:
            lst = found.setdefault(uid, [])
            if len(lst) < PER_ARTIFACT:
                lst.append((rel, 'n'))
            elif len(lst) == PER_ARTIFACT:
                lst.append(('', 'more'))
        return found

    def files_of(self, uid):
        """The files of one artifact the index knows: [(rel, size, state)]."""
        if self.con is None:
            return []
        return self.con.execute('select rel, size, state from files where uid = ? order by rel', (uid,)).fetchall()


def snippet(root, rel, words, max_bytes=SNIPPET_READ):
    """A line of context around the first word found in the file (read now, its first bytes), the file's own text -
    '' when nothing is found or the file is not readable."""
    path = os.path.join(root, *rel.split('/'))
    text = read_text(path, _ext(os.path.basename(path)), max_bytes)
    if not text:
        return ''
    low = text.lower()
    for w in words:
        w = w.lower().replace('*', '').replace('?', '')
        if not w:
            continue
        i = low.find(w)
        if i < 0:
            continue
        a = max(0, i - SNIPPET_LEN // 3)
        b = min(len(text), i + len(w) + SNIPPET_LEN * 2 // 3)
        piece = WS_RE.sub(' ', text[a:b]).strip()
        return ('... ' if a > 0 else '') + piece + (' ...' if b < len(text) else '')
    return ''
