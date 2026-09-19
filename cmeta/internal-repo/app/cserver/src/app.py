"""
Minimal cMeta server

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import subprocess
import argparse
import hashlib
import hmac
import html as html_escaper
import ipaddress
import os
import mimetypes
import secrets
import time
import urllib.parse

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import uvicorn

app = FastAPI()

# The key that signs the session cookie. A fixed, published default would let anyone forge a session on any
# server reachable over a network, so it is taken from the environment (CSERVER_SESSION_SECRET, exported both by
# `cx app run cserver --param.session_secret=...` and by a `param:` block in the cserver config) and is otherwise
# random per start - in which case restarting the server simply asks for the password again.
session_secret = os.environ.get('CSERVER_SESSION_SECRET', '').strip() or secrets.token_urlsafe(32)

# How long a session cookie stays valid, in seconds (CSERVER_SESSION_MAX_AGE / --param.session_max_age).
try:
    session_max_age = int(os.environ.get('CSERVER_SESSION_MAX_AGE', '').strip() or 604800)
except ValueError:
    session_max_age = 604800

# The session middleware itself is registered further down, after the password gate: Starlette runs the most
# recently added middleware first, and the gate reads request.session, so the session must wrap it.

script_path = os.path.abspath(__file__)
home_dir = os.path.basename(os.path.dirname(script_path))

home_dir_templates = os.path.join(home_dir, 'templates')
templates = Jinja2Templates(directory = home_dir_templates)

home_dir_static = os.path.join(home_dir, 'static')
app.mount('/static', StaticFiles(directory = home_dir_static), name="static")

##################################################################################################
# Prepare cMeta
from cmeta.core_async import CMetaAsync
from cmeta import catch as cmeta_catch

cpu_count = os.cpu_count()

max_workers = int (cpu_count * 0.8 + 0.5)

cm_debug = True if os.environ.get('CSERVER_CM_DEBUG', '').lower() in ['1', 'yes', 'true'] else False
cm_print_host_info = True if os.environ.get('CSERVER_CM_PRINT_HOST_INFO', '').lower() in ['1', 'yes', 'true'] else False

cm = CMetaAsync(max_workers = max_workers, debug = cm_debug, print_host_info = cm_print_host_info)

##################################################################################################
# Get configuration

cfg = {}

@app.on_event("startup")
async def test_cmeta_repos():
    """
    test_cmeta_repos function.

    Args:
        None.

    Returns:
        dict: Operation result.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
    global cm, cfg
    r = await cm.access({'category':'config,cc6bfe174be847ed', 'command':'get', 'arg1':'cserver'})
    if r['return'] > 0: cmeta_catch(r)

    cfg = r['config_cmeta']

##################################################################################################
# One shared password in front of every page (optional)
#
# Set it in the cserver config and the server asks for it once per browser, then remembers the answer in the
# session cookie:
#
#   cx config set cserver --meta.password="<your password>"
#   cx config set cserver --meta.password_sha256=<sha256 of it>   # the same, without the plain text on disk
#   cx config unset cserver --meta.password                       # off again
#
# This is a door with a lock, not a security system: one shared secret, no accounts, no lockout beyond a naive
# per-address delay, and - unless the server is reached over HTTPS or through an encrypted overlay network such
# as a private VPN - a password that travels in clear text. It exists to keep a server that listens on a routable
# address out of reach of port scanners and curious passers-by.
#
# Requests from the machine itself are exempt by default (password_allow_local), so the CLI, local scripts and
# development keep working untouched. A request carrying a valid api_key is exempt too, so automation that
# already authenticates does not need a second secret.

LOGIN_PATH = '/_cserver_login'

# naive per-address throttle: {ip: [failures, first_failure_timestamp]}
_login_failures = {}


def _cfg_str(key, default=''):
    v = cfg.get(key, default)
    return '' if v is None else str(v).strip()


def _cfg_int(key, default):
    try:
        return int(str(cfg.get(key, default)).strip())
    except (TypeError, ValueError):
        return default


def _cfg_bool(key, default=True):
    v = cfg.get(key, None)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ['1', 'yes', 'true', 'on']


def _password_sha256():
    """The sha256 of the configured password, from either `password` or `password_sha256`; '' when not protected."""
    digest = _cfg_str('password_sha256').lower()
    if digest:
        return digest
    plain = _cfg_str('password')
    if plain:
        return hashlib.sha256(plain.encode('utf-8')).hexdigest()
    return ''


def _session_token(digest):
    """What a logged-in session stores: the password digest keyed by the cookie secret.

    The cookie is signed but readable, so it must not carry the password or a bare hash of it. Keying it with the
    session secret makes the stored value useless anywhere else, and changing the password (or the secret) ends
    every session that was opened with the old one.
    """
    return hmac.new(session_secret.encode('utf-8'), digest.encode('utf-8'), hashlib.sha256).hexdigest()


def _client_ip(request):
    fwd = request.headers.get('x-forwarded-for', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return getattr(request.client, 'host', '') or ''


def _is_local(ip):
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _wants_json(request):
    """An AJAX call of a page (native_action / force_json / an Accept of JSON) must not be answered with HTML."""
    q = request.query_params
    if q.get('native_action') or q.get('force_json'):
        return True
    accept = request.headers.get('accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def _login_page(request, next_url, message='', status_code=status.HTTP_401_UNAUTHORIZED):
    """A self-contained prompt: no assets to fetch, so it renders before anything else is authorised."""
    realm = _cfg_str('password_realm') or 'cMeta server'
    note = ('<p class="msg">%s</p>' % html_escaper.escape(message)) if message else ''
    body = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(realm)s</title>
<style>
 :root {color-scheme: light dark;}
 body {margin:0; min-height:100vh; display:grid; place-items:center;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:#f4f5f8; color:#14161a;}
 form {width:min(92vw,360px); padding:26px 24px; background:#fff; border:1px solid #e3e6ec;
       border-radius:14px; box-shadow:0 8px 30px rgba(0,0,0,.06);}
 h1 {margin:0 0 4px; font-size:19px; font-weight:640;}
 p {margin:0 0 18px; font-size:13.5px; color:#6b7180;}
 p.msg {color:#a21b1b; font-weight:560;}
 input[type=password] {width:100%%; padding:12px 13px; font-size:16px; color:inherit; background:#fff;
       border:1px solid #d7dbe3; border-radius:9px; box-sizing:border-box;}
 input[type=password]:focus {outline:2px solid rgba(92,15,201,.18); border-color:#5c0fc9;}
 button {width:100%%; margin-top:12px; padding:12px; font-size:15px; font-weight:560; color:#fff;
       background:#5c0fc9; border:0; border-radius:9px; cursor:pointer;}
 button:hover {background:#4a0ca4;}
 @media (prefers-color-scheme: dark) {
   body {background:#101216; color:#e8eaee;}
   form {background:#1b1e24; border-color:#2c3038; box-shadow:none;}
   p {color:#9aa1ad;}
   p.msg {color:#ff9d9d;}
   input[type=password] {background:#14161a; border-color:#343a44; color:#e8eaee;}
   button {background:#7c4dff;}
 }
</style></head>
<body>
 <form method="post" action="%(action)s">
  <h1>%(realm)s</h1>
  <p>This server asks for a password before showing its pages.</p>
  %(note)s
  <input type="hidden" name="next" value="%(next)s">
  <input type="password" name="password" placeholder="Password" autocomplete="current-password" autofocus required>
  <button type="submit">Open</button>
 </form>
</body></html>
""" % {'realm': html_escaper.escape(realm),
       'action': LOGIN_PATH,
       'next': html_escaper.escape(next_url, quote=True),
       'note': note}
    return HTMLResponse(content=body, status_code=status_code)


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """Ask for the shared password before any route runs, when one is configured."""
    digest = _password_sha256()

    path = request.url.path

    if not digest:
        # no password configured: the server behaves exactly as it always did
        if path == LOGIN_PATH:
            return RedirectResponse(url='/', status_code=status.HTTP_303_SEE_OTHER)
        return await call_next(request)

    wanted = _session_token(digest)
    ip = _client_ip(request)

    # the login form itself
    if path == LOGIN_PATH:
        if request.method != 'POST':
            return RedirectResponse(url='/', status_code=status.HTTP_303_SEE_OTHER)

        window = _cfg_int('password_lockout_min', 5) * 60
        limit = _cfg_int('password_max_attempts', 10)
        fails, since = _login_failures.get(ip, [0, 0.0])
        now = time.time()
        if since and now - since > window:
            fails, since = 0, 0.0
        if limit > 0 and fails >= limit:
            left = int((window - (now - since)) / 60) + 1
            return _login_page(request, '/', 'Too many attempts. Try again in %d minute(s).' % left,
                               status_code=status.HTTP_429_TOO_MANY_REQUESTS)

        # The body is parsed here rather than with request.form(), which would pull in python-multipart: the login
        # form posts application/x-www-form-urlencoded, and the standard library reads that.
        form = {}
        try:
            raw = (await request.body()).decode('utf-8', 'replace')
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
        except Exception:
            form = {}
        given = str(form.get('password', '') or '')
        next_url = str(form.get('next', '') or '/') or '/'
        if not next_url.startswith('/') or next_url.startswith('//'):
            next_url = '/'                       # never redirect off this server

        if hmac.compare_digest(hashlib.sha256(given.encode('utf-8')).hexdigest(), digest):
            _login_failures.pop(ip, None)
            request.session['auth'] = wanted
            return RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)

        _login_failures[ip] = [fails + 1, since or now]
        return _login_page(request, next_url, 'Wrong password.')

    # already in, or exempt
    if request.session.get('auth') == wanted:
        return await call_next(request)
    if path == '/favicon.ico':
        return await call_next(request)
    if _cfg_bool('password_allow_local', True) and _is_local(ip):
        return await call_next(request)

    api_keys = cfg.get('api_keys', [])
    if len(api_keys) > 0:
        key = request.query_params.get('api_key') or request.session.get('api_key') or ''
        if key in api_keys:
            return await call_next(request)

    if _wants_json(request):
        return JSONResponse(content={'return': 1, 'error': 'this cMeta server asks for a password'},
                            status_code=status.HTTP_401_UNAUTHORIZED)

    next_url = request.url.path
    if request.url.query:
        next_url += '?' + request.url.query
    return _login_page(request, next_url)


# Added last on purpose: Starlette runs the most recently added middleware first, so this wraps the password gate
# above and request.session is already loaded when the gate reads and writes it.
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    session_cookie="cserver_session",
    max_age=session_max_age,  # a week by default, so a tablet is not asked for the password again every hour
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

##################################################################################################
@app.get("/")
async def home(
    request: Request,  # Input dictionary used by this function.
):
    """
    home function.

    Args:
        request (Request): Input dictionary used by this function.

    Returns:
        dict: Operation result.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
    r = await cm.utils.net.unify_request(request)
    if r['return']>0:
        # A POST whose body could not be read as a JSON object (an aborted request whose
        # body arrived truncated, a form-encoded body, ...): answer with the error instead
        # of handing a dict to an HTMLResponse route, which crashed with
        # "'dict' object has no attribute 'encode'" and a 500.
        return JSONResponse(content = r, status_code = 400)

    query = r['query']

    txt = f'Welcome to the cMeta server v{cm.__version__}!'

    out = query.get('out', '')
    if out == 'json':
        return JSONResponse(content = {'return': 0, 'text': txt})
    else:
        html_meta = {'request': request, 'html': f'<h3>{txt}</h3>'}
        return templates.TemplateResponse(request, 'task.html', html_meta, status_code = 200)


##################################################################################################
@app.get("/favicon.ico")
async def favicon():
    """
    favicon function.

    Args:
        None.

    Returns:
        dict: Operation result.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
    return FileResponse(os.path.join(home_dir_static, "images", "favicon.ico"))

##################################################################################################
##################################################################################################
@app.api_route("/{task}", methods=["GET", "POST"], response_class=HTMLResponse)
@app.api_route("/{task}/", methods=["GET", "POST"], response_class=HTMLResponse)
async def task_handler(
    request: Request,  # Input dictionary used by this function.
    task: str,  # Value for task.
):

    """
    task_handler function.

    Args:
        request (Request): Input dictionary used by this function.
        task (str): Value for task.

    Returns:
        dict: Operation result.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
    r = await cm.utils.net.unify_request(request)
    if r['return']>0:
        # A POST whose body could not be read as a JSON object (an aborted request whose
        # body arrived truncated, a form-encoded body, ...): answer with the error instead
        # of handing a dict to an HTMLResponse route, which crashed with
        # "'dict' object has no attribute 'encode'" and a 500.
        return JSONResponse(content = r, status_code = 400)

    query = r['query']

    force_json = query.get('force_json', False)

    # Check if API KEYS (very basic, native and insecure implementation just for testing)
    api_keys = cfg.get('api_keys', [])
    validated_api_key = None
    if len(api_keys)>0:
        err = ''
        api_key = query.get('api_key')
        if api_key is None or api_key == '':
            api_key = request.session.get('api_key')

        if api_key is None or api_key == '':
            err = 'api_key must be present in the query'
        else:
            if api_key not in api_keys:
                err = 'this api_key is not authorized'
            else:
                validated_api_key = api_key

        if err != '':
            r = {'return':1, 'error': err}

            if force_json:
               return JSONResponse(content = r)

            html_meta = {"message": r['error'], 'request': request}
            return templates.TemplateResponse(request, 'error.html', html_meta, status_code = 200)
        
        # Store validated API key in session
        request.session['api_key'] = validated_api_key

    url = str(request.url_for("task_handler", task=task)) + '?'
    url2 = str(request.url_for("home"))
    url_server = str(request.url_for("home"))
    url_server_js_script = url_server + 'static/js/cmeta_server.js'
    url_files = str(request.url_for("task_handler", task=task))
    if not url_files.endswith('/'): url_files += '/'

    command = query.get('command', '')
    if command is None or command.strip() == '':
        command = 'web'

    cmeta_params = {'category':f'cserver.{task}',
                    'command':command}

    cmeta_params['urls'] = {
        'url': url,
        'url2': url2,
        'url_files': url_files,
        'url_server': url_server,
        'url_server_js_script': url_server_js_script,
    }

    cmeta_params['query'] = query

    r = await cm.access(cmeta_params)
    if r['return']>0: 
        if force_json:
            return JSONResponse(content = r)

        html_meta = {"message": r['error'], 'request': request}
        return templates.TemplateResponse(request, 'error.html', html_meta, status_code = 200)

    if 'json' in r:
        return JSONResponse(content = r['json'])

    html_meta = r.get('html_meta',{})

    html_meta['request'] = request

    if force_json:
        return JSONResponse(content = cm.utils.common.safe_serialize_json(r))

    return templates.TemplateResponse(request, 'task.html', html_meta, status_code = 200)

##################################################################################################
@app.get("/{task}/{file_path:path}")
async def task_files(
    request: Request,  # Input dictionary used by this function.
    task: str,  # Value for task.
    file_path: str,  # Filesystem path.
):

    # Forbid relative paths
    """
    task_files function.

    Args:
        request (Request): Input dictionary used by this function.
        task (str): Value for task.
        file_path (str): Filesystem path.

    Returns:
        dict: Operation result.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
    if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Relative paths are not allowed")

    api_keys = cfg.get('api_keys', [])
    if len(api_keys)>0:
        # Check if API key exists in session
        api_key = request.session.get('api_key')
        
        # If not in session, check query parameter as fallback
        if api_key is None:
            api_key = request.query_params.get('api_key')
            if api_key is not None and api_key in api_keys:
                # Store in session for future requests
                request.session['api_key'] = api_key
        
        # Validate API key
        if api_key is None or api_key not in api_keys:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access - invalid or missing API key")

    task_name = f'cserver.{task}'

    r = await cm.access({'category': 'category',
                         'command': 'find',
                         'arg1': task_name})
    if r['return'] > 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to find category {task_name}")  

    artifacts = r['artifacts']

    if len(artifacts) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cmeta artifact for files not found")
    elif len(artifacts) > 1:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Multiple cmeta artifacts found for files")   

    artifact = artifacts[0]

    project_files_path = artifact['path']
    project_files_path = os.path.join(project_files_path, 'files')

    full_file_path = os.path.join(project_files_path, file_path)

    # Prevent directory traversal
    try:
        full_file_path = os.path.abspath(full_file_path)
        project_files_path = os.path.abspath(project_files_path)
        if not full_file_path.startswith(project_files_path):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid file path")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    # Check if file exists
    if os.path.isdir(full_file_path):
        full_file_path_to_index = os.path.join(full_file_path, 'index.html')
        if os.path.isfile(full_file_path_to_index):
            full_file_path = full_file_path_to_index

    if not os.path.isfile(full_file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Determine media type
    media_type, _ = mimetypes.guess_type(full_file_path)
    if media_type is None:
        media_type = 'application/octet-stream'

    if media_type == 'text/html':
        html_meta={'request': request}
        return templates.TemplateResponse(request, 'task.html', html_meta, status_code = 200)

    return FileResponse(full_file_path, media_type=media_type)
