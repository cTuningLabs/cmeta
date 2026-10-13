"""
Run and register cMeta artifacts as Mozilla native messaging hosts.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys


MAX_INPUT = 4 * 1024 * 1024
MAX_OUTPUT = 1024 * 1024 - 1
REF_PATTERN = re.compile(r'^[A-Za-z0-9_.,:-]+::[A-Za-z0-9_.,:-]+$')
HOST_PATTERN = re.compile(r'^[a-z0-9_.-]+$')


def resolve(cm, ref):
    """Resolve a host artifact in the active cMeta home, then validate its declaration."""
    if not isinstance(ref, str) or not REF_PATTERN.fullmatch(ref):
        raise ValueError('Give one cMeta category::artifact reference (UIDs are recommended).')
    category, artifact = ref.split('::', 1)
    found = cm.access({'category': category, 'command': 'find', 'arg1': artifact,
                       'con': False, 'quiet': True})
    if found.get('return'):
        raise RuntimeError(found.get('error') or 'Native host artifact lookup failed.')
    matches = found.get('artifacts', [])
    if len(matches) != 1:
        raise RuntimeError('Expected one native host artifact in the active cMeta home; found ' + str(len(matches)) + '.')
    root = Path(matches[0]['path']).resolve()
    declaration = json.loads((root / 'native-host.json').read_text(encoding='utf-8'))
    name = declaration.get('name')
    extensions = declaration.get('allowed_extensions')
    entry_name = declaration.get('entry')
    checks = declaration.get('checks', [{'command': 'ping'}])
    if not isinstance(name, str) or not HOST_PATTERN.fullmatch(name):
        raise ValueError('Invalid native host name in native-host.json.')
    if not isinstance(extensions, list) or not extensions or not all(isinstance(x, str) and x for x in extensions):
        raise ValueError('Invalid allowed_extensions in native-host.json.')
    if not isinstance(entry_name, str) or not entry_name.endswith('.py'):
        raise ValueError('Invalid Python entry in native-host.json.')
    entry = (root / entry_name).resolve()
    if root not in entry.parents or not entry.is_file():
        raise ValueError('Native host entry must be a Python file inside its artifact.')
    if not isinstance(checks, list) or not checks or not all(isinstance(x, dict) for x in checks):
        raise ValueError('Invalid checks in native-host.json.')
    return {'ref': ref, 'root': root, 'entry': entry, 'name': name,
            'description': declaration.get('description', name),
            'allowed_extensions': extensions, 'checks': checks}


def locations(name):
    """Keep launchers independent of the repository and selected cMeta home."""
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'cmeta/native-messaging'
        return base / (name + '.bat'), base / (name + '.json')
    if sys.platform == 'darwin':
        launcher = Path.home() / 'Library/Application Support/cmeta/native-messaging' / (name + '.sh')
        manifest = Path.home() / 'Library/Application Support/Mozilla/NativeMessagingHosts' / (name + '.json')
        return launcher, manifest
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    launcher = data / 'cmeta/native-messaging' / (name + '.sh')
    manifest = Path.home() / '.mozilla/native-messaging-hosts' / (name + '.json')
    return launcher, manifest


def _registered_manifest(name):
    if os.name != 'nt':
        return None
    import winreg
    key_name = 'Software\\Mozilla\\NativeMessagingHosts\\' + name
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
            return Path(winreg.QueryValueEx(key, '')[0])
    except FileNotFoundError:
        return None


def _write_registration(name, manifest):
    if os.name == 'nt':
        import winreg
        key_name = 'Software\\Mozilla\\NativeMessagingHosts\\' + name
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_name) as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest))


def _owned_previous(previous, host):
    """Permit migration only from this same artifact's legacy registration."""
    if not previous or not previous.is_file():
        return False
    try:
        data = json.loads(previous.read_text(encoding='utf-8'))
        launcher = Path(data['path']).resolve()
        current_launcher, _ = locations(host['name'])
        same_name = data.get('name') == host['name']
        same_extensions = data.get('allowed_extensions') == host['allowed_extensions']
        same_artifact = host['root'] in launcher.parents
        stable_launcher = launcher == current_launcher.resolve()
        return same_name and same_extensions and (same_artifact or stable_launcher)
    except (OSError, ValueError, KeyError):
        return False


def install(cm, ref, apply=False):
    host = resolve(cm, ref)
    launcher, manifest = locations(host['name'])
    previous = _registered_manifest(host['name']) if os.name == 'nt' else (manifest if manifest.exists() else None)
    if previous and previous.resolve() != manifest.resolve() and not _owned_previous(previous, host):
        raise RuntimeError('Native host name is registered to a different artifact: ' + str(previous))
    if manifest.exists() and not _owned_previous(manifest, host):
        raise RuntimeError('Refusing to overwrite a different native host manifest: ' + str(manifest))
    expected = {'name': host['name'], 'description': host['description'],
                'path': str(launcher), 'type': 'stdio',
                'allowed_extensions': host['allowed_extensions']}
    # A cRef contains only shell-safe characters. The active cMeta CLI on PATH
    # resolves the current home and artifact afresh on every browser request.
    args = ' utils native-host-run ' + ref + ' --quiet'
    if os.name == 'nt':
        content = ('@echo off\r\nsetlocal DisableDelayedExpansion\r\n'
                   'where.exe cx >nul 2>nul\r\nif errorlevel 1 goto try_cmeta\r\n'
                   'cx' + args + '\r\nexit /b %errorlevel%\r\n'
                   ':try_cmeta\r\nwhere.exe cmeta >nul 2>nul\r\n'
                   'if errorlevel 1 goto missing\r\ncmeta' + args + '\r\n'
                   'exit /b %errorlevel%\r\n:missing\r\n'
                   '>&2 echo cMeta CLI cx or cmeta is not on PATH.\r\nexit /b 127\r\n')
    else:
        content = ('#!/bin/sh\n'
                   'if command -v cx >/dev/null 2>&1; then exec cx' + args + '; fi\n'
                   'if command -v cmeta >/dev/null 2>&1; then exec cmeta' + args + '; fi\n'
                   'echo "cMeta CLI cx or cmeta is not on PATH." >&2\nexit 127\n')
    print('Active cMeta home:', cm.home_path)
    print('Native host artifact:', host['root'])
    print('Native host manifest:', manifest)
    if not apply:
        print('Review only. Add --apply to register the host.')
        return {'return': 0, 'manifest': str(manifest), 'applied': False}
    launcher.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_bytes(content.encode('mbcs' if os.name == 'nt' else 'utf-8'))
    if os.name != 'nt':
        launcher.chmod(0o700)
    manifest.write_text(json.dumps(expected, indent=2) + '\n', encoding='utf-8')
    _write_registration(host['name'], manifest)
    return {'return': 0, 'manifest': str(manifest), 'applied': True}


def _send(command, request, home):
    body = json.dumps(request).encode('utf-8')
    env = os.environ.copy()
    env['CMETA_HOME'] = str(home)
    result = subprocess.run(command, input=struct.pack('=I', len(body)) + body,
                            capture_output=True, timeout=30, env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode or len(result.stdout) < 4:
        raise RuntimeError(result.stderr.decode(errors='replace') or 'Native host returned no frame.')
    count = struct.unpack('=I', result.stdout[:4])[0]
    if count != len(result.stdout) - 4:
        raise RuntimeError('Invalid native host framing.')
    response = json.loads(result.stdout[4:])
    if response.get('return'):
        raise RuntimeError(response.get('error') or str(response))
    return response


def check(cm, ref):
    host = resolve(cm, ref)
    launcher, manifest = locations(host['name'])
    if not launcher.is_file() or not manifest.is_file():
        raise RuntimeError('Native host is not installed. Run native-host-install --apply first.')
    registered = _registered_manifest(host['name']) if os.name == 'nt' else manifest
    if not registered or registered.resolve() != manifest.resolve():
        raise RuntimeError('Native host registration points elsewhere.')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('path') != str(launcher) or data.get('allowed_extensions') != host['allowed_extensions']:
        raise RuntimeError('Native host manifest does not match this artifact.')
    if os.name == 'nt':
        command = subprocess.list2cmdline([os.environ.get('COMSPEC', 'cmd.exe')]) + \
            ' /d /v:off /s /c ""' + str(launcher) + '""'
    else:
        command = [str(launcher)]
    for request in host['checks']:
        _send(command, request, cm.home_path)
    print('Native host and backend checks passed:', host['name'])
    print('Active cMeta home:', cm.home_path)
    return {'return': 0, 'host': host['name']}


def _read_exact(stream, count):
    result = bytearray()
    while len(result) < count:
        chunk = stream.read(count - len(result))
        if not chunk:
            raise ValueError('Incomplete native message.')
        result.extend(chunk)
    return bytes(result)


def serve(cm, ref):
    """Preserve a private binary stdout stream before loading any plugin code."""
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    wire = os.fdopen(os.dup(sys.stdout.fileno()), 'wb', buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    try:
        host = resolve(cm, ref)
        size = struct.unpack('=I', _read_exact(sys.stdin.buffer, 4))[0]
        if size > MAX_INPUT:
            raise ValueError('Native message is too large.')
        request = json.loads(_read_exact(sys.stdin.buffer, size).decode('utf-8'))
        spec = importlib.util.spec_from_file_location('cmeta_native_host_' + host['name'], host['entry'])
        if spec is None or spec.loader is None:
            raise RuntimeError('Could not load the native host entry.')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        response = module.dispatch(request, cm=cm)
        if not isinstance(response, dict):
            raise TypeError('Native host dispatch must return a dictionary.')
    except Exception as exc:
        response = {'return': 1, 'error': str(exc)}
    packet = json.dumps(response, ensure_ascii=False).encode('utf-8')
    if len(packet) > MAX_OUTPUT:
        packet = json.dumps({'return': 1, 'error': 'The result exceeds the native messaging limit.'}).encode('utf-8')
    wire.write(struct.pack('=I', len(packet)) + packet)
    wire.flush()
    return {'return': 0}
