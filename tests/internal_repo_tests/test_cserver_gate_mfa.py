"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for the two-step sign-in of the cserver app (2026-11-12, login_mfa): with a password and login_email set and
login_mfa: yes, the password first - it opens a half sign-in and mails a six-digit code -, then the code; neither alone
opens a page, no code is mailed (nor taken) before the password, the half sign-in runs out, a session from before
with one way in is asked again, failures are limited per address; with login_mfa off everything is as it was.

The app runs in-process with FastAPI's TestClient against a fresh <CMETA_HOME> in tmp_path; the mail goes to a fake
SMTP server that keeps the messages. Skipped without the server extra (fastapi) or httpx.
"""

import hashlib
import importlib.util
import os
import re
import smtplib
import socket

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')
PASSWORD = 'correct horse'
LOGIN = '/_cserver_login'


class FakeSMTP:
    """smtplib.SMTP / SMTP_SSL that keeps what it is given."""
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)

    def quit(self):
        pass


@pytest.fixture()
def server(tmp_path, monkeypatch):
    """The cserver app module and a client, on a fresh home; MFA set up (a password, one address, login_mfa)."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.chdir(APP_DIR)
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', FakeSMTP)
    FakeSMTP.sent = []
    spec = importlib.util.spec_from_file_location('cserver_app_mfa_under_test', os.path.join(APP_DIR, 'src', 'app.py'))
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    try:
        with TestClient(app_module.app) as client:
            app_module.cfg.clear()
            app_module.cfg.update({'password_sha256': hashlib.sha256(PASSWORD.encode('utf-8')).hexdigest(),
                                   'login_email': 'me@example.com', 'login_mfa': 'yes', 'password_allow_local': 'no',
                                   'login_smtp_host': 'smtp.example.com', 'login_smtp_user': 'admin@example.com',
                                   'login_smtp_password': 'x'})
            app_module._login_failures.clear()
            yield app_module, client
    finally:
        app_module.cm.shutdown()


def post(client, **form):
    return client.post(LOGIN, data=dict({'next': '/settings'}, **form), follow_redirects=False)


def code_of(msg):
    return re.search(r'\b(\d{6})\b', msg['Subject']).group(1)


def text_of(msg):
    """The plain text of the mail (it has an HTML part too)."""
    return msg.get_body(('plain',)).get_content()


def html_of(msg):
    return msg.get_body(('html',)).get_content()


def test_the_password_first_then_the_code(server):
    app, client = server
    r = client.get('/settings')
    assert r.status_code == 401 and 'type="password"' in r.text and 'name="code"' not in r.text
    assert 'then for a code it sends by e-mail' in r.text
    # while the server answers: the buttons gray, a spinner and what is being done (not "disabled": the form keeps them)
    assert 'data-busy="Checking the password, then sending the code by e-mail ..."' in r.text
    assert "classList.add('busy')" in r.text and not re.search(r'<button[^>]*\sdisabled', r.text)

    # neither a code nor a mail before the password
    assert 'The password first' in post(client, email='0', code='123456').text
    assert 'The password first' in post(client, send='0').text
    assert FakeSMTP.sent == []
    r = post(client, password='wrong')
    assert 'Wrong password' in r.text and FakeSMTP.sent == []

    # the password: a half sign-in, the code mailed, the pages still closed
    r = post(client, password=PASSWORD, keep='1')
    assert r.status_code == 401 and 'A code was sent to m***@example.com' in r.text and 'name="code"' in r.text
    assert 'type="password"' not in r.text
    assert len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]['To'] == 'me@example.com'
    body = text_of(FakeSMTP.sent[0])                  # the machine, who asked, and what a code nobody asked for means
    assert socket.gethostname() in FakeSMTP.sent[0]['Subject'] and 'It was asked from testclient.' in body
    assert 'someone else knows the password' in body
    code = code_of(FakeSMTP.sent[0])
    assert '\n\n    %s\n\n' % code in body                                      # the code alone on its line
    assert 'font-weight:700' in html_of(FakeSMTP.sent[0]) and '>%s</p>' % code in html_of(FakeSMTP.sent[0])   # bold
    assert 'data-busy="Sending the code to m***@example.com ..."' in r.text   # "Send again": its own busy line
    r = client.get('/settings')
    assert r.status_code == 401 and 'The password is right' in r.text and 'name="code"' in r.text

    # a wrong code: refused; the right one: in
    wrong = '%06d' % ((int(code) + 1) % 1000000)
    assert 'Wrong or expired code' in post(client, email='0', code=wrong).text
    r = post(client, email='0', code=code)
    assert r.status_code == 303 and r.headers['location'] == '/settings'
    assert client.get('/settings').status_code == 200


def test_a_session_with_one_way_in_is_asked_again(server):
    app, client = server
    app.cfg['login_mfa'] = 'no'                        # as before: the password alone
    assert post(client, password=PASSWORD).status_code == 303
    assert client.get('/settings').status_code == 200
    app.cfg['login_mfa'] = 'yes'                       # MFA turned on: the password's session is not enough
    r = client.get('/settings')
    assert r.status_code == 401 and 'type="password"' in r.text


def test_the_half_sign_in_runs_out(server, monkeypatch):
    app, client = server
    monkeypatch.setattr(app, 'MFA_STEP', -1)            # the time between the password and the code: over at once
    post(client, password=PASSWORD)
    code = code_of(FakeSMTP.sent[-1])
    r = post(client, email='0', code=code)
    assert r.status_code == 401 and 'The password first' in r.text
    assert client.get('/settings').status_code == 401


def test_guesses_are_limited(server):
    app, client = server
    app.cfg['password_max_attempts'] = '3'
    for _ in range(3):
        assert 'Wrong password' in post(client, password='nope').text
    r = post(client, password=PASSWORD)
    assert r.status_code == 429 and 'Too many attempts' in r.text and FakeSMTP.sent == []


def test_the_smtp_password_file_by_cref(server):
    """login_smtp_password_file as {{{cRef}}}/<path> - split at the cRef's comma, as the command line does - is found
    at startup; one not found stays as written, and the mail then says why."""
    app, client = server
    utils = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'category', 'utils')
    app.cfg['login_smtp_password_file'] = ['{{{category::utils', '234ce5e3262e4d52}}}/_cmeta.yaml']
    client.portal.call(app._resolve_cfg_paths)
    assert os.path.normcase(app.cfg['login_smtp_password_file']) == os.path.normcase(os.path.join(utils, '_cmeta.yaml'))

    app.cfg['login_smtp_password'] = ''
    app.cfg['login_smtp_password_file'] = '{{{category::no-such-category-of-this-test}}}/files/password'
    client.portal.call(app._resolve_cfg_paths)
    assert app.cfg['login_smtp_password_file'].startswith('{{{')
    r = post(client, password=PASSWORD)
    assert 'The code could not be sent' in r.text and 'was not found when the server started' in r.text
    assert FakeSMTP.sent == []


def test_a_failed_mail_gives_the_minute_back(server, monkeypatch):
    """A mail that fails does not count as sent: the retry right after it is not told to wait a minute."""
    app, client = server
    refused, kept = [], FakeSMTP.send_message

    def refused_once(self, msg):
        if not refused:
            refused.append(msg['To'])
            raise smtplib.SMTPRecipientsRefused({msg['To']: (550, b'no')})
        return kept(self, msg)
    monkeypatch.setattr(FakeSMTP, 'send_message', refused_once)
    r = post(client, password=PASSWORD)
    assert 'The code could not be sent' in r.text and 'name="send"' in r.text and refused == ['me@example.com']
    r = post(client, send='0')
    assert 'A code was sent to m***@example.com' in r.text and len(FakeSMTP.sent) == 1
    assert post(client, email='0', code=code_of(FakeSMTP.sent[0])).status_code == 303


def test_without_mfa_everything_is_as_it_was(server):
    app, client = server
    app.cfg['login_mfa'] = 'no'
    r = client.get('/settings')
    assert r.status_code == 401 and 'type="password"' in r.text and 'Send a code to' in r.text   # either way in
    assert post(client, password=PASSWORD).status_code == 303 and client.get('/settings').status_code == 200
    client.cookies.clear()
    post(client, send='0')                             # a code alone opens too
    assert 'If you did not ask for it, ignore this message.' in text_of(FakeSMTP.sent[-1])
    assert post(client, email='0', code=code_of(FakeSMTP.sent[-1])).status_code == 303
    assert client.get('/settings').status_code == 200
    # login_mfa with no address set: the password alone (nothing to send a code to)
    client.cookies.clear()
    app.cfg['login_mfa'] = 'yes'
    app.cfg['login_email'] = ''
    assert post(client, password=PASSWORD).status_code == 303 and client.get('/settings').status_code == 200
