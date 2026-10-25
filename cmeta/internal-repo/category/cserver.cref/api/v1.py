"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.cref - the page of one artifact, named by its cRef.

    cx app run cserver      ->  http://127.0.0.1:8004/cref/<category>::<alias>,<UID>[/<relative path>]
                                http://127.0.0.1:8004/cref?cref=<cRef>

What a reader sees, in this order: the title, the artifact's text (README.md, or the file its category names in
`cref_view.text` of its _cmeta.yaml - the latest dated copy of a note, say), the connections grouped by category,
what connects to it, and at the end, folded: the commands, the _cmeta, the _desc and the files. The host that serves
the page (the engine cserver, a site built on it) keeps the cRef in the address bar: the cRef is how artifacts are
referenced, and a reader sees what is referenced.

The reference is resolved and the artifact read through cserver.browse (one catalogue, the same rules: hidden
repositories, key and secret categories, the file browser only where it is allowed); the text is read here under the
same guards, without the file browser.

The view is extended, never rewritten - `cref_view` in the category's _cmeta.yaml, or in an artifact's _desc:
    text:   a file, or a list of candidates (the first that exists wins); {ck.<key>} placeholders read the _desc
    title:  a dotted key of the _desc (default: the _cmeta name, else the alias)
    hide:   sections left out: connections, incoming, commands, cmeta, desc, files
A host may pass misc.persona: a persona other than engineering / dev / all sees no technical sections at all.
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
SECTIONS = ('connections', 'incoming', 'commands', 'cmeta', 'desc', 'files')

_view_cache = {}      # category alias -> (mtime, cref_view of its _cmeta)


def _esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


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
        tried = []
        for cand in candidates:
            cand = PLACEHOLDER_RE.sub(lambda m: str(_get(desc or {}, m.group(1)) or ''), str(cand))
            if '{' in cand or not cand:
                continue
            full = self._safe_rel(root, cand)
            tried.append(cand)
            if not full:
                if rel and cand == rel:
                    return rel, '', 'the file %s is not shown (missing, outside the artifact, or a key)' % _esc(rel)
                continue
            if not cand.lower().endswith(TEXT_EXT):
                return cand, '', 'the file %s is not a text: open it in the browser\'s file view' % _esc(cand)
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

    # ------------------------------------------------------------------ the page
    def web_(self, ctx, urls, query={}, misc={}):
        """Render the page of the artifact named by ?cref= (or ?uid= with ?file=)."""
        query, misc = query or {}, misc or {}
        urls = urls or {}
        base = urls.get('url_server') or '/'
        self._cref_url = str(misc.get('cref_url') or (base + 'cref/'))
        browse_url = str(misc.get('browse_url') or (base + 'browse'))
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
        shown, text_html, text_note = self._text(root, view, desc, rel) if root else ('', '', '')
        if text_html:
            # a README that opens with the artifact's own title would show it twice: the page's title stands
            text_html = re.sub(r'^\s*<h1(?:\s[^>]*)?>(.*?)</h1>\s*',
                               lambda m: '' if re.sub(r'<[^>]+>', '', m.group(1)).strip().lower() == _esc(str(title)).strip().lower() else m.group(0),
                               text_html, count=1, flags=re.S)

        H = []
        H.append('<div class="cxr-top"><a class="cxr-back" id="cxr-back" href="#" hidden>&larr; Back</a>'
                 '<span class="cxr-crumb">%s &middot; %s</span><span class="cxr-actions">'
                 '<a href="%s?uid=%s">Browser</a> &middot; <a href="%s?uid=%s&amp;view=graph&amp;focus=%s">Graph</a>'
                 ' &middot; <button type="button" class="cxr-copy" data-copy="%s">Copy cRef</button></span></div>'
                 % (_esc(cat), _esc(row.get('repo') or '(registry)'), _esc(browse_url), _esc(uid), _esc(browse_url),
                    _esc(uid), _esc(uid), _esc(short)))
        H.append('<h1 class="cxr-title">%s</h1>' % _esc(title))
        H.append('<div class="cxr-ref"><code>%s</code></div>' % _esc(cref))
        if row.get('tags'):
            H.append('<div class="cxr-tags">%s</div>' % ''.join('<span class="cxr-chip">%s</span>' % _esc(t) for t in row['tags']))
        if text_html:
            H.append('<article class="cxr-text">%s</article>' % text_html)
            H.append('<div class="cxr-muted">from <code>%s</code>%s</div>' % (_esc(shown), (' - ' + text_note) if text_note else ''))
        elif text_note:
            H.append('<p class="cxr-notice">%s</p>' % text_note)
        elif desc and isinstance(desc.get('ck'), dict) and not tech:
            H.append('<p class="cxr-muted">This artifact has no text of its own; its records are in the description below.</p>')

        def item_link(c):
            if c.get('found') is False or not c.get('uid'):
                return '<li class="cxr-missing" title="not shown by this server">%s</li>' % _esc(c.get('alias') or c.get('cref') or c.get('ref'))
            r2 = '%s::%s,%s' % (c.get('cat') or '', c.get('alias') or '', c['uid'])
            extra = (' &middot; uses it' if c.get('uses') else '') + (' &middot; its AI reads this one' if c.get('ai') else '')
            return '<li><a href="%s">%s</a><span class="cxr-muted"> %s</span></li>' % (
                _esc(self._cref_url + r2), _esc(c.get('alias') or c['uid']), extra)

        if 'connections' not in hide:
            groups = {}
            for c in (a.get('connections') or []) + (a.get('uses') or []) + (a.get('ai_uses') or []):
                groups.setdefault(c.get('cat') or '?', []).append(c)
            if groups:
                H.append('<section class="cxr-sec"><h2>Connections <span class="cxr-n">(%d)</span></h2>' % sum(len(v) for v in groups.values()))
                for g in sorted(groups):
                    H.append('<h3>%s</h3><ul class="cxr-links">%s</ul>' % (_esc(g), ''.join(item_link(c) for c in groups[g])))
                H.append('</section>')
        if 'incoming' not in hide and a.get('incoming'):
            n = a.get('incoming_total') or len(a['incoming'])
            H.append('<section class="cxr-sec"><h2>Connected from <span class="cxr-n">(%d)</span></h2><ul class="cxr-links">%s%s</ul></section>'
                     % (n, ''.join(item_link(c) for c in a['incoming']),
                        ('<li class="cxr-muted">... and %d more: open the graph</li>' % (n - len(a['incoming']))) if n > len(a['incoming']) else ''))
        elif 'incoming' not in hide and a.get('index') and not (a['index'] or {}).get('ready'):
            H.append('<p class="cxr-muted">What connects to this artifact is still being read - open the page again in a moment.</p>')

        if tech:
            T = []
            if 'commands' not in hide and a.get('commands'):
                T.append('<details><summary>Commands</summary>%s</details>' % ''.join('<div class="cxr-cmd"><code>%s</code></div>' % _esc(c) for c in a['commands']))
            if 'cmeta' not in hide:
                T.append('<details><summary>See _cmeta</summary><pre class="cxr-pre">%s</pre></details>' % _esc(json.dumps(meta, indent=2, ensure_ascii=False, default=str)))
            if 'desc' not in hide and desc:
                T.append('<details><summary>See _desc (%s)</summary><pre class="cxr-pre">%s</pre></details>'
                         % (_esc(a.get('desc_file') or ''), _esc(json.dumps(desc, indent=2, ensure_ascii=False, default=str))))
            if 'files' not in hide and a.get('files'):
                fj = self._browse(urls, misc, native_action='files', uid=uid)
                if fj.get('files'):
                    rows = ''.join('<li><a href="%s">%s</a><span class="cxr-muted"> %s</span></li>'
                                   % (_esc(self._cref_url + short + '/' + f['rel']), _esc(f['rel']), _esc(f.get('size', ''))) for f in fj['files'])
                    T.append('<details><summary>Files (%s)</summary><ul class="cxr-files">%s</ul></details>' % (fj.get('total', len(fj['files'])), rows))
            if T:
                H.append('<section class="cxr-tech"><h2>Technical details</h2>%s</section>' % ''.join(T))
        return self._page(dark, title, '\n'.join(H))

    def _page(self, dark, title, body, head_only=False):
        css = CSS
        html_body = '<div id="cxr" class="cxr%s">%s</div>%s' % (' cxr-dark' if dark else '', body, JS)
        return {'return': 0, 'html_meta': {'html': html_body, 'page_title': title,
                                            'page_extra_style': '<meta name="viewport" content="width=device-width, initial-scale=1">\n<style>%s</style>' % css}}


CSS = """
.cxr{--fg:#14161a;--muted:#6b7280;--accent:#2a78d6;--line:#e5e7eb;--soft:#f6f7f9;color:var(--fg);max-width:960px;margin:0 auto;padding:12px 16px 48px;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.cxr.cxr-dark{--fg:#e8eaee;--muted:#9aa3b2;--accent:#3987e5;--line:#2a2f3a;--soft:#171a21}
.cxr a{color:var(--accent);text-decoration:none}.cxr a:hover{text-decoration:underline}
.cxr-top{display:flex;gap:12px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:13px;margin-bottom:8px}
.cxr-actions{margin-left:auto}.cxr-copy{font:inherit;color:var(--accent);background:none;border:1px solid var(--line);border-radius:6px;padding:2px 8px;cursor:pointer}
.cxr-title{font-size:28px;line-height:1.2;margin:4px 0 6px}.cxr-ref code{font-size:12.5px;color:var(--muted)}
.cxr-tags{margin:8px 0 14px}.cxr-chip{display:inline-block;background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:1px 9px;margin:2px 4px 2px 0;font-size:12px}
.cxr-text{border-top:1px solid var(--line);padding-top:12px}.cxr-text h1{font-size:24px}.cxr-text h2{font-size:20px;margin-top:22px}.cxr-text h3{font-size:16.5px}
.cxr-text pre,.cxr-pre{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow:auto;font-size:12.5px;line-height:1.45}
.cxr-text code,.cxr-cmd code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.cxr-text table{border-collapse:collapse;margin:10px 0;font-size:14px}.cxr-text th,.cxr-text td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
.cxr-text blockquote{border-left:3px solid var(--line);margin:8px 0;padding:2px 12px;color:var(--muted)}.cxr-text img{max-width:100%}
.cxr-wiki{border-bottom:1px dotted var(--muted)}
.cxr-muted{color:var(--muted);font-size:13px}.cxr-notice{color:#b4232c}.cxr-n{color:var(--muted);font-weight:normal;font-size:14px}
.cxr-sec{margin-top:26px;border-top:1px solid var(--line);padding-top:10px}.cxr-sec h2{font-size:18px;margin:4px 0 8px}.cxr-sec h3{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:12px 0 4px}
.cxr-links,.cxr-files{list-style:none;padding:0;margin:0 0 6px}.cxr-links li,.cxr-files li{padding:2px 0}.cxr-missing{color:var(--muted)}
.cxr-tech{margin-top:30px;border-top:1px solid var(--line);padding-top:10px}.cxr-tech h2{font-size:15px;color:var(--muted);margin:4px 0 6px}
.cxr-tech details{border:1px solid var(--line);border-radius:8px;padding:6px 12px;margin:6px 0;background:var(--soft)}.cxr-tech summary{cursor:pointer;font-weight:500}
.cxr-cmd{margin:6px 0}
@media (max-width:640px){.cxr{padding:8px 12px 40px}.cxr-title{font-size:22px}}
"""

JS = """<script>
(function(){
  var b=document.getElementById('cxr-back');
  try{if(b&&history.length>1&&document.referrer&&new URL(document.referrer).origin===location.origin){b.hidden=false;b.addEventListener('click',function(e){e.preventDefault();history.back();});}}catch(e){}
  document.querySelectorAll('.cxr-copy').forEach(function(x){x.addEventListener('click',function(){
    var t=x.getAttribute('data-copy');var done=function(){x.textContent='Copied';setTimeout(function(){x.textContent='Copy cRef';},1200);};
    if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done,function(){});}
    else{var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(e){}document.body.removeChild(ta);}
  });});
})();
</script>"""
