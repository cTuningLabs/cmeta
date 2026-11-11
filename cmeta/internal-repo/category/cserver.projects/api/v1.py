"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.projects - the home page of cserver: every cserver.* web page plugged into this machine as cards,
grouped by repository, with a search box, pins and copy-URL buttons; under the cards, the version of this
server and where cMeta lives.

    cx app run cserver      ->  http://127.0.0.1:8004/   (the same page as /projects)

There is no registry: the list is discovered from the index - every category whose alias starts with "cserver."
in EVERY plugged repository. A category whose api defines web_ is a page; the others (helper actions,
artifact-only categories) are listed in a footnote. A page whose _cmeta says `card: false` is reached through
links only (cserver.cref needs a cRef to show anything): no card for it, the terminal still lists it. Links are
built from urls['url_server'] (on the engine cserver a page is /<alias without the cserver. prefix>), never
hard-coded.

    cx cserver.projects pages                   the same list in the terminal
    cx cserver.projects pages --repo=aops       only the repositories whose alias contains "aops"
    cx cserver.projects pages --all             also the cserver.* categories that have no page
    cx cserver.projects pages --as_json         as JSON
    ?native_action=projects                     the JSON the page renders (GET or POST on the page URL)
    ?repo=<text>                                the page and its JSON: only the repositories whose alias contains it
    ?dark=1                                     dark theme on the engine cserver (cPlatform passes misc['theme'])

Two keys of the cserver config shape it:

    cx config set cserver --meta.default_page=/projects        what "/" shows (read by the cserver app at
                                                                startup); none = the plain welcome page
    cx config set cserver --meta.hide_repos=a,b*               repositories left off this page (aliases or
                                                                fnmatch patterns); read on every request, and
                                                                their pages stay reachable at their own URLs

The customized view (2026-11-10): the same pages as sections of buttons with names of one's own, arranged in
place - the other way to see this page, chosen with its Customized switch (kept in the browser; off by default:
the cards). Each button is an artifact of this category, cserver.projects::<name>, whose _desc.yaml says

    title:   Browse                the text of its button
    page:    browse                the page it opens on the server that shows it (/browse; a path or ?query may follow)
    url:     https://host:8004/x   or an address of its own (a page of another machine, any link), instead of page
    section: cMeta                 the section it shows in
    order:   10                    its place, the smaller first; a section shows where its first button is
    star:    true                  an important button: a filled one
    note:    ...                   a line shown when the button is pointed at
    newline: true                  the next button of the section starts a line of its own (several lines per section)

so the view lives where its buttons are: a repository that syncs between machines gives each of them the same
view. A section without buttons yet ("+ Section": its name alone) is an artifact of this category too, whose
_desc.yaml holds `kind: section`, its section and its order - no title, page or address: it keeps the section in its
place until it is removed (the x of an empty section in Edit); a button put into it lands after it, and it moves and
is renamed with its section. It is made once from the pages of this machine ("Make my view": a section per repository, a button per
page, in the repository chosen there; none chosen: cserver_projects_create_repo of the default config, else
local); a new button goes to the repository that holds the view. A page the view names that this machine does not
have shows dimmed; the pages of this machine the view does not name are listed under it, to be added.

    cx cserver.projects view                     the view in the terminal (--as_json: as JSON)
    ?native_action=view                          the view as JSON (with the pages it leaves out, the repositories)
    ?native_action=view_make                     the view made from this machine's pages (repo)
    ?native_action=view_save                     a button added or changed (uid, title, page | url, section, star,
                                                 note, newline, before, order)
    ?native_action=view_arrange                  a button moved (uid, section, before), a section moved
                                                 (move_section, before_section) or renamed (section, rename),
                                                 orders set back (orders: Undo)
    ?native_action=view_section                  an empty section made (section: its name), at the end of the view
    ?native_action=view_discard | view_restore   a button deleted (uid) | put back (removed: what discard gave);
                                                 an empty section removed (the uid of its record) | put back

A change is taken from a browser on this machine or one that passed the server's password, and only from a page
of this server; never on the cTuning platform. Another page of this server may draw the view with the board of
files/js/projects.js (CmetaProjects.board) and send its changes here with the request's misc: it names itself in
misc['projects_via'], and what is made records it as the place it was made.
"""

import fnmatch
import html
import json
import math
import os
import re
import traceback

import yaml

from cmeta.category import InitCategory
from cmeta.utils import files

PREFIX = 'cserver.'

# ---------------------------------------------------------------------------------------- the customized view
VIEW_KEYS = ('title', 'page', 'url', 'section', 'order', 'star', 'note', 'newline')   # a button's _desc.yaml, in this order
STEP = 10                       # the distance between two orders numbered again
FINEST = 1.0 / 1024             # the closest two orders may come before all are numbered again
TEXT_MAX = 100                  # at most: a title or a section; a note; an address or a page
NOTE_MAX = 1000
URL_MAX = 4000
NAME_MAX = 100                  # an artifact's name made of a title
TITLE_MAX = 48                  # a card's heading longer than this: the page's name instead
CREATE_REPO_KEY = 'cserver_projects_create_repo'    # of the default config: where a view is made (the engine's rule)
GENERATOR = {'method': 'manual', 'via': 'cserver.projects (the home page of cserver)'}
VIEW_WRITES = {                 # what a browser may send to each change of the view
    'view_make': ('repo',),
    'view_save': ('uid', 'title', 'page', 'url', 'section', 'star', 'note', 'newline', 'before', 'order'),
    'view_arrange': ('uid', 'section', 'before', 'move_section', 'before_section', 'rename', 'orders'),
    'view_section': ('section',),
    'view_discard': ('uid',),
    'view_restore': ('removed',),
}
SECTION_KIND = 'section'        # the kind: in the _desc.yaml of an empty section's record (it has no page or address)

CTRL_RE = re.compile(r'[\x00-\x1f\x7f]')
BAD_SCHEME_RE = re.compile(r'^(?:javascript|data|vbscript):', re.I)   # never kept: they run in the page
SCHEME_RE = re.compile(r'^(?:[a-z][\w+.\-]*:|//)', re.I)               # an address, not a page of this server
PAGE_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-]*(?:[/?#].*)?$')     # a page's name, then a path or a query
UID_RE = re.compile(r'^[0-9a-fA-F]{16}$')
NAME_DROP_RE = re.compile(r' ?[?*"<>|\x00-\x1f]+ ?')
BAD_NAME_RE = re.compile(r'[\\/:*?"<>|,\x00-\x1f]')

_DESC = {}      # what a button's _desc.yaml held while it is unchanged: path -> ((mtime, size), dict)


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
    """Repository aliases or fnmatch patterns, from a list or a comma-separated string, lower-cased."""
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(',')
    return [str(v).strip().lower() for v in value if str(v).strip()]


def _hidden(repo, patterns):
    """True when the repository alias matches one of the patterns (case-insensitive)."""
    repo = (repo or '').lower()
    return any(fnmatch.fnmatchcase(repo, p) for p in patterns)


# ---------------------------------------------------------------------------------------- the customized view
def _card_title(page):
    """The heading of a page's card (as projects.js splits its name): the name's part before " - ", ": " or " – ",
    the whole name when it has none, the page's own name when that part is long or there is no name."""
    name = str(page.get('name') or '').strip()
    if not name:
        return page['page']
    cut = -1
    for s in (' - ', ': ', ' – '):
        i = name.find(s)
        if i > 0 and (cut < 0 or i < cut):
            cut = i
    head = name[:cut] if cut > 0 else name
    return page['page'] if len(head) > TITLE_MAX else head


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _yes(value):
    return value in (True, 1, '1', 'true', 'True', 'yes', 'on')


def _tidy(value):
    """An order as it is written: a whole number as an int, else at most 6 decimals."""
    value = round(float(value), 6)
    return int(value) if value.is_integer() else value


def _clean_text(value, what, limit, need=False, lines=False):
    """A title, a section or a note as kept: its ends trimmed, control characters as spaces (a note keeps its line
    ends) -> (the text, an error)."""
    t = re.sub(r'\r\n?', '\n', str(value if value is not None else ''))
    t = re.sub(r'[\x00-\x09\x0b-\x1f\x7f]' if lines else r'[\x00-\x1f\x7f]', ' ', t).strip()
    if need and not t:
        return '', '%s: a text is needed' % what
    if len(t) > limit:
        return '', '%s: at most %d characters' % (what, limit)
    return t, ''


def _clean_url(url):
    """An address as a button keeps it -> (the address, an error): never javascript:, data: or vbscript: (they would
    run in the page), nor control characters."""
    u = re.sub(r'[\t\r\n]', '', str(url or '')).strip()
    if not u:
        return '', 'url: an address is needed'
    if len(u) > URL_MAX:
        return '', 'url: at most %d characters' % URL_MAX
    if CTRL_RE.search(u):
        return '', 'url: no control characters'
    if BAD_SCHEME_RE.match(re.sub(r'[\x00-\x20]', '', u)):
        return '', 'url: a javascript:, data: or vbscript: address is never kept'
    return u, ''


def _clean_page(page):
    """A page of the server as a button keeps it -> (the page, an error): its name (the category's alias without
    cserver.), a path or a ?query may follow (monitor?watch=x); no leading "/", no address of another site."""
    p = re.sub(r'[\t\r\n]', '', str(page or '')).strip().lstrip('/')
    if p.startswith(PREFIX):
        p = p[len(PREFIX):]
    if not p:
        return '', 'page: the name of a page is needed'
    if len(p) > URL_MAX:
        return '', 'page: at most %d characters' % URL_MAX
    if CTRL_RE.search(p) or SCHEME_RE.match(p) or not PAGE_RE.match(p) or '..' in _page_name(p):
        return '', 'page: %r is not the name of a page of this server (browse, monitor?watch=x)' % p
    return p, ''


def _page_name(page):
    """The name of the page a button opens: what its page has before a path or a query."""
    return re.split(r'[/?#]', str(page or ''), maxsplit=1)[0]


def _title_of(url):
    """A title for an address that comes without one: its site's name (https://github.com/x -> Github), else its
    host and port (a machine of one's own: host:8004)."""
    host = re.sub(r'^[a-z][\w+.-]*://', '', str(url or ''), flags=re.I).split('/')[0].split('?')[0].split('@')[-1]
    name, _, port = host.partition(':')
    parts = [p for p in name.lower().split('.') if p and p not in ('www', 'app', 'm')]
    if len(parts) >= 2 and not parts[-1].isdigit():
        word = parts[-2] if parts[-2] not in ('co', 'com', 'org', 'ac', 'gov') or len(parts) < 3 else parts[-3]
        return word[:1].upper() + word[1:]
    return host[:TEXT_MAX]


def _name_part(title):
    """A title as an artifact's name: kept as typed but what a folder (Windows, Linux, macOS) or a cRef cannot hold -
    ":" becomes " - ", "/" and "\\" "-", a comma a space, ? * " < > | and control characters one space; nothing in
    front that hides a folder or reads as a flag, no space or dot at the end; at most NAME_MAX characters."""
    t = re.sub(r'[\t\r\n\v\f]', ' ', str(title or ''))
    t = re.sub(r'^[ :]+|[ :]+$', '', t)
    t = re.sub(r' *: *', ' - ', t)
    t = re.sub(r' *, *', ' ', t).replace('/', '-').replace('\\', '-')
    t = NAME_DROP_RE.sub(' ', t).lstrip(' .-').rstrip(' .')
    return t[:NAME_MAX].rstrip(' .') if len(t) > NAME_MAX else t


def _valid_name(name):
    """A whole name as restore gives it back: one a folder can have."""
    return bool(name) and not BAD_NAME_RE.search(name) and name not in ('.', '..') and name == name.strip() and \
        not name.endswith('.') and len(name) <= 255 and not UID_RE.match(name)


def _read_desc(path):
    """The _desc.yaml of a button's folder, read once while it is unchanged -> a dict ({} when there is none)."""
    p = os.path.join(path, '_desc.yaml')
    try:
        st = os.stat(p)
    except OSError:
        return {}
    key = (st.st_mtime_ns, st.st_size)
    hit = _DESC.get(p)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(p, encoding='utf-8-sig') as f:
            data = yaml.safe_load(f) or {}
    except (OSError, ValueError, yaml.YAMLError):
        data = {}
    data = data if isinstance(data, dict) else {}
    if len(_DESC) > 20000:
        _DESC.clear()
    _DESC[p] = (key, data)
    return data


def _write_desc(folder, data):
    """A button's _desc.yaml written: an existing one changed in place (only its keys that changed, the rest of its
    text kept), a new one with the keys in the order given - under the engine's lock of the file."""
    path = os.path.join(folder, '_desc.yaml')
    _DESC.pop(path, None)
    if os.path.isfile(path):
        r = files.safe_write_file(path, data, preserve=True)
        if r.get('return', 1) > 0:
            raise OSError(r.get('error', 'cannot write %s' % path))
        return
    text = files.yaml_dump_keep(data)
    with files.PathLock(path + '.lock'):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        os.replace(tmp, path)


def _desc_of(old, button):
    """The _desc of a button: what its file holds (its other keys kept, in their places) with the button's own keys
    set - the empty ones taken out."""
    data = dict(old or {})
    for k in VIEW_KEYS:
        v = button.get(k)
        if v is None or v is False or v == '':
            data.pop(k, None)
        else:
            data[k] = _tidy(v) if k == 'order' else v
    return data


def _okey(button):
    return (0, button['order']) if button['order'] is not None else (1, 0)


def _sort_buttons(buttons):
    """The buttons as the page shows them: the sections in the order of their first button, in a section by order
    (those without one at its end), then by title."""
    first = {}
    for x in buttons:
        k = _okey(x)
        if x['section'] not in first or k < first[x['section']]:
            first[x['section']] = k
    return sorted(buttons, key=lambda x: (first[x['section']], x['section'].lower(), x['section'], _okey(x),
                                          x['title'].lower(), x['uid']))


def _sections_of(buttons):
    """The names of the sections, in the order the page shows them."""
    out = []
    for x in _sort_buttons(buttons):
        if x['section'] not in out:
            out.append(x['section'])
    return out


def _lis(values):
    """The positions of a longest strictly increasing run of the numbers in values (None never counts)."""
    tails, prev = [], [-1] * len(values)
    for i, v in enumerate(values):
        if v is None:
            continue
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if values[tails[mid]] < v:
                lo = mid + 1
            else:
                hi = mid
        if lo:
            prev[i] = tails[lo - 1]
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    out, i = set(), tails[-1] if tails else -1
    while i >= 0:
        out.add(i)
        i = prev[i]
    return out


def _spread(lo, hi, m):
    """m orders after lo and before hi (None: no bound) -> a list, or None when there is no room for them."""
    if lo is None and hi is None:
        return [STEP * (k + 1) for k in range(m)]
    if lo is None:
        return [_tidy(hi - STEP * (m - k)) for k in range(m)]
    if hi is None:
        return [_tidy(lo + STEP * (k + 1)) for k in range(m)]
    gap = hi - lo
    if gap / (m + 1) < FINEST:
        return None
    if float(lo).is_integer() and float(hi).is_integer() and gap >= m + 1:
        out = [int(lo) + (int(gap) * (k + 1)) // (m + 1) for k in range(m)]
    else:
        out = [_tidy(lo + gap * (k + 1) / (m + 1)) for k in range(m)]
    seq = [lo] + out + [hi]
    return out if all(a < b for a, b in zip(seq, seq[1:])) else None


def _assign_orders(seq, moving=()):
    """New orders for buttons in the sequence they must show in -> {UID: order} of those that change: the longest run
    of orders that already increase stays (the buttons in moving never count in it), the others get orders between
    their neighbours that stay; when two of them leave no room, every button is numbered again (10, 20, ...)."""
    values = [None if (x['uid'] in moving or x['order'] is None) else x['order'] for x in seq]
    keep = _lis(values)
    out, i, n = {}, 0, len(seq)
    while i < n:
        if i in keep:
            i += 1
            continue
        j = i
        while j < n and j not in keep:
            j += 1
        spread = _spread(values[i - 1] if i else None, values[j] if j < n else None, j - i)
        if spread is None:
            return {x['uid']: STEP * (k + 1) for k, x in enumerate(seq) if x['order'] != STEP * (k + 1)}
        for k, v in enumerate(spread):
            out[seq[i + k]['uid']] = v
        i = j
    was = {x['uid']: x['order'] for x in seq}
    return {u: v for u, v in out.items() if was[u] != v}


class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def _uses(self, key, default):
        return ((self.cmeta or {}).get('uses_categories', {}) or {}).get(key, default)

    # ------------------------------------------------------------------ data
    @staticmethod
    def _has_web(path):
        """True when any api/v*.py of the category defines web_ (the page contract of both hosts)."""
        api = os.path.join(path, 'api')
        try:
            names = sorted(n for n in os.listdir(api) if n.startswith('v') and n.endswith('.py'))
        except Exception:
            return False
        for n in names:
            try:
                with open(os.path.join(api, n), encoding='utf-8', errors='ignore') as f:
                    if 'def web_' in f.read():
                        return True
            except Exception:
                pass
        return False

    def _own_alias(self):
        return ((self.cmeta or {}).get('alias') or os.path.basename(os.path.dirname(os.path.dirname(__file__)))).strip()

    def _scan(self):
        """Every cserver.* category of every plugged repository -> {'return':0, 'pages':[...], 'others':[...]}.

        Named with a leading underscore on purpose: a method without a trailing underscore would be dispatched as
        a CLI command and called with one positional params dict.
        """
        cat_category = self._uses('category', 'category,dd9ea50e7f76467f')
        r = self.cm.access({'category': cat_category, 'command': 'find', 'arg1': PREFIX + '*', 'con': False})
        if self.cm.catch_error(r):
            return r
        own = self._own_alias()
        pages, others = [], []
        for a in (r.get('artifacts') or []):
            parts = a.get('cmeta_ref_parts') or {}
            path = a.get('path') or ''
            alias = (parts.get('artifact_alias') or os.path.basename(path) or '').strip()
            if not alias.startswith(PREFIX):
                continue
            meta = a.get('cmeta') or {}
            uid = str(meta.get('artifact') or parts.get('artifact_uid') or '').split(',')[-1]
            item = {
                'alias': alias,
                'page': alias[len(PREFIX):],
                'uid': uid,
                'repo': parts.get('repo_alias') or '',
                'name': str(meta.get('name') or '').strip(),
                'desc': str(meta.get('desc') or ('' if not meta.get('name') else meta.get('note') or '')).strip(),
                'tags': [str(t) for t in (meta.get('tags') or [])],
                'updated': str(meta.get('last_update_timestamp') or meta.get('creation_timestamp') or '')[:10],
                'self': alias == own,
                'card': meta.get('card', True) is not False,     # card: false - a page reached through links only
                'path': path,
            }
            (pages if self._has_web(path) else others).append(item)
        key = lambda i: (i['repo'].lower(), i['page'].lower())
        pages.sort(key=key)
        others.sort(key=key)
        return {'return': 0, 'pages': pages, 'others': others}

    def _cserver_config(self):
        """The cserver config, read on every request ({} when it cannot be read)."""
        r = self.cm.access({'category': self._uses('config', 'config,cc6bfe174be847ed'), 'command': 'get',
                            'arg1': 'cserver', 'con': False})
        if r.get('return', 1) > 0:
            return {}
        return r.get('config_cmeta') or {}

    @staticmethod
    def _href(url_server, page):
        return url_server + page

    def _payload(self, urls, query):
        """The JSON the page renders: the other pages with their hrefs, repos in order, counts, the version.

        This page itself is left out of the cards (it is the page being looked at), and so is a page whose _cmeta
        says card: false; repositories matching hide_repos of the cserver config are left out, and ?repo=<text>
        keeps only the repositories whose alias contains the text.
        """
        r = self._scan()
        if r['return'] > 0:
            return r
        hide = _patterns(self._cserver_config().get('hide_repos'))
        want = str((query or {}).get('repo') or '').strip().lower()

        def keep(p):
            return (not p['self'] and p['card'] and not _hidden(p['repo'], hide)
                    and (not want or want in p['repo'].lower()))

        pages = [p for p in r['pages'] if keep(p)]
        others = [p for p in r['others'] if keep(p)]
        url_server = urls.get('url_server') or '/'
        repos = []
        for p in pages + others:
            p['href'] = self._href(url_server, p['page'])
            p.pop('path', None)          # not shown on the page; a path is a detail of one machine
            if p['repo'] not in repos:
                repos.append(p['repo'])
        return {'return': 0, 'pages': pages, 'others': others, 'repos': repos, 'count': len(pages),
                'url_server': url_server, 'version': getattr(self.cm, '__version__', '')}

    # ------------------------------------------------------------------ the customized view
    def _cat(self):
        """This category as alias,UID: the buttons of the view are its artifacts."""
        return '%s,%s' % (self._own_alias(), str((self.cmeta or {}).get('artifact') or '').split(',')[-1].strip())

    @staticmethod
    def _may_write(misc):
        """Who may change the view: a browser on this machine, or one that passed the server's password; never the
        cTuning platform -> (ok, why not)."""
        misc = misc or {}
        if misc.get('ctuning_server'):
            return False, 'the view is changed on the cMeta server of its machine, not here'
        if not (misc.get('client_local') or misc.get('password_gate')):
            return False, ('changing the view is for a browser on the server\'s own machine, or one that signed in '
                           'to it with its password')
        return True, ''

    def _buttons(self):
        """Every button of the view in the plugged repositories, in no order -> [button]: uid, alias, repo, title,
        page, url, section, order (None: none), note, marker (the record of a section: no page or address); _path and
        _repo_uid (never sent to a page)."""
        r = self.cm.access({'category': self._cat(), 'command': 'find', 'arg1': '', 'con': False})
        if r.get('return', 1) > 0:
            if r.get('return') == 16:
                return []
            raise RuntimeError(r.get('error', 'cannot list the buttons of the view'))
        out = []
        for a in r.get('artifacts') or []:
            parts = a.get('cmeta_ref_parts') or {}
            path = a.get('path') or ''
            d = _read_desc(path) if path else {}
            alias = str(parts.get('artifact_alias') or '')
            order = d.get('order')
            page, url = str(d.get('page') or '').strip(), str(d.get('url') or '').strip()
            # the record of a section has no title: none is written back into it when it moves or is renamed
            marker = str(d.get('kind') or '').strip().lower() == SECTION_KIND or not (page or url)
            out.append({'uid': str(parts.get('artifact_uid') or '').lower(), 'alias': alias,
                        'repo': parts.get('repo_alias') or '',
                        'title': '' if marker else (str(d.get('title') or '').strip() or alias),
                        'page': page, 'url': url,
                        'section': str(d.get('section') or '').strip(), 'order': order if _num(order) else None,
                        'star': _yes(d.get('star')), 'note': str(d.get('note') or '').strip(), 'marker': marker,
                        'newline': _yes(d.get('newline')),
                        '_path': path, '_repo_uid': str(parts.get('repo_uid') or '').lower()})
        return out

    @staticmethod
    def _public(button):
        return {k: v for k, v in button.items() if not k.startswith('_')}

    def _repos(self):
        """The repositories plugged here that may keep a view (every one but the engine's own) -> [alias]."""
        r = self.cm.access({'category': self._uses('repo', 'repo,f4f792ab40c7498f'), 'command': 'find', 'arg1': '',
                            'con': False})
        out = []
        for a in (r.get('artifacts') or []) if r.get('return', 1) == 0 else []:
            alias = str((a.get('cmeta_ref_parts') or {}).get('artifact_alias') or '')
            if alias and alias != 'internal' and alias not in out:
                out.append(alias)
        return sorted(out, key=str.lower)

    def _default_repo(self):
        """Where a view is made when none is named: cserver_projects_create_repo of the default config, else local."""
        name = (getattr(self.cm, 'cfg', None) or {}).get('default_config_name') or 'default'
        r = self.cm.access({'category': self._uses('config', 'config,cc6bfe174be847ed'), 'command': 'read',
                            'arg1': name, 'con': False})
        repo = str(((r.get('config_cmeta') or {}) if r.get('return', 1) == 0 else {}).get(CREATE_REPO_KEY) or '').strip()
        return repo.split(',')[0].strip() or 'local'

    @staticmethod
    def _home(buttons):
        """The repository that holds the view: the one with most of its buttons ('' with none)."""
        count = {}
        for b in buttons:
            count[b['repo']] = count.get(b['repo'], 0) + 1
        return sorted(count, key=lambda k: (-count[k], k.lower()))[0] if count else ''

    def _repo_for(self, buttons, repo=''):
        """Where a new button goes: the repository named, else the one that holds the view, else the engine's rule
        (cserver_projects_create_repo of the default config, else local) -> (the repository as a cRef's prefix -
        '' lets the engine choose -, an error)."""
        repo = str(repo or '').strip() or self._home(buttons)
        if not repo:
            return '', ''
        r = self.cm.access({'category': self._uses('repo', 'repo,f4f792ab40c7498f'), 'command': 'find', 'arg1': repo,
                            'con': False})
        found = (r.get('artifacts') or []) if r.get('return', 1) == 0 else []
        if len(found) != 1:
            return '', ('there is no repository %r here' % repo if not found else
                        '%d repositories match %r - name one by alias,UID' % (len(found), repo))
        parts = found[0].get('cmeta_ref_parts') or {}
        if parts.get('artifact_alias') == 'internal':
            return '', 'the engine\'s own repository keeps no view: choose another one'
        return str(parts.get('artifact_uid') or parts.get('artifact_alias') or repo), ''

    def _view(self, urls):
        """The view as the page draws it -> {buttons (in order, with href and missing: a page this machine does not
        have), sections (every one, in order - an empty one too), markers (the records of the sections: [{uid,
        section}]), loose (the pages of this machine the view does not name), home (the repository that holds the
        view), repos (those that may keep one), default_repo}."""
        scan = self._scan()
        if scan['return'] > 0:
            return {'error': scan.get('error', 'the index could not be read')}
        url_server = (urls or {}).get('url_server') or '/'
        pages = {p['page']: p for p in scan['pages']}
        every = _sort_buttons(self._buttons())
        buttons = [b for b in every if not b['marker']]
        out = []
        for b in buttons:
            x = self._public(b)
            if b['page']:
                p = pages.get(_page_name(b['page']))
                x['href'] = url_server + b['page']
                x['missing'] = p is None
                x['about'] = (p['desc'] or p['name']) if p else ''
            else:
                x['href'] = _clean_url(b['url'])[0]
                x['missing'] = False
                x['about'] = ''
            out.append(x)
        named = {_page_name(b['page']) for b in buttons if b['page']}
        hide = _patterns(self._cserver_config().get('hide_repos'))
        loose = [{'page': p['page'], 'title': _card_title(p), 'about': p['desc'] or p['name'], 'repo': p['repo'],
                  'href': url_server + p['page']}
                 for p in scan['pages'] if p['page'] not in named and not p['self'] and p['card']
                 and not _hidden(p['repo'], hide)]
        pages_here = [{'page': p['page'], 'title': _card_title(p)} for p in scan['pages'] if not p['self'] and p['card']]
        return {'buttons': out, 'sections': _sections_of(every), 'loose': loose, 'pages': pages_here,
                'markers': [{'uid': b['uid'], 'section': b['section']} for b in every if b['marker']],
                'home': self._home(every), 'repos': self._repos(), 'default_repo': self._default_repo(), 'count': len(out)}

    def _one(self, buttons, name):
        """The button a change names: its UID, its name (a case apart), its title, or the only one whose title or
        name holds the text -> (the button, an error)."""
        name = str(name or '').strip()
        m = re.match(r'^\{\{\{(.+?)\}\}\}$', name)
        if m:
            name = m.group(1)
        if '::' in name:
            name = name.split('::', 1)[1]
        if ',' in name:
            name = name.split(',')[-1].strip()
        if not name:
            return None, 'a button is expected: its UID, its name or a word of its title'
        low = name.lower()
        hit = [x for x in buttons if x['uid'] == low] or [x for x in buttons if x['alias'].lower() == low] or \
            [x for x in buttons if x['title'].lower() == low] or \
            [x for x in buttons if low in x['title'].lower() or low in x['alias'].lower()]
        if len(hit) != 1:
            return None, ('no button %r' % name if not hit else '%d buttons match %r: %s' %
                          (len(hit), name, ', '.join('%s (%s)' % (x['alias'], x['uid']) for x in hit[:8])))
        return hit[0], ''

    @staticmethod
    def _canon_section(section, buttons):
        """A section's name as the buttons have it already, a case apart ("cmeta" -> "cMeta")."""
        s = str(section or '').strip()
        for x in buttons:
            if x['section'].lower() == s.lower():
                return x['section']
        return s

    def _place(self, buttons, button, section, before):
        """Where a button goes: before the button `before` (into its section), else at the end of `section` (a new
        section: at the end of all) -> (the sequence of every button with it there, its section, an error)."""
        seq = [x for x in _sort_buttons(buttons) if x['uid'] != button['uid']]
        if before:
            b, error = self._one([x for x in seq if not x.get('marker')], before)
            if error:
                return None, '', 'before: ' + error
            section = b['section']
            at = seq.index(b)
        else:
            ends = [i for i, x in enumerate(seq) if x['section'] == section]
            at = ends[-1] + 1 if ends else len(seq)
        return seq[:at] + [dict(button, section=section)] + seq[at:], section, ''

    def _write(self, button, old_desc):
        _write_desc(button['_path'], _desc_of(old_desc, button))

    def _orders(self, seq, moving, skip=()):
        """The new orders of a sequence written into the buttons' files (except those in skip) -> {uid: order}."""
        new = _assign_orders(seq, moving)
        for x in seq:
            if x['uid'] in new and x['uid'] not in skip:
                self._write(dict(x, order=new[x['uid']]), _read_desc(x['_path']))
        return new

    def _create(self, where, title, section, taken, generator=None, uid=''):
        """A new button artifact (its _desc written by the caller) -> (the button, an error); its name: its title,
        else "<title> - <section>", else numbered - never one a button has in any repository."""
        if uid:
            alias = title
        else:
            base = _name_part(title) or 'page'
            if UID_RE.match(base):
                base += ' page'
            alias = base
            if alias.lower() in taken:
                alias = _name_part(base + ' - ' + section) or base
            stem, n = alias, 2
            while alias.lower() in taken:
                alias = '%s %d' % (stem, n)
                n += 1
        name = alias + (',' + uid if uid else '')
        r = self.cm.access({'category': self._cat(), 'command': 'get', 'arg1': '%s:%s' % (where, name) if where else name,
                            'con': False, 'meta': {'generator': dict(generator or GENERATOR)}})
        if r.get('return', 1) > 0:
            return None, '%s::%s: %s' % (self._own_alias(), alias, r.get('error', 'not made'))
        if not r.get('created'):
            return None, '%s::%s is there already' % (self._own_alias(), alias)
        art = r.get('artifact') or {}
        parts = art.get('cmeta_ref_parts') or {}
        new_uid = str(parts.get('artifact_uid') or (r.get('cmeta') or {}).get('artifact') or '').split(',')[-1].strip().lower()
        taken.add(alias.lower())
        return {'uid': new_uid, 'alias': alias, 'repo': parts.get('repo_alias') or '', '_path': art.get('path') or r.get('path') or '',
                '_repo_uid': str(parts.get('repo_uid') or '').lower()}, ''

    def _view_make(self, repo='', generator=None):
        """The view made from the pages of this machine as the cards show them: a section per repository, a button
        per page with its card's heading; only while there is no view -> {'made', 'home'} or {'error'}."""
        buttons = [b for b in self._buttons() if not b['marker']]
        if buttons:
            return {'error': 'there is a view already (%d buttons): change it on the page' % len(buttons)}
        scan = self._scan()
        if scan['return'] > 0:
            return {'error': scan.get('error', 'the index could not be read')}
        hide = _patterns(self._cserver_config().get('hide_repos'))
        pages = [p for p in scan['pages'] if not p['self'] and p['card'] and not _hidden(p['repo'], hide)]
        if not pages:
            return {'error': 'this machine has no page to make a view of'}
        where, error = self._repo_for([], repo or self._default_repo())
        if error:
            return {'error': error}
        taken, made = set(), []
        for k, p in enumerate(pages):
            section = p['repo'] or 'local'
            b, error = self._create(where, _card_title(p), section, taken, generator)
            if error:
                return {'error': error, 'made': len(made)}
            b.update(title=_card_title(p), page=p['page'], url='', section=section, order=STEP * (k + 1), star=False, note='')
            self._write(b, {})
            made.append(b)
        home = made[0]['repo'] if made else ''
        print('cMeta info: cserver.projects: the view made - %d buttons in %d sections, in %s' %
              (len(made), len(_sections_of(made)), home))
        return {'made': len(made), 'home': home}

    def _view_save(self, uid='', title=None, page=None, url=None, section=None, star=None, note=None, before='',
                   order=None, repo='', generator=None, newline=None):
        """A new button (no uid) or a button changed (only what is given: a page or an address, its title, section,
        note, newline - the next button starts a line of its own; a new section puts it at that section's end,
        before: before that button, order: exactly there - Undo) -> {'button', 'created'} and, for a change, 'old'
        and 'changed'; or {'error'}."""
        buttons = self._buttons()
        given = {}
        if page not in (None, ''):
            given['page'], error = _clean_page(page)
            if error:
                return {'error': error}
            given['url'] = ''
        elif url not in (None, ''):
            given['url'], error = _clean_url(url)
            if error:
                return {'error': error}
            given['page'] = ''
        if title is not None:
            given['title'], error = _clean_text(title, 'title', TEXT_MAX)
            if error:
                return {'error': error}
        if section is not None:
            given['section'], error = _clean_text(section, 'section', TEXT_MAX)
            if error:
                return {'error': error}
            given['section'] = self._canon_section(given['section'], buttons)
        if note is not None:
            given['note'], error = _clean_text(note, 'note', NOTE_MAX, lines=True)
            if error:
                return {'error': error}
        if star is not None:
            given['star'] = _yes(star)
        if newline is not None:
            given['newline'] = _yes(newline)
        if order is not None and order != '':
            try:
                given['order'] = float(order)
            except (TypeError, ValueError):
                return {'error': 'order: a number is expected'}
            if not math.isfinite(given['order']):
                return {'error': 'order: a number is expected'}

        if str(uid or '').strip():
            return self._view_change(buttons, uid, given, before)

        # a new button: a page or an address, a section; a title (else the page's card heading, the site's name)
        if not given.get('page') and not given.get('url'):
            return {'error': 'page: a page of this server or an address is needed'}
        if not given.get('title'):
            if given.get('page'):
                scan = self._scan()
                p = {x['page']: x for x in (scan.get('pages') or [])}.get(_page_name(given['page']))
                given['title'] = _card_title(p) if p else _page_name(given['page'])
            else:
                given['title'] = _title_of(given['url']) or given['url'][:TEXT_MAX]
            given['title'] = given['title'][:TEXT_MAX]
        if not given.get('section') and not before:
            return {'error': 'section: the section of the new button is needed'}
        where, error = self._repo_for(buttons, repo)
        if error:
            return {'error': error}
        button = {'uid': '', 'order': None, 'title': given['title'], 'section': given.get('section', '')}
        seq, sec, error = self._place(buttons, button, given.get('section', ''), before)
        if error:
            return {'error': error}
        made, error = self._create(where, given['title'], sec, {x['alias'].lower() for x in buttons}, generator)
        if error:
            return {'error': error}
        made.update(title=given['title'], page=given.get('page', ''), url=given.get('url', ''), section=sec,
                    star=given.get('star', False), note=given.get('note', ''), newline=given.get('newline', False), order=None)
        seq = [made if x['uid'] == '' else x for x in seq]
        if 'order' in given:
            made['order'] = _tidy(given['order'])
        else:
            made['order'] = self._orders(seq, {made['uid']}, skip={made['uid']}).get(made['uid'], STEP)
        self._write(made, {})
        print('cMeta info: cserver.projects: added the button %s (%s) in %s' % (made['alias'], sec, made['repo']))
        return {'button': self._public(made), 'created': True}

    def _view_change(self, buttons, uid, given, before):
        button, error = self._one([x for x in buttons if not x['marker']], uid)
        if error:
            return {'error': error}
        old = {k: button[k] for k in ('title', 'page', 'url', 'section', 'star', 'note', 'newline', 'order')}
        new = dict(button, **{k: v for k, v in given.items() if k != 'order'})
        if not new['section']:
            return {'error': 'section: a button is in a section'}
        if not new['title']:
            return {'error': 'title: a text is needed'}
        if 'order' in given:
            new['order'] = _tidy(given['order'])
        elif before or new['section'] != button['section']:
            seq, sec, error = self._place(buttons, button, new['section'], before)
            if error:
                return {'error': error}
            new['section'] = sec
            seq = [dict(new, order=None) if x['uid'] == button['uid'] else x for x in seq]
            new['order'] = self._orders(seq, {button['uid']}, skip={button['uid']}).get(button['uid'], button['order'])
        changed = any(new[k] != old[k] for k in old)
        if changed:
            self._write(new, _read_desc(button['_path']))
            print('cMeta info: cserver.projects: changed the button %s (%s)' %
                  (button['alias'], ', '.join(k for k in old if new[k] != old[k])))
        return {'button': self._public(new), 'old': old, 'changed': changed}

    def _view_arrange(self, uid='', section=None, before='', move_section='', before_section='', rename=None,
                      orders=None):
        """The view rearranged: a button moved (uid: before the button `before`, into its section, or to the end of
        `section`), a section moved (move_section: before before_section, or to the end), a section renamed (section,
        rename: a name another section has joins them), or orders and sections set exactly (orders: [{uid, order,
        section}] - Undo) -> {'changed': [{uid, title, section, order}], 'undo': [{uid, order, section}]} or
        {'error'}."""
        buttons = self._buttons()
        by_uid = {x['uid']: x for x in buttons}
        want = {}           # uid -> (section, order) of the buttons that change

        if orders is not None:
            if not isinstance(orders, list):
                return {'error': 'orders: a list of {uid, order, section} is expected'}
            for o in orders:
                x = by_uid.get(str((o or {}).get('uid') or '').strip().lower()) if isinstance(o, dict) else None
                if not x:
                    return {'error': 'orders: no button %r' % ((o or {}).get('uid') if isinstance(o, dict) else o)}
                s, error = _clean_text(o.get('section', x['section']), 'section', TEXT_MAX, need=True)
                if error:
                    return {'error': error}
                v = o.get('order')
                if v is not None and not _num(v):
                    return {'error': 'orders: the order of %s is no number' % x['alias']}
                want[x['uid']] = (s, _tidy(v) if v is not None else None)

        elif str(uid or '').strip():
            button, error = self._one([x for x in buttons if not x['marker']], uid)
            if error:
                return {'error': error}
            s = None
            if section is not None:
                s, error = _clean_text(section, 'section', TEXT_MAX, need=not before)
                if error:
                    return {'error': error}
                s = self._canon_section(s, buttons)
            seq, sec, error = self._place(buttons, button, s if s is not None else button['section'], before)
            if error:
                return {'error': error}
            seq = [dict(button, section=sec) if x['uid'] == button['uid'] else x for x in seq]
            new = _assign_orders(seq, {button['uid']})
            for x in seq:
                if x['uid'] in new or x['uid'] == button['uid']:
                    want[x['uid']] = (x['section'], new.get(x['uid'], x['order']))

        elif str(move_section or '').strip():
            ms = self._canon_section(move_section, buttons)
            mine = [x for x in _sort_buttons(buttons) if x['section'] == ms]
            if not mine:
                return {'error': 'move_section: no section %r' % move_section}
            rest = [x for x in _sort_buttons(buttons) if x['section'] != ms]
            at = len(rest)
            if str(before_section or '').strip():
                bs = self._canon_section(before_section, buttons)
                ends = [i for i, x in enumerate(rest) if x['section'] == bs]
                if not ends:
                    return {'error': 'before_section: no section %r' % before_section}
                at = ends[0]
            seq = rest[:at] + mine + rest[at:]
            new = _assign_orders(seq, {x['uid'] for x in mine})
            want = {u: (by_uid[u]['section'], v) for u, v in new.items()}

        elif section is not None and rename is not None:
            s = self._canon_section(section, buttons)
            mine = [x for x in _sort_buttons(buttons) if x['section'] == s]
            if not mine:
                return {'error': 'section: no section %r' % section}
            to, error = _clean_text(rename, 'rename', TEXT_MAX, need=True)
            if error:
                return {'error': error}
            to = self._canon_section(to, [x for x in buttons if x['section'] != s]) if to.lower() != s.lower() else to
            if [x for x in buttons if x['section'] == to and x['section'] != s]:
                # into a section that exists: its buttons go to that section's end, in their order
                rest = [x for x in _sort_buttons(buttons) if x['section'] != s]
                at = max(i for i, x in enumerate(rest) if x['section'] == to) + 1
                seq = rest[:at] + [dict(x, section=to) for x in mine] + rest[at:]
                new = _assign_orders(seq, {x['uid'] for x in mine})
                for x in mine:
                    want[x['uid']] = (to, new.get(x['uid'], x['order']))
                for u, v in new.items():
                    if u not in want:
                        want[u] = (by_uid[u]['section'], v)
            else:
                for x in mine:
                    want[x['uid']] = (to, x['order'])

        else:
            return {'error': 'what to arrange: uid (with before or section), move_section (with before_section), '
                             'section with rename, or orders'}

        changed, undo = [], []
        for u, (s, v) in want.items():
            x = by_uid[u]
            if s == x['section'] and v == x['order']:
                continue
            self._write(dict(x, section=s, order=v), _read_desc(x['_path']))
            changed.append({'uid': u, 'title': x['title'], 'section': s, 'order': v})
            undo.append({'uid': u, 'order': x['order'], 'section': x['section']})
        if changed:
            print('cMeta info: cserver.projects: arranged %d button(s) of the view' % len(changed))
        return {'changed': changed, 'undo': undo}

    def _view_section(self, section='', repo='', generator=None):
        """An empty section (2026-11-11, the user: "+ Section ... should just ask me for a name of the section and
        create an empty one"): the record of a section - kind: section, its name and its order, no page or address -
        at the end of the view, in the repository that holds the view; a name a section has already (a case apart) is
        refused -> {'section', 'uid', 'created'} or {'error'}."""
        name, error = _clean_text(section, 'section', TEXT_MAX, need=True)
        if error:
            return {'error': error}
        buttons = self._buttons()
        have = [x['section'] for x in buttons if x['section'].lower() == name.lower()]
        if have:
            return {'error': 'section: there is a section %s already' % have[0]}
        where, error = self._repo_for(buttons, repo)
        if error:
            return {'error': error}
        marker = {'uid': '', 'order': None, 'title': '', 'section': name, 'marker': True}
        seq, sec, error = self._place(buttons, marker, name, '')
        if error:
            return {'error': error}
        made, error = self._create(where, 'Section ' + name, name, {x['alias'].lower() for x in buttons}, generator)
        if error:
            return {'error': error}
        made.update(title='', page='', url='', section=name, star=False, note='', order=None, marker=True)
        seq = [made if x['uid'] == '' else x for x in seq]
        made['order'] = self._orders(seq, {made['uid']}, skip={made['uid']}).get(made['uid'], STEP)
        self._write(made, {'kind': SECTION_KIND})
        print('cMeta info: cserver.projects: made the empty section %s (%s) in %s' % (name, made['alias'], made['repo']))
        return {'section': name, 'uid': made['uid'], 'created': True}

    def _view_discard(self, uid=''):
        """A button deleted, or the record of an empty section -> {'removed': {uid, alias, repo, desc}} - what restore
        takes to put it back - or {'error'}."""
        buttons = self._buttons()
        button, error = self._one(buttons, uid)
        if error:
            return {'error': error}
        removed = {'uid': button['uid'], 'alias': button['alias'], 'repo': button['repo'],
                   'desc': dict(_read_desc(button['_path']))}
        r = self.cm.access({'category': self._cat(), 'command': 'delete', 'arg1': button['uid'], 'force': True,
                            'con': False})
        if r.get('return', 1) > 0:
            return {'error': '%s::%s: %s' % (self._own_alias(), button['alias'], r.get('error', 'not deleted'))}
        _DESC.pop(os.path.join(button['_path'], '_desc.yaml'), None)
        print('cMeta info: cserver.projects: deleted %s %s from %s' % ('the record of the section' if button['marker'] else
                                                                       'the button', button['alias'], button['repo']))
        return {'removed': removed}

    def _view_restore(self, removed=None, generator=None):
        """A button deleted by discard put back as it was - its name, UID, repository and _desc -> {'button'} or
        {'error'}."""
        if not isinstance(removed, dict):
            return {'error': 'removed: what discard gave back is expected ({uid, alias, repo, desc})'}
        uid = str(removed.get('uid') or '').strip().lower()
        alias = str(removed.get('alias') or '').strip()
        if not UID_RE.match(uid):
            return {'error': 'removed: the UID of the button (16 hex digits) is expected'}
        if not _valid_name(alias):
            return {'error': 'removed: %r cannot name a button' % alias}
        desc = removed.get('desc') if isinstance(removed.get('desc'), dict) else {}
        clean = {}
        for k, limit in (('title', TEXT_MAX), ('section', TEXT_MAX), ('note', NOTE_MAX)):
            clean[k], error = _clean_text(desc.get(k), k, limit, lines=k == 'note')
            if error:
                return {'error': error}
        page, url, error = '', '', ''
        marker = str(desc.get('kind') or '').strip().lower() == SECTION_KIND
        if marker:
            if not clean['section']:
                return {'error': 'removed: the record of a section names its section'}
        elif desc.get('page'):
            page, error = _clean_page(desc.get('page'))
        else:
            url, error = _clean_url(desc.get('url'))
        if error:
            return {'error': error}
        buttons = self._buttons()
        if any(x['uid'] == uid for x in buttons):
            return {'error': 'a button with the UID %s is here already' % uid}
        if any(x['alias'].lower() == alias.lower() for x in buttons):
            return {'error': 'a button %s::%s is here already' % (self._own_alias(), alias)}
        where, error = self._repo_for(buttons, removed.get('repo'))
        if error:
            return {'error': error}
        made, error = self._create(where, alias, clean['section'], set(), generator, uid=uid)
        if error:
            return {'error': error}
        order = desc.get('order')
        made.update(title='' if marker else (clean['title'] or alias), page=page, url=url, section=clean['section'],
                    note=clean['note'], star=_yes(desc.get('star')), newline=_yes(desc.get('newline')),
                    order=order if _num(order) else None, marker=marker)
        self._write(made, {k: v for k, v in desc.items() if k not in VIEW_KEYS})
        print('cMeta info: cserver.projects: restored %s %s in %s' % ('the record of the section' if marker else 'the button',
                                                                      alias, made['repo']))
        return {'button': self._public(made)}

    # ------------------------------------------------------------------ web
    def web_(self, ctx, urls, query={}, misc={}):
        """Render the page (command web) or answer ?native_action=projects | view | view_* with JSON."""
        query = query or {}
        misc = misc or {}
        na = query.get('native_action', '')
        if na:
            try:
                if na == 'projects':
                    r = self._payload(urls, query)
                    if r['return'] > 0:
                        return {'return': 0, 'json': {'error': r.get('error', 'scan failed')}}
                    r.pop('return', None)
                    return {'return': 0, 'json': r}
                if na == 'view':
                    out = self._view(urls)
                    out['edit'] = self._may_write(misc)[0]
                    return {'return': 0, 'json': out}
                if na in VIEW_WRITES:
                    ok, why = self._may_write(misc)
                    if not ok:
                        return {'return': 0, 'json': {'error': why}}
                    if not misc.get('same_origin'):
                        return {'return': 0, 'json': {'error': 'refused: the request did not come from a page of this server'}}
                    params = {k: query[k] for k in VIEW_WRITES[na] if k in query}
                    if na in ('view_make', 'view_save', 'view_section', 'view_restore'):
                        # what it makes records who made it: this page, or the page of this server that drew the view
                        # and sent the change on (misc projects_via - set by that page's code, never by a browser)
                        params['generator'] = dict(GENERATOR, via=str(misc.get('projects_via') or GENERATOR['via']))
                    return {'return': 0, 'json': getattr(self, '_' + na)(**params)}
                return {'return': 0, 'json': {'error': 'unknown native_action %r' % na}}
            except Exception as e:
                print('cserver.projects: native_action %r failed: %s\n%s' % (na, e, traceback.format_exc()))
                return {'return': 0, 'json': {'error': '%s: %s' % (type(e).__name__, e)}}

        try:
            path_to_files = os.path.join(self.path, 'files')
            url_files = urls.get('url_files') or ''
            theme = misc.get('theme', '')
            dark = theme == 'dark' or str(query.get('dark', '')).lower() in ('1', 'true', 'yes')
            version = getattr(self.cm, '__version__', '')
            config = {'api_url': urls.get('url', '?'), 'url_server': urls.get('url_server') or '/',
                      'dark_mode': bool(dark), 'files': url_files, 'version': version,
                      'repo': str(query.get('repo') or '').strip(), 'edit': self._may_write(misc)[0],
                      'cref_url': '' if misc.get('ctuning_server') else (urls.get('url_server') or '/') + 'cref/'}
            with open(os.path.join(path_to_files, 'index.html'), encoding='utf-8') as f:
                body = f.read()
            body = body.replace('%%CONFIG%%', _js(config)).replace('%%VERSION%%', _esc(version))
            head = (
                '<link rel="stylesheet" href="%s">\n' % _asset(path_to_files, url_files, 'css/projects.css') +
                '<script src="%s" defer></script>\n' % _asset(path_to_files, url_files, 'js/projects.js')
            )
            return {'return': 0, 'html_meta': {'html': body, 'page_title': 'Projects',
                                                'page_extra_style': head}}
        except Exception as e:
            return self.cm.error('cserver.projects: %s: %s' % (type(e).__name__, e))

    # ------------------------------------------------------------------ cli
    def pages_(self, ctx, repo='', as_json=False, all=False):
        """List every cserver.* page of this machine in the terminal.

        Args:
            repo: show only the categories of this repository alias (substring match)
            as_json: print the list as JSON instead of a table
            all: also list cserver.* categories without a web_ (helper actions)
        """
        r = self._scan()
        if r['return'] > 0:
            return r
        pages = r['pages'] + (r['others'] if all else [])
        if repo:
            pages = [p for p in pages if repo.lower() in p['repo'].lower()]
        if as_json:
            print(json.dumps({'pages': pages}, indent=2, ensure_ascii=False))
            return {'return': 0, 'pages': pages}
        web = set(p['alias'] for p in r['pages'])
        last = None
        for p in pages:
            if p['repo'] != last:
                last = p['repo']
                print('\n%s' % last)
            flag = '' if p['alias'] in web else '   (no web_)'
            name = p['name'] or p['desc']
            print('  /%-32s %s%s' % (p['page'], name[:90], flag))
        shown = len([p for p in pages if p['alias'] in web])
        if repo:
            print('\n%d of %d pages, repository matching %r' % (shown, len(r['pages']), repo))
        else:
            print('\n%d pages%s' % (len(r['pages']),
                  (', %d other cserver.* categories' % len(r['others'])) if r['others'] else ''))
        return {'return': 0, 'pages': pages}

    def view_(self, ctx, as_json=False):
        """The customized view of the home page in the terminal: its sections and their buttons (made and arranged
        on the page itself, its Customized switch); a page this machine does not have is marked.

        Args:
            as_json: print the view as JSON instead
        """
        out = self._view({'url_server': '/'})
        if out.get('error'):
            return {'return': 1, 'error': out['error']}
        if ctx.get('control', {}).get('con'):
            if as_json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            elif not out['buttons']:
                print('No view yet: it is made on the home page of cserver (its Customized switch, then "Make my view").')
            else:
                for section in out['sections']:
                    print('\n%s' % section)
                    mine = [b for b in out['buttons'] if b['section'] == section]
                    if not mine:
                        print('  (empty)')
                    for b in mine:
                        print('  %-30s %s%s' % (b['title'][:30], ('/' + b['page']) if b['page'] else b['url'],
                                                '   (not on this machine)' if b['missing'] else ''))
                print('\n%d buttons in %d sections, kept in %s; %d pages of this machine not in it' %
                      (len(out['buttons']), len(out['sections']), out['home'], len(out['loose'])))
        return dict({'return': 0}, **out)
