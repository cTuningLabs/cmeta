"""
The date an alias starts with (cmeta.utils.names.date_in_alias, 2026-11-05): the one rule behind -dt (nothing is
put in front of an alias that has its date), the warning of a dated category, the dated order of /browse and the
date window of cx utils find_by_cid. A day, a month, a year, a day with a time, dashes or not, the unknown part
written with x, a range by its first date; digits that make no date are none.
"""

import pytest

from cmeta.utils.names import date_in_alias


@pytest.mark.parametrize('alias,text,ymd', [
    ('20261105.a note',               '20261105',        (2026, 11, 5)),
    ('20261105',                      '20261105',        (2026, 11, 5)),
    ('2026-11-05 notes',              '2026-11-05',      (2026, 11, 5)),
    ('20261105-1430.meeting',         '20261105-1430',   (2026, 11, 5)),
    ('20261105-143000.session',       '20261105-143000', (2026, 11, 5)),
    ('20261105_1430_meeting',         '20261105_1430',   (2026, 11, 5)),
    ('202611.this month',             '202611',          (2026, 11, 1)),
    ('2026.plans',                    '2026',            (2026, 1, 1)),
    ('2026 plans',                    '2026',            (2026, 1, 1)),
    ('2026_plans',                    '2026',            (2026, 1, 1)),
    ('20250814 - cTuning Labs',       '20250814',        (2025, 8, 14)),

    # the unknown part written with x: the start of what is known
    ('2026xxxx.some time this year',  '2026xxxx',        (2026, 1, 1)),
    ('202604xx.prepare the tax',      '202604xx',        (2026, 4, 1)),
    ('198xxxxx.very young',           '198xxxxx',        (1980, 1, 1)),
    ('20xxxxxx.this century',         '20xxxxxx',        (2000, 1, 1)),
    ('2017XXXX.capital x',            '2017XXXX',        (2017, 1, 1)),
    ('202604xx',                      '202604xx',        (2026, 4, 1)),

    # a range starts with its first date
    ('2020-2022.photos',              '2020',            (2020, 1, 1)),
    ('202601-202603.quarter',         '202601',          (2026, 1, 1)),
    ('20260101-20260131.january',     '20260101',        (2026, 1, 1)),
])
def test_the_date_an_alias_starts_with(alias, text, ymd):
    found = date_in_alias(alias)
    assert found is not None, alias
    assert found['text'] == text
    assert (found['date'].year, found['date'].month, found['date'].day) == ymd


@pytest.mark.parametrize('alias', [
    'a note', '', None,
    'improve the dashboard 2026',   # a date, but not in front
    '2026x', '2026beta.x',          # neither a separator after the year nor x placeholders
    '20261301.no such month', '20261132.no such day', '202613xx.no such month',
    '0000.no such year',
    '12345678.not a date',
    '20261105abcdef01',             # a UID-like text
    '2026110x.a digit short',       # the x forms: 2, 3, 4 or 6 digits, then x to eight characters
    '2026xxxxx.one x too many',
])
def test_an_alias_that_starts_with_no_date(alias):
    assert date_in_alias(alias) is None
