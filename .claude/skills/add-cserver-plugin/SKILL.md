---
name: add-cserver-plugin
description: Author a `cserver.*` cMeta category that renders an interactive web page (HTML + CSS + JS + AJAX) and runs unchanged on BOTH the engine's internal `cserver` app and the cTuning cPlatform (`ctuning.server`). Covers the `web_()` contract, the `urls`/`query`/`misc` inputs, the `native_action` AJAX pattern, forwarding page params into AJAX calls, asset cache-busting, dark-theme handling, the cPlatform project pointer, and how to run/verify on both hosts. Use when the user asks to "add a cserver plugin/project", "add a page/dashboard/visualization to the platform", or "make a cMeta category render a web UI".
---

# add-cserver-plugin — one category, two web hosts

A **cserver plugin** is a cMeta category named `cserver.<name>` whose `api/v1.py`
renders an interactive HTML page. The same category is served by two different
hosts, and a plugin is only "done" when it works on both:

| | **internal cserver** (engine) | **cPlatform** (`ctuning.server`) |
|---|---|---|
| App | `cmeta/internal-repo/app/cserver/src/app.py` | `…-platform/repo/app/ctuning.server/dev/project_v1.py` |
| Default port | `8004` | `8118` |
| Page URL | `/<name>` → category `cserver.<name>` | `/project/<username>/<project>/` |
| `urls['url']` | `http://…/<name>/?` | `http://…/project/<user>/<project>/?` |
| `urls['url_files']` | `http://…/<name>/` | `http://…/project/<user>/<project>/files/` |
| Wiring needed | none — route derives the category from the path | a `project-<name>.json` pointer (see §5) |
| Auth | optional `api_keys` in the `cserver` config | session + `private`/`private_usernames` |
| `command` from query | any (defaults to `web`) | only if listed in `allowed_commands` |
| `misc` | minimal, **no theme** | `theme`, `theme_bg_color`, `ctuning_server: True` |

**The two hosts differ only in launch and URL convention.** Everything else is
identical, which is exactly why the rules below ("build every URL from `urls`",
"handle the dark theme", "cache-bust your assets") are not optional polish —
each one is a place where a plugin silently works on one host and breaks on the
other.

---

## 1. Scaffold

```bash
cx category add <repo>:cserver.<name>     # creates the folder, _cmeta.yaml, api/v1.py stub
cx category find cserver.<name>           # confirm it resolves; note the UID
```

If you create the folder **by hand** (`mkdir` + `_cmeta.yaml`), register just
that one artifact instead of rebuilding the whole home:

```bash
cx category index  <repo>:cserver.<name>   # index a hand-made folder
cx category update <repo>:cserver.<name>   # after editing its _cmeta.* meta
```

`cx --reindex` walks every category and is slow — keep it for moves, bulk
`git pull`, or a wiped `CMETA_HOME`. **Editing `api/`, `files/` or `src/` needs
no reindex at all**; a server restart (or `--reload`) picks those up.

Layout:

```
category/cserver.<name>/
  _cmeta.yaml              # artifact UID + category: category,dd9ea50e7f76467f
  api/v1.py                # web_() — renders the page AND serves its AJAX
  files/
    index.html             # page body only (no <html>/<head>)
    css/layout.css
    js/graph.js            # your page logic
    *.json                 # data, if any
```

---

## 2. The `web_` contract

```python
from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def web_(self, ctx, urls, query={}, misc={}):
        ...
```

- **The trailing `_` is required.** Methods ending in a single `_` are called
  with unpacked kwargs (`func(**params)`); without it cMeta passes one
  positional dict and you get a `TypeError`. Command `web` → method `web_`.
- **`urls`** — `url` (this page's `?`-terminated endpoint), `url2`, `url_files`,
  `url_server`, `url_server_js_script` (`…/static/js/cmeta_server.js`).
  **Never hardcode a path**; the prefixes differ per host and cPlatform may sit
  behind `CTUNING_SERVER_URL_PREFIX` / a reverse proxy.
- **`query`** — merged GET params **and POST JSON body**, plus `username` on
  cPlatform and `native_action` for AJAX calls. Both hosts merge the body:
  engine `cmeta/utils/net.py::unify_request`, platform `dev/utils.py::unify_request`.
- **`misc`** — session bits. `theme` is `'dark'`/`'light'` on cPlatform and
  **absent** on the internal cserver.
- **`ctx`** — `{'category','command','control':{'con':bool},…}`. Re-enter the
  framework with `self.cm.access(...)`; your own path is `self.path`.

Return **one of**:

```python
{'return': 0, 'html_meta': {...}}   # full page
{'return': 0, 'json': {...}}        # AJAX response (both hosts return it as JSONResponse)
```

On failure return the standard error dict — `return self.cm.error('...')` — and
check nested calls with `if self.cm.catch_error(r): return r`. Don't let an
exception escape `web_()`: both hosts expect a dict. For an AJAX branch,
prefer returning `{'return': 0, 'json': {'error': '...'}}` so the page can
render the message instead of the request failing. See
`docs/error-handling.md`.

`html_meta` keys the hosts consume: `html` (body, rendered safe), `page_title`,
`page_extra_style` (inject `<script>`/`<link>`), `global_footer`. cPlatform also
adds `project_home_url` / `projects_home_url` when the project sets `add_home` /
`add_back_to_projects`.

---

## 3. The `native_action` AJAX pattern

**One category serves both the page and its API.** The page JS calls back into
the same URL with `native_action=<x>`; `web_` branches on it.

Both hosts serve `cmeta_server.js`, which exposes:

```js
accessCT(api_url, dict)   // fetch POST, JSON body, returns parsed JSON
```

### Forwarding page params into the AJAX call

The page may be opened with params (`?limit=5`), but the graph data is fetched
by a *second* request that the server never sees the page URL of. Declare, in
one place, which query keys each action accepts, and forward them:

```python
# Which query keys each AJAX native_action reads from the high-level page request.
# Both the page URL (GET) and POST body fields are honored.
NATIVE_ACTION_PARAMS = {
    'load_graph': ['limit', 'max_nodes'],
}

def _js(obj):
    """Serialize to a JSON/JS literal safe to embed inside a <script> tag."""
    return json.dumps(obj).replace('</', '<\\/')
```

```python
def web_(self, ctx, urls, query={}, misc={}):
    native_action = query.get('native_action', '')
    if native_action == 'load_graph':
        return self._build_graph(query)          # -> {'return':0,'json':{...}}

    # allow-listed params the user passed to the page, per action
    initial_params = {}
    for action, keys in NATIVE_ACTION_PARAMS.items():
        picked = {k: query[k] for k in keys
                  if k in query and query[k] not in (None, '')}
        if picked:
            initial_params[action] = picked
```

…embedded into the page as `CONFIG.params` / `CONFIG.param_keys`, then on the JS
side merged from three sources (later overriding earlier):

```js
function collectActionParams(action) {
  const params = {};
  if (CONFIG.params && CONFIG.params[action])       // 1. server-forwarded
    Object.assign(params, CONFIG.params[action]);
  const allowed = (CONFIG.param_keys && CONFIG.param_keys[action]) || [];
  const sp = new URLSearchParams(window.location.search || '');
  allowed.forEach(k => { if (sp.has(k)) params[k] = sp.get(k); });   // 2. live URL
  document.querySelectorAll('[data-action="' + action + '"]').forEach(el => {
    if (el.name && el.value !== '') params[el.name] = el.value;      // 3. UI fields
  });
  return params;
}

const params = collectActionParams('load_graph');
const out = await accessCT(CONFIG.api_url + 'native_action=load_graph', params);
```

Give the page real controls rather than making the user hand-edit the URL — an
`<input name="limit" data-action="load_graph">` plus a Reload button is enough,
since `collectActionParams` already reads them. Seed those inputs from the
effective params on load, and write the params of the last request back with
`history.replaceState` so the view stays shareable and a plain reload reproduces
it (the server re-forwards them).

**Adding a param is then a one-line change** to `NATIVE_ACTION_PARAMS` plus an
input whose `name` matches. Only declared keys are forwarded — an undeclared or
misspelled key (`num_nodes` vs `max_nodes`) is silently ignored by design.

---

## 4. Two gotchas that only bite on one host

### 4.1 Cache-bust your `files/` assets — **the** cross-host trap

Neither host sends `Cache-Control` for artifact files (engine `task_files`,
platform `project_files`), so browsers apply *heuristic* freshness and can keep
running a stale `graph.js` for a long time after you edit it. The classic
symptom: the plugin works on the host you just started and appears broken on the
other, with a `ReferenceError` for a function you know you wrote.

Fix it in the category, so both hosts benefit and neither server needs changing:

```python
def _asset(path_to_files, url_files, rel):
    """Build a versioned URL for a file under files/ (mtime -> new URL per edit)."""
    url = url_files + rel
    try:
        return f'{url}?v={int(os.path.getmtime(os.path.join(path_to_files, *rel.split("/"))))}'
    except Exception:
        return url
```

```python
f'<link rel="stylesheet" href="{_asset(path_to_files, url_files, "css/layout.css")}">\n'
f'<script src="{_asset(path_to_files, url_files, "js/graph.js")}"></script>\n'
```

When debugging a "works here, broken there" report, **check which copy of the JS
actually ran** before assuming the server logic is wrong:

```js
// in the page console / javascript_tool
[...document.scripts].map(s => s.src)
typeof myFunctionAddedInTheLastEdit      // "undefined" => stale cache
```

### 4.2 Handle the dark theme

cPlatform passes the user's theme; the internal cserver has none. A page styled
only for light renders as a near-white panel with light-grey labels for every
dark-theme platform user.

```python
theme = misc.get('theme', '')
dark = 'true' if theme == 'dark' else 'false'      # into CONFIG.dark_mode
```

```js
const darkMode = (typeof CONFIG !== 'undefined' && CONFIG.dark_mode) === true;
if (darkMode) document.getElementById('<root-id>').classList.add('dark');
```

Then style `#<root-id>.dark …` in your CSS (panel background, borders, control
inputs, legend text) and flip any colors your JS sets inline — SVG strokes,
label fills, canvas colors — since CSS can't reach those.

---

## 5. Wire it into cPlatform

The internal cserver needs nothing: `/<name>` already maps to `cserver.<name>`.

cPlatform needs a **userspace pointer** at
`…-platform/repo/ctuning.user/___<xx>/___<username>/projects/project-<name>.json`:

```json
{
  "name": "cMeta connections",
  "menu_name": "cMeta connections",
  "private": true,
  "private_usernames": ["gh_<user>", "go_<user>@example.com"],
  "cmeta_params_for_html": {
    "category": "cserver.<name>,<UID>",
    "command": "web",
    "api": 1
  },
  "add_back_to_projects": true,
  "cmeta_artifact_for_files": "category::cserver.<name>,<UID>"
}
```

- `cmeta_artifact_for_files` is what makes `…/files/**` resolve to the
  category's `files/` dir (path-traversal guarded).
- Optional: `group` (+ `group_sort`) lists the project under a heading on the user's
  projects page (`<li class="ctp-project-group">`, styled by the platform stylesheet or the
  user's `project_extra_html`); the course/install/tools pointers of `___cmeta` show the pattern.
- Optional: `allowed_commands` (permits `?command=…`), `skip_files_prefix`
  (drops `/files/` from `url_files`), `logged`, `sort`, `add_home`.
- **Reference by `alias,UID`.** The UID is authoritative and the alias advisory,
  so the folder can gain/lose a `cserver.` prefix without breaking the pointer.

---

## 6. Run and verify — both hosts, every time

```bash
# A) internal cserver (from CMETA_HOME)
cx app run cserver                      # -> http://127.0.0.1:8004/<name>
cx app run cserver --param.port=8010 --con
# If the launcher can't find _run.bat, run uvicorn directly from the app artifact:
#   cd <cmeta>/internal-repo/app/cserver && python -m uvicorn src.app:app --host 127.0.0.1 --port 8004

# B) cPlatform (from repo/app/ctuning.server/)
./6_run_uvicorn.sh                      # 6_run_uvicorn.bat on Windows -> :8118
# -> http://localhost:8118/project/<username>/<name>/
```

Exercise the AJAX branch straight from the shell (no browser, no session on the
internal cserver):

```bash
curl -s -X POST 'http://127.0.0.1:8004/<name>/?native_action=load_graph' \
     -H 'Content-Type: application/json' -d '{"limit":"2"}'
```

Then in a browser, on **both** hosts:

- [ ] Page renders; no console errors.
- [ ] `?<param>=N` in the URL changes the result **and** seeds the matching UI input.
- [ ] Changing an input + Reload re-fetches and updates the URL.
- [ ] The loaded asset URLs carry a `?v=` stamp matching your latest edit.
- [ ] cPlatform in dark theme is legible (panel, labels, controls, node strokes).
- [ ] All links/assets came from `urls` — nothing hardcoded.

---

## 7. Reference implementations

- `gfursin@cmeta-personal/category/cserver.cmeta.connections` — D3 force graph;
  the full pattern: `NATIVE_ACTION_PARAMS` forwarding, `data-action` controls,
  `_asset()` cache-busting, dark-theme handling.
- `…/cserver.lumai.graph` — Plotly dashboard reading `files/input-*.json`; the
  template to copy for a chart.
- `…/cserver.habits` — read/write example (`native_action` persisting meta.json).

Related skills: `add-plugin` (category scaffolding + `api/v1.py` conventions),
`use-cmeta-cli`, `use-cmeta-python`.
