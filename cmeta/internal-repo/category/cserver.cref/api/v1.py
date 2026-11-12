"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.cref - the page of one artifact, named by its cRef.

    cx app run cserver      ->  http://127.0.0.1:8004/cref/<category>::<alias>,<UID>[/<relative path>]
                                http://127.0.0.1:8004/cref?cref=<cRef>

What a reader sees: the title and the cRef, each with a button that copies it (the cRef also as {{{...}}}, the form
a text holds), the tags, a line; the artifact's text (README.md, or the file its category names in `cref_view.text`
of its _cmeta.yaml - the latest dated copy of a note, say) with README.md and _info.md after it when it has them;
beside it the facts - the category (a link to every artifact of it), the repository (a link to every artifact of
it), the origin (the artifact's folder on GitHub, when the repository is a clone of one), the UID, the dates, the
path on this machine (a browser on the server's own machine), the buttons that open the folder in the file manager,
a shell or Far (the same browser), the graph focused on this artifact and the knowledge-graph page a host offers;
at the end, folded: the commands, the _cmeta, the _desc, the lists - its connections, its AI uses (whose memory and
skills its AI sessions read), what it uses, what connects to it: each a category, then its artifacts under it, with
a button that copies each cRef - and the files - a tree of the artifact's folder (the dated records of
`ck/YYYYMMDD/` explained), each file opening in place. A reader the page does not count as technical (misc.persona)
sees the connections and what connects to it after the text instead. The host that serves the page (the engine
cserver, a site built on it) keeps the cRef in the address bar: the cRef is how artifacts are referenced, and a
reader sees what is referenced.

The reference is resolved and the artifact read through cserver.browse (one catalogue, the same rules: the scope of
the request, hidden repositories, key and secret categories, the file browser only where it is allowed); the text
is read here under the same guards. The files and the open buttons are asked of cserver.browse from the page itself
(misc.browse_url says where it is served), so the rules are applied once, there. A text file can be edited and
saved from this page as from /browse (since 2026-11-03: the edit button in the file's head, "+ _desc.yaml" and
"+ README.md" after the tree) - cserver.browse's save, with its rules, its checks and its fingerprint. Since
2026-11-09 the texts are edited where they are read (README.md and _info.md made the same way when missing), and
the connections and the AI uses change in their lists - a field adds names or cRefs, x removes one (a connection
from both sides), through cserver.browse's link: the category's own update. Since 2026-11-10 the connections are
shown apart - "Connected with" (both _desc name each other: cserver.browse marks them mutual), "Connected to" (this
artifact's _desc only), "Connected from" (the other's only) - and each list's field is a picker: what is typed is
searched as one types (the most recent artifacts first), a pick becomes a chip, ";" or Enter takes the next; Add
writes them - "with" on both sides (cserver.browse's link with both), "to" on this one.

The view is extended, never rewritten - `cref_view` in the category's _cmeta.yaml, or in an artifact's _desc:
    text:   a file, or a list of candidates (the first that exists wins); {ck.<key>} placeholders read the _desc
    title:  a dotted key of the _desc (default: the _cmeta name, else the alias)
    hide:   sections left out: connections, incoming, commands, cmeta, desc, files, facts
    page:   a page category (cserver.<name>) that renders this artifact instead of the text: its web_ is called with
            query.cref = the cRef and query.uid - a demo, a dashboard, a view of the artifact's data
A host may pass misc.persona: a persona other than engineering / dev / all sees no technical sections at all;
misc.graph_url names the knowledge-graph page of the host (with ?focus=<alias> appended).
"""

import html
import json
import os
import re

import yaml

from cmeta.category import InitCategory

TEXT_DEFAULT = ['README.md', 'readme.md', '_info.md', 'note.md', 'index.md']
TEXT_EXT = ('.md', '.markdown', '.txt', '.rst', '.yaml', '.yml', '.json', '.py', '.js', '.css', '.html', '.sh', '.bat',
            '.csv', '.cfg', '.ini', '.toml', '.log')
TEXT_CAP = 512 * 1024
SECRET_FILE_RE = re.compile(r'(^\.env|\.pem$|\.key$|^id_(rsa|ed25519|ecdsa)|token|secret|password|credential)', re.I)
SECRET_DIR_RE = re.compile(r'(crypt|secret|credential)', re.I)
CREF_RE = re.compile(r'\{\{\{([^{}:]+)::([^{}]+?),([0-9a-fA-F]{16})\}\}\}((?:/[^\s"\'`<>)\]]*)?)')
WIKI_RE = re.compile(r'(!?)\[\[([^\]|#]+)(#[^\]|]*)?(?:\|([^\]]*))?\]\]')
PLACEHOLDER_RE = re.compile(r'\{([A-Za-z0-9_.-]+)\}')
TOKEN = '\x00%d\x00'
TOKEN_RE = re.compile(r'\x00(\d+)\x00')
TECH_PERSONAS = ('', 'all', 'engineering', 'dev', 'developer', 'internal')
SECTIONS = ('connections', 'incoming', 'commands', 'cmeta', 'desc', 'files', 'facts')
PAGE_RE = re.compile(r'^cserver\.[A-Za-z0-9_.-]+$')

# The texts shown after the one the page shows first, when the artifact has them (the names a file may have on a
# file system that tells case), and what their "+" buttons say: a README, and a note of one's own
TEXT_BESIDE = (('README.md', 'readme.md'), ('_info.md',))
TEXT_NEW = {'README.md': 'A README: what this artifact is - the page shows it first',
            '_info.md': 'A note of your own, shown after the README'}
COPY_SVG = ('<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/>'
            '<path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/></svg>')

# The lists of the technical details: the key of the box (kept open in the browser), its title, what it is
LISTS = {'connections': ('Connections', 'what this artifact connects to (its _desc)'),
         # the connections apart (2026-11-10, the user): both name each other / this artifact's _desc only / the other's only
         'connections_with': ('Connected with', 'both name each other: a connection in both _desc'),
         'connections_to': ('Connected to', 'named in the _desc of this artifact only'),
         'ai_uses': ('AI uses', 'whose memory and skills its AI sessions read (its _desc)'),
         'uses': ('Uses', 'what it runs'),
         'incoming': ('Connected from', 'the artifacts whose _desc names this one, which does not name them back')}
ADD_HINT = {'connections': ('add a connection: a name or a cRef (; between several)',
                            'Connect this artifact to others: a name, category::name, a cRef or {{{...}}} - several with ; '
                            'between them. Written in the _desc of this artifact; the other one lists it under "Connected from".'),
            'connections_with': ('connect with: type a name or a word, pick one, ; or Enter for the next',
                                 'Connect this artifact with others, both ways: the _desc of each names the other. Type a name or '
                                 'a word and pick an artifact (the most recent first); a cRef or {{{...}}} pasted is taken as it is.'),
            'connections_to': ('connect to: type a name or a word, pick one, ; or Enter for the next',
                               'Connect this artifact to others, one way: only its own _desc names them; their pages list it under '
                               '"Connected from". Type a name or a word and pick an artifact; a cRef pasted is taken as it is.'),
            'ai_uses': ('add an AI context: its short name, a name or a cRef',
                        'Whose memory and skills the AI sessions of this artifact read: the short name of an AI context (as '
                        '-ai takes it), a name, category::name or a cRef - several with ; between them.')}

_view_cache = {}      # category alias -> (mtime, cref_view of its _cmeta)


def _esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def _js(obj):
    """A JSON literal safe to embed inside a <script> tag."""
    return json.dumps(obj, ensure_ascii=False, default=str).replace('</', '<\\/')


def _get(d, dotted):
    """A dotted key of a dict: 'ck.latest.date'."""
    cur = d
    for k in str(dotted).split('.'):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _md(text):
    """A small Markdown to HTML conversion for READMEs and notes: headings, paragraphs, lists, fenced code, quotes,
    tables, rules, inline code, bold, italic, links, images (http only). Every piece of text is escaped first."""
    out, para, lst, fence, table = [], [], [], None, []

    def flush_para():
        if para:
            out.append('<p>%s</p>' % _inline(' '.join(para)))
            para.clear()

    def flush_list():
        if lst:
            tag = lst[0][0]
            out.append('<%s>%s</%s>' % (tag, ''.join('<li>%s</li>' % _inline(t) for _, t in lst), tag))
            lst.clear()

    def flush_table():
        if table:
            rows = [r for r in table if not re.fullmatch(r'\|?[\s:|-]+\|?', r)]
            if rows:
                cells = [[_inline(c.strip()) for c in r.strip().strip('|').split('|')] for r in rows]
                head = ''.join('<th>%s</th>' % c for c in cells[0])
                body = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in r) for r in cells[1:])
                out.append('<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (head, body))
            table.clear()

    for raw in text.splitlines():
        line = raw.rstrip('\r')
        if fence is not None:
            if line.strip().startswith('```'):
                out.append('<pre><code>%s</code></pre>' % _esc('\n'.join(fence)))
                fence = None
            else:
                fence.append(line)
            continue
        if line.strip().startswith('```'):
            flush_para(); flush_list(); flush_table()
            fence = []
            continue
        if line.strip().startswith('|') and line.strip().endswith('|'):
            flush_para(); flush_list()
            table.append(line)
            continue
        flush_table()
        if not line.strip():
            flush_para(); flush_list()
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            flush_para(); flush_list()
            out.append('<h%d>%s</h%d>' % (len(m.group(1)), _inline(m.group(2).strip()), len(m.group(1))))
            continue
        if re.fullmatch(r'\s*([-*_])(\s*\1){2,}\s*', line):
            flush_para(); flush_list()
            out.append('<hr>')
            continue
        m = re.match(r'^\s*([-*+]|\d+[.)])\s+(.*)$', line)
        if m:
            flush_para()
            tag = 'ol' if m.group(1)[0].isdigit() else 'ul'
            if lst and lst[0][0] != tag:
                flush_list()
            lst.append((tag, m.group(2)))
            continue
        if line.startswith('>'):
            flush_para(); flush_list()
            out.append('<blockquote>%s</blockquote>' % _inline(line.lstrip('> ')))
            continue
        if lst and raw.startswith(('  ', '\t')):
            lst[-1] = (lst[-1][0], lst[-1][1] + ' ' + line.strip())    # a wrapped list item
            continue
        flush_list()
        para.append(line.strip())
    flush_para(); flush_list(); flush_table()
    if fence is not None:
        out.append('<pre><code>%s</code></pre>' % _esc('\n'.join(fence)))
    return '\n'.join(out)


def _inline(s):
    """Inline Markdown on one escaped line: code, images, links, bold, italic, bare URLs; the \\x00 tokens of the
    references survive untouched."""
    parts = re.split(r'(`[^`]*`)', s)
    for i, p in enumerate(parts):
        if p.startswith('`') and p.endswith('`') and len(p) > 1:
            parts[i] = '<code>%s</code>' % _esc(p[1:-1])
            continue
        t = _esc(p)
        t = re.sub(r'!\[([^\]]*)\]\((https?://[^)\s]+)\)', r'<img src="\2" alt="\1">', t)
        t = re.sub(r'\[([^\]]+)\]\(((?:https?://|mailto:|/|\./|\.\./|#)[^)\s]+)\)', r'<a href="\2">\1</a>', t)
        t = re.sub(r'(?<![="\w/])(https?://[^\s<)]+)', r'<a href="\1">\1</a>', t)
        t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
        t = re.sub(r'(?<![\w*])\*([^*\n]+?)\*(?![\w*])', r'<em>\1</em>', t)
        t = re.sub(r'(?<![\w_])_([^_\n]+?)_(?![\w_])', r'<em>\1</em>', t)
        parts[i] = t
    return ''.join(parts)


def _stamp(ts):
    """'2026-10-02T09:12:11.39+00:00' -> '2026-10-02 09:12' ('' when missing)."""
    ts = str(ts or '')
    return ts[:16].replace('T', ' ') if len(ts) >= 16 else ts[:10]


def _item_cref(c):
    """The cRef of an entry of a list (cserver.browse's artifact: connections, uses, ai_uses, incoming): the full one
    of an artifact this server shows, else as the _desc writes it."""
    if c.get('uid') and c.get('cat') and c.get('found') is not False:
        if c.get('cat_uid'):
            return '%s,%s::%s,%s' % (c['cat'], c['cat_uid'], c.get('alias') or '', c['uid'])
        return '%s::%s,%s' % (c['cat'], c.get('alias') or '', c['uid'])
    return str(c.get('cref') or c.get('ref') or '')


def _item_cat(c):
    """The category an entry of a list is listed under: its own, else the one its cRef names."""
    if c.get('cat'):
        return c['cat']
    left = str(c.get('cref') or '').partition('::')
    return left[0].split(',')[0].strip() if left[1] else ''


class Category(InitCategory):
    """The page of one artifact."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    # ------------------------------------------------------------------ helpers
    def _browse(self, urls, misc, **query):
        """One call to cserver.browse's AJAX side: the same catalogue and rules as the browse page."""
        r = self.cm.access({'category': 'cserver.browse', 'command': 'web', 'urls': urls, 'misc': misc,
                            'query': query, 'con': False})
        if r.get('return', 1) > 0:
            return {'error': r.get('error', 'cserver.browse failed')}
        return r.get('json') or {}

    def _path(self, cat, uid, alias):
        """The folder of the artifact, from the index."""
        for ref in (uid, alias):
            r = self.cm.access({'category': cat, 'command': 'find', 'arg1': ref, 'con': False})
            for a in (r.get('artifacts') or []) if r.get('return', 1) == 0 else []:
                if (a.get('cmeta_ref_parts') or {}).get('artifact_uid', '').lower() == uid.lower():
                    return a.get('path') or ''
        return ''

    def _view(self, cat, desc):
        """The cref_view of the category's _cmeta, overridden by the artifact's _desc."""
        view = {}
        try:
            r = self.cm.access({'category': 'category', 'command': 'find', 'arg1': cat, 'con': False})
            path = ((r.get('artifacts') or [{}])[0].get('path') or '') if r.get('return', 1) == 0 else ''
            for name in ('_cmeta.yaml', '_cmeta.json'):
                p = os.path.join(path, name)
                if path and os.path.isfile(p):
                    st = os.stat(p)
                    cached = _view_cache.get(cat)
                    if cached and cached[0] == st.st_mtime_ns:
                        view = dict(cached[1])
                    else:
                        with open(p, encoding='utf-8') as f:
                            meta = yaml.safe_load(f) if name.endswith('.yaml') else json.load(f)
                        view = dict((meta or {}).get('cref_view') or {})
                        _view_cache[cat] = (st.st_mtime_ns, dict(view))
                    break
        except Exception:
            view = {}
        if isinstance(desc, dict) and isinstance(desc.get('cref_view'), dict):
            view.update(desc['cref_view'])
        return view

    @staticmethod
    def _safe_rel(root, rel):
        """The real path of a relative file inside the artifact, or None (outside, a key, a secret, missing)."""
        rel = str(rel or '').replace('\\', '/').strip('/')
        parts = rel.split('/')
        if not rel or ':' in rel or any(p in ('', '.', '..') for p in parts):
            return None
        if any(SECRET_DIR_RE.search(p) for p in parts[:-1]) or SECRET_FILE_RE.search(parts[-1]):
            return None
        full = os.path.realpath(os.path.join(root, *parts))
        if not os.path.normcase(full).startswith(os.path.normcase(os.path.realpath(root).rstrip('\\/') + os.sep)):
            return None
        return full if os.path.isfile(full) else None

    def _text(self, root, view, desc, rel):
        """(relative path shown, HTML, note) of the artifact's text: the file asked for, else the first candidate."""
        candidates = [rel] if rel else []
        text = view.get('text')
        candidates += ([text] if isinstance(text, str) else list(text or [])) + TEXT_DEFAULT
        for cand in candidates:
            cand = PLACEHOLDER_RE.sub(lambda m: str(_get(desc or {}, m.group(1)) or ''), str(cand))
            if '{' in cand or not cand:
                continue
            full = self._safe_rel(root, cand)
            if not full:
                if rel and cand == rel:
                    return rel, '', 'the file %s is not shown (missing, outside the artifact, or a key)' % _esc(rel)
                continue
            return (cand,) + self._render(full, cand, desc)
        return '', '', ''

    def _render(self, full, cand, desc):
        """(HTML, note) of one text file of the artifact: Markdown rendered (a note's front matter folded), any other
        text as it is (coloured by the page's script)."""
        if not cand.lower().endswith(TEXT_EXT):
            return '', 'the file %s is not a text: open it from the Files below' % _esc(cand)
        with open(full, 'rb') as f:
            raw = f.read(TEXT_CAP + 1)
        body = raw[:TEXT_CAP].decode('utf-8', errors='replace')
        note = 'the first %d KB' % (TEXT_CAP // 1024) if len(raw) > TEXT_CAP else ''
        if cand.lower().endswith(('.md', '.markdown')):
            front = ''
            m = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n', body, re.S)    # a note's YAML front matter: folded, not prose
            if m:
                front, body = m.group(1), body[m.end():]
            out = self._render_md(body, desc)
            if front:
                out = ('<details class="cxr-front"><summary>Front matter</summary><pre class="cxr-pre" data-name="front-matter.yaml">%s</pre></details>\n'
                       % _esc(front)) + out
            return out, note
        return '<pre class="cxr-pre" data-name="%s">%s</pre>' % (_esc(cand), _esc(body)), note

    def _list_html(self, items, browse_link, key=''):
        """Artifacts as the page lists them (2026-11-09): the categories A to Z, each with its artifacts under it A to
        Z - a link to the page of each, a button that copies its cRef, and with `key` (connections or ai_uses: a list
        this viewer may change) a button that removes it. An entry the _cmeta declares (the layout before the _desc)
        is not removed here."""
        groups = {}
        for c in items:
            groups.setdefault(_item_cat(c) or '?', []).append(c)
        out = []
        for g in sorted(groups, key=lambda x: x.lower()):
            rows = []
            for c in sorted(groups[g], key=lambda c: str(c.get('alias') or c.get('cref') or c.get('ref') or '').lower()):
                ref = _item_cref(c)
                if c.get('found') is False or not c.get('uid') or not c.get('cat'):
                    name = '<span class="cxr-missing" title="not shown by this server (gone, or in a repository it hides)">%s</span>' \
                           % _esc(c.get('alias') or c.get('cref') or c.get('ref'))
                else:
                    name = '<a href="%s">%s</a>' % (_esc(self._cref_url + '%s::%s,%s' % (c['cat'], c.get('alias') or '', c['uid'])),
                                                    _esc(c.get('alias') or c['uid']))
                extra = (' <span class="cxr-n">uses it</span>' if c.get('uses') else '') + \
                        (' <span class="cxr-n">its AI reads this one</span>' if c.get('ai') else '') + \
                        (' <span class="cxr-n" title="declared in the _cmeta (the layout before the _desc): edit the _cmeta to change it">in its _cmeta</span>'
                         if c.get('meta') else '')
                btns = ('<button type="button" class="cxr-ic" data-copy="%s" title="Copy its cRef: %s" aria-label="Copy its cRef">%s</button>'
                        % (_esc(ref), _esc(ref), COPY_SVG)) if ref else ''
                if key and ref and not c.get('meta'):
                    btns += ('<button type="button" class="cxr-ic cxr-lx" data-key="%s" data-ref="%s" title="Remove it from this list" '
                             'aria-label="Remove %s">&times;</button>' % (key, _esc(ref), _esc(c.get('alias') or ref)))
                rows.append('<li><span class="cxr-lname">%s%s</span>%s</li>' % (name, extra, btns))
            out.append('<div class="cxr-lcat"><a href="%s" title="Every artifact of this category">%s</a> <span class="cxr-n">%d</span></div>'
                       '<ul class="cxr-litems">%s</ul>' % (browse_link(view='browse', cats=g), _esc(g), len(groups[g]), ''.join(rows)))
        return ''.join(out)

    def _list_box(self, key, items, browse_link, editable=False, count=None, extra='', link_key='', both=False):
        """One list of the technical details, folded (the browser keeps it open once opened): its title, how many and
        what it is; "copy all" (the cRefs with ; between them - what the field of another artifact takes); the list;
        for a viewer who may change it, the picker that adds artifacts (the names typed searched as one types, the
        picked ones as chips) to the list link_key (the key of the _desc: connections, ai_uses; by default the box's
        own), both: the other artifact names this one back too (Connected with)."""
        title, what = LISTS[key]
        link_key = link_key or key
        body = ''
        if items:
            body += ('<p class="cxr-ltools"><button type="button" class="cxr-copy sm" data-copy="%s" title="Copy every cRef '
                     'of this list, ; between them - what the field of another artifact takes">copy all</button></p>'
                     % _esc(';'.join(x for x in (_item_cref(c) for c in items) if x)))
            body += self._list_html(items, browse_link, link_key if editable else '')
        else:
            body += '<p class="cxr-muted">none yet</p>'
        body += extra
        if editable:
            body += ('<form class="cxr-ladd" data-key="%s" data-box="%s" data-both="%s" autocomplete="off"><span class="cmp-chips"></span>'
                     '<input type="text" placeholder="%s" title="%s" aria-label="Add to the %s" spellcheck="false">'
                     '<button type="submit" class="cxr-btn">Add</button><span class="cxr-emsg" role="status"></span>'
                     '<div class="cmp-list" role="listbox" hidden></div></form>'
                     % (link_key, key, '1' if both else '', _esc(ADD_HINT[key][0]), _esc(ADD_HINT[key][1]), _esc(title.lower())))
        return ('<details class="cxr-lbox" data-box="%s"><summary>%s <span class="cxr-n">(%d) %s</span></summary>'
                '<div class="cxr-lbody">%s</div></details>' % (key, title, len(items) if count is None else count, what, body))

    def _texts_of(self, root, view, desc, rel=''):
        """The texts of an artifact as the page shows them: the file its view names (or rel: one file asked for),
        then README.md and _info.md when it has them -> ([(name, html, note)], a note when there is no text, the
        file shown first - '' when the file asked for could not be shown as a text)."""
        texts = []
        shown, text_html, text_note = self._text(root, view, desc, rel)
        if text_html:
            texts.append((shown, text_html, text_note))
            text_note = ''
        if not rel:
            for names in TEXT_BESIDE:
                have = next((n for n in names if self._safe_rel(root, n)), '')
                if have and have.lower() not in [x[0].lower() for x in texts]:
                    html_, note_ = self._render(self._safe_rel(root, have), have, desc)
                    if html_:
                        texts.append((have, html_, note_))
        return texts, text_note, shown if text_html else ''

    def _texts_json(self, urls, misc, uid):
        """The texts of the artifact uid for another page (the browser's panel): [{rel, html, note}]."""
        if not uid:
            return []
        base = urls.get('url_server') or '/'
        self._cref_url = str(misc.get('cref_url') or (base + 'cref/'))
        a = self._browse(urls, misc, native_action='artifact', uid=uid, texts='0')
        if 'error' in a:
            return []
        row, desc = a['row'], a.get('desc') or {}
        view = self._view(row['cat'], desc)
        root = self._path(row['cat'], uid, row['alias'])
        if not root or view.get('page'):
            return []
        texts, _note, _shown = self._texts_of(root, view, desc)
        return [{'rel': n, 'html': h, 'note': note} for n, h, note in texts]

    def _render_md(self, body, desc):
        """Markdown with the references turned into links: {{{cRef}}}/path and the artifact's own wikilinks map."""
        anchors = []
        wiki = (desc or {}).get('ck', {}).get('wikilinks') if isinstance((desc or {}).get('ck'), dict) else None
        wiki = wiki if isinstance(wiki, dict) else {}

        def cref_link(m):
            rel = m.group(4).rstrip('.,;:')
            tail = m.group(4)[len(rel):]
            ref = '%s::%s,%s' % (m.group(1), m.group(2), m.group(3))
            anchors.append('<a class="cxr-cref" href="%s">%s</a>' % (
                _esc(self._cref_url + ref + rel), _esc('{{{%s}}}%s' % (ref, rel))))
            return TOKEN % (len(anchors) - 1) + tail

        def wiki_link(m):
            target, label = m.group(2).strip(), (m.group(4) or m.group(2)).strip()
            hit = wiki.get(target) or wiki.get(target + '.md')
            cm = CREF_RE.match(hit) if isinstance(hit, str) else None
            if not cm:
                anchors.append('<span class="cxr-wiki">%s</span>' % _esc(label))
            else:
                ref = '%s::%s,%s' % (cm.group(1), cm.group(2), cm.group(3))
                anchors.append('<a class="cxr-cref" href="%s">%s</a>' % (_esc(self._cref_url + ref), _esc(label)))
            return TOKEN % (len(anchors) - 1)

        text = CREF_RE.sub(cref_link, body)
        text = WIKI_RE.sub(wiki_link, text)
        out = _md(text)
        return TOKEN_RE.sub(lambda m: anchors[int(m.group(1))], out)

    def _embedded_page(self, page, urls, query, misc, uid, cref):
        """The HTML of a page category rendering this artifact (cref_view.page): its web_ with the cRef in the query."""
        if not PAGE_RE.match(str(page or '')):
            return '', '<p class="cxr-notice">cref_view.page must name a cserver.* category (%s)</p>' % _esc(page)
        q = dict(query)
        q.update({'cref': cref, 'uid': uid, 'embedded': '1'})
        q.pop('native_action', None)
        page_urls = dict(urls)
        # the page's own files are served by the host under its own name: <url_server><page>/... (the engine's
        # layout; a site built on it maps /c/<page>/ the same way)
        base = urls.get('url_server') or '/'
        name = page[len('cserver.'):]
        page_urls['url_files'] = str(misc.get('page_files_url') or (base + name + '/'))
        page_urls['url'] = str(misc.get('page_url') or (base + name + '/?'))
        r = self.cm.access({'category': page, 'command': 'web', 'urls': page_urls, 'misc': misc, 'query': q, 'con': False})
        if r.get('return', 1) > 0:
            return '', '<p class="cxr-notice">the page %s could not be shown: %s</p>' % (_esc(page), _esc(r.get('error', '')))
        hm = r.get('html_meta') or {}
        return str(hm.get('page_extra_style') or ''), str(hm.get('html') or '')

    # ------------------------------------------------------------------ the page
    def web_(self, ctx, urls, query={}, misc={}):
        """Render the page of the artifact named by ?cref= (or ?uid= with ?file=)."""
        query, misc = query or {}, misc or {}
        urls = urls or {}
        base = urls.get('url_server') or '/'
        self._cref_url = str(misc.get('cref_url') or (base + 'cref/'))
        browse_url = str(misc.get('browse_url') or (base + 'browse'))
        graph_url = str(misc.get('graph_url') or '')
        persona = str(misc.get('persona') or query.get('persona') or '').strip().lower()
        tech = persona in TECH_PERSONAS
        dark = str(misc.get('theme') or '') == 'dark' or str(query.get('dark', '')).lower() in ('1', 'true', 'yes')
        # inside the cPlatform's shell the page follows the shell's theme (THEME_JS); elsewhere it has its own switch
        self._hosted = bool(misc.get('ctuning_server'))

        # the texts of an artifact for the browser's detail panel (2026-11-10): README.md, _info.md and the file its
        # view names, rendered as this page renders them - [{rel, html, note}]
        if query.get('native_action') == 'texts':
            try:
                return {'return': 0, 'json': {'texts': self._texts_json(urls, misc, str(query.get('uid') or '').strip().lower())}}
            except Exception as e:
                return {'return': 0, 'json': {'error': '%s: %s' % (type(e).__name__, e), 'texts': []}}

        ref = str(query.get('cref') or '').strip()
        if ref:
            j = self._browse(urls, misc, native_action='resolve', cref=ref)
            uid, rel, notice = j.get('uid') or '', j.get('rel') or '', j.get('notice') or j.get('error') or ''
        else:
            uid, rel, notice = str(query.get('uid') or '').strip().lower(), str(query.get('file') or ''), ''
            if not uid:
                notice = 'no artifact named: /cref/<category>::<alias>,<UID>'
        a = self._browse(urls, misc, native_action='artifact', uid=uid, texts='0') if uid else {}
        if not uid or 'error' in a:
            return self._page(dark, 'Not found', '<p class="cxr-notice">%s</p>' % _esc(notice or a.get('error', '')),
                              head_only=True)

        row, desc, meta = a['row'], a.get('desc') or {}, a.get('meta') or {}
        cat, alias = row['cat'], row['alias']
        cref = a.get('cref') or '%s::%s,%s' % (cat, alias, uid)
        short = '%s::%s,%s' % (cat, alias, uid)
        view = self._view(cat, desc)
        hide = set(str(x).strip().lower() for x in (view.get('hide') or []))
        if not tech:
            hide |= {'commands', 'cmeta', 'desc', 'files'}
        title = (_get(desc, view['title']) if view.get('title') else None) or row.get('name') or alias
        root = self._path(cat, uid, alias)

        # the editor (2026-11-03): whether this viewer may save here - the edit buttons of the texts, of the _cmeta
        # and the _desc, the lists and the files
        can_edit = tech and bool(a.get('edit')) and bool(a.get('files')) and 'files' not in hide

        # the artifact's text: a page category that renders it (cref_view.page), else the file it names (README.md,
        # a note), with README.md and _info.md after it when it has them (2026-11-09: both shown, each edited in place)
        page_head, page_html, texts, text_note, shown = '', '', [], '', ''
        if view.get('page') and not rel:
            page_head, page_html = self._embedded_page(str(view['page']), urls, query, misc, uid, short)
        elif root:
            # shown: the file the first text block shows (the one asked for, when it could be rendered: then the
            # file browser is not asked to open it as well)
            texts, text_note, shown = self._texts_of(root, view, desc, rel)
        missing = [names[0] for names in TEXT_BESIDE if not any(self._safe_rel(root, n) for n in names)] \
            if can_edit and root and not page_html else []

        # the browser is asked by cRef, never by a bare UID (unique only with its category's): its own form,
        # <category UID>::<artifact UID> (':' and ',' stay readable in an address)
        node = '%s::%s' % (str(row.get('cat_uid') or cat).lower(), uid)

        # the graph of this artifact (repos=*) follows every connection the page lists - into a repository the server
        # unticks by default as well (browse_untick_repos: an archive; 2026-11-09, such a connection was not drawn)
        def browse_link(**keys):
            return _esc(browse_url + ('&' if '?' in browse_url else '?') + '&'.join('%s=%s' % (k, _q(v, ':,')) for k, v in keys.items() if v))

        def copy_button(text, what):
            return ('<button type="button" class="cxr-ic" data-copy="%s" title="Copy %s: %s" aria-label="Copy %s">%s</button>'
                    % (_esc(text), what, _esc(text), what, COPY_SVG))

        H = []
        H.append('<div class="cxr-top"><a class="cxr-back" id="cxr-back" href="#" hidden>&larr; Back</a>'
                 '<span class="cxr-crumb"><a href="%s" title="Every artifact of this category">%s</a> &middot; '
                 '<a data-cxr-repo="1" href="%s" title="Every artifact of this repository">%s</a></span><span class="cxr-actions">'
                 '<a href="%s" title="This artifact in the knowledge browser">Browser</a> &middot; '
                 '<a href="%s" title="This artifact and its connections, drawn">Graph</a>%s'
                 ' <button type="button" class="cxr-copy" id="cxr-new" hidden title="A new artifact of this category, in this repository, with these tags">+ Similar</button>'
                 ' <button type="button" class="cxr-copy" id="cxr-move" hidden title="Move it to another repository: same name, same UID, same files">Move to ...</button>'
                 ' <button type="button" class="cxr-copy" id="cxr-theme" title="Dark / light (kept in this browser)">&#9680;</button></span></div>'
                 % (browse_link(view='browse', cats=cat), _esc(cat),
                    browse_link(view='browse', repos=row.get('repo') or ''), _esc(row.get('repo') or '(registry)'),
                    browse_link(cref=node), browse_link(view='graph', repos='*', focus=node),
                    (' &middot; <a href="%s" title="The knowledge-graph page, focused on this artifact">Knowledge graph</a>'
                     % _esc(graph_url + ('&' if '?' in graph_url else '?') + 'focus=' + _q(alias))) if graph_url else ''))
        # the name and the cRef, each with a button that copies it (2026-11-09) - the cRef also as a text holds it
        H.append('<h1 class="cxr-title"><span class="cxr-tt">%s</span>%s</h1>' % (_esc(title), copy_button(str(title), 'the name')))
        H.append('<div class="cxr-ref"><code>%s</code>%s<button type="button" class="cxr-copy sm" data-copy="{{{%s}}}" '
                 'title="Copy it as a text holds it - a note, a memory, an AI prompt: {{{%s}}}">{{{ }}}</button></div>'
                 % (_esc(cref), copy_button(cref, 'the cRef'), _esc(short), _esc(short)))
        # the tags (2026-11-10: edited in place by a viewer who may write - the chips, then a field with all of them
        # in order: add, remove, reorder, Save; the knowledge browser's tags action writes the _cmeta)
        if row.get('tags') or can_edit:
            H.append('<div class="cxr-tags" id="cxr-tags" data-tags="%s">%s%s</div>' % (
                _esc(json.dumps([str(t) for t in row.get('tags') or []], ensure_ascii=False)),
                ''.join('<a class="cxr-chip" href="%s" title="Every artifact with this tag">%s</a>' % (browse_link(view='browse', q='tag:' + t), _esc(t))
                        for t in row.get('tags') or []),
                ' <button type="button" class="cxr-copy sm" id="cxr-tags-edit" title="Add, remove or reorder the tags">%s</button>'
                % ('edit tags' if row.get('tags') else '+ tags') if can_edit else ''))
        H.append('<hr class="cxr-hr">')

        def text_block(rel_, html_, note_):
            # a text that opens with the artifact's own title would show it twice: the page's title stands
            html_ = re.sub(r'^\s*<h1(?:\s[^>]*)?>(.*?)</h1>\s*',
                           lambda m: '' if re.sub(r'<[^>]+>', '', m.group(1)).strip().lower() == _esc(str(title)).strip().lower() else m.group(0),
                           html_, count=1, flags=re.S)
            edit = (' <button type="button" class="cxr-copy sm cxr-tedit" data-rel="%s" title="Edit %s here (Ctrl+S saves)">edit</button>'
                    % (_esc(rel_), _esc(rel_))) if can_edit and rel_.lower().endswith(TEXT_EXT) else ''
            return ('<div class="cxr-tblock" data-rel="%s"><article class="cxr-text">%s</article>'
                    '<div class="cxr-tfoot">from <code>%s</code>%s%s</div></div>'
                    % (_esc(rel_), html_, _esc(rel_), (' - ' + note_) if note_ else '', edit))

        # two columns: the texts on the left (then, folded, the technical details), the facts on the right (stacked
        # on a narrow screen)
        H.append('<div class="cxr-cols"><div class="cxr-mainc"><div class="cxr-texts">')
        if page_html:
            H.append('<article class="cxr-text">%s</article>' % page_html)
        for t in texts:
            H.append(text_block(*t))
        if not page_html and not texts:
            if text_note:
                H.append('<p class="cxr-notice">%s</p>' % text_note)
            elif desc and isinstance(desc.get('ck'), dict):
                H.append(self._facts_of_desc(desc, tech))
            else:
                H.append('<p class="cxr-muted">This artifact has no text of its own.</p>')
        if missing:
            H.append('<p class="cxr-tadd">%s</p>' % ''.join(
                '<button type="button" class="cxr-copy sm cxr-tnew" data-rel="%s" title="%s">+ %s</button>' % (n, _esc(TEXT_NEW[n]), n)
                for n in missing))
        H.append('</div>')

        # the connections apart (2026-11-10, the user: "separately show Connected with and Connected to"): with = both
        # name each other (cserver.browse marks them mutual), to = this artifact's _desc only, from = the other's only
        links = a.get('connections') or []
        with_ = [c for c in links if c.get('mutual')]
        to_ = [c for c in links if not c.get('mutual')]
        incoming_all = a.get('incoming') or []
        incoming = [r for r in incoming_all if not r.get('mutual')]
        n_in = (a.get('incoming_total') or len(incoming_all)) - (len(incoming_all) - len(incoming))
        more_in = ('<p class="cxr-muted">... and %d more: <a href="%s">open the graph</a></p>' % (n_in - len(incoming), browse_link(view='graph', repos='*', focus=node))) \
            if n_in > len(incoming) else ''
        reading = 'incoming' not in hide and not incoming_all and a.get('index') and not (a['index'] or {}).get('ready')
        reading = '<p class="cxr-muted">What connects to this artifact is still being read - open the page again in a moment.</p>' if reading else ''

        # a reader the page does not count as technical: the connections after the text, to follow
        if not tech:
            outgoing = to_ + (a.get('uses') or []) + (a.get('ai_uses') or [])
            if 'connections' not in hide and with_:
                H.append('<section class="cxr-sec"><h2>Connected with <span class="cxr-n">(%d)</span></h2>%s</section>'
                         % (len(with_), self._list_html(with_, browse_link)))
            if 'connections' not in hide and outgoing:
                H.append('<section class="cxr-sec"><h2>Connected to <span class="cxr-n">(%d)</span></h2>%s</section>'
                         % (len(outgoing), self._list_html(outgoing, browse_link)))
            if 'incoming' not in hide and incoming:
                H.append('<section class="cxr-sec"><h2>Connected from <span class="cxr-n">(%d)</span></h2>%s%s</section>'
                         % (n_in, self._list_html(incoming, browse_link), more_in))
            H.append(reading)

        if tech:
            T = []
            if 'commands' not in hide and a.get('commands'):
                T.append('<details><summary>Commands</summary><p class="cxr-muted">The same artifact from a terminal with cMeta installed.</p>%s</details>'
                         % ''.join('<div class="cxr-cmd"><code>%s</code><button type="button" class="cxr-copy sm" data-copy="%s">copy</button></div>' % (_esc(c), _esc(c)) for c in a['commands']))

            def edit_row(name, new=False):
                if not can_edit or not name:
                    return ''
                return ('<p class="cxr-edit-row"><button type="button" class="cxr-copy sm cxr-edit" data-rel="%s" data-new="%s">%s</button>%s</p>'
                        % (_esc(name), '1' if new else '0', ('+ ' if new else 'edit ') + _esc(name),
                           ' <span class="cxr-n">no _desc yet: the facts and the connections of this artifact</span>' if new else ''))

            if 'cmeta' not in hide:
                T.append('<details><summary>See _cmeta <span class="cxr-n">who made it, when, the tags</span></summary><pre class="cxr-pre cxr-refs" data-name="_cmeta.json">%s</pre>%s</details>'
                         % (_esc(json.dumps(meta, indent=2, ensure_ascii=False, default=str)), edit_row(a.get('meta_file'))))
            if 'desc' not in hide and desc:
                T.append('<details><summary>See _desc <span class="cxr-n">the facts and the connections (%s)</span></summary><pre class="cxr-pre cxr-refs" data-name="_desc.json">%s</pre>%s</details>'
                         % (_esc(a.get('desc_file') or ''), _esc(json.dumps(desc, indent=2, ensure_ascii=False, default=str)), edit_row(a.get('desc_file'))))
            elif 'desc' not in hide and can_edit:
                T.append(edit_row('_desc.yaml', new=True))
            # the lists after the _desc that declares them (2026-11-09): each category, its artifacts under it; the
            # connections and the AI uses changed here by a viewer who may write (cserver.browse's link)
            if 'connections' not in hide:
                if with_ or can_edit:
                    T.append(self._list_box('connections_with', with_, browse_link, editable=can_edit, link_key='connections', both=True))
                if to_ or can_edit:
                    T.append(self._list_box('connections_to', to_, browse_link, editable=can_edit, link_key='connections'))
                items = a.get('ai_uses') or []
                if items or can_edit:
                    T.append(self._list_box('ai_uses', items, browse_link, editable=can_edit))
                if a.get('uses'):
                    T.append(self._list_box('uses', a['uses'], browse_link))
            if 'incoming' not in hide and incoming:
                T.append(self._list_box('incoming', incoming, browse_link, count=n_in, extra=more_in))
            T.append(reading)
            if 'files' not in hide and a.get('files'):
                T.append('<details id="cxr-files" data-uid="%s"><summary>Files <span class="cxr-n">the artifact\'s folder</span></summary>'
                         '<div class="cxr-files-body"><p class="cxr-muted">Loading the files...</p></div></details>' % _esc(uid))
            if any(T):
                H.append('<section class="cxr-tech"><h2>Technical details</h2>%s</section>' % ''.join(T))
        H.append('</div>')      # end of the main column

        # the facts column
        H.append('<aside class="cxr-side">')
        if 'facts' not in hide:
            origin = a.get('origin') or {}
            rows_html = []
            rows_html.append(('Category', '<a href="%s" title="Every artifact of this category">%s</a>%s' % (
                browse_link(view='browse', cats=cat), _esc(cat),
                (' <a class="cxr-muted" href="%s" title="The category itself: its definition">(definition)</a>'
                 % _esc(self._cref_url + 'category::%s,%s' % (cat, a['category']['uid']))) if a.get('category') else '')))
            rows_html.append(('Repository', '<a data-cxr-repo="1" href="%s" title="Every artifact of this repository">%s</a>' % (
                browse_link(view='browse', repos=row.get('repo') or ''), _esc(row.get('repo') or '(registry)'))))
            if origin.get('url'):
                rows_html.append(('Origin', '<a href="%s" target="_blank" rel="noopener" title="%s">%s%s</a> &#8599;' % (
                    _esc(origin['url']), _esc(origin['url']), 'GitHub: ' if origin.get('kind') == 'github' else '', _esc(origin.get('label') or origin['url']))))
            else:
                rows_html.append(('Origin', '<span class="cxr-muted">%s</span>' % _esc(origin.get('label') or 'none')))
            rows_html.append(('UID', '<code>%s</code>' % _esc(uid)))
            if row.get('created'):
                rows_html.append(('Created', _esc(row['created'])))
            if row.get('updated'):
                rows_html.append(('Updated', _esc(row['updated'])))
            gen = meta.get('generator') if isinstance(meta.get('generator'), dict) else None
            if gen:
                who = ' by %s' % _esc(gen.get('by')) if gen.get('by') else ''
                rows_html.append(('Made', '%s%s' % (_esc(gen.get('method') or ''), who)))
            if a.get('path'):
                rows_html.append(('Path', '<code class="cxr-path">%s</code>' % _esc(a['path'])))
            H.append('<table class="cxr-facts">%s</table>' % ''.join('<tr><td>%s</td><td>%s</td></tr>' % (k, v) for k, v in rows_html))
            H.append('<div id="cxr-open" class="cxr-open" hidden></div>')
            H.append('<div class="cxr-graph"><a class="cxr-btn cxr-primary" id="cxr-focus" href="%s">Focus the graph here</a>'
                     '<label>depth <select id="cxr-depth">%s</select></label></div>'
                     % (browse_link(view='graph', repos='*', focus=node), ''.join('<option value="%d"%s>%s</option>' % (d, ' selected' if d == 2 else '', 'all' if d == 12 else d) for d in (1, 2, 3, 4, 5, 6, 12))))
            if graph_url:
                H.append('<div class="cxr-graph2"><a href="%s">Knowledge graph &#8599;</a></div>'
                         % _esc(graph_url + ('&' if '?' in graph_url else '?') + 'focus=' + _q(alias)))
        H.append('</aside></div>')      # end of the columns

        config = {'browse_url': browse_url, 'cref_url': self._cref_url, 'uid': uid, 'cref': short,
                  'open': bool(misc.get('client_local')) and tech, 'focus_url': browse_url + ('&' if '?' in browse_url else '?') + 'view=graph&repos=*&focus=' + _q(node, ':'),
                  'files': bool(a.get('files')) and tech and 'files' not in hide, 'file': rel if rel and not shown else '',
                  # "+ Similar": a new artifact of this category, in this repository, with these tags (a viewer who may write)
                  'create': bool(a.get('can_create')) and tech,
                  # "Move to" (2026-11-11): into another repository, for a viewer who may write here
                  'move': bool(a.get('edit')) and tech,
                  'new': {'cat': cat, 'repo': row.get('repo') or '', 'tags': list(row.get('tags') or [])}}
        return self._page(dark, title, '\n'.join(H), config=config, extra_head=page_head)

    def _facts_of_desc(self, desc, tech):
        """An artifact without a text: the facts of its _desc (ck) as a small table, so that a reader sees what it is."""
        ck = desc.get('ck') or {}
        rows = []
        for k, v in ck.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, default=str)
                if len(v) > 300:
                    v = v[:300] + '...'
            rows.append('<tr><td>%s</td><td>%s</td></tr>' % (_esc(k), _esc(v)))
        if not rows:
            return '<p class="cxr-muted">This artifact has no text of its own; its facts are in its description.</p>'
        return ('<div class="cxr-facts-desc"><h2>Facts <span class="cxr-n">from the description (_desc.ck)</span></h2>'
                '<table class="cxr-facts">%s</table></div>' % ''.join(rows))

    def _page(self, dark, title, body, head_only=False, config=None, extra_head=''):
        css = CSS
        # THEME_JS first in the page's box: the theme is set before anything of the page is drawn
        hosted = bool(getattr(self, '_hosted', False))
        html_body = '<div id="cxr" class="cxr%s"%s>%s%s</div>%s%s' % (
            ' cxr-dark' if dark else '', ' data-hosted="1"' if hosted else '', THEME_JS, body,
            '<script>var CXR_CONFIG = %s;</script><script>%s</script><script>%s</script><script>%s</script>' % (_js(dict(config or {}, hosted=hosted)), HL_JS, PICKER_JS, MOVE_JS), JS)
        return {'return': 0, 'html_meta': {'html': html_body, 'page_title': title,
                                            'page_extra_style': '<meta name="viewport" content="width=device-width, initial-scale=1">\n<style>%s</style>\n%s' % (css, extra_head or '')}}


def _q(s, safe=''):
    from urllib.parse import quote
    return quote(str(s), safe=safe)


# The file viewer's colouring, shared with cserver.browse - one source, its files/js/hl.js, inlined into this page
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'cserver.browse', 'files', 'js', 'hl.js'), encoding='utf-8') as _f:
        HL_JS = _f.read()
except OSError:
    HL_JS = ''
# The picker of the lists (2026-11-10), shared with cserver.browse the same way: its files/js/picker.js
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'cserver.browse', 'files', 'js', 'picker.js'), encoding='utf-8') as _f:
        PICKER_JS = _f.read()
except OSError:
    PICKER_JS = ''
# The dialog of "Move to" (2026-11-11), shared with cserver.browse the same way: its files/js/move.js
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'cserver.browse', 'files', 'js', 'move.js'), encoding='utf-8') as _f:
        MOVE_JS = _f.read()
except OSError:
    MOVE_JS = ''

CSS = """
.cxr{--fg:#14161a;--muted:#6b7280;--accent:#2a78d6;--line:#e5e7eb;--soft:#f6f7f9;color:var(--fg);max-width:1180px;margin:0 auto;padding:12px 16px 48px;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.cxr.cxr-dark{--fg:#e8eaee;--muted:#9aa3b2;--accent:#3987e5;--line:#2a2f3a;--soft:#171a21}
.cxr a{color:var(--accent);text-decoration:none}.cxr a:hover{text-decoration:underline}
.cxr-top{display:flex;gap:12px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:13px;margin-bottom:8px}
.cxr-actions{margin-left:auto}.cxr-copy{font:inherit;color:var(--accent);background:none;border:1px solid var(--line);border-radius:6px;padding:2px 8px;cursor:pointer}
.cxr-copy.sm{font-size:12px;padding:1px 6px}
.cxr-title{display:flex;align-items:center;gap:2px;font-size:28px;line-height:1.2;margin:4px 0 6px;overflow-wrap:anywhere}.cxr-title .cxr-tt{min-width:0}
.cxr-ref{display:flex;align-items:center;flex-wrap:wrap;gap:2px}.cxr-ref code{font-size:12.5px;color:var(--muted);overflow-wrap:anywhere;min-width:0}
.cxr-hr{border:0;border-top:1px solid var(--line);opacity:1;margin:10px 0 16px}
.cxr-tags{margin:8px 0 14px}.cxr-chip{display:inline-block;background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:1px 9px;margin:2px 4px 2px 0;font-size:12px;color:var(--fg)}
.cxr-cols{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px;align-items:start}
.cxr-mainc{min-width:0}.cxr-side{position:sticky;top:10px;border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--soft);font-size:13px}
.cxr-facts{width:100%;border-collapse:collapse;font-size:13px}.cxr-facts td{padding:3px 6px 3px 0;vertical-align:top;overflow-wrap:anywhere}.cxr-facts td:first-child{color:var(--muted);white-space:nowrap;width:84px}
.cxr-path{font-size:11.5px}
.cxr-open{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px}.cxr-open .msg{font-size:12px;color:var(--muted);width:100%}.cxr-open .msg.bad{color:#b4232c}
.cxr-btn{display:inline-block;font:inherit;font-size:13px;color:var(--fg);background:#fff;border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
.cxr-dark .cxr-btn{background:#1f242e}.cxr-btn:hover{text-decoration:none;filter:brightness(.97)}
.cxr-primary{background:var(--accent)!important;border-color:var(--accent)!important;color:#fff!important;font-weight:600}
.cxr-graph{display:flex;align-items:center;gap:10px;margin-top:10px;font-size:13px;color:var(--muted)}.cxr-graph select{font:inherit;font-size:12.5px}
.cxr-graph2{margin-top:8px;font-size:13px}
.cxr-text h1{font-size:24px}.cxr-text h2{font-size:20px;margin-top:22px}.cxr-text h3{font-size:16.5px}
.cxr-text pre,.cxr-pre{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow:auto;font-size:12.5px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere}
.cxr-text code,.cxr-cmd code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.cxr-text table{border-collapse:collapse;margin:10px 0;font-size:14px}.cxr-text th,.cxr-text td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
.cxr-text blockquote{border-left:3px solid var(--line);margin:8px 0;padding:2px 12px;color:var(--muted)}.cxr-text img{max-width:100%}
.cxr-wiki{border-bottom:1px dotted var(--muted)}
.cxr-muted{color:var(--muted);font-size:13px}.cxr-notice{color:#b4232c}.cxr-n{color:var(--muted);font-weight:normal;font-size:13px}
.cxr-sec{margin-top:26px;border-top:1px solid var(--line);padding-top:10px}.cxr-sec h2{font-size:18px;margin:4px 0 8px}
.cxr-files{list-style:none;padding:0;margin:0 0 6px}.cxr-files li{padding:2px 0;overflow-wrap:anywhere}.cxr-missing{color:var(--muted)}
.cxr-facts-desc h2{font-size:16px;margin:6px 0}
.cxr-tech{margin-top:30px;border-top:1px solid var(--line);padding-top:10px}.cxr-tech h2{font-size:15px;color:var(--muted);margin:4px 0 6px}
.cxr-tech details{border:1px solid var(--line);border-radius:8px;padding:6px 12px;margin:6px 0;background:var(--soft)}.cxr-tech summary{cursor:pointer;font-weight:500}
.cxr-cmd{display:flex;align-items:center;gap:8px;margin:6px 0}.cxr-cmd code{flex:1;overflow-wrap:anywhere}
.cxr-tree{list-style:none;margin:6px 0;padding:0;font-size:13px}.cxr-tree ul{list-style:none;margin:0;padding-left:18px}
.cxr-tree li{padding:1px 0}.cxr-tree .dir>span.nm{font-weight:600;cursor:pointer}.cxr-tree .dir>span.nm:before{content:'\\25BE ';color:var(--muted);font-size:11px}
.cxr-tree .dir.closed>span.nm:before{content:'\\25B8 '}.cxr-tree .dir.closed>ul{display:none}
.cxr-tree .file>a{cursor:pointer}.cxr-tree .file.on>a{font-weight:600}.cxr-tree .sz{color:var(--muted);font-size:11.5px;margin-left:6px}
.cxr-tree .why{color:var(--muted);font-size:12px;margin-left:8px;font-style:italic}
.cxr-fview{margin-top:10px;border-top:1px solid var(--line);padding-top:8px}.cxr-fhead{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px;margin-bottom:4px;overflow-wrap:anywhere}
.cxr-fview img{max-width:100%;border:1px solid var(--line);border-radius:6px}.cxr-fview iframe{width:100%;height:560px;border:1px solid var(--line);border-radius:6px;background:#fff}
.cxr-fview .cxr-text{border-top:0;padding-top:0}
.cxr-editor{width:100%;box-sizing:border-box;min-height:160px;margin-top:4px;padding:8px;resize:vertical;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--soft);color:var(--fg);border:1px solid var(--line);border-radius:6px;tab-size:2;white-space:pre;overflow:auto}
.cxr-emsg{color:#b42318;font-size:12.5px}
.cxr-edit-row{margin:6px 0 0}
.cxr-del{color:#b42318;margin-left:6px}
.cxr-newform{margin:10px 0;padding:10px 12px;max-width:560px;display:grid;gap:6px;border:1px solid var(--line);border-radius:8px;background:var(--soft)}
.cxr-newform-title{font-weight:600}.cxr-newform label{display:grid;grid-template-columns:90px 1fr;align-items:center;gap:8px;font-size:13px}
.cxr-newform input,.cxr-newform select{font:inherit;font-size:13px;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--fg)}
.cxr-dark .cxr-newform input,.cxr-dark .cxr-newform select{background:#1f242e}.cxr-newform-acts{display:flex;gap:8px;align-items:center}
.hl-c{color:#6a737d;font-style:italic}.hl-s{color:#0a7a3f}.hl-k{color:#1f4fbf;font-weight:600}.hl-v{color:#b35c00}.hl-n{color:#9a2a7a}.hl-h{color:#1f4fbf;font-weight:700}.hl-d{color:#7a3ab8}.hl-p{color:#6a737d}.hl-t{color:#1f4fbf}.hl-r{color:var(--accent);text-decoration:underline dotted}
.cxr-dark .hl-c{color:#8b949e}.cxr-dark .hl-s{color:#7ee787}.cxr-dark .hl-k{color:#79c0ff}.cxr-dark .hl-v{color:#ffa657}.cxr-dark .hl-n{color:#d2a8ff}.cxr-dark .hl-h{color:#79c0ff}.cxr-dark .hl-d{color:#d2a8ff}.cxr-dark .hl-t{color:#79c0ff}
.cxr-ic{display:inline-flex;align-items:center;justify-content:center;flex:none;width:26px;height:26px;margin-left:4px;padding:0;color:var(--muted);background:none;border:1px solid transparent;border-radius:6px;cursor:pointer;font:inherit;font-size:17px;line-height:1;vertical-align:middle}
.cxr-ic:hover,.cxr-ic:focus-visible{color:var(--accent);border-color:var(--line)}.cxr-ic.cxr-lx:hover,.cxr-ic.cxr-lx:focus-visible{color:#b42318}
.cxr-done{color:#0a7a3f!important;border-color:#0a7a3f!important}
.cxr-tblock+.cxr-tblock{margin-top:22px;padding-top:12px;border-top:1px dashed var(--line)}
.cxr-tfoot{display:flex;align-items:center;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:13px;margin-top:6px}
.cxr-tadd{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}
.cxr-ltools{margin:4px 0 2px}
.cxr-lcat{margin:10px 0 2px;font-size:13px;font-weight:600}.cxr-lcat a{color:var(--fg)}
.cxr-litems{list-style:none;margin:0;padding:0 0 0 22px}.cxr-litems li{display:flex;align-items:center;flex-wrap:wrap;min-height:26px;overflow-wrap:anywhere}
.cxr-lname{min-width:0}.cxr-lname .cxr-n{margin-left:6px}
.cxr-lsure{display:inline-flex;align-items:center;gap:6px;margin-left:8px}
.cxr-ladd{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:12px 0 4px}
.cxr-ladd input{flex:1 1 260px;min-width:0;font:inherit;font-size:13px;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--fg)}
.cxr-dark .cxr-ladd input{background:#1f242e}
.cxr-ladd{position:relative}.cxr{--cmp-accent:var(--accent);--cmp-line:var(--line);--cmp-bg:#fff;--cmp-muted:var(--muted);--cmp-soft:rgba(42,120,214,.12)}
.cxr.cxr-dark{--cmp-bg:#1f242e;--cmp-soft:rgba(57,135,229,.22)}
.cxr-tagform{display:inline-flex;flex-wrap:wrap;align-items:center;gap:6px;margin-left:6px;vertical-align:middle}.cxr-tagform input{min-width:280px;font:inherit;font-size:13px;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--fg)}
.cxr-dark .cxr-tagform input{background:#1f242e}
.cxr-tags-editing{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.cxr-tagedit{display:inline-flex;align-items:center;gap:1px;padding:1px 3px 1px 9px}
.cxr-tagbtn{border:0;background:none;color:var(--muted);font:inherit;font-size:12px;line-height:1;padding:2px 4px;border-radius:999px;cursor:pointer}
.cxr-tagbtn:hover{background:var(--line);color:var(--fg)}.cxr-tagbtn.cxr-tagdel:hover{background:#d64545;color:#fff}
.cxr-taginput{font:inherit;font-size:12.5px;padding:2px 8px;border:1px solid var(--line);border-radius:999px;background:#fff;color:var(--fg);min-width:150px}
.cxr-taginput.wide{min-width:320px;border-radius:6px}.cxr-dark .cxr-taginput{background:#1f242e}
.cxr-flash{margin:6px 0 8px;padding:6px 10px;border-left:3px solid #0a7a3f;background:var(--soft);font-size:13px;overflow-wrap:anywhere}.cxr-flash.bad{border-left-color:#b42318}
.cxr-toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);max-width:min(92vw,720px);padding:8px 14px;border-radius:8px;background:#14161a;color:#fff;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:opacity .15s;z-index:50;overflow-wrap:anywhere}
.cxr-dark .cxr-toast{background:#e8eaee;color:#14161a}.cxr-toast.on{opacity:1}.cxr-toast.bad{background:#b42318;color:#fff}
@media (max-width:860px){.cxr{padding:8px 12px 40px}.cxr-title{font-size:22px}.cxr-cols{grid-template-columns:minmax(0,1fr)}.cxr-side{position:static}}
"""

# The theme (2026-11-09: a page in dark mode opened its cRef links in light mode), decided before the page is drawn:
# ?dark=1|0 in the address; else the one theme of every page of this server, cmeta.theme in the browser (2026-11-10:
# the pages of a server share it - its switch writes it, a change on another page is followed); else the theme of the
# page of this server the reader came from, as pages kept it before cmeta.theme - each page keeps its own
# as cserver.<name>.theme in the browser (the knowledge browser cserver.browse.theme, the home page
# cserver.projects.theme, a page of another repository the same way), with the engine's pages' keys after it as those
# pages read them; else the choice kept here (cserver.cref.theme); else the server's (a platform theme,
# ?dark). Whatever is decided is kept, so the next cRef page opened from this one has it too. In dark mode the page
# colours the window; inside the cPlatform's shell it follows the shell's theme instead (html[data-ctp-theme]).
THEME_JS = """<script>
(function(){
  var r=document.getElementById('cxr'),html=document.documentElement,K='cserver.cref.theme';if(!r)return;
  var hosted=r.getAttribute('data-hosted')==='1';
  function paint(d){r.classList.toggle('cxr-dark',!!d);if(!hosted){var bg=d?'#14161a':'';html.style.backgroundColor=bg;
    if(document.body)document.body.style.backgroundColor=bg;html.style.colorScheme=d?'dark':'';}}
  window.cxrTheme=paint;
  if(hosted){var t=html.getAttribute('data-ctp-theme');if(t)paint(t==='dark');return;}
  function get(k){try{return localStorage.getItem(k);}catch(e){return null;}}
  var d=null;
  try{var q=new URLSearchParams(location.search).get('dark');if(q)d=/^(1|true|yes|dark)$/i.test(q);}catch(e){}
  if(d===null){var sh=get('cmeta.theme');if(sh)d=sh==='dark';}
  if(d===null){try{var f=document.referrer?new URL(document.referrer):null;
    if(f&&f.origin===location.origin){var page=f.pathname.replace(/^[/]+/,'').split('/')[0]||'projects';
      if(page!=='cref'){var v=get('cserver.'+page+'.theme')||get('cserver.browse.theme')||get('cserver.projects.theme');if(v)d=v==='dark';}}}catch(e){}}
  if(d===null){var s=get(K);if(s)d=s==='dark';}
  if(d===null)d=r.classList.contains('cxr-dark');
  try{localStorage.setItem(K,d?'dark':'light');}catch(e){}
  paint(d);
})();
</script>"""

JS = """<script>
(function(){
  var C=window.CXR_CONFIG||{};
  // the theme switch (THEME_JS decided the theme): kept here; inside the cPlatform the shell's theme, followed
  var tb=document.getElementById('cxr-theme'),root=document.getElementById('cxr');
  if(tb&&C.hosted){tb.hidden=true;var ht=document.documentElement;
    if(window.MutationObserver)new MutationObserver(function(){var t=ht.getAttribute('data-ctp-theme');if(t&&window.cxrTheme)cxrTheme(t==='dark');}).observe(ht,{attributes:true,attributeFilter:['data-ctp-theme']});}
  else if(tb){tb.addEventListener('click',function(){var d=!root.classList.contains('cxr-dark');if(window.cxrTheme)cxrTheme(d);
    try{localStorage.setItem('cserver.cref.theme',d?'dark':'light');localStorage.setItem('cmeta.theme',d?'dark':'light');}catch(e){}});
    // the theme of every page of this server, changed on another page (another tab): followed
    window.addEventListener('storage',function(e){if(e.key==='cmeta.theme'&&e.newValue&&window.cxrTheme)cxrTheme(e.newValue==='dark');});}
  // the text blocks named by their file (the text shown, a front matter, the _cmeta/_desc) coloured by their kind, the cRefs inside as links
  if(window.cmetaHL){document.querySelectorAll('pre.cxr-pre[data-name]').forEach(function(p){var n=p.getAttribute('data-name');if(cmetaHL.lang(n))p.innerHTML=cmetaHL(p.textContent,n,{cref_url:C.cref_url||'/cref/'});});}
  var b=document.getElementById('cxr-back');
  try{if(b&&history.length>1&&document.referrer&&new URL(document.referrer).origin===location.origin){b.hidden=false;b.addEventListener('click',function(e){e.preventDefault();history.back();});}}catch(e){}
  function api(action,params){var u=C.browse_url||'/browse';u+=(u.indexOf('?')>=0?'&':'?')+'native_action='+action;
    return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(params||{})}).then(function(r){return r.text().then(function(t){var d;try{d=JSON.parse(t);}catch(e){throw new Error('HTTP '+r.status);}if(d&&d.error)throw new Error(d.error);return d;});});}
  function h(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function size(n){return n<1024?n+' B':n<1048576?(n/1024).toFixed(n<10240?1:0)+' KB':(n/1048576).toFixed(1)+' MB';}
  // copy (2026-11-09): every button with data-copy - the name, the cRef, {{{...}}}, the entries of a list, a list, the
  // commands; the clipboard's API where the page is a secure context (https, this machine), else a selected text and
  // the browser's own copy (a server reached over http by its name); a note at the foot of the window says what
  function toast(text,bad){var t=document.getElementById('cxr-toast');if(!t){t=h('div','cxr-toast');t.id='cxr-toast';t.setAttribute('role','status');root.appendChild(t);}
    t.textContent=text;t.className='cxr-toast on'+(bad?' bad':'');clearTimeout(t._h);t._h=setTimeout(function(){t.className='cxr-toast';},2400);}
  function legacyCopy(text){var keep=document.activeElement,ta=document.createElement('textarea');ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.top='0';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,text.length);var ok=false;try{ok=document.execCommand('copy');}catch(e){ok=false;}document.body.removeChild(ta);
    if(keep&&keep.focus){try{keep.focus({preventScroll:true});}catch(e){}}return ok?Promise.resolve():Promise.reject(new Error('this browser did not let the page copy'));}
  function copyText(text){if(navigator.clipboard&&window.isSecureContext)return navigator.clipboard.writeText(text).catch(function(){return legacyCopy(text);});return legacyCopy(text);}
  document.querySelectorAll('[data-copy]').forEach(function(x){x.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();var t=x.getAttribute('data-copy');
    copyText(t).then(function(){toast('Copied: '+t);x.classList.add('cxr-done');setTimeout(function(){x.classList.remove('cxr-done');},1200);}).catch(function(er){toast('Not copied ('+er.message+'): '+t,true);});});});
  // the lists' boxes stay as the reader left them, open or folded (in this browser)
  var OPEN='cserver.cref.open',opened=[];try{opened=JSON.parse(localStorage.getItem(OPEN)||'[]')||[];}catch(e){opened=[];}
  document.querySelectorAll('details.cxr-lbox[data-box]').forEach(function(d){var k=d.getAttribute('data-box');if(opened.indexOf(k)>=0)d.open=true;
    d.addEventListener('toggle',function(){var i=opened.indexOf(k);if(d.open&&i<0)opened.push(k);else if(!d.open&&i>=0)opened.splice(i,1);else return;try{localStorage.setItem(OPEN,JSON.stringify(opened));}catch(e){}});});
  // a change is drawn again by the server (the page reloads); what the change said is shown after it, where it was made:
  // a list's box, the technical details, the texts
  var FLASH='cserver.cref.flash';
  function again(where,lines,bad){try{sessionStorage.setItem(FLASH,JSON.stringify({uid:C.uid,where:where||'',lines:lines||[],bad:!!bad}));}catch(e){}location.reload();}
  (function(){var f=null;try{f=JSON.parse(sessionStorage.getItem(FLASH)||'null');sessionStorage.removeItem(FLASH);}catch(e){f=null;}
    if(!f||f.uid!==C.uid||!(f.lines||[]).length)return;
    var d=h('div','cxr-flash'+(f.bad?' bad':''));f.lines.forEach(function(l){d.appendChild(h('div',null,l));});
    var box=null;document.querySelectorAll('details.cxr-lbox[data-box]').forEach(function(x){if(x.getAttribute('data-box')===f.where)box=x;});
    var tech=document.querySelector('.cxr-tech'),texts=document.querySelector('.cxr-texts');
    if(box){box.open=true;var b=box.querySelector('.cxr-lbody');b.insertBefore(d,b.firstChild);}
    else if(f.where==='tags'&&document.getElementById('cxr-tags')){var tg=document.getElementById('cxr-tags');tg.parentNode.insertBefore(d,tg.nextSibling);}
    else if(f.where==='tech'&&tech){tech.insertBefore(d,tech.children[1]||null);}
    else if(texts){texts.insertBefore(d,texts.firstChild);}})();
  // the editor of one text file (2026-11-03): the server says who may save; Save (Ctrl+S) hands the text back with the
  // fingerprint it was read with, so that a file changed meanwhile is not overwritten; a refusal comes back as the message
  function editorBox(rel,text,stamp,saved,cancel){var box=h('div','cxr-ebox');
    var ta=h('textarea','cxr-editor');ta.spellcheck=false;ta.wrap='off';ta.value=text||'';ta.rows=Math.max(8,Math.min(40,(ta.value.match(/\\n/g)||[]).length+2));
    var msg=h('span','cxr-emsg'),sv=h('button','cxr-btn','Save'),cn=h('button','cxr-copy sm','cancel');sv.type='button';cn.type='button';
    function doSave(){msg.textContent='';sv.disabled=true;api('save',{uid:C.uid,rel:rel,text:ta.value,stamp:stamp||''}).then(saved).catch(function(e){sv.disabled=false;msg.textContent=e.message;});}
    sv.addEventListener('click',doSave);cn.addEventListener('click',cancel);
    ta.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();doSave();}
      else if(e.key==='Tab'){e.preventDefault();var s=ta.selectionStart,t=ta.selectionEnd;ta.value=ta.value.slice(0,s)+'  '+ta.value.slice(t);ta.selectionStart=ta.selectionEnd=s+2;}});
    var head=h('div','cxr-fhead');head.appendChild(h('b',null,(stamp?'editing ':'new file ')+rel));head.appendChild(sv);head.appendChild(cn);head.appendChild(msg);
    box.appendChild(head);box.appendChild(ta);box.ta=ta;return box;}
  // the texts (2026-11-09): README.md, _info.md, the file the page shows - edited where they are read, a missing one
  // made the same way; the server draws the page again after a save
  function textEdit(block,rel,isNew){if(block.querySelector('.cxr-ebox'))return;var kids=Array.prototype.slice.call(block.children);
    function close(){var e=block.querySelector('.cxr-ebox');if(e)e.remove();if(isNew){block.remove();}else{kids.forEach(function(k){k.hidden=false;});}}
    function open(text,stamp){kids.forEach(function(k){k.hidden=true;});var box=editorBox(rel,text,stamp,function(r){again('texts',[(r.created?'Made ':'Saved ')+rel].concat(r.warnings||[]));},close);
      block.appendChild(box);box.ta.focus();box.scrollIntoView({block:'nearest'});}
    if(isNew){open('','');return;}
    api('file',{uid:C.uid,rel:rel}).then(function(j){if(j.kind==='text'&&j.editable&&j.stamp){open(j.text,j.stamp);}
      else{toast(rel+': '+(j.truncated?'too large to edit here':'not editable here'),true);}}).catch(function(e){toast(e.message,true);});}
  document.querySelectorAll('.cxr-tedit').forEach(function(x){x.addEventListener('click',function(){textEdit(x.closest('.cxr-tblock'),x.getAttribute('data-rel'),false);});});
  document.querySelectorAll('.cxr-tnew').forEach(function(x){x.addEventListener('click',function(){var rel=x.getAttribute('data-rel'),texts=x.closest('.cxr-texts'),ex=null;
    texts.querySelectorAll('.cxr-tblock.cxr-new').forEach(function(b){if(b.getAttribute('data-rel')===rel)ex=b;});
    if(ex){ex.querySelector('textarea').focus();return;}
    var b=h('div','cxr-tblock cxr-new');b.setAttribute('data-rel',rel);texts.insertBefore(b,x.parentNode);textEdit(b,rel,true);});});
  // the lists (2026-11-09): x removes an entry (asked on its line; a connection goes from both sides where this reader
  // may write), the field adds names or cRefs (";" between them), offering the AI contexts and the artifacts whose names
  // hold what is typed; cserver.browse's link makes the change with the category's own update, then the page is drawn
  // again with what it said
  function said(r){var l=(r.changes||[]).map(function(c){return c.charAt(0)==='+'?'added '+c.slice(2):c.charAt(0)==='-'?'removed '+c.slice(2):c;});
    (r.warnings||[]).forEach(function(w){l.push(w);});return l.length?l:['nothing changed'];}
  document.querySelectorAll('.cxr-lx').forEach(function(x){x.addEventListener('click',function(e){e.preventDefault();var li=x.parentNode;if(li.querySelector('.cxr-lsure'))return;
    var key=x.getAttribute('data-key'),box=(x.closest('details.cxr-lbox')||x).getAttribute('data-box')||key,sure=h('span','cxr-lsure'),yes=h('button','cxr-copy sm cxr-del','remove'),no=h('button','cxr-copy sm','keep');yes.type='button';no.type='button';
    yes.title=key==='connections'?'Remove this connection - from the other artifact\\'s _desc too, where it names this one':'Remove it from the AI uses of this artifact';
    sure.appendChild(yes);sure.appendChild(no);li.appendChild(sure);x.hidden=true;yes.focus();
    no.addEventListener('click',function(){sure.remove();x.hidden=false;x.focus();});
    yes.addEventListener('click',function(){yes.disabled=true;no.disabled=true;api('link',{uid:C.uid,key:key,remove:x.getAttribute('data-ref')}).then(function(r){again(box,said(r));})
      .catch(function(er){sure.textContent='';sure.appendChild(h('span','cxr-emsg',er.message));x.hidden=false;});});});});
  // the picker of a list (2026-11-10): cmetaPicker of cserver.browse's picker.js, inlined above - what is typed is searched
  // as one types (the most recent first), chips, ";" or Enter for the next; Add writes the chips ("with": both sides, "to":
  // this artifact's _desc) through cserver.browse's link, then the page is drawn again with what it said
  document.querySelectorAll('form.cxr-ladd').forEach(function(f){var key=f.getAttribute('data-key'),box=f.getAttribute('data-box')||key,both=f.getAttribute('data-both')==='1',msg=f.querySelector('.cxr-emsg');
    if(!window.cmetaPicker)return;
    cmetaPicker(f,{api:api,self:C.uid,key:key,submit:function(all){msg.textContent='';
      return api('link',{uid:C.uid,key:key,add:all.join(';'),both:both?'1':''}).then(function(r){if(!(r.changes||[]).length){msg.textContent=said(r).join('; ');return true;}again(box,said(r));})
        .catch(function(er){msg.textContent=er.message;return true;});}});});
  // the tags (2026-11-12, the user: "add cross (to delete) and edit (to rename) for each tag and a button to add new tag"):
  // "edit tags" turns each chip into one with a rename and a delete, "+ tag" adds one (commas between several), "as text"
  // is the field of before (reorder, paste a list); each change is saved at once through cserver.browse's tags action;
  // "done" draws the page again with what changed (Esc leaves a box, Enter saves it)
  var tb=document.getElementById('cxr-tags-edit'),tagsBox=document.getElementById('cxr-tags');
  if(tb&&tagsBox){
    var tags0=[];try{tags0=JSON.parse(tagsBox.getAttribute('data-tags')||'[]');}catch(e){tags0=[];}
    var tagsNow=tags0.slice(),tagsBusy=false,tagsMsg=h('span','cxr-emsg');
    var tagUniq=function(list){var out=[];list.forEach(function(x){x=String(x||'').trim();if(x&&out.indexOf(x)<0)out.push(x);});return out;};
    var tagSplit=function(v){return tagUniq(String(v||'').split(','));};
    var tagSave=function(next,what){if(tagsBusy)return;tagsBusy=true;tagsMsg.textContent='saving ...';
      api('tags',{uid:C.uid,tags:tagUniq(next)}).then(function(r){tagsBusy=false;tagsNow=(r.tags||tagUniq(next)).slice();tagsMsg.textContent=r.changed?what:'nothing changed';tagsDraw();})
        .catch(function(er){tagsBusy=false;tagsMsg.textContent=er.message;});};
    var tagInput=function(value,place,ok){var inp=document.createElement('input');inp.type='text';inp.className='cxr-taginput';inp.value=value||'';inp.placeholder=place;inp.spellcheck=false;inp.setAttribute('aria-label',place);
      inp.addEventListener('keydown',function(e){if(e.key==='Escape'){e.preventDefault();e.stopPropagation();tagsDraw();}else if(e.key==='Enter'){e.preventDefault();ok(inp.value);}});
      return inp;};
    var tagsDraw=function(){tagsBox.innerHTML='';tagsBox.setAttribute('data-tags',JSON.stringify(tagsNow));tagsBox.classList.add('cxr-tags-editing');
      tagsNow.forEach(function(t,i){var c=h('span','cxr-chip cxr-tagedit'),rn=h('button','cxr-tagbtn','✎'),rm=h('button','cxr-tagbtn cxr-tagdel','✕');
        rn.type='button';rm.type='button';rn.title='Rename '+t;rm.title='Delete the tag '+t;rn.setAttribute('aria-label','Rename '+t);rm.setAttribute('aria-label','Delete '+t);
        rn.addEventListener('click',function(){var inp=tagInput(t,'the new name of '+t,function(v){var parts=tagSplit(v);if(!parts.length||(parts.length===1&&parts[0]===t)){tagsDraw();return;}
          tagSave(tagsNow.slice(0,i).concat(parts,tagsNow.slice(i+1)),'renamed '+t+' to '+parts.join(', '));});c.replaceWith(inp);inp.focus();inp.select();});
        rm.addEventListener('click',function(){tagSave(tagsNow.filter(function(x,j){return j!==i;}),'deleted '+t);});
        c.appendChild(h('span','cxr-tagtext',t));c.appendChild(rn);c.appendChild(rm);tagsBox.appendChild(c);});
      var add=h('button','cxr-copy sm cxr-tagadd','+ tag'),txt=h('button','cxr-copy sm','as text'),done=h('button','cxr-btn','done');add.type='button';txt.type='button';done.type='button';
      add.title='A new tag (commas between several)';txt.title='All the tags as one text: reorder them, paste a list';done.title='The page drawn again with the tags as they are now';
      add.addEventListener('click',function(){var inp=tagInput('','a new tag (commas: several)',function(v){var parts=tagSplit(v);if(!parts.length){tagsDraw();return;}tagSave(tagsNow.concat(parts),'added '+parts.join(', '));});tagsBox.insertBefore(inp,add);inp.focus();});
      txt.addEventListener('click',function(){var inp=tagInput(tagsNow.join(', '),'the tags, in order - commas between them',function(v){tagSave(tagSplit(String(v).split(' ').join(',')),'the tags written as given');});
        inp.classList.add('wide');tagsBox.insertBefore(inp,add);inp.focus();inp.select();});
      done.addEventListener('click',function(){if(JSON.stringify(tagsNow)===JSON.stringify(tags0)){location.reload();return;}
        again('tags',['tags: '+(tagsNow.join(', ')||'none')+(tags0.length?' (were '+tags0.join(', ')+')':'')]);});
      tagsBox.appendChild(add);tagsBox.appendChild(txt);tagsBox.appendChild(done);tagsBox.appendChild(tagsMsg);};
    tb.addEventListener('click',function(){tagsDraw();if(!tagsNow.length){var a=tagsBox.querySelector('.cxr-tagadd');if(a)a.click();}});}
  // the depth of the focused graph
  var sel=document.getElementById('cxr-depth'),fo=document.getElementById('cxr-focus');
  if(sel&&fo){sel.addEventListener('change',function(){fo.href=C.focus_url+(sel.value&&sel.value!=='2'?'&depth='+sel.value:'');});}
  // the open buttons: a browser on the server's own machine
  var ob=document.getElementById('cxr-open');
  if(ob&&C.open){ob.hidden=false;var msg=h('span','msg');[['folder','Open folder','Open this folder in the file manager'],['shell','Shell','A terminal in this folder'],['far','Far','Far Manager in this folder']].forEach(function(w){
    var bt=h('button','cxr-btn',w[1]);bt.type='button';bt.title=w[2];bt.addEventListener('click',function(){msg.className='msg';msg.textContent='opening...';
      api('open',{uid:C.uid,what:w[0]}).then(function(){msg.textContent=w[1]+' opened on this machine';}).catch(function(e){msg.className='msg bad';msg.textContent=e.message;});});
    ob.appendChild(bt);});ob.appendChild(msg);}
  // "Move to" (2026-11-11): the dialog of cserver.browse's move.js; after the move (and its Undo) the repository the
  // page names, at the top and in the facts, is the new one - no reload, so that the Undo stays at hand
  var mvb=document.getElementById('cxr-move');
  if(mvb&&C.move&&window.cmetaMove){mvb.hidden=false;mvb.addEventListener('click',function(){
    cmetaMove({api:api,uid:C.uid,dark:!!document.querySelector('.cxr-dark'),done:function(out){
      var u=C.browse_url||'/browse';u+=(u.indexOf('?')>=0?'&':'?')+'view=browse&repos='+encodeURIComponent(out.to);
      document.querySelectorAll('[data-cxr-repo]').forEach(function(a){a.textContent=out.to;a.setAttribute('href',u);});
      if(C.new)C.new.repo=out.to;}});});}
  // "+ Similar" (2026-11-03): a new artifact of this category - its name, its tags (these ones), its repository (this one first) -
  // made by the category's own "add" on the server (a dated category puts the day in front), then its page opens
  var nb=document.getElementById('cxr-new');
  if(nb&&C.create&&C.new){nb.hidden=false;nb.addEventListener('click',function(){var old=document.getElementById('cxr-newform');if(old){old.remove();return;}
    var f=document.createElement('form');f.id='cxr-newform';f.className='cxr-newform';
    function field(label,el){var l=h('label');l.appendChild(h('span',null,label));l.appendChild(el);f.appendChild(l);}
    var nm=document.createElement('input');nm.type='text';nm.required=true;nm.autocomplete='off';nm.placeholder='the name (a dated category puts the day in front)';
    var tg=document.createElement('input');tg.type='text';tg.autocomplete='off';tg.value=(C.new.tags||[]).join(', ');tg.placeholder='tags, comma-separated';
    var rp=document.createElement('select');if(C.new.repo){var o=document.createElement('option');o.value=C.new.repo;o.textContent=C.new.repo;rp.appendChild(o);}
    api('options',{}).then(function(j){(j.repos||[]).forEach(function(x){if(x[0]===C.new.repo||x[0]==='(registry)')return;var o2=document.createElement('option');o2.value=x[0];o2.textContent=x[0];rp.appendChild(o2);});}).catch(function(){});
    var msg=h('span','cxr-emsg'),ok=h('button','cxr-btn cxr-primary','Create'),no=h('button','cxr-copy sm','cancel');ok.type='submit';no.type='button';no.addEventListener('click',function(){f.remove();});
    f.appendChild(h('div','cxr-newform-title','New '+C.new.cat));field('Name',nm);field('Tags',tg);field('Repository',rp);
    var acts=h('div','cxr-newform-acts');acts.appendChild(ok);acts.appendChild(no);acts.appendChild(msg);f.appendChild(acts);
    f.addEventListener('submit',function(e){e.preventDefault();msg.textContent='';ok.disabled=true;
      api('create',{cat:C.new.cat,repo:rp.value,alias:nm.value.trim(),tags:tg.value}).then(function(r){location.href=(C.cref_url||'/cref/')+encodeURI(r.cref);}).catch(function(er){ok.disabled=false;msg.textContent=er.message;});});
    var top=document.querySelector('.cxr-top');if(top&&top.parentNode){top.parentNode.insertBefore(f,top.nextSibling);}else{document.body.appendChild(f);}nm.focus();});}
  // the files: a tree of the folder, loaded when the section opens (or at once when the address names a file)
  var fd=document.getElementById('cxr-files');
  if(fd&&C.files){var loaded=false,body=fd.querySelector('.cxr-files-body'),view=null,blob=null,pendingEdit=null;
    function why(name,depth){if(depth===0&&name==='ck')return 'the dated records: one folder per day (YYYYMMDD) the facts were observed - nothing is overwritten';
      if(depth===1&&/^\\d{8}$/.test(name))return 'the facts observed on '+name.slice(0,4)+'-'+name.slice(4,6)+'-'+name.slice(6);
      if(depth===0&&name==='files')return 'the files the artifact serves (a page: its scripts and styles)';return '';}
    function openFile(rel,li,edit){api('file',{uid:C.uid,rel:rel}).then(function(j){if(!view){view=h('div','cxr-fview');body.appendChild(view);}view.innerHTML='';if(blob){URL.revokeObjectURL(blob);blob=null;}
      if(edit&&j.kind==='text'&&j.editable){editFile(j,li);return;}
      fd.querySelectorAll('.file.on').forEach(function(x){x.classList.remove('on');});if(li)li.classList.add('on');
      var head=h('div','cxr-fhead');head.appendChild(h('b',null,j.rel));head.appendChild(document.createTextNode(' \\u00b7 '+size(j.size)+(j.truncated?' \\u00b7 the first 512 KB':'')));
      var cl=h('button','cxr-copy sm','close');cl.type='button';cl.addEventListener('click',function(){view.innerHTML='';});head.appendChild(cl);
      var ln=h('a','cxr-copy sm','link');ln.href=(C.cref_url||'/cref/')+encodeURI(C.cref)+'/'+j.rel.split('/').map(encodeURIComponent).join('/');ln.title='The address of this file';head.appendChild(ln);
      if(j.kind==='text'&&j.editable){var ed=h('button','cxr-copy sm','edit');ed.type='button';ed.title='Edit this file here (Ctrl+S saves)';ed.addEventListener('click',function(){editFile(j,li);});head.appendChild(ed);}
      view.appendChild(head);
      if(j.kind==='text'){var pre=h('pre','cxr-pre cxr-refs');if(window.cmetaHL){pre.innerHTML=cmetaHL(j.text,j.rel,{cref_url:C.cref_url||'/cref/'});}else{pre.textContent=j.text;}view.appendChild(pre);}
      else if(j.kind==='binary'&&j.b64){var bin=atob(j.b64),arr=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);blob=URL.createObjectURL(new Blob([arr],{type:j.mime}));
        var a=h('a',null,'open in a new tab');a.href=blob;a.target='_blank';a.rel='noopener';view.appendChild(a);
        if(j.mime.indexOf('image/')===0){var im=document.createElement('img');im.src=blob;im.alt=j.rel;view.appendChild(im);}else if(j.mime==='application/pdf'){var fr=document.createElement('iframe');fr.src=blob;fr.title=j.rel;view.appendChild(fr);}}
      else{view.appendChild(h('p','cxr-muted',j.note||'not shown'));}
      view.scrollIntoView({block:'nearest'});}).catch(function(e){if(!view){view=h('div','cxr-fview');body.appendChild(view);}view.textContent=e.message;});}
    // the editor (2026-11-03), as on /browse: the server says which files this viewer may save (cserver.browse's save,
    // its checks and its fingerprint); a saved _cmeta reloads the page, whose meta is rendered on the server
    function editFile(j,li){if(!view){view=h('div','cxr-fview');body.appendChild(view);}view.innerHTML='';
      var text=j.text||(j.rel==='_desc.yaml'&&!j.stamp?'# What this artifact declares: links to other artifacts (connections), what it runs (uses),\\n# whose memory its AI sessions read (ai_uses), and any facts of its own.\\nconnections: []\\n':'');
      // a _cmeta, a _desc, a text the page shows or a new README.md / _info.md are drawn again by the server; another file here
      var shown=/^_(cmeta|desc)\\.|^(readme\\.md|_info\\.md)$/i.test(j.rel);
      document.querySelectorAll('.cxr-tblock').forEach(function(b){if(b.getAttribute('data-rel')===j.rel)shown=true;});
      var box=editorBox(j.rel,text,j.stamp,function(r){
          if(shown){again('tech',[(r.created?'Made ':'Saved ')+j.rel].concat(r.warnings||[]));return;}
          (r.warnings||[]).forEach(function(w){body.insertBefore(h('p','cxr-notice',w),view);});openFile(j.rel,li);},
        function(){if(j.stamp)openFile(j.rel,li);else view.innerHTML='';});
      view.appendChild(box);box.ta.focus();view.scrollIntoView({block:'nearest'});}
    function reload(){loaded=false;load();}
    // delete a file or an empty folder: the person is asked first; the tree is read again after
    function del(rel,what){var x=h('button','cxr-copy sm cxr-del','\\u00d7');x.type='button';x.title='Delete this '+what;
      x.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();if(!confirm('Delete the '+what+' '+rel+'? This cannot be undone here.'))return;
        api('delete',{uid:C.uid,rel:rel}).then(function(){reload();}).catch(function(er){alert(er.message);});});return x;}
    function load(){if(loaded)return;loaded=true;api('files',{uid:C.uid,limit:2000}).then(function(j){body.innerHTML='';view=null;
      body.appendChild(h('p','cxr-muted',j.files.length+' of '+j.total+(j.more?'+':'')+' file'+(j.total===1?'':'s')+' - the meta first; click a file to read it here'));
      if(j.edit){var tb=h('p','cxr-edit-row');var nf=h('button','cxr-copy sm','+ file');nf.type='button';nf.title='A new text file in this artifact: the editor opens, the file is made when you save';
        nf.addEventListener('click',function(){var n=prompt('The name of the new file - a path inside the artifact, a text name (notes.md, files/plan.txt):','');if(n&&n.trim())editFile({rel:n.trim(),text:'',stamp:''},null);});
        var nd=h('button','cxr-copy sm','+ folder');nd.type='button';nd.title='A new folder in this artifact';
        nd.addEventListener('click',function(){var n=prompt('The name of the new folder - a path inside the artifact:','');if(n&&n.trim())api('mkdir',{uid:C.uid,rel:n.trim()}).then(function(){reload();}).catch(function(e){alert(e.message);});});
        tb.appendChild(nf);tb.appendChild(nd);body.appendChild(tb);}
      var root={dirs:{},files:[]};function node(path){var cur=root;path.split('/').forEach(function(p){cur=cur.dirs[p]||(cur.dirs[p]={dirs:{},files:[]});});return cur;}
      (j.dirs||[]).forEach(function(d){node(d);});
      j.files.forEach(function(f){var parts=f.rel.split('/');var cur=parts.length>1?node(parts.slice(0,-1).join('/')):root;cur.files.push(f);});
      function draw(node,depth,ul,prefix){Object.keys(node.dirs).sort().forEach(function(d){var child=node.dirs[d],rel=prefix+d;var li=h('li','dir'+(depth>=1&&!/^\\d{8}$/.test(d)?' closed':''));var nm=h('span','nm',d+'/');nm.addEventListener('click',function(){li.classList.toggle('closed');});li.appendChild(nm);
          var w=why(d,depth);if(w)li.appendChild(h('span','why',w));if(j.edit&&!Object.keys(child.dirs).length&&!child.files.length)li.appendChild(del(rel,'folder'));
          var sub=h('ul');draw(child,depth+1,sub,rel+'/');li.appendChild(sub);ul.appendChild(li);});
        node.files.forEach(function(f){var li=h('li','file');li.setAttribute('data-rel',f.rel);var a=h('a',null,f.rel.split('/').pop());a.href='#';a.addEventListener('click',function(e){e.preventDefault();openFile(f.rel,li);});li.appendChild(a);li.appendChild(h('span','sz',size(f.size)));
          if(j.edit&&!/^_(cmeta|desc)\\./i.test(f.rel))li.appendChild(del(f.rel,'file'));if(f.rel===C.file)setTimeout(function(){openFile(f.rel,li);},0);ul.appendChild(li);});}
      var tree=h('ul','cxr-tree');draw(root,0,tree,'');body.appendChild(tree);
      (j.can_add||[]).forEach(function(n){var ad=h('button','cxr-copy sm','+ '+n);ad.type='button';ad.title='Create '+n+' in this artifact';ad.addEventListener('click',function(){editFile({rel:n,text:'',stamp:''},null);});body.appendChild(ad);});
      if(pendingEdit){var g=pendingEdit;pendingEdit=null;g();}
      if(C.file&&!j.files.some(function(f){return f.rel===C.file;}))openFile(C.file,null);
    }).catch(function(e){body.innerHTML='';body.appendChild(h('p','cxr-notice',e.message));});}
    // the edit buttons under the viewers (See _cmeta, See _desc, + _desc.yaml): the editor on that file, in the files section
    function openEditor(rel,isNew){fd.open=true;var go=function(){var li=null;fd.querySelectorAll('li.file').forEach(function(x){if(x.getAttribute('data-rel')===rel)li=x;});
        if(isNew){editFile({rel:rel,text:'',stamp:''},null);}else{openFile(rel,li,true);}};
      if(loaded){go();}else{pendingEdit=go;load();}}
    document.querySelectorAll('.cxr-edit').forEach(function(x){x.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();openEditor(x.getAttribute('data-rel'),x.getAttribute('data-new')==='1');});});
    fd.addEventListener('toggle',function(){if(fd.open)load();});
    if(C.file){fd.open=true;load();}}
})();
</script>"""
