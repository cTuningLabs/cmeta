"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.cref - the page of one artifact, named by its cRef.

    cx app run cserver      ->  http://127.0.0.1:8004/cref/<category>::<alias>,<UID>[/<relative path>]
                                http://127.0.0.1:8004/cref?cref=<cRef>

What a reader sees: the title, the cRef, the tags; the artifact's text (README.md, or the file its category names in
`cref_view.text` of its _cmeta.yaml - the latest dated copy of a note, say); beside it the facts - the category (a
link to every artifact of it), the repository (a link to every artifact of it), the origin (the artifact's folder
on GitHub, when the repository is a clone of one), the UID, the dates, the path on this machine (a browser on the
server's own machine), the buttons that open the folder in the file manager, a shell or Far (the same browser), the
graph focused on this artifact and the knowledge-graph page a host offers; then the connections grouped by
category, what connects to it, and at the end, folded: the commands, the _cmeta, the _desc and the files - a tree
of the artifact's folder (the dated records of `ck/YYYYMMDD/` explained), each file opening in place. The host that
serves the page (the engine cserver, a site built on it) keeps the cRef in the address bar: the cRef is how
artifacts are referenced, and a reader sees what is referenced.

The reference is resolved and the artifact read through cserver.browse (one catalogue, the same rules: the scope of
the request, hidden repositories, key and secret categories, the file browser only where it is allowed); the text
is read here under the same guards. The files and the open buttons are asked of cserver.browse from the page itself
(misc.browse_url says where it is served), so the rules are applied once, there.

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
            if not cand.lower().endswith(TEXT_EXT):
                return cand, '', 'the file %s is not a text: open it from the Files below' % _esc(cand)
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
                    out = ('<details class="cxr-front"><summary>Front matter</summary><pre class="cxr-pre">%s</pre></details>\n'
                           % _esc(front)) + out
                return cand, out, note
            return cand, '<pre class="cxr-pre">%s</pre>' % _esc(body), note
        return '', '', ''

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

        ref = str(query.get('cref') or '').strip()
        if ref:
            j = self._browse(urls, misc, native_action='resolve', cref=ref)
            uid, rel, notice = j.get('uid') or '', j.get('rel') or '', j.get('notice') or j.get('error') or ''
        else:
            uid, rel, notice = str(query.get('uid') or '').strip().lower(), str(query.get('file') or ''), ''
            if not uid:
                notice = 'no artifact named: /cref/<category>::<alias>,<UID>'
        a = self._browse(urls, misc, native_action='artifact', uid=uid) if uid else {}
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

        # the artifact's text: a page category that renders it (cref_view.page), else its README or note
        page_head, text_html, text_note, shown = '', '', '', ''
        if view.get('page') and not rel:
            page_head, text_html = self._embedded_page(str(view['page']), urls, query, misc, uid, short)
        elif root:
            shown, text_html, text_note = self._text(root, view, desc, rel)
            if text_html:
                # a README that opens with the artifact's own title would show it twice: the page's title stands
                text_html = re.sub(r'^\s*<h1(?:\s[^>]*)?>(.*?)</h1>\s*',
                                   lambda m: '' if re.sub(r'<[^>]+>', '', m.group(1)).strip().lower() == _esc(str(title)).strip().lower() else m.group(0),
                                   text_html, count=1, flags=re.S)

        def browse_link(**keys):
            return _esc(browse_url + ('&' if '?' in browse_url else '?') + '&'.join('%s=%s' % (k, _q(v)) for k, v in keys.items() if v))

        H = []
        H.append('<div class="cxr-top"><a class="cxr-back" id="cxr-back" href="#" hidden>&larr; Back</a>'
                 '<span class="cxr-crumb"><a href="%s" title="Every artifact of this category">%s</a> &middot; '
                 '<a href="%s" title="Every artifact of this repository">%s</a></span><span class="cxr-actions">'
                 '<a href="%s" title="This artifact in the knowledge browser">Browser</a> &middot; '
                 '<a href="%s" title="This artifact and its connections, drawn">Graph</a>%s'
                 ' &middot; <button type="button" class="cxr-copy" data-copy="%s">Copy cRef</button></span></div>'
                 % (browse_link(view='browse', cats=cat), _esc(cat),
                    browse_link(view='browse', repos=row.get('repo') or ''), _esc(row.get('repo') or '(registry)'),
                    browse_link(uid=uid), browse_link(view='graph', focus=uid),
                    (' &middot; <a href="%s" title="The knowledge-graph page, focused on this artifact">Knowledge graph</a>'
                     % _esc(graph_url + ('&' if '?' in graph_url else '?') + 'focus=' + _q(alias))) if graph_url else '',
                    _esc(short)))
        H.append('<h1 class="cxr-title">%s</h1>' % _esc(title))
        H.append('<div class="cxr-ref"><code>%s</code></div>' % _esc(cref))
        if row.get('tags'):
            H.append('<div class="cxr-tags">%s</div>' % ''.join(
                '<a class="cxr-chip" href="%s" title="Every artifact with this tag">%s</a>' % (browse_link(view='browse', q='tag:' + t), _esc(t))
                for t in row['tags']))

        # two columns: the text and the lists on the left, the facts on the right (stacked on a narrow screen)
        H.append('<div class="cxr-cols"><div class="cxr-mainc">')
        if text_html:
            H.append('<article class="cxr-text">%s</article>' % text_html)
            if shown:
                H.append('<div class="cxr-muted">from <code>%s</code>%s</div>' % (_esc(shown), (' - ' + text_note) if text_note else ''))
        elif text_note:
            H.append('<p class="cxr-notice">%s</p>' % text_note)
        elif desc and isinstance(desc.get('ck'), dict):
            H.append(self._facts_of_desc(desc, tech))
        else:
            H.append('<p class="cxr-muted">This artifact has no text of its own.</p>')

        def item_link(c):
            if c.get('found') is False or not c.get('uid'):
                return '<li class="cxr-missing" title="not shown by this server">%s</li>' % _esc(c.get('alias') or c.get('cref') or c.get('ref'))
            r2 = '%s::%s,%s' % (c.get('cat') or '', c.get('alias') or '', c['uid'])
            extra = (' &middot; uses it' if c.get('uses') else '') + (' &middot; its AI reads this one' if c.get('ai') else '')
            return '<li><a href="%s">%s</a><span class="cxr-muted"> %s%s</span></li>' % (
                _esc(self._cref_url + r2), _esc(c.get('alias') or c['uid']), _esc(c.get('cat') or ''), extra)

        if 'connections' not in hide:
            groups = {}
            for c in (a.get('connections') or []) + (a.get('uses') or []) + (a.get('ai_uses') or []):
                groups.setdefault(c.get('cat') or '?', []).append(c)
            if groups:
                n = sum(len(v) for v in groups.values())
                H.append('<section class="cxr-sec"><h2>Connects to <span class="cxr-n">(%d)</span></h2>' % n)
                for g in sorted(groups):
                    H.append('<h3><a href="%s" title="Every artifact of this category">%s</a> <span class="cxr-n">%d</span></h3><ul class="cxr-links">%s</ul>'
                             % (browse_link(view='browse', cats=g), _esc(g), len(groups[g]), ''.join(item_link(c) for c in groups[g])))
                H.append('</section>')
        if 'incoming' not in hide and a.get('incoming'):
            n = a.get('incoming_total') or len(a['incoming'])
            groups = {}
            for c in a['incoming']:
                groups.setdefault(c.get('cat') or '?', []).append(c)
            H.append('<section class="cxr-sec"><h2>Connected from <span class="cxr-n">(%d)</span></h2>' % n)
            for g in sorted(groups):
                H.append('<h3><a href="%s">%s</a> <span class="cxr-n">%d</span></h3><ul class="cxr-links">%s</ul>'
                         % (browse_link(view='browse', cats=g), _esc(g), len(groups[g]), ''.join(item_link(c) for c in groups[g])))
            if n > len(a['incoming']):
                H.append('<p class="cxr-muted">... and %d more: <a href="%s">open the graph</a></p>' % (n - len(a['incoming']), browse_link(view='graph', focus=uid)))
            H.append('</section>')
        elif 'incoming' not in hide and a.get('index') and not (a['index'] or {}).get('ready'):
            H.append('<p class="cxr-muted">What connects to this artifact is still being read - open the page again in a moment.</p>')

        if tech:
            T = []
            if 'commands' not in hide and a.get('commands'):
                T.append('<details><summary>Commands</summary><p class="cxr-muted">The same artifact from a terminal with cMeta installed.</p>%s</details>'
                         % ''.join('<div class="cxr-cmd"><code>%s</code><button type="button" class="cxr-copy sm" data-copy="%s">copy</button></div>' % (_esc(c), _esc(c)) for c in a['commands']))
            if 'cmeta' not in hide:
                T.append('<details><summary>See _cmeta <span class="cxr-n">who made it, when, the tags</span></summary><pre class="cxr-pre cxr-refs">%s</pre></details>' % _esc(json.dumps(meta, indent=2, ensure_ascii=False, default=str)))
            if 'desc' not in hide and desc:
                T.append('<details><summary>See _desc <span class="cxr-n">the facts and the connections (%s)</span></summary><pre class="cxr-pre cxr-refs">%s</pre></details>'
                         % (_esc(a.get('desc_file') or ''), _esc(json.dumps(desc, indent=2, ensure_ascii=False, default=str))))
            if 'files' not in hide and a.get('files'):
                T.append('<details id="cxr-files" data-uid="%s"><summary>Files <span class="cxr-n">the artifact\'s folder</span></summary>'
                         '<div class="cxr-files-body"><p class="cxr-muted">Loading the files...</p></div></details>' % _esc(uid))
            if T:
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
            rows_html.append(('Repository', '<a href="%s" title="Every artifact of this repository">%s</a>' % (
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
                     % (browse_link(view='graph', focus=uid), ''.join('<option value="%d"%s>%s</option>' % (d, ' selected' if d == 2 else '', 'all' if d == 12 else d) for d in (1, 2, 3, 4, 5, 6, 12))))
            if graph_url:
                H.append('<div class="cxr-graph2"><a href="%s">Knowledge graph &#8599;</a></div>'
                         % _esc(graph_url + ('&' if '?' in graph_url else '?') + 'focus=' + _q(alias)))
        H.append('</aside></div>')      # end of the columns

        config = {'browse_url': browse_url, 'cref_url': self._cref_url, 'uid': uid, 'cref': short,
                  'open': bool(misc.get('client_local')) and tech, 'focus_url': browse_url + ('&' if '?' in browse_url else '?') + 'view=graph&focus=' + _q(uid),
                  'files': bool(a.get('files')) and tech and 'files' not in hide, 'file': rel if rel and not shown else ''}
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
        html_body = '<div id="cxr" class="cxr%s">%s</div>%s%s' % (
            ' cxr-dark' if dark else '', body,
            '<script>var CXR_CONFIG = %s;</script>' % _js(config or {}), JS)
        return {'return': 0, 'html_meta': {'html': html_body, 'page_title': title,
                                            'page_extra_style': '<meta name="viewport" content="width=device-width, initial-scale=1">\n<style>%s</style>\n%s' % (css, extra_head or '')}}


def _q(s):
    from urllib.parse import quote
    return quote(str(s), safe='')


CSS = """
.cxr{--fg:#14161a;--muted:#6b7280;--accent:#2a78d6;--line:#e5e7eb;--soft:#f6f7f9;color:var(--fg);max-width:1180px;margin:0 auto;padding:12px 16px 48px;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.cxr.cxr-dark{--fg:#e8eaee;--muted:#9aa3b2;--accent:#3987e5;--line:#2a2f3a;--soft:#171a21}
.cxr a{color:var(--accent);text-decoration:none}.cxr a:hover{text-decoration:underline}
.cxr-top{display:flex;gap:12px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:13px;margin-bottom:8px}
.cxr-actions{margin-left:auto}.cxr-copy{font:inherit;color:var(--accent);background:none;border:1px solid var(--line);border-radius:6px;padding:2px 8px;cursor:pointer}
.cxr-copy.sm{font-size:12px;padding:1px 6px}
.cxr-title{font-size:28px;line-height:1.2;margin:4px 0 6px;overflow-wrap:anywhere}.cxr-ref code{font-size:12.5px;color:var(--muted);overflow-wrap:anywhere}
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
.cxr-text{border-top:1px solid var(--line);padding-top:12px}.cxr-text h1{font-size:24px}.cxr-text h2{font-size:20px;margin-top:22px}.cxr-text h3{font-size:16.5px}
.cxr-text pre,.cxr-pre{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow:auto;font-size:12.5px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere}
.cxr-text code,.cxr-cmd code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.cxr-text table{border-collapse:collapse;margin:10px 0;font-size:14px}.cxr-text th,.cxr-text td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
.cxr-text blockquote{border-left:3px solid var(--line);margin:8px 0;padding:2px 12px;color:var(--muted)}.cxr-text img{max-width:100%}
.cxr-wiki{border-bottom:1px dotted var(--muted)}
.cxr-muted{color:var(--muted);font-size:13px}.cxr-notice{color:#b4232c}.cxr-n{color:var(--muted);font-weight:normal;font-size:13px}
.cxr-sec{margin-top:26px;border-top:1px solid var(--line);padding-top:10px}.cxr-sec h2{font-size:18px;margin:4px 0 8px}.cxr-sec h3{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:12px 0 4px}
.cxr-links,.cxr-files{list-style:none;padding:0;margin:0 0 6px}.cxr-links li,.cxr-files li{padding:2px 0;overflow-wrap:anywhere}.cxr-missing{color:var(--muted)}
.cxr-links{columns:2;column-gap:24px}.cxr-links li{break-inside:avoid}
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
@media (max-width:860px){.cxr{padding:8px 12px 40px}.cxr-title{font-size:22px}.cxr-cols{grid-template-columns:minmax(0,1fr)}.cxr-side{position:static}.cxr-links{columns:1}}
"""

JS = """<script>
(function(){
  var C=window.CXR_CONFIG||{};
  var b=document.getElementById('cxr-back');
  try{if(b&&history.length>1&&document.referrer&&new URL(document.referrer).origin===location.origin){b.hidden=false;b.addEventListener('click',function(e){e.preventDefault();history.back();});}}catch(e){}
  document.querySelectorAll('.cxr-copy').forEach(function(x){x.addEventListener('click',function(){
    var t=x.getAttribute('data-copy'),was=x.textContent;var done=function(){x.textContent='Copied';setTimeout(function(){x.textContent=was;},1200);};
    if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done,function(){});}
    else{var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(e){}document.body.removeChild(ta);}
  });});
  function api(action,params){var u=C.browse_url||'/browse';u+=(u.indexOf('?')>=0?'&':'?')+'native_action='+action;
    return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(params||{})}).then(function(r){return r.text().then(function(t){var d;try{d=JSON.parse(t);}catch(e){throw new Error('HTTP '+r.status);}if(d&&d.error)throw new Error(d.error);return d;});});}
  function h(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function size(n){return n<1024?n+' B':n<1048576?(n/1024).toFixed(n<10240?1:0)+' KB':(n/1048576).toFixed(1)+' MB';}
  // the depth of the focused graph
  var sel=document.getElementById('cxr-depth'),fo=document.getElementById('cxr-focus');
  if(sel&&fo){sel.addEventListener('change',function(){fo.href=C.focus_url+(sel.value&&sel.value!=='2'?'&depth='+sel.value:'');});}
  // the open buttons: a browser on the server's own machine
  var ob=document.getElementById('cxr-open');
  if(ob&&C.open){ob.hidden=false;var msg=h('span','msg');[['folder','Open folder','Open this folder in the file manager'],['shell','Shell','A terminal in this folder'],['far','Far','Far Manager in this folder']].forEach(function(w){
    var bt=h('button','cxr-btn',w[1]);bt.type='button';bt.title=w[2];bt.addEventListener('click',function(){msg.className='msg';msg.textContent='opening...';
      api('open',{uid:C.uid,what:w[0]}).then(function(){msg.textContent=w[1]+' opened on this machine';}).catch(function(e){msg.className='msg bad';msg.textContent=e.message;});});
    ob.appendChild(bt);});ob.appendChild(msg);}
  // the files: a tree of the folder, loaded when the section opens (or at once when the address names a file)
  var fd=document.getElementById('cxr-files');
  if(fd&&C.files){var loaded=false,body=fd.querySelector('.cxr-files-body'),view=null,blob=null;
    function why(name,depth){if(depth===0&&name==='ck')return 'the dated records: one folder per day (YYYYMMDD) the facts were observed - nothing is overwritten';
      if(depth===1&&/^\\d{8}$/.test(name))return 'the facts observed on '+name.slice(0,4)+'-'+name.slice(4,6)+'-'+name.slice(6);
      if(depth===0&&name==='files')return 'the files the artifact serves (a page: its scripts and styles)';return '';}
    function openFile(rel,li){api('file',{uid:C.uid,rel:rel}).then(function(j){if(!view){view=h('div','cxr-fview');body.appendChild(view);}view.innerHTML='';if(blob){URL.revokeObjectURL(blob);blob=null;}
      fd.querySelectorAll('.file.on').forEach(function(x){x.classList.remove('on');});if(li)li.classList.add('on');
      var head=h('div','cxr-fhead');head.appendChild(h('b',null,j.rel));head.appendChild(document.createTextNode(' \\u00b7 '+size(j.size)+(j.truncated?' \\u00b7 the first 512 KB':'')));
      var cl=h('button','cxr-copy sm','close');cl.type='button';cl.addEventListener('click',function(){view.innerHTML='';});head.appendChild(cl);
      var ln=h('a','cxr-copy sm','link');ln.href=(C.cref_url||'/cref/')+encodeURI(C.cref)+'/'+j.rel.split('/').map(encodeURIComponent).join('/');ln.title='The address of this file';head.appendChild(ln);view.appendChild(head);
      if(j.kind==='text'){var pre=h('pre','cxr-pre cxr-refs');pre.textContent=j.text;view.appendChild(pre);}
      else if(j.kind==='binary'&&j.b64){var bin=atob(j.b64),arr=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);blob=URL.createObjectURL(new Blob([arr],{type:j.mime}));
        var a=h('a',null,'open in a new tab');a.href=blob;a.target='_blank';a.rel='noopener';view.appendChild(a);
        if(j.mime.indexOf('image/')===0){var im=document.createElement('img');im.src=blob;im.alt=j.rel;view.appendChild(im);}else if(j.mime==='application/pdf'){var fr=document.createElement('iframe');fr.src=blob;fr.title=j.rel;view.appendChild(fr);}}
      else{view.appendChild(h('p','cxr-muted',j.note||'not shown'));}
      view.scrollIntoView({block:'nearest'});}).catch(function(e){if(!view){view=h('div','cxr-fview');body.appendChild(view);}view.textContent=e.message;});}
    function load(){if(loaded)return;loaded=true;api('files',{uid:C.uid,limit:2000}).then(function(j){body.innerHTML='';
      body.appendChild(h('p','cxr-muted',j.files.length+' of '+j.total+(j.more?'+':'')+' file'+(j.total===1?'':'s')+' - the meta first; click a file to read it here'));
      var root={dirs:{},files:[]};j.files.forEach(function(f){var parts=f.rel.split('/'),cur=root;for(var i=0;i<parts.length-1;i++){cur=cur.dirs[parts[i]]||(cur.dirs[parts[i]]={dirs:{},files:[]});}cur.files.push(f);});
      function draw(node,depth,ul){Object.keys(node.dirs).sort().forEach(function(d){var li=h('li','dir'+(depth>=1&&!/^\\d{8}$/.test(d)?' closed':''));var nm=h('span','nm',d+'/');nm.addEventListener('click',function(){li.classList.toggle('closed');});li.appendChild(nm);
          var w=why(d,depth);if(w)li.appendChild(h('span','why',w));var sub=h('ul');draw(node.dirs[d],depth+1,sub);li.appendChild(sub);ul.appendChild(li);});
        node.files.forEach(function(f){var li=h('li','file');var a=h('a',null,f.rel.split('/').pop());a.href='#';a.addEventListener('click',function(e){e.preventDefault();openFile(f.rel,li);});li.appendChild(a);li.appendChild(h('span','sz',size(f.size)));if(f.rel===C.file)setTimeout(function(){openFile(f.rel,li);},0);ul.appendChild(li);});}
      var tree=h('ul','cxr-tree');draw(root,0,tree);body.appendChild(tree);
      if(C.file&&!j.files.some(function(f){return f.rel===C.file;}))openFile(C.file,null);
    }).catch(function(e){body.innerHTML='';body.appendChild(h('p','cxr-notice',e.message));});}
    fd.addEventListener('toggle',function(){if(fd.open)load();});
    if(C.file){fd.open=true;load();}}
})();
</script>"""
