"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cserver.projects - the home page of cserver: every cserver.* web page plugged into this machine as cards,
grouped by repository, with a search box, pins and copy-URL buttons; under the cards, the version of this
server and where cMeta lives.

    cx app run cserver      ->  http://127.0.0.1:8004/   (the same page as /projects)

There is no registry: the list is discovered from the index - every category whose alias starts with "cserver."
in EVERY plugged repository. A category whose api defines web_ is a page; the others (helper actions,
artifact-only categories) are listed in a footnote. Links are built from urls['url_server'] (on the engine
cserver a page is /<alias without the cserver. prefix>), never hard-coded.

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
    cx config set cserver --meta.projects_hide_repos=a,b*      repositories left off this page (aliases or
                                                                fnmatch patterns); read on every request, and
                                                                their pages stay reachable at their own URLs
"""

import fnmatch
import html
import json
import os
import traceback

from cmeta.category import InitCategory

PREFIX = 'cserver.'


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

        This page itself is left out of the cards (it is the page being looked at); repositories matching
        projects_hide_repos of the cserver config are left out, and ?repo=<text> keeps only the repositories
        whose alias contains the text.
        """
        r = self._scan()
        if r['return'] > 0:
            return r
        hide = _patterns(self._cserver_config().get('projects_hide_repos'))
        want = str((query or {}).get('repo') or '').strip().lower()

        def keep(p):
            return not p['self'] and not _hidden(p['repo'], hide) and (not want or want in p['repo'].lower())

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

    # ------------------------------------------------------------------ web
    def web_(self, ctx, urls, query={}, misc={}):
        """Render the page (command web) or answer ?native_action=projects with JSON."""
        na = (query or {}).get('native_action', '')
        if na:
            try:
                if na == 'projects':
                    r = self._payload(urls, query)
                    if r['return'] > 0:
                        return {'return': 0, 'json': {'error': r.get('error', 'scan failed')}}
                    r.pop('return', None)
                    return {'return': 0, 'json': r}
                return {'return': 0, 'json': {'error': 'unknown native_action %r' % na}}
            except Exception as e:
                print('cserver.projects: native_action %r failed: %s\n%s' % (na, e, traceback.format_exc()))
                return {'return': 0, 'json': {'error': '%s: %s' % (type(e).__name__, e)}}

        try:
            path_to_files = os.path.join(self.path, 'files')
            url_files = urls.get('url_files') or ''
            theme = (misc or {}).get('theme', '')
            dark = theme == 'dark' or str((query or {}).get('dark', '')).lower() in ('1', 'true', 'yes')
            version = getattr(self.cm, '__version__', '')
            config = {'api_url': urls.get('url', '?'), 'url_server': urls.get('url_server') or '/',
                      'dark_mode': bool(dark), 'files': url_files, 'version': version,
                      'repo': str((query or {}).get('repo') or '').strip()}
            with open(os.path.join(path_to_files, 'index.html'), encoding='utf-8') as f:
                body = f.read()
            body = body.replace('%%CONFIG%%', _js(config)).replace('%%VERSION%%', _esc(version))
            head = (
                '<link rel="stylesheet" href="%s">\n' % _asset(path_to_files, url_files, 'css/projects.css') +
                '<script src="%s" defer></script>\n' % _asset(path_to_files, url_files, 'js/projects.js')
            )
            return {'return': 0, 'html_meta': {'html': body, 'page_title': 'cMeta server',
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
