"""Executable website entries preserve the existing static build behavior.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
from pathlib import Path

import pytest
import yaml

from cmeta import CMeta


@pytest.fixture
def website(tmp_path, monkeypatch):
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('CMETA_VERBOSE', 'false')
    cm = CMeta(home=str(tmp_path / 'home'))
    result = cm.access({'category': 'website', 'command': 'add', 'arg1': 'local:sample', 'con': False})
    assert result['return'] == 0

    result = cm.access({'category': 'website', 'command': 'find', 'arg1': 'local:sample', 'con': False})
    path = Path(result['artifacts'][0]['path'])
    return cm, path


def call(cm, command, **options):
    return cm.access(dict(category='website', command=command, arg1='local:sample', con=False, **options))


def test_static_build_without_description_still_works(website):
    cm, path = website
    (path / '_build.yaml').write_text('template_file: template.txt\nvars: {title: Example}\n', encoding='utf-8')
    (path / 'template.txt').write_text('<title>{{title}}</title>{{cx_body}}', encoding='utf-8')
    (path / 'index.html').write_text('Body', encoding='utf-8')
    (path / 'index.yaml').write_text('vars: {}\n', encoding='utf-8')

    assert call(cm, 'build')['return'] == 0
    assert (path / '_build.tmp/index.html').read_text(encoding='utf-8') == '<title>Example</title>Body'


def test_runner_receives_literal_arguments_and_build_action(website):
    cm, path = website
    (path / '_desc.yaml').write_text(yaml.safe_dump({'website': {'runner': 'manage.py'}}), encoding='utf-8')
    (path / 'manage.py').write_text(
        'import json, pathlib, sys\n'
        'pathlib.Path("received.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")\n', encoding='utf-8')

    arguments = ['spaces and quotes "here"', 'literal&echo', '$not_a_variable', 'a=b', '!literal!']
    assert call(cm, 'run', arg2='start', unparsed=arguments)['return'] == 0
    assert json.loads((path / 'received.json').read_text()) == ['start'] + arguments

    assert call(cm, 'build')['return'] == 0
    assert json.loads((path / 'received.json').read_text()) == ['build']


def test_runner_cannot_escape_the_artifact(website):
    cm, path = website
    (path / '_desc.yaml').write_text('website:\n  runner: ../outside.py\n', encoding='utf-8')

    result = call(cm, 'run')
    assert result['return'] == 1
    assert 'inside' in result['error']


def test_runner_failure_is_not_reported_as_success(website):
    cm, path = website
    (path / '_desc.yaml').write_text('website:\n  runner: manage.py\n', encoding='utf-8')
    (path / 'manage.py').write_text('raise SystemExit(7)\n', encoding='utf-8')

    assert call(cm, 'run')['return'] == 7


def test_declared_tasks_receive_native_flags_and_bootstrap_action(website, monkeypatch):
    cm, path = website
    (path / '_desc.yaml').write_text(yaml.safe_dump({'automation': {
        'run': {'task': 'movable-runner,1234567890abcdef', 'reference_param': 'website'},
        'bootstrap': {'task': 'movable-manager,fedcba0987654321', 'reference_param': 'definition',
                      'params': {'action': 'bootstrap'}},
    }}), encoding='utf-8')
    original = cm.access
    requests = []
    def capture(params):
        if isinstance(params.get('category'), str) and params['category'].startswith('task,'):
            requests.append(params)
            return {'return': 0}
        return original(params)
    monkeypatch.setattr(cm, 'access', capture)
    assert call(cm, 'run', current=True, params={'port': 8118})['return'] == 0
    assert requests[-1]['arg1'] == 'movable-runner,1234567890abcdef'
    assert requests[-1]['params'] == {'port': 8118} and requests[-1]['current'] is True
    assert '::sample,' in requests[-1]['website']
    assert call(cm, 'bootstrap', project_home='a project with spaces')['return'] == 0
    assert requests[-1]['action'] == 'bootstrap'
    assert requests[-1]['project_home'] == 'a project with spaces'
    assert '::sample,' in requests[-1]['definition']
