"""
cmeta.utils.sys.read_hidden: a password, a token or a key read from the console with a mask shown for every
character - Backspace, Escape / Ctrl-U, Enter, Ctrl-C, special keys - and the line read without a console.
"""

import io
import sys as stdlib_sys

import pytest

from cmeta.utils import sys as usys


def chars_of(text):
    """A getch that gives the characters of text one by one."""
    it = iter(text)
    return lambda: next(it, '')


def read(text, **kwargs):
    out = io.StringIO()
    value = usys.read_hidden('Token: ', stream = out, getch = chars_of(text), **kwargs)
    return value, out.getvalue()


def test_every_character_typed_or_pasted_shows_the_mask():
    assert read('abc\r') == ('abc', 'Token: ***\n')
    assert read('abc\n') == ('abc', 'Token: ***\n')
    assert read('hf_a-very-long-token-pasted-at-once\r')[0] == 'hf_a-very-long-token-pasted-at-once'
    assert read('\r') == ('', 'Token: \n')


def test_backspace_takes_the_last_character_away():
    value, shown = read('ab\x7fc\x08\x08\x08d\r')
    assert value == 'd'
    assert shown == 'Token: **\b \b*\b \b\b \b*\n'       # a third Backspace on nothing shows nothing


def test_escape_or_ctrl_u_takes_everything_away_to_start_again():
    assert read('abc\x1bxy\r') == ('xy', 'Token: ***' + '\b \b' * 3 + '**\n')
    assert read('abc\x15x\r')[0] == 'x'
    assert read('\x1bz\r') == ('z', 'Token: *\n')


def test_ctrl_c_stops_and_the_end_of_the_input_is_an_error():
    with pytest.raises(KeyboardInterrupt):
        read('ab\x03')
    with pytest.raises(EOFError):
        read('ab')                                        # the characters end before Enter
    with pytest.raises(EOFError):
        read('\x04')                                      # Ctrl-D on an empty input
    assert read('ab\x04c\r')[0] == 'abc'                  # Ctrl-D with characters: dropped like any control key


def test_special_keys_and_control_characters_are_dropped_and_the_mask_can_be_wider_or_none():
    assert read('a\x00b\tc\r') == ('abc', 'Token: ***\n')
    assert read('ab\x7f\r', mask = '**') == ('a', 'Token: ****' + '\b \b' * 2 + '\n')
    assert read('abc\r', mask = '') == ('abc', 'Token: \n')


def test_without_a_console_the_line_is_read_and_nothing_shown(monkeypatch):
    monkeypatch.setattr(stdlib_sys, 'stdin', io.StringIO('secret value\nnext line\n'))
    out = io.StringIO()
    assert usys.read_hidden('P: ', stream = out) == 'secret value'
    assert out.getvalue() == 'P: \n'
    monkeypatch.setattr(stdlib_sys, 'stdin', io.StringIO(''))
    with pytest.raises(EOFError):
        usys.read_hidden('P: ', stream = io.StringIO())
