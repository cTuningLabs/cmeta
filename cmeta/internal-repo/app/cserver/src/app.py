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
import socket
import json
import asyncio
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
cfg_path = ''

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
    global cm, cfg, cfg_path
    r = await cm.access({'category':'config,cc6bfe174be847ed', 'command':'get', 'arg1':'cserver'})
    if r['return'] > 0: cmeta_catch(r)

    cfg = r['config_cmeta']
    cfg_path = (r.get('artifact') or {}).get('path', '') or ''      # the folder: the e-mailed login codes live there

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
# development keep working untouched. That exemption is decided on the real peer address and only for a request
# with no proxy header, because those headers are written by whoever connects. A request carrying a valid
# api_key is exempt too, so automation that already authenticates does not need a second secret.
#
# Behind a reverse proxy on the same host, every request arrives from loopback. Such a proxy normally adds
# `X-Forwarded-For`, which already disables the exemption; if yours does not, set password_allow_local=no.
# Set password_trust_proxy=yes to count failed attempts per forwarded client rather than per proxy.

# A code by e-mail instead of (or beside) the password - off until `login_email` is set:
#
#   cx config set cserver --meta.login_email=you@example.com          # who receives the codes (a comma-separated list is fine)
#   cx config set cserver --meta.login_smtp_host=smtp.example.com --meta.login_smtp_port=587
#   cx config set cserver --meta.login_smtp_user=you@example.com --meta.login_smtp_password="<app password>"
#   cx config set cserver --meta.login_days=30                        # how long a code keeps a browser in (30)
#   cx config set cserver --meta.login_code_minutes=10                # how long a code is good for (10)
#   cx config set cserver --meta.login_smtp_from=...                  # the sender (the user by default)
#   cx config set cserver --meta.login_smtp_password_file=<path>      # the password read from a file instead
#
# Port 465 means TLS from the start, any other port STARTTLS (login_smtp_starttls=no turns it off). The login page
# then shows the masked address, a "Send a code" button and the code field; a code is six digits, one per minute
# per address, five tries, kept hashed with its expiry in `login-codes.json` of the cserver config artifact (the
# workers share it through that file). A password set as well stays a second way in. Same caveats as the password:
# clear text unless HTTPS or an overlay network such as Tailscale carries it.

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


def _login_emails():
    """The addresses a code may be sent to (login_email, comma-separated); [] when the e-mail way is off."""
    return [e.strip().lower() for e in _cfg_str('login_email').replace(';', ',').split(',') if e.strip()]


def _gate_on():
    """Whether this server asks browsers for a password or an e-mailed code."""
    return bool(_password_sha256() or _login_emails())


def _mask_email(email):
    """g***@example.com: enough to recognise the address on the login page, not enough to copy it."""
    name, _, domain = email.partition('@')
    return (name[:1] + '***' if name else '***') + '@' + domain


def _email_token(email):
    """What a session opened with a code stores: the address keyed by the cookie secret (see _session_token)."""
    return hmac.new(session_secret.encode('utf-8'), ('email:' + email).encode('utf-8'), hashlib.sha256).hexdigest()


def _past(written, plus=0.0):
    """Whether the wall clock is past a time written down (a code's expiry or sending time in the codes file, a
    login's end in the session cookie), `plus` seconds later: the one wall-clock comparison that is right - the
    writer and the reader are different processes and the written time must be read back as it was."""
    return time.time() > float(written or 0) + plus


def _later(seconds):
    """A wall-clock time to write down, `seconds` from now (read back by _past)."""
    return time.time() + float(seconds)


def _codes_path():
    return os.path.join(cfg_path, 'login-codes.json') if cfg_path else ''


def _codes_read():
    try:
        with open(_codes_path(), encoding='utf-8') as f:
            codes = json.load(f)
        return codes if isinstance(codes, dict) else {}
    except Exception:
        return {}


def _codes_write(codes):
    """Written whole, then named into place: a worker never reads a half file."""
    path = _codes_path()
    if not path:
        raise RuntimeError('the cserver config artifact has no folder: a code cannot be kept')
    tmp = path + '.tmp-%d' % os.getpid()
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(codes, f)
    os.replace(tmp, path)


def _send_code(email):
    """Makes a six-digit code for the address, keeps its hash with the expiry, sends it; one per minute."""
    codes = _codes_read()
    entry = codes.get(email) or {}
    if not _past(entry.get('sent_at'), 60):
        raise RuntimeError('a code was sent less than a minute ago: look in the mailbox, or wait a moment')
    code = '%06d' % secrets.randbelow(1000000)
    minutes = max(1, _cfg_int('login_code_minutes', 10))
    codes[email] = {'hash': _email_token(email + ':' + code), 'until': _later(minutes * 60), 'tries': 0, 'sent_at': time.time()}
    _codes_write(codes)

    import smtplib
    from email.message import EmailMessage
    host = _cfg_str('login_smtp_host')
    if not host:
        raise RuntimeError('login_smtp_host is not set in the cserver config')
    port = _cfg_int('login_smtp_port', 587)
    user = _cfg_str('login_smtp_user')
    password = _cfg_str('login_smtp_password')
    if not password and _cfg_str('login_smtp_password_file'):
        with open(_cfg_str('login_smtp_password_file'), encoding='utf-8') as f:
            password = f.read().strip()
    sender = _cfg_str('login_smtp_from') or user or ('cserver@' + socket.gethostname())
    realm = _cfg_str('password_realm') or 'cMeta server'
    msg = EmailMessage()
    msg['Subject'] = '%s: your code %s' % (realm, code)
    msg['From'] = sender
    msg['To'] = email
    msg.set_content('Your code for %s is %s.\n\nIt is good for %d minutes. If you did not ask for it, ignore this message.\n'
                    % (realm, code, minutes))
    timeout = max(5, _cfg_int('login_smtp_timeout', 30))
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        server.ehlo()
        if port != 465 and _cfg_bool('login_smtp_starttls', True):
            server.starttls()
            server.ehlo()
        if user:
            server.login(user, password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _check_code(email, given):
    """True when the code is the one sent to the address and still good; a used or spent code is removed."""
    codes = _codes_read()
    entry = codes.get(email)
    if not entry:
        return False
    ok = not _past(entry.get('until')) and hmac.compare_digest(_email_token(email + ':' + given.strip()), str(entry.get('hash') or ''))
    entry['tries'] = int(entry.get('tries') or 0) + 1
    if ok or entry['tries'] >= 5 or _past(entry.get('until')):
        codes.pop(email, None)
    else:
        codes[email] = entry
    _codes_write(codes)
    return ok


def _session_open(request, wanted):
    """Whether the session cookie opens the gate: the password's token, or a code login that has not run out."""
    auth = request.session.get('auth')
    if auth and wanted and auth == wanted:
        until = request.session.get('auth_until')
        return until is None or not _past(until)
    token = request.session.get('auth_email')
    if token and any(hmac.compare_digest(token, _email_token(e)) for e in _login_emails()):
        return not _past(request.session.get('auth_until'))
    return False


# Headers a reverse proxy adds. Anyone can send them, so they are never trusted for the loopback exemption.
FORWARDING_HEADERS = ('x-forwarded-for', 'x-real-ip', 'forwarded')


def _peer_ip(request):
    """The address the connection came from, as the server stack reports it.

    Not read from a header here, but not fully trustworthy either: uvicorn's proxy-header middleware runs
    outside this app and overwrites it from `X-Forwarded-For` when the peer is in `--forwarded-allow-ips`
    (loopback by default). That is why every decision below also asks whether a proxy header was present at all.
    """
    return getattr(request.client, 'host', '') or ''


def _forwarded_ip(request):
    """The left-most address a proxy claims the request came from, or '' when no proxy header is present."""
    fwd = request.headers.get('x-forwarded-for', '') or request.headers.get('x-real-ip', '')
    return fwd.split(',')[0].strip()


def _via_proxy(request):
    """True when the request carries any proxy header, so it did not come straight from a local process."""
    return any(request.headers.get(h) for h in FORWARDING_HEADERS)


def _is_local(ip):
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _host_local(request):
    """True when the Host header names this machine: localhost, *.localhost or a loopback address.

    A page that a browser on this machine loads from another name that resolves to 127.0.0.1 (DNS rebinding)
    reaches the server from loopback too; its Host header still carries that other name.
    """
    host = request.headers.get('host', '').strip().lower()
    if host.startswith('['):
        name = host[1:].split(']', 1)[0]
    else:
        name = host.rsplit(':', 1)[0] if host.count(':') == 1 else host
    return name == 'localhost' or name.endswith('.localhost') or _is_local(name)


def _same_origin(request):
    """True unless a browser says the request came from a page of another site.

    Browsers send Sec-Fetch-Site (same-origin, same-site, cross-site, or none for a typed address) and, on a POST,
    Origin. A request with neither did not come from a web page (the CLI, curl, a script).
    """
    site = request.headers.get('sec-fetch-site', '').strip().lower()
    if site:
        return site in ('same-origin', 'none')
    origin = request.headers.get('origin', '').strip().lower()
    if not origin:
        return True
    try:
        return urllib.parse.urlsplit(origin).netloc == request.headers.get('host', '').strip().lower()
    except ValueError:
        return False


VIA_PROXY_BUCKET = 'via-untrusted-proxy'


def _throttle_key(request):
    """Which address the failed-attempt counter is kept under.

    Behind a proxy the peer is always the proxy, so every client would share one bucket and one attacker could
    lock everybody out. There the forwarded address is the useful key, but only when `password_trust_proxy` says
    the header comes from a proxy under your control.

    Without that, a forwarded address must not become a key at all: uvicorn already rewrites `request.client`
    from `X-Forwarded-For` when the peer is in its `--forwarded-allow-ips` (loopback by default), so a caller
    that reaches the port could otherwise mint a fresh bucket per request by varying the header and never meet
    the lockout. Every request carrying an untrusted proxy header therefore shares one bucket.
    """
    if _via_proxy(request):
        if _cfg_bool('password_trust_proxy', False):
            fwd = _forwarded_ip(request)
            if fwd:
                return fwd
        return VIA_PROXY_BUCKET
    return _peer_ip(request)


def _wants_json(request):
    """A machine caller (AJAX, force_json, out=json, an Accept of JSON) must not be answered with HTML."""
    q = request.query_params
    if q.get('native_action') or q.get('force_json'):
        return True
    if str(q.get('out', '')).strip().lower() == 'json':
        return True
    accept = request.headers.get('accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def _login_page(request, next_url, message='', status_code=status.HTTP_401_UNAUTHORIZED, sent_to=None, ok=False):
    """A self-contained prompt: no assets to fetch, so it renders before anything else is authorised.

    With login_email set: the masked address(es) each with a "Send a code" button, then - once sent - the code
    field; with a password set: the password field (both when both are set). `sent_to` is the index of the address
    a code has just gone to; `ok` colours the message as a notice rather than an error.
    """
    realm = _cfg_str('password_realm') or 'cMeta server'
    note = ('<p class="msg%s">%s</p>' % (' ok' if ok else '', html_escaper.escape(message))) if message else ''
    emails = _login_emails()
    hidden_next = '<input type="hidden" name="next" value="%s">' % html_escaper.escape(next_url, quote=True)
    parts = []
    if emails:
        if sent_to is not None and 0 <= sent_to < len(emails):
            parts.append('<form method="post" action="%s">%s<input type="hidden" name="email" value="%d">'
                         '<p>The code sent to <b>%s</b>:</p>'
                         '<input type="text" name="code" placeholder="6 digits" inputmode="numeric" pattern="[0-9]{6}" '
                         'autocomplete="one-time-code" autofocus required>'
                         '<button type="submit">Open</button></form>'
                         % (LOGIN_PATH, hidden_next, sent_to, html_escaper.escape(_mask_email(emails[sent_to]))))
        buttons = ''.join('<button type="submit" name="send" value="%d"%s>%s a code to %s</button>'
                          % (i, ' class="second"' if (sent_to is not None or i) else '',
                             'Send again' if sent_to == i else 'Send', html_escaper.escape(_mask_email(e)))
                          for i, e in enumerate(emails))
        parts.append('<form method="post" action="%s">%s%s</form>' % (LOGIN_PATH, hidden_next, buttons))
    if _password_sha256():
        parts.append('<form method="post" action="%s">%s%s'
                     '<input type="password" name="password" placeholder="Password" autocomplete="current-password"%s required>'
                     '<button type="submit"%s>Open</button></form>'
                     % (LOGIN_PATH, hidden_next, '<p class="or">or the password</p>' if emails else '',
                        '' if emails else ' autofocus', ' class="second"' if emails else ''))
    lead = ('This server asks for a code sent by e-mail' + (' or its password' if _password_sha256() else '')
            if emails else 'This server asks for a password') + ' before showing its pages.'
    body = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(realm)s</title>
<style>
 :root {color-scheme: light dark;}
 body {margin:0; min-height:100vh; display:grid; place-items:center;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:#f4f5f8; color:#14161a;}
 main {width:min(92vw,360px); padding:26px 24px; background:#fff; border:1px solid #e3e6ec;
       border-radius:14px; box-shadow:0 8px 30px rgba(0,0,0,.06);}
 form {margin:0;}
 h1 {margin:0 0 4px; font-size:19px; font-weight:640;}
 p {margin:0 0 14px; font-size:13.5px; color:#6b7180;}
 p.msg {color:#a21b1b; font-weight:560;}
 p.msg.ok {color:#1b7a3d;}
 p.or {margin:14px 0 6px; text-align:center;}
 input[type=password], input[type=text] {width:100%%; padding:12px 13px; font-size:16px; color:inherit; background:#fff;
       border:1px solid #d7dbe3; border-radius:9px; box-sizing:border-box;}
 input:focus {outline:2px solid rgba(92,15,201,.18); border-color:#5c0fc9;}
 button {width:100%%; margin-top:12px; padding:12px; font-size:15px; font-weight:560; color:#fff;
       background:#5c0fc9; border:0; border-radius:9px; cursor:pointer;}
 button:hover {background:#4a0ca4;}
 button.second {background:#fff; color:#5c0fc9; border:1px solid #d7dbe3;}
 button.second:hover {background:#f4f5f8;}
 @media (prefers-color-scheme: dark) {
   body {background:#101216; color:#e8eaee;}
   main {background:#1b1e24; border-color:#2c3038; box-shadow:none;}
   p {color:#9aa1ad;}
   p.msg {color:#ff9d9d;}
   p.msg.ok {color:#8fe0a8;}
   input[type=password], input[type=text] {background:#14161a; border-color:#343a44; color:#e8eaee;}
   button {background:#7c4dff;}
   button.second {background:#1b1e24; color:#c9b6ff; border-color:#343a44;}
 }
</style></head>
<body>
 <main>
  <h1>%(realm)s</h1>
  <p>%(lead)s</p>
  %(note)s
  %(forms)s
 </main>
</body></html>
""" % {'realm': html_escaper.escape(realm), 'lead': html_escaper.escape(lead), 'note': note, 'forms': ''.join(parts)}
    return HTMLResponse(content=body, status_code=status_code)


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """Ask for the shared password, or a code sent by e-mail, before any route runs, when one is configured."""
    digest = _password_sha256()
    emails = _login_emails()

    path = request.url.path

    if not digest and not emails:
        # nothing configured: the server behaves exactly as it always did
        if path == LOGIN_PATH:
            return RedirectResponse(url='/', status_code=status.HTTP_303_SEE_OTHER)
        return await call_next(request)

    wanted = _session_token(digest) if digest else ''
    ip = _throttle_key(request)

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
        next_url = str(form.get('next', '') or '/') or '/'
        if not next_url.startswith('/') or next_url.startswith('//'):
            next_url = '/'                       # never redirect off this server

        def index_of(key):
            try:
                i = int(str(form.get(key, '')).strip())
            except ValueError:
                return None
            return i if 0 <= i < len(emails) else None

        # "Send a code": the address by its index, never the address itself from the form
        if emails and form.get('send', '') != '':
            i = index_of('send')
            if i is None:
                return _login_page(request, next_url, 'No such address.')
            try:
                await asyncio.to_thread(_send_code, emails[i])
            except Exception as e:
                return _login_page(request, next_url, 'The code could not be sent: %s' % e)
            return _login_page(request, next_url, 'A code was sent to %s - it is good for %d minutes.'
                               % (_mask_email(emails[i]), max(1, _cfg_int('login_code_minutes', 10))), sent_to=i, ok=True)

        # the code
        if emails and form.get('code', '') != '':
            i = index_of('email')
            given = str(form.get('code', '') or '')
            if i is not None and given.strip().isdigit() and _check_code(emails[i], given):
                _login_failures.pop(ip, None)
                request.session.pop('auth', None)
                request.session['auth_email'] = _email_token(emails[i])
                request.session['auth_until'] = _later(max(1, _cfg_int('login_days', 30)) * 86400)
                return RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)
            _login_failures[ip] = [fails + 1, since or now]
            return _login_page(request, next_url, 'Wrong or expired code.', sent_to=i)

        # the password
        given = str(form.get('password', '') or '')
        if digest and hmac.compare_digest(hashlib.sha256(given.encode('utf-8')).hexdigest(), digest):
            _login_failures.pop(ip, None)
            request.session.pop('auth_email', None)
            request.session['auth'] = wanted
            request.session['auth_until'] = _later(session_max_age)
            return RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)

        _login_failures[ip] = [fails + 1, since or now]
        return _login_page(request, next_url, 'Wrong password.' if digest else 'Ask for a code first.')

    # already in, or exempt
    if _session_open(request, wanted):
        return await call_next(request)
    if path == '/favicon.ico':
        return await call_next(request)

    # The loopback exemption is decided on the address the connection really came from, and only for a request
    # that carries no proxy header at all. A local browser or a local script sends none; a request that arrived
    # through a proxy does, and so does an attacker hoping that `X-Forwarded-For: 127.0.0.1` will be taken at
    # face value. Reading the header here would hand that attacker the whole server.
    if _cfg_bool('password_allow_local', True) and _is_local(_peer_ip(request)) and not _via_proxy(request):
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
    max_age=max(session_max_age, 31 * 86400),  # the gate keeps its own expiry per login (auth_until): a week for the password, login_days for a code
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

##################################################################################################
# The home page
#
# "/" shows the page named by `default_page` in the cserver config. By default that is /projects: the cards of
# every cserver.* page plugged into this machine, with the version of this server and where cMeta lives under
# them.
#
#   cx config set cserver --meta.default_page=/projects     # the default
#   cx config set cserver --meta.default_page=/<page>       # any other cserver.<page>
#   cx config set cserver --meta.default_page=none          # the plain welcome page
#
# When that page cannot be shown (its category is not plugged in, it fails, or it refuses the api_key), "/"
# shows the plain welcome page instead, so the home page never turns into an error. `/?out=json` answers as
# it always did.

def _default_page():
    """The page "/" shows, without slashes ('' for the plain welcome page)."""
    page = _cfg_str('default_page', '/projects').strip('/')
    return '' if page.lower() in ('', 'none', 'off', 'no', 'false') else page


def _welcome(request):
    """The plain welcome page: the version of this server and where cMeta lives."""
    html_meta = {'request': request, 'page_title': 'cMeta server', 'version': cm.__version__}
    return templates.TemplateResponse(request, 'welcome.html', html_meta, status_code = 200)


@app.get("/")
async def home(
    request: Request,  # Input dictionary used by this function.
):
    """
    home function: the page named by `default_page` (by default /projects), else the plain welcome page.

    Args:
        request (Request): Input dictionary used by this function.

    Returns:
        Response: the page, the welcome page, or {'return': 0, 'text': ...} for ?out=json.

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

    page = _default_page()
    if page:
        response = await _serve_page(request, page, query, quiet = True)
        if response is not None:
            return response

    return _welcome(request)


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
@app.get("/cref/{ref:path}")
async def cref_shortcut(
    request: Request,  # Input dictionary used by this function.
    ref: str,  # <category>::<alias>,<UID>[/<relative path>] - any form the browse page's cref= takes.
):
    """
    The page of an artifact: /cref/<category>::<alias>,<UID>[/<relative path>] is served by cserver.cref as it is -
    the cRef stays in the address bar - which resolves the reference through cserver.browse and applies this
    server's rules.

    Returns:
        Response: the page of cserver.cref.
    """
    r = await cm.utils.net.unify_request(request)
    if r['return'] > 0:
        return JSONResponse(content = r, status_code = 400)
    query = r['query']
    query['cref'] = ref
    return await _serve_page(request, 'cref', query)

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

    return await _serve_page(request, task, r['query'])


async def _serve_page(
    request: Request,  # Input dictionary used by this function.
    task: str,  # The page: category cserver.<task>.
    query: dict,  # The unified query (GET parameters and the POST JSON body).
    quiet: bool = False,  # The home page: None instead of an error page, so "/" can fall back to the welcome.
):
    """
    Render the page of category cserver.<task> (command `web` unless ?command= says otherwise) or answer its
    AJAX call with JSON. Shared by /<task> and by "/" (the default page).

    Returns:
        Response, or None when `quiet` and the page cannot be shown.
    """
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
            if quiet:
                return None

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

    # Whether the browser runs on this machine: the real peer address, no proxy header, and a Host header that
    # names this machine (a loopback peer alone could be a page reached by DNS rebinding). A page may then offer
    # more than to the network - cserver.browse shows the files of an artifact and opens its folder.
    # same_origin: no browser said the request came from a page of another site - for actions with side effects.
    # password_gate: this server asks browsers for its password (the gate runs before any route), so a request that
    # reached the page passed it, or was exempt as local or by an api key - a page with a secret of its own may trust it.
    cmeta_params['misc'] = {'client_local': (_is_local(_peer_ip(request)) and not _via_proxy(request)
                                             and _host_local(request)),
                            'same_origin': _same_origin(request),
                            'password_gate': _gate_on()}

    r = await cm.access(cmeta_params)
    if r['return']>0:
        if quiet:
            return None

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

    # A real file under files/ is served as it is - an HTML asset too (a self-contained page such as a 3D view with
    # its own <html>, import map and module scripts): wrapping it in the server's template left only the shell, so
    # the page loaded without its scripts (the dcloc 3D map was blank, 2026-10-26). Text keeps a UTF-8 charset.
    if media_type and media_type.startswith('text/'):
        return FileResponse(full_file_path, media_type=media_type + '; charset=utf-8')

    return FileResponse(full_file_path, media_type=media_type)
