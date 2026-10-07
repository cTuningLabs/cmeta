"""
cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.

utils.sys.decode_output and utils.sys.run: the output of a command becomes text on any machine in any
language - UTF-8 (with or without a byte-order mark), the Windows console's own code page, the locale's
encoding, and bytes that are none of these - and a command printing such bytes never ends with the
engine's exit code -1 (a decode error inside run()).
"""

import os
import sys
import ctypes

import pytest

from cmeta.utils import sys as cm_sys


def oem_code_page():
    """The console (OEM) code page of this Windows, or None elsewhere."""
    if os.name != 'nt':
        return None
    return ctypes.windll.kernel32.GetOEMCP()


def test_none_and_str_pass_through():
    assert cm_sys.decode_output(None) is None
    assert cm_sys.decode_output('déjà') == 'déjà'
    assert cm_sys.decode_output(b'') == ''


def test_utf8_with_and_without_bom():
    assert cm_sys.decode_output(b'caf\xc3\xa9 \xe6\x97\xa5\xe6\x9c\xac \xe2\x82\xac') == 'café 日本 €'
    assert cm_sys.decode_output(b'\xef\xbb\xbfcaf\xc3\xa9') == 'café'          # the mark is dropped, not kept as
    assert cm_sys.decode_output(b'\xd0\x90\xd0\xb1\xd0\xb2') == 'Абв'           # bytes 0x90 .. are fine inside UTF-8


def test_line_endings_as_text_mode_did():
    assert cm_sys.decode_output(b'a\r\nb\rc\n') == 'a\nb\nc\n'


def test_never_raises_on_any_bytes():
    text = cm_sys.decode_output(b'\xff\xfe\x90\x8d junk \x81\x9d')
    assert isinstance(text, str) and 'junk' in text


def test_explicit_encoding_first():
    assert cm_sys.decode_output(b'\xe9t\xe9', encoding = 'cp1252') == 'été'
    assert cm_sys.decode_output(b'\xe9t\xe9', encoding = 'latin-1') == 'été'
    assert cm_sys.decode_output(b'caf\xc3\xa9', encoding = 'no-such-codec') == 'café'    # an unknown name is skipped


def test_windows_console_code_page():
    """0x90 is É and 0x82 is é in CP437 and CP850 (what cmd-line tools print on an English or French
    Windows that has not switched its system locale to UTF-8); elsewhere the bytes are replaced, never fatal."""
    text = cm_sys.decode_output(b'\x90t\x82 ok')
    if oem_code_page() in (437, 850):
        assert text == 'Été ok'
    else:
        assert text.endswith(' ok') and '�' in text


def test_as_on_a_french_windows(monkeypatch):
    """Stand in for a French Windows with the default system locale: the console prints CP850, GUI-era
    tools CP1252; UTF-8 still wins when the bytes are UTF-8, and the console page comes before ANSI."""
    monkeypatch.setattr(cm_sys, 'system_code_pages', lambda: ['cp850', 'cp1252'])
    assert cm_sys.decode_output(b'\x90t\x82 ok') == 'Été ok'                      # CP850 from cmd-line tools
    assert cm_sys.decode_output(b'caf\xc3\xa9') == 'café'                          # UTF-8 from git or Python
    assert cm_sys.decode_output(b'456 GB free') == '456 GB free'
    assert cm_sys.decode_output(b'\xe9') == 'Ú'                               # one CP1252 byte reads as CP850 first (Ú): a known limit, never an error
    assert isinstance(cm_sys.decode_output(b'\xff\xfe\x00\x81'), str)
    # one run, two tools: git prints UTF-8, a cmd-line tool prints the console's page - each line is read right
    assert cm_sys.decode_output(b'utf8: caf\xc3\xa9\r\nraw: \x90t\x82\r\n') == 'utf8: café\nraw: Été\n'


def test_mixed_output_on_a_latin1_machine(monkeypatch):
    """Latin-1 accepts every byte: decoded as a whole it would turn the UTF-8 lines into mojibake."""
    monkeypatch.setattr(cm_sys, 'system_code_pages', lambda: ['ISO8859-1'])
    assert cm_sys.decode_output(b'utf8: caf\xc3\xa9\nraw: \xe9t\xe9\n') == 'utf8: café\nraw: été\n'


def test_as_on_a_latin1_linux(monkeypatch):
    monkeypatch.setattr(cm_sys, 'system_code_pages', lambda: ['ISO8859-1'])      # as locale.getpreferredencoding names it
    assert cm_sys.decode_output(b'\xe9t\xe9 ok') == 'été ok'
    assert cm_sys.decode_output(b'caf\xc3\xa9') == 'café'


def test_as_on_a_utf8_only_machine(monkeypatch):
    monkeypatch.setattr(cm_sys, 'system_code_pages', lambda: [])
    assert cm_sys.decode_output(b'\xe9t\xe9 ok') == '�t� ok'
    assert cm_sys.decode_output(b'caf\xc3\xa9') == 'café'


def test_system_code_pages_of_this_machine():
    pages = cm_sys.system_code_pages()
    if os.name == 'nt':
        assert pages == ['oem', 'mbcs']
    else:
        assert all(isinstance(p, str) and p for p in pages)


def _script_printing_bytes(tmp_path):
    script = tmp_path / 'print_bytes.py'
    script.write_text(
        "import sys\n"
        "sys.stdout.buffer.write(b'utf8: caf\\xc3\\xa9 \\xe6\\x97\\xa5\\xe6\\x9c\\xac\\n')\n"
        "sys.stdout.buffer.write(b'raw: \\x90\\x82\\xff\\x8d\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stderr.buffer.write(b'err: \\xe9\\xff\\n')\n"
        "sys.stderr.flush()\n",
        encoding = 'utf-8')
    return f'"{sys.executable}" "{script}"'


@pytest.mark.parametrize('timeout', [None, 60])
def test_run_captures_output_in_any_encoding(tmp_path, timeout):
    """Both paths of run(): plain subprocess.run, and the timeout path (a Job Object on Windows, a process
    group elsewhere). Before, a byte the locale's codec could not decode made run() return -1."""
    r = cm_sys.run(_script_printing_bytes(tmp_path), capture_output = True, timeout = timeout)
    assert r['return'] == 0
    assert r['returncode'] == 0, r
    assert 'utf8: café 日本' in r['stdout']
    assert 'raw: ' in r['stdout'] and r['stdout'].endswith('\n')
    assert 'err: ' in r['stderr']
    assert '\r' not in r['stdout']
