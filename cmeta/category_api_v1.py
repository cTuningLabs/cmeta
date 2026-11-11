"""
CMeta base category class

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import logging
import os
import re
import shutil
import copy
from pathlib import Path

from . import utils
from .category import InitCategory
from .utils.common import _error


def _parse_generator(value):
    """
        Read the value of the generator environment variable.

        JSON gives an object ({"method": "task", "task": "<alias>,<UID>", ...});
        a single word is read as {"method": <word>}; any other text as {"note": <text>}.

        Returns:
            dict | None: The generator record, or None for an empty value.
    """

    import json

    value = (value or '').strip()
    if value == '':
        return None

    try:
        parsed = json.loads(value)
    except ValueError:
        parsed = None

    if isinstance(parsed, dict):
        return parsed

    if ' ' not in value and ';' not in value:
        return {'method': value}

    return {'note': value}


def apply_artifact_defaults(
    cmeta: dict,  # Artifact meta, changed in place.
    repo_meta: dict = None,  # Meta of the target repository (its _cmr.yaml).
    env: dict = None,  # Environment (os.environ when None).
    cfg: dict = None,  # cMeta configuration with the environment variable names.
    creating: bool = True,  # True when the artifact is created, False when it is updated.
    today: str = None,  # Date for "last_generator" (YYYY-MM-DD, today in UTC when None).
):
    """
        Stamp who made an artifact and how: authors, copyright and generator.

        When an artifact is created, keys already in its meta are kept, and missing ones are filled:
          - authors: CMETA_AUTHORS, else artifact_defaults.authors of the repository
            (the person at work comes before the repository default);
          - copyright: artifact_defaults.copyright of the repository, else CMETA_COPYRIGHT
            (the repository decides who holds the copyright);
          - generator: CMETA_GENERATOR (set by the task or agent that is running), else
            artifact_defaults.generator of the repository; "by" defaults to the authors.

        When an artifact is updated and CMETA_GENERATOR is set, "last_generator" records it
        with the date, so a regeneration stays visible next to how the artifact was created.

        Returns:
            dict: The same cmeta.
    """

    env = os.environ if env is None else env
    cfg = cfg or {}

    var_authors = cfg.get('env_var_cmeta_authors', 'CMETA_AUTHORS')
    var_copyright = cfg.get('env_var_cmeta_copyright', 'CMETA_COPYRIGHT')
    var_generator = cfg.get('env_var_cmeta_generator', 'CMETA_GENERATOR')

    defaults = (repo_meta or {}).get('artifact_defaults')
    if not isinstance(defaults, dict):
        defaults = {}

    generator = _parse_generator(env.get(var_generator, ''))

    if not creating:
        if generator is not None:
            if 'by' not in generator and cmeta.get('authors'):
                generator['by'] = cmeta['authors']
            if 'date' not in generator:
                from datetime import datetime, timezone
                generator['date'] = today or datetime.now(timezone.utc).date().isoformat()
            cmeta['last_generator'] = generator
        return cmeta

    if 'authors' not in cmeta:
        if env.get(var_authors, '') != '':
            cmeta['authors'] = env[var_authors]
        elif defaults.get('authors'):
            cmeta['authors'] = copy.deepcopy(defaults['authors'])

    if 'copyright' not in cmeta:
        if defaults.get('copyright'):
            cmeta['copyright'] = copy.deepcopy(defaults['copyright'])
        elif env.get(var_copyright, '') != '':
            cmeta['copyright'] = env[var_copyright]

    if 'generator' not in cmeta:
        if generator is None and isinstance(defaults.get('generator'), dict):
            generator = copy.deepcopy(defaults['generator'])
        if generator is not None:
            if 'by' not in generator and cmeta.get('authors'):
                generator['by'] = cmeta['authors']
            cmeta['generator'] = generator

    return cmeta


###################################################################################################
# The AI context of an artifact: its `ai_uses` list in the sidecar _desc.yaml (what run-ai reads), chosen
# among the artifacts that declare themselves a template for that purpose in their own meta:
#
#   template:
#     ai_uses:
#       alias: fgg                              # the short name typed after -ai
#       title: FGG personal projects context
#       sort: 1000
#
# `cx <category> add <artifact> -ai` lists them (sorted by sort, then title) and asks which; `-ai=cmeta,fgg`
# takes them by that alias without a question, else by an artifact alias in any category, else as cat::alias
# - several artifacts for one name is an error that names them. What is written is the full cRef
# (<category alias>,<UID>::<alias>,<UID>), as run-ai reads it, so the context survives renames and machines.
# The same on `update` (appended, no duplicates). A generic `desc` dict is merged into _desc.yaml the same way
# (--desc.<key>=<value>, or several keys in a whole @file.yaml argument holding desc:); a _desc.json found there
# is converted to YAML, never both.
# The declaration lives in the meta because the index keeps every meta: the list is one query, no file walk.
#
# The connections of an artifact (2026-11-03): `--connect=<names>` on add / update writes the full cRef of each
# artifact named into this artifact's `connections` and this artifact's cRef into theirs (the graph draws an
# edge declared on either side, so both say it); `--connect-to=<names>` (`--ct`) writes this side only. A name
# with "-" in front removes (`--connect=-<name>` from both sides, `--ct=-<name>` and `-ai=-<name>` from this
# one); a name no artifact has any more is removed by what the entries say. Entries are compared by the
# artifact's UID, so an entry written before a rename is neither duplicated nor left behind; an entry written by
# hand without one (cat::alias) by the parts it gives.
DESC_FILENAME_BASE = '_desc'
TEMPLATE_KEY = 'template'
AI_USES_KEY = 'ai_uses'
CONNECTIONS_KEY = 'connections'


def _cref_of(parts):
    """The full cRef of an indexed artifact from its cmeta_ref_parts: <category alias>,<UID>::<alias>,<UID>."""
    parts = parts or {}
    cat = parts.get('category_alias') or ''
    if parts.get('category_uid'):
        cat = f"{cat},{parts['category_uid']}" if cat else parts['category_uid']
    art = parts.get('artifact_alias') or ''
    if parts.get('artifact_uid'):
        art = f"{art},{parts['artifact_uid']}" if art else parts['artifact_uid']
    return f'{cat}::{art}'


def template_entries(artifacts, purpose = AI_USES_KEY):
    """
        The template declarations for a purpose among found artifacts.
        Args:
            artifacts (list): Artifacts as the find commands return them (with cmeta and cmeta_ref_parts).
            purpose (str): The key under `template` (ai_uses).
        Returns:
            list: [{'alias', 'title', 'sort', 'cref', 'path'}], sorted by sort, then title, then cref.
    """
    out = []
    for a in artifacts or []:
        cmeta = a.get('cmeta') if isinstance(a, dict) else None
        decl = (cmeta or {}).get(TEMPLATE_KEY)
        decl = decl.get(purpose) if isinstance(decl, dict) else None
        if not isinstance(decl, dict):
            continue
        try:
            sort = float(decl.get('sort', 0) or 0)
        except (TypeError, ValueError):
            sort = 0.0
        out.append({'alias': str(decl.get('alias') or '').strip(), 'title': str(decl.get('title') or '').strip(),
                    'sort': sort, 'cref': _cref_of(a.get('cmeta_ref_parts')), 'path': a.get('path')})
    out.sort(key = lambda e: (e['sort'], e['title'].lower(), e['cref']))
    return out


def split_context_names(text):
    """
        The names of an ai_uses request: aliases separated by commas (cmeta,fgg); a cRef keeps its commas
        (fgg.project,<UID>::cMeta,<UID>), so a list that holds cRefs is separated by ";" instead, as run-ai's
        --context is. A list already split is returned as it is.
    """
    if isinstance(text, (list, tuple)):
        return [str(n).strip() for n in text if str(n).strip()]
    text = str(text or '')
    parts = [p.strip() for p in text.split(';')] if ';' in text else [text.strip()]
    out = []
    for p in parts:
        if '::' in p:
            out.append(p)
        else:
            out += [x.strip() for x in p.split(',') if x.strip()]
    return [o for o in out if o]


def find_all(cm, cid, match = None):
    """
        Every indexed artifact of every category that a CID with wildcards names ("*::*": all; "*::name": an
        alias anywhere): the index search of utils find_by_cid - every record keeps the artifact's meta, so no
        file is read. Returns {'return', 'artifacts': [...]}, an empty list when nothing matches.
    """
    ii = {'category': 'utils', 'command': 'find_by_cid', 'arg1': cid, 'con': False}
    if match:
        ii['match'] = match
    r = cm.access(ii)
    if r['return'] == 16:            # nothing found: an empty list, not an error
        return {'return':0, 'artifacts':[]}
    if r['return']>0: return r
    return {'return':0, 'artifacts': r.get('artifacts') or []}


def ai_context_entries(cm, purpose = AI_USES_KEY):
    """The declared templates for a purpose, sorted (template_entries), from one index query."""
    r = find_all(cm, '*::*')
    if r['return']>0: return r
    return {'return':0, 'entries': template_entries(r['artifacts'], purpose)}


def resolve_artifacts(cm, names, entries = None, missing_ok = False):
    """
        The artifacts the names name (split_context_names): a template's alias first when `entries` (the declared
        templates of a purpose) are given, then an artifact alias in any category, then a cRef (cat::alias or
        cat,UID::alias,UID); more than one artifact for a name is an error that names them all, so the person
        picks one by its cRef. A name nothing matches is an error, or, with `missing_ok` (a name to remove: its
        artifact may be gone), comes back without a cRef.
        Returns {'return', 'artifacts': [{'name', 'cref', 'path'}]}.
    """
    out = []
    for name in split_context_names(names) or []:
        if '::' in name:
            r = find_all(cm, name)
            if r['return']>0: return r
            found = r['artifacts']
            what = f'the cRef "{name}"'
        else:
            hits = [e for e in entries or [] if e['alias'] == name]
            if len(hits) == 1:
                out.append({'name': name, 'cref': hits[0]['cref'], 'path': hits[0].get('path')})
                continue
            if len(hits) > 1:
                return {'return':1, 'error': f'the AI context "{name}" is declared by several artifacts: ' +
                        ', '.join(e['cref'] for e in hits) + ' - name one of them by its cRef'}
            r = find_all(cm, '*::' + name)
            if r['return']>0: return r
            found = r['artifacts']
            what = f'the name "{name}"'
        if len(found) == 0:
            if missing_ok:
                out.append({'name': name, 'cref': None, 'path': None})
                continue
            why = 'no AI context template with that alias, no artifact with that alias in any category' if entries is not None \
                  else 'no artifact with that alias in any category'
            return {'return':1, 'error': f'no artifact for {what} ({why})'}
        if len(found) > 1:
            return {'return':1, 'error': f'{what} matches several artifacts: ' +
                    ', '.join(_cref_of(a.get('cmeta_ref_parts')) for a in found) + ' - name one of them by its cRef'}
        out.append({'name': name, 'cref': _cref_of(found[0].get('cmeta_ref_parts')), 'path': found[0].get('path')})
    return {'return':0, 'artifacts':out}


def resolve_ai_context(cm, names, entries):
    """
        The full cRefs of the names (split_context_names): a template's alias first, then an artifact alias in
        any category, then a cRef (cat::alias or cat,UID::alias,UID); more than one artifact for a name is an
        error that names them all, so the person picks one by its cRef. Returns {'return', 'crefs': [...]}.
    """
    r = resolve_artifacts(cm, names, entries or [])
    if r['return']>0: return r
    return {'return':0, 'crefs': [a['cref'] for a in r['artifacts']]}


def _cref_key(value):
    """The cRef string of an ai_uses entry (a string, or {cref, note}) for comparisons."""
    if isinstance(value, dict):
        value = value.get('cref')
    return str(value or '').strip()


def _cref_split(value):
    """
        The four parts of a cRef, an entry or a name: (category alias, category UID, artifact alias, artifact UID),
        '' where it has none - "cat,UID::alias,UID", "cat::alias", "alias", a bare UID.
    """
    text = _cref_key(value)
    cat, art = text.split('::', 1) if '::' in text else ('', text)

    def two(part):
        part = part.strip()
        if ',' in part:
            alias, uid = part.rsplit(',', 1)
            if utils.names.is_valid_cmeta_uid(uid.strip()):
                return alias.strip(), uid.strip()
        if utils.names.is_valid_cmeta_uid(part):
            return '', part
        return part, ''

    return two(cat) + two(art)


def cref_matches(entry, name):
    """
        Whether an entry of ai_uses or connections (a cRef string, or {cref, note}) is the artifact a name names:
        by the artifact's UID when both carry one (an entry written before a rename keeps the old alias), else
        by every part the side without the artifact's UID gives - the name (a cRef, cat::alias, an alias, a UID:
        an artifact that is gone), or the entry (written by hand as cat::alias, against the full cRef a name was
        resolved to, 2026-11-09: it was neither removed nor kept from a duplicate); aliases without case.
    """
    ec, ecu, ea, eau = _cref_split(entry)
    nc, ncu, na, nau = _cref_split(name)
    if eau and nau:
        return eau == nau and not (ecu and ncu and ecu != ncu)
    (gc, gcu, ga, gau), (oc, ocu, oa, oau) = ((ec, ecu, ea, eau), (nc, ncu, na, nau)) if nau else \
                                             ((nc, ncu, na, nau), (ec, ecu, ea, eau))
    given = [(g, o, True) for g, o in ((gc, oc), (ga, oa)) if g] + [(g, o, False) for g, o in ((gcu, ocu), (gau, oau)) if g]
    if not given:
        return False
    return all((g.lower() == o.lower()) if fold else (g == o) for g, o, fold in given)


def split_changes(names):
    """
        A request of --connect, --connect-to (--ct) or -ai split into the names to add and the names to remove: a
        name with "-" in front is removed; the rest is split as split_context_names splits it (aliases by commas,
        cRefs by ";"), and a {{{cRef}}} (a path after it too) is the cRef. Returns (add, remove).
    """
    add, remove = [], []
    for name in split_context_names(names):
        drop = name.startswith('-')
        if drop:
            name = name[1:].strip()
        if name.startswith('{{{') and '}}}' in name:
            name = name[3:name.index('}}}')].strip()
        if name:
            (remove if drop else add).append(name)
    return add, remove


def _lists_kept(data, desc, top = True):
    """
        `desc` with a single value made a one-item list where `data` holds a list (dicts followed) and for
        ai_uses and connections, which are lists even when new, so that the merge appends it:
        --desc.connections=<cRef> put one string in the place of the whole list (2026-11-03).
    """
    if not isinstance(desc, dict) or not isinstance(data, dict):
        return desc
    out = {}
    for k, v in desc.items():
        old = data.get(k)
        single = v is not None and not isinstance(v, (list, dict))
        if single and (isinstance(old, list) or (top and k in (AI_USES_KEY, CONNECTIONS_KEY))):
            out[k] = [v]
        elif isinstance(old, dict) and isinstance(v, dict):
            out[k] = _lists_kept(old, v, False)
        else:
            out[k] = v
    return out


def merge_desc(data, desc = None, crefs = None, lists = None):
    """
        A _desc dict with `desc` merged in (dicts deep, lists appended without duplicates; a single value given
        for a list is appended to it, never put in its place), `crefs` appended to its ai_uses list, and the
        `lists` changes made - {key: (entries to append, names to remove)}: a name removes every entry of its
        artifact, an entry whose artifact is there already is not appended again (cref_matches: an entry kept as
        a string or {cref, note} stays as it is), and a list left empty goes with its key.
        Returns (the new dict, changed).
    """
    data = copy.deepcopy(data) if isinstance(data, dict) else {}
    before = copy.deepcopy(data)
    if isinstance(desc, dict) and desc:
        data = utils.common.deep_merge(data, _lists_kept(data, copy.deepcopy(desc)), append_lists = True)
    changes = dict(lists or {})
    if crefs:
        add, drop = changes.get(AI_USES_KEY) or ((), ())
        changes[AI_USES_KEY] = (list(add) + list(crefs), drop)
    for key, (add, drop) in changes.items():
        if not add and not drop:
            continue
        value = data.get(key)
        old = list(value) if isinstance(value, list) else ([value] if value else [])
        items = [i for i in old if not any(cref_matches(i, d) for d in drop or [])]
        for a in add or []:
            if _cref_key(a) and not any(cref_matches(i, a) for i in items):
                items.append(a)
        if items == old and (value is None or isinstance(value, list)):
            continue                    # nothing to do (a single value is still made a list)
        if items:
            data[key] = items
        else:
            data.pop(key, None)
    return data, data != before


def edit_list_text(text, key, add = (), drop = None):
    """
        The text of a _desc.yaml with `add` appended as items of its top-level `key` list and the items for which
        `drop` (a function of an item's value) is true removed, everything else - the comments, the order, the
        quoting of a file written by hand - kept as it is: new items go after the last item of the block (or its
        continuation lines) at the block's indentation, a file without the key gets the block at its end, a
        removed item takes its own lines (its continuation lines, a comment on its line), and a list left empty
        takes its key and its block. Returns the new text, or None when the key holds an inline value
        ("key: [a, b]", a scalar) or an item cannot be read: then the caller rewrites the key as YAML.
    """
    import yaml
    lines = text.splitlines(True)
    head = None
    for i, line in enumerate(lines):
        bare = line.rstrip('\r\n')
        if re.match(re.escape(key) + r'\s*:\s*(#.*)?$', bare):
            head = i
            break
        if re.match(re.escape(key) + r'\s*:', bare):
            return None
    nl = '\r\n' if '\r\n' in text else '\n'              # new lines end as the file's lines end
    added = ''.join(yaml.safe_dump([a], default_flow_style = False, allow_unicode = True, width = 10000) for a in add or [])
    if head is None:
        if not added:
            return text
        new = text
        if new and not new.endswith('\n'):
            new += nl
        if new and not new.endswith('\n' + nl):
            new += nl
        return new + key + ':' + nl + ''.join('  ' + l + nl for l in added.splitlines())   # lists indented, as the engine writes them

    # the block: its items (a "- " line at the block's indentation and the lines indented deeper after it), with
    # the comments and blank lines between them
    indent = None
    items = []
    j = head + 1
    while j < len(lines):
        bare = lines[j].rstrip('\r\n')
        stripped = bare.strip()
        if stripped == '' or stripped.startswith('#'):
            j += 1
            continue
        lead = len(bare) - len(bare.lstrip(' '))
        dash = stripped == '-' or stripped.startswith('- ')
        if indent is None:
            if not dash:
                break
            indent = lead
        if lead == indent and dash:
            items.append([j, j + 1])
        elif lead > indent and items:
            items[-1][1] = j + 1
        else:
            break
        j += 1
    end = items[-1][1] if items else head + 1

    # the value of each item, read on its own lines
    gone = set()
    for n, (s, e) in enumerate(items):
        chunk = ''.join(l[indent:] if l[:indent].strip() == '' else l for l in lines[s:e])
        try:
            value = yaml.safe_load(chunk)
        except yaml.YAMLError:
            return None
        if not isinstance(value, list) or len(value) != 1:
            return None
        if drop and drop(value[0]):
            gone.add(n)
    if not gone and not added:
        return text

    kept = [it for n, it in enumerate(items) if n not in gone]
    if not kept and not added:
        # the list is empty now: its key goes with the block, the lines after the block stay - without two blank
        # lines in a row where it was, or a blank line at the top of the file
        before, rest = lines[:head], lines[end:]
        while before and rest and before[-1].strip() == '' and rest[0].strip() == '':
            rest = rest[1:]
        out = before + rest
        while out and out[0].strip() == '':
            out = out[1:]
        return ''.join(out)
    removed = {k for n in gone for k in range(items[n][0], items[n][1])}
    after = kept[-1][1] if kept else head + 1            # the new items go after the last item kept
    pad = ' ' * (indent if indent is not None else 0)
    out = [l for k, l in enumerate(lines[:after]) if k not in removed]
    if out and not out[-1].endswith('\n'):
        out[-1] += nl
    out += [pad + l + nl for l in added.splitlines()]
    out += [l for k, l in enumerate(lines[after:], after) if k not in removed]
    return ''.join(out)


def append_ai_uses_text(text, crefs):
    """
        The text of a _desc.yaml with `crefs` appended as items of its top-level ai_uses list, everything
        else kept as it is (edit_list_text). Returns the new text, or None when the key holds an inline value.
    """
    return edit_list_text(text, AI_USES_KEY, crefs)


class Category(InitCategory):
    """
    Standard Base Category with artifact management functions
    """

    def __init__(
        self,
        *args,  # CLI positional arguments passed to the entry point.
        **kwargs,  # Keyword arguments forwarded to the base initializer.
    ):
        """
            Initialize the standard base category implementation.

            Args:
                *args: CLI positional arguments passed to the entry point.
                **kwargs: Keyword arguments forwarded to the base initializer.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        super().__init__(*args, module_file_path = __file__, **kwargs)

    ############################################################
    def test(
        self,
        params: dict,  # Parameters dictionary.
    ):
        """
            Test category.

            Args:
                params (dict): Parameters dictionary.
            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def info_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        clip: bool = True,  # If True, copy the reference to the clipboard.
        url: bool = False,  # If True, copy URL with detected cRef to the clipboard.
        name: bool = False,  # If True, copy artifact name to the clipboard
        cref: bool = False,  # If True, the old form cRef=<category>,<UID>::<alias>,<UID> instead of {{{<category>::<alias>,<UID>}}}.
        plain: bool = False,  # If True, the reference without the braces: <category>::<alias>,<UID> (what a field of a page takes).
        qplain: bool = False,  # If True, the plain reference in double quotes: "<category>::<alias>,<UID>" (pasted into a command line as one word).
    ):
        """
            Get artifact info. The reference printed and copied is {{{<category>::<alias>,<UID>}}} - how memories,
            records and docs name an artifact (the browse and cref pages make it a link, smart_find_by_cid reads it);
            --plain gives it without the braces (<category>::<alias>,<UID>: what the search of /browse, a picker of a
            page or cx <category> find takes), --qplain the same in double quotes (one word of a command line, a name
            with spaces too), --cref the full cRef=... that info printed up to cMeta 0.38.9.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                clip (bool): If True, copy the reference to the clipboard.
                url (bool): If True, copy URL with detected cRef to the clipboard.
                name (bool): If True, copy artifact name to the clipboard
                cref (bool): If True, print and copy cRef=<full cRef> (the form up to 0.38.9).
                plain (bool): If True, print and copy <category>::<alias>,<UID> - the reference without the braces.
                qplain (bool): If True, the plain reference in double quotes - one word of a command line, whatever the name holds.
            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): List of matched artifacts.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx['control'].get('con', False)
        verbose = ctx['control'].get('verbose', False)

        ctx['control']['con'] = False

        result = self.find_(ctx, arg1)
        if result['return']>0: return result

        artifacts = result['artifacts']

        for artifact in artifacts:
            if con:
                if len(artifacts)>1:
                    print('='*80)

                print ('Artifact path: ' + artifact['path'])

            cmeta_ref_parts = artifact['cmeta_ref_parts']

            r = utils.names.restore_cmeta_ref(cmeta_ref_parts)
            if r['return']>0: return r

            ref = r['ref']

            # The reference printed and copied: {{{<category>::<alias>,<UID>}}}, with --plain the same without the
            # braces (2026-11-10, the user: "copy/paste only cRef without {{{}}}"), or with --cref the full cRef=...
            if cref:
                cref_text = f'cRef={ref}'
            else:
                r = utils.names.restore_cmeta_name(cmeta_ref_parts, key='artifact', fail_on_error = self.fail_on_error)
                if r['return']>0: return r

                category = cmeta_ref_parts.get('category_alias') or cmeta_ref_parts.get('category_uid', '')
                cref_text = f"{category}::{r['name']}" if plain else f'"{category}::{r["name"]}"' if qplain else '{{{' + f"{category}::{r['name']}" + '}}}'

            if con:
                print ('')
                print (cref_text)

                print ('')
                for k in sorted(cmeta_ref_parts):
                    print (k + ': ' + cmeta_ref_parts[k])

            if url:
                import urllib.parse
                url = os.environ.get(self.cm.cfg['env_var_cmeta_server_info_url'], '')
                if url == '':
                    r = self.cm.access({'category': 'config,cc6bfe174be847ed', 'command': 'get', 'arg1': 'default'})
                    if r['return'] > 0: return r

                    cfg = r['config_cmeta']
                    url = cfg.get('url_cserver_info', '')

                if url == '':
                    url = self.cm.cfg['url_cserver_info']
                
                clipboard_text = url + urllib.parse.quote(ref, safe="")

                if con:
                    print ('')
                    print (f'cRef URL: {clipboard_text}')
                     
            elif name:
                r = utils.names.restore_cmeta_name(cmeta_ref_parts, key='artifact', fail_on_error = self.fail_on_error)
                if r['return']>0: return r

                clipboard_text = r['name']

            elif clip:
                clipboard_text = cref_text

            if clip:
                r = self.cm.utils.common.copy_text_to_clipboard(clipboard_text, do_not_fail = not verbose)
                if r['return']>0: return r

        return result


    ############################################################
    def find_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Comma-separated string or iterable of tags to match.
        sort: bool = None,  # Sort by path (True by default).
        add_index_file: bool = False,  # Add index file information.
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        match: dict = None,  # Value for match.
        match_empty_version: bool = False,  # Value for match empty version.
        match_empty_values: bool = False,  # Match when queried values or keys are empty.
        all_tags: str = None,  # Value for all tags.
        load_files = [],  # Load files (omit extension to load either yaml or json)
        follow_migrated: bool = True,  # Follow an old alias left by "migrate" to its artifact.
    ):
        """
            Find artifacts.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Comma-separated string or iterable of tags to match.
                sort (bool): Sort by path (True by default).
                add_index_file (bool): Add index file information.
                skip_uids (bool): Skip UIDs when using wildcards.
                match (dict): Value for match.
                match_empty_version (bool): Value for match empty version.
                match_empty_values (bool): Match artifacts whose queried values or keys are empty.
                all_tags (str): Value for all tags.
                load_files (list): Metadata file basenames to load from each matched artifact.
                follow_migrated (bool): An alias given alone that is a migration stub (left by
                    `migrate`) stands for the artifact it points to, with a notice; False returns
                    the stub itself. A UID always finds exactly what it names.
            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): List of matched artifacts.

            Raises:
                Exception: Propagated runtime errors, if any.                           \
        """

        con = ctx['control'].get('con', False)

        # From the command line the value is a string (--follow_migrated=no)
        if isinstance(follow_migrated, str):
            follow_migrated = follow_migrated.strip().lower() not in ('0', 'off', 'false', 'no', '')

        artifact_ref_parts = {}

        if arg1 is not None:
            r = utils.names.parse_cmeta_obj(arg1, key="artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            artifact_ref_parts.update(r['obj_parts'])

        category_cmeta_ref_parts = ctx['category_artifact']['cmeta_ref_parts']
        category_cmeta = ctx['category_artifact']['cmeta']

        artifact_ref_parts['category_alias'] = category_cmeta_ref_parts['artifact_alias']
        artifact_ref_parts['category_uid'] = category_cmeta_ref_parts['artifact_uid']

        if self.cm.debug:
            self.logger.debug(f"  self.cm.repos.find({artifact_ref_parts})")

        r = self.cm.repos.find(
              artifact_ref_parts, 
              add_index_file = add_index_file, 
              tags = tags,
              skip_uids = skip_uids, 
              match = match, 
              match_empty_version = match_empty_version, 
              match_empty_values = match_empty_values, 
              all_tags = all_tags,
              follow_migrated = follow_migrated,
           )
        if r['return']>0: return r

        artifacts = r['artifacts']

        if len(load_files) > 0:
            artifacts = artifacts.copy()

            for artifact in artifacts:
                path = artifact['path']

                r = utils.files.load_files(path, load_files, self.fail_on_error)
                if r['return']>0: return r

                artifact['loaded_files'] = r['loaded_files']

            r['artifacts'] = artifacts

        if sort is None:
            sort = category_cmeta.get('find_sort', False)

        if sort:
            r['artifacts'].sort(key=lambda x: x['cmeta_ref_parts'].get('artifact_alias_lower', 
                                              x['cmeta_ref_parts'].get('artifact_alias', 
                                              x['cmeta_ref_parts'].get('artifact_uid', ''))).lower())

        if con:
            for a in r['artifacts']:
                print (a['path'])

        return r

    ############################################################
    def tags_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Comma-separated string or iterable of tags to match.
        sort: bool = False,  # Value for sort.
    ):
        """
            Find unique tags in artifacts.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Comma-separated string or iterable of tags to match.
                sort (bool): Value for sort.
            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): List of matched artifacts.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx['control'].get('con', False)

        artifact_ref_parts = {}

        if arg1 is not None:
            r = utils.names.parse_cmeta_obj(arg1, key="artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            artifact_ref_parts.update(r['obj_parts'])

        category_cmeta_ref_parts = ctx['category_artifact']['cmeta_ref_parts']
        category_cmeta = ctx['category_artifact']['cmeta']

        artifact_ref_parts['category_alias'] = category_cmeta_ref_parts['artifact_alias']
        artifact_ref_parts['category_uid'] = category_cmeta_ref_parts['artifact_uid']

        if self.cm.debug:
            self.logger.debug(f"  self.cm.repos.tags({artifact_ref_parts})")

        r = self.cm.repos.find(artifact_ref_parts, tags = tags, follow_migrated = False)
        if r['return']>0: return r

        artifacts = r['artifacts']

        unique_tags = {}

        for artifact in artifacts:
            xtags = artifact['cmeta'].get('tags',[])

            for xtag in xtags:
                xtag = xtag.strip()
                if xtag not in unique_tags:
                    unique_tags[xtag] = 0
                unique_tags[xtag] += 1

        if con:
            if sort:
                for utag in sorted(unique_tags):
                    freq = unique_tags[utag]
                    x = f'{utag} ({freq})'
                    print (x)

            else:
                for k, v in sorted(unique_tags.items(), key=lambda item: item[1], reverse=True):
                    print(f"{k} ({v})")

        return {'return':0, 'tags': unique_tags}

    ############################################################
    def update_(
        self,
        ctx: dict,  # Execution context dictionary with category, command, and control data.
        arg1: str = None,  # First positional argument from command input.
        tags: str = None,  # Value for tags.
        sort: bool = True,  # Value for sort.
        skip_uids: bool = False,  # If True, skip UID validation in wildcard lookups.
        meta: dict = {},  # Metadata dictionary to persist.
        new_tags: str = None,  # Value for new tags.
        replace_lists: bool = False,  # Value for replace lists.
        replace: bool = False,  # Value for replace.
        ignore_errors: bool = False,  # Value for ignore errors.
        create: bool = False,  # Value for create.
        create_params: dict = {},  # Value for create params.
        update_category: bool = False,  # Value for update category.
        match: dict = None,  # Value for match.
        match_empty_version: bool = False,  # Value for match empty version.
        all_tags: str = None,  # Value for all tags.
        desc: dict = None,  # Keys merged into the artifact's _desc.yaml (--desc.<key>=<value>, or a whole @file.yaml holding desc:).
        ai_uses = None,  # AI context to add: template aliases, artifact aliases or cRefs ("-name" removes); True = ask.
        ai = None,  # The short form of ai_uses (-ai, -ai=cmeta,fgg, -ai=-fgg).
        connect = None,  # Connect both ways: names or cRefs (";" between cRefs, "-name" disconnects); True = ask.
        connect_to = None,  # Connect this artifact to them (its own _desc only): the same forms.
        ct = None,  # The short form of connect_to (--ct=<cRef>).
    ):
        """
            Update artifact(s).

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): cMeta artifact(s) with wildcards.
                tags (str | list | None): Prune artifacts by tags.
                sort (bool): Sort artifacts by alias and UID when updating in batch.
                skip_uids (bool): Skip UIDs when using wildcards.
                meta (dict): Meta dictionary to merge recursively with existing artifact.
                new_tags (str | list | None): Add more tags.
                replace_lists (bool): Replace lists during merging.
                replace (bool): Replace existing meta dictionary entirely.
                ignore_errors (bool): Ignore errors when updating multiple artifacts.
                create (bool): If artifact doesn't exist attempt to create.
                create_params (dict): Pass params to create function.
                update_category (bool): Allow category update in meta.
                match (dict | None): Match artifact metadata before updating.
                match_empty_version (bool): Match artifacts with an empty version value.
                all_tags (str | None): Require all supplied tags when selecting artifacts.
                desc (dict | None): Keys merged into the artifact's _desc.yaml.
                ai_uses, ai: The AI context to add (template aliases, artifact aliases, cRefs; "-name" removes);
                    True asks.
                connect: Artifacts to connect both ways - their cRefs go into this artifact's `connections`
                    and its cRef into theirs ("-name" removes both); True asks.
                connect_to, ct: Artifacts to connect this one to, in its own _desc.yaml only ("-name" removes).

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): All matched artifacts.
                    - **updated_artifacts** (list): Updated artifacts.
                    - **desc_changes** (list): What the _desc.yaml changes added (+) and removed (-), as lines.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # meta and desc take keys: anything else is refused before an artifact is found, made or changed
        meta, r = utils.cli.keys_param('meta', meta, {})
        if r: return r
        desc, r = utils.cli.keys_param('desc', desc, None)
        if r: return r

        # First, find artifact(s)
        con = ctx.get('control',{}).get('con', False)

        ctx['control']['con'] = False

        r = self.find_(ctx, 
                       arg1, 
                       tags, 
                       sort, 
                       add_index_file=True, 
                       skip_uids=skip_uids,
                       match=match,
                       match_empty_version=match_empty_version,
                       all_tags=all_tags,
                       follow_migrated=False,
        )
        if r['return']>0:
            if r['return']!=16 or not create: 
                return r

            r = self.create_(ctx, arg1, **create_params)
            if r['return']>0: return r

            r = self.find_(ctx, 
                           arg1, 
                           tags, 
                           sort, 
                           add_index_file=True, 
                           skip_uids=skip_uids,
                           match=match,
                           match_empty_version=match_empty_version,
                           all_tags=all_tags,
                           follow_migrated=False,
            )
            if r['return']>0: return r

        artifacts = r['artifacts']
        updated_artifacts = []

        category_cmeta = ctx['category_artifact']['cmeta']
        no_index = category_cmeta.get('no_index', False)

        ignore_root_keys = ['artifact']
        if not update_category:
            ignore_root_keys.append('category')

        # The AI context and the connections: resolved (or asked) once, before any artifact is touched
        plan = None
        if connect_to is None:
            connect_to = ct
        if artifacts and (ai_uses is not None or ai is not None or connect is not None or connect_to is not None):
            # a question about one artifact shows what it has (chosen: removed); about several, what may be added
            current, title = None, ''
            if len(artifacts) == 1:
                current = self._read_desc(artifacts[0]['path'])
                parts = artifacts[0].get('cmeta_ref_parts') or {}
                title = (parts.get('category_alias') or '') + '::' + (parts.get('artifact_alias') or parts.get('artifact_uid') or '')
            plan = self._desc_plan(ctx, ai_uses if ai_uses is not None else ai, connect, connect_to, current, title)
            if plan['return']>0: return plan
        desc_changes = []

        for artifact in artifacts:
            updated = False

            artifact_path = artifact['path']

            # Read real meta file
            found_cmeta_filename = None
            for ext in ['json', 'yaml']:
                cmeta_filename = os.path.join(artifact_path, self.cm.cfg['meta_filename_base'] + '.' + ext)

                if os.path.isfile(cmeta_filename):
                    found_cmeta_filename = cmeta_filename
                    break

            if found_cmeta_filename is None:
                if not ignore_errors:
                    return {'return':1, 'error':f'artifact meta file not found in "{artifact_path}"'}

            if found_cmeta_filename is not None:
               # Safe updating of meta data
               r = utils.files.safe_read_file(found_cmeta_filename, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
               if r['return']>0: 
                   if r['return']!=16: return r

                   cmeta = {}
                   cmeta_file_lock = None
               else:
                   cmeta = r['data']
                   cmeta_file_lock = r['file_lock']

               # Replace or merge
               if replace:
                   orig_artifact = cmeta.get('artifact')
                   orig_category = cmeta.get('category')

                   cmeta = meta

                   if 'artifact' not in cmeta: cmeta['artifact'] = orig_artifact
                   if 'category' not in cmeta: cmeta['category'] = orig_category

               else:                                     
                   cmeta = utils.common.deep_merge(cmeta, meta, append_lists=not replace_lists, ignore_root_keys=ignore_root_keys)


               if new_tags is not None:
                   meta_tags = cmeta.get('tags', [])

                   r = utils.common.normalize_tags(new_tags)
                   if r['return']>0: return r
                     
                   for t in r['tags']:
                       if t.endswith('-'):
                           t = t[:-1]
                           if t in meta_tags:
                               meta_tags.remove(t)
                       elif t not in meta_tags:
                           meta_tags.append(t)

                   cmeta['tags'] = meta_tags

               from datetime import datetime, timezone

               if 'creation_timestamp' not in cmeta:
                   cmeta['creation_timestamp'] = datetime.now(timezone.utc).isoformat()
               else:
                   cmeta['last_update_timestamp'] = datetime.now(timezone.utc).isoformat()

               # A task or agent that updates the artifact leaves its record (CMETA_GENERATOR)
               apply_artifact_defaults(cmeta, cfg=self.cm.cfg, creating=False)

               # A YAML meta file written by hand keeps its text: only the keys that changed are
               # rewritten, and the result is read back and checked before it replaces the file
               r = utils.files.safe_write_file(found_cmeta_filename, cmeta, file_lock=cmeta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger, preserve=True)
               if r['return']>0: return r

               if con and ctx['control'].get('verbose', False):
                   how = {'edit': 'edited in place (only the keys that changed)', 'dump': 'rewritten (full dump)'}.get(r.get('method'))
                   if how is not None:
                       print (f'  meta file {how}: {found_cmeta_filename}')

               updated = True

               # Update index - under the index lock, with the meta as the file holds it then: another update
               # may write the file between this write and this record, and the record that comes to the
               # index last must not bring an older meta than the file has
               if not no_index:
                   artifact_index_file = artifact['index_file']

                   artifact_cmeta_ref_parts = artifact['cmeta_ref_parts']

                   sharding_slices_num = artifact.get('sharding_slices_num', 0)

                   r = self.cm.repos.lock_index('the update of a record')
                   if r['return']>0: return r
                   index_lock = r['lock']

                   try:
                       r = utils.files.safe_read_file(found_cmeta_filename, fail_on_error=self.fail_on_error, logger=self.logger)
                       current = r['data'] if r['return'] == 0 and isinstance(r.get('data'), dict) else cmeta

                       r = self.cm.repos.add_to_index(current, artifact_cmeta_ref_parts, artifact_path,
                                                      sharding_slices_num = sharding_slices_num, index_lock = index_lock)
                   finally:
                       index_lock.release()

                   if r['return']>0: return r

            # The AI context, the connections and the other _desc keys (the sidecar, not the meta: the index
            # is untouched)
            if desc or (plan and (plan['lists'] or plan['others'])):
                r = self._apply_desc(artifact_path, _cref_of(artifact.get('cmeta_ref_parts')), desc, plan, con)
                if r['return']>0: return r
                desc_changes += r.get('lines') or []
                if r.get('changed'):
                    updated = True

            # Provide info
            if updated:
                updated_artifacts.append(artifact)

            if con:
                if updated:
                    x = 'Artifact was updated'
                else:
                    x = 'Skipped updating artifact'

                print (x + ' in ' + artifact_path)

        return {'return':0, 'artifacts': artifacts, 'updated_artifacts': updated_artifacts, 'desc_changes': desc_changes}

    ############################################################
    def list_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Optional tag filter.
        sort: bool = None,  # Sort by alias or UID.
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
    ):
        """
            List artifact names.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Optional tag filter.
                sort (bool): Sort by alias or UID.
                skip_uids (bool): Skip UIDs when using wildcards.
            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): List of matched artifacts.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        con = ctx['control'].get('con', False)

        ctx['control']['con'] = False

        r = self.find_(ctx, arg1, tags=tags, sort=sort, skip_uids = skip_uids, follow_migrated = False)
        if r['return']>0: return r

        if sort:
            r['artifacts'].sort(key=utils.names.get_sort_key_cmeta_obj_alias_or_uid)

        if con:
            for a in r['artifacts']:
                cmeta_ref_parts = a['cmeta_ref_parts']
                artifact_alias_or_uid = cmeta_ref_parts.get('artifact_alias', cmeta_ref_parts.get('artifact_uid'))

                migrated_to = (a.get('cmeta') or {}).get('migrated_to')
                if migrated_to:
                    artifact_alias_or_uid += f'  -> {migrated_to} (migrated)'

                print (artifact_alias_or_uid)

        return r

    ############################################################
    def read_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Optional tag filter.
        extra: bool = False,  # Show extra info.
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        yaml: bool = False,  # Output as YAML instead of JSON.
        load_files = [],  # Value for load files.
    ):
        """
            Read artifact meta.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Optional tag filter.
                extra (bool): Show extra info.
                skip_uids (bool): Skip UIDs when using wildcards.
                yaml (bool): Output as YAML instead of JSON.
                load_files: Value for load files.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifact** (dict): Matched artifact.
                    - **cmeta** (dict): Artifact metadata.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        con = ctx['control'].get('con', False)

        if arg1 is None:
            return {'return':1, 'error':'artifact (arg1) is not specified'}

        ctx['control']['con'] = False

        r = self.find_(ctx, arg1, tags=tags, skip_uids=skip_uids)
        if r['return']>0: return r

        artifacts = r['artifacts']

        if len(artifacts)>1:
            return {'return':1, 'error':f'more than 1 artifact found for "{arg1}"'}

        artifact = artifacts[0]

        сmeta = artifact['cmeta']

        result = {'return':0, 'artifact': artifact, 'cmeta': сmeta}

        if len(load_files) > 0:
            path = artifact['path']

            r = utils.files.load_files(path, load_files, self.fail_on_error)
            if r['return']>0: return r

            result['loaded_files'] = r['loaded_files']

        if con:
            data = artifact if extra else сmeta

            if yaml:
                import yaml
                print (yaml.dump(data, indent=2, sort_keys=True))
            else:
                import json
                print (json.dumps(data, indent=2, sort_keys=True))
        
        return result

    ############################################################
    def delete_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Optional tag filter.
        sort: bool = True,  # Sort artifacts by alias and UID.
        force: bool = False,  # Force deletion without confirmation.
        f: bool = False,  # Shorthand for force.
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        ignore_errors: bool = False,  # Ignore errors when deleting multiple artifacts.
        print_time: bool = False,  # Print time per deletion.
        match: dict = None,  # Value for match.
        match_empty_version: bool = False,  # Value for match empty version.
        all_tags: str = None,  # Value for all tags.
    ):
        """
            Delete and unindex artifact(s).

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Optional tag filter.
                sort (bool): Sort artifacts by alias and UID.
                force (bool): Force deletion without confirmation.
                f (bool): Shorthand for force.
                skip_uids (bool): Skip UIDs when using wildcards.
                ignore_errors (bool): Ignore errors when deleting multiple artifacts.
                print_time (bool): Print time per deletion.
                match (dict | None): Match artifact metadata before deleting.
                match_empty_version (bool): Match artifacts with an empty version value.
                all_tags (str | None): Require all supplied tags when selecting artifacts.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): All matched artifacts.
                    - **deleted_artifacts** (list): Deleted artifacts.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # First, find artifact(s)
        con = ctx.get('control',{}).get('con', False)

        ctx['control']['con'] = False

        # A migration stub is deleted as itself, never through to the artifact it points to
        r = self.find_(ctx,
                       arg1,
                       tags,
                       sort,
                       add_index_file=True,
                       skip_uids=skip_uids,
                       match=match,
                       match_empty_version=match_empty_version,
                       all_tags=all_tags,
                       follow_migrated=False,
        )
        if r['return']>0: return r

        artifacts = r['artifacts']

        deleted_artifacts = []

        force = force or f
    
        category_cmeta = ctx['category_artifact']['cmeta']
        sharding_slices = category_cmeta.get('sharding_slices')
        no_index = category_cmeta.get('no_index', False)

        for artifact in artifacts:
            artifact_path = artifact['path']
            artifact_cmeta = artifact['cmeta']

            if artifact_cmeta.get('permanent', False):
                if con:
                    print (f'Skipping permanent artifact located at "{artifact_path}" ...')

                continue

            if print_time:
                import time
                start_time = time.perf_counter()                

            r = utils.files.ask_to_delete(con, force, artifact_path)
            if r['return']>0: return r
            if not r['confirmed']: continue

#            if con:
#                print (f'Deleting artifact located at "{artifact_path}" ...')
#                if not force:
#                    x = input('  Proceed (y/N)? ')
#                    x = x.strip().lower()
#
#                    if x not in ['y', 'yes']:
#                        print ('    Skipped!')
#                        continue

            artifact_cmeta_ref_parts = artifact['cmeta_ref_parts']
            artifact_uid = artifact_cmeta_ref_parts['artifact_uid']
            artifact_alias_lowercase = artifact_cmeta_ref_parts.get('artifact_alias_lowercase', artifact_cmeta_ref_parts.get('artifact_alias'))

            # The record and the folder go under the lock of the folder (the one safe_delete_directory
            # takes): a process working inside it - a cache entry being built holds that lock - makes the
            # deletion wait and then fail as a whole, instead of removing the record and leaving the folder
            error = False
            folder_lock = None
            try:
                folder_lock = utils.files._acquire_lock(artifact_path, logger=self.logger, what=f"the deletion of '{artifact_path}'")
            except Exception as e:
                r = {'return':1, 'error': f'cannot delete "{artifact_path}": {e}'}
                error = True

            try:
                # The folder first, then the record: a folder that cannot be removed (a file held open by
                # another process, the working directory of a process on Windows) leaves everything as it
                # was, never a record without its folder or a folder without its record
                if not error:
                    r = self.cm.utils.files.safe_delete_directory(artifact_path, file_lock=folder_lock)
                    if r['return']>0:
                        error = True

                if not error and not no_index:
                    artifact_index_file = artifact['index_file']

                    r = self.cm.repos.remove_from_index(artifact_index_file, artifact_uid, artifact_alias_lowercase)
                    if r['return']>0:
                        error = True
            finally:
                if folder_lock is not None:
                    try:
                        folder_lock.release()
                    except Exception:
                        pass

            # Delete root if empty
            if not error:
                r = utils.files.safe_delete_directory_if_empty_with_sharding(artifact_path, sharding_slices)
                if r['return'] > 0:
                    error = True

            if error:
                if not ignore_errors:
                    return r

                if con:
                    print(f'    Skipped deletion or partially deleted due to error: {r["error"]}')

            if not error:
                deleted_artifacts.append(artifact)

            if print_time:
                print ('        Elapsed time: %.3f sec.' % (time.perf_counter() - start_time))


        return {'return':0, 'artifacts': artifacts, 'deleted_artifacts': deleted_artifacts}

    ############################################################
    def _alias_with_date(
        self,
        ctx: dict,  # cMeta context.
        arg1 = None,  # The artifact the command was given: alias, UID, alias,UID, with a repository or not.
        dt = None,  # True: today's date in front of the alias; a date as text (20261001, 202610): that one; None: nothing.
    ):
        """
            The alias of a new artifact with its date in front, as the dated categories name theirs
            (20261105.a note): -dt puts today's date (--dt=<date> that date) in front of an alias that starts
            with none, and the date alone names an artifact given no alias. Nothing is put in front of an alias
            that starts with a date (20261001.x, 202604xx.x, 2020-2022.x: utils.names.date_in_alias). A category
            whose meta says `dated_aliases: true` gets a warning for an alias without a date - the alias is kept.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): The artifact the command was given.
                dt (bool | str | None): The date to put in front.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **arg1** (str | None): The artifact to create (as given when nothing changes).
                    - **warnings** (list): The warning of a dated category, or nothing.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        warnings = []

        r = utils.names.parse_cmeta_obj(arg1, fail_on_error = self.fail_on_error)
        if r['return'] >0: return r

        obj_parts = r['obj_parts']

        alias = obj_parts.get('alias')
        dated = alias is not None and utils.names.date_in_alias(alias) is not None

        if dt is not None and dt is not False and dt != '' and not dated:
            if dt is True:
                from datetime import datetime
                prefix = datetime.now().strftime('%Y%m%d')
            else:
                prefix = str(dt).strip()
                found = utils.names.date_in_alias(prefix)
                if found is None or found['text'] != prefix:
                    return {'return':1, 'error': f'"{prefix}" is not a date to put in front of the alias (20261001, 202610, 2026, 2026-10-01)'}

            obj_parts['alias'] = prefix if alias is None or alias == '' else f'{prefix}.{alias}'

            r = utils.names.restore_cmeta_obj(obj_parts, fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            arg1 = r['obj']
            dated = True

        if not dated and ctx['category_artifact']['cmeta'].get('dated_aliases', False):
            from datetime import datetime
            category_alias = ctx['category']['artifact_alias']
            what = f'"{alias}" has none; add -dt to put today\'s date in front' if alias else \
                   'none was given; add -dt to name it by today\'s date'
            warnings.append(f'cMeta warning: a {category_alias} alias starts with its date '
                            f'({datetime.now().strftime("%Y%m%d")}.name) - {what}')

        return {'return':0, 'arg1':arg1, 'warnings':warnings}

    ############################################################
    def _create_repo_of(
        self,
        ctx: dict,  # cMeta context.
    ):
        """
            The repository the default config names for the category's new artifacts: the key
            `<category alias, "_" for its dots>_create_repo` (work_create_repo: fgg), read by every create
            since 0.38.9 (the dated categories' own create read it before). No config, or no key: none.

            Args:
                ctx (dict): cMeta context.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **repo_alias** (str | None), **repo_uid** (str | None): The repository, both None when the
                      config names none.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        none = {'return':0, 'repo_alias': None, 'repo_uid': None}

        r = self.cm.access({'category': f"config,{self.cm.cfg['category_config_uid']}",
                            'command': 'read',
                            'arg1': self.cm.cfg['default_config_name'],
                            'con': False})
        if r['return'] == 16:
            return none
        if r['return'] >0: return r

        key = ctx['category']['artifact_alias'].replace('.', '_') + '_create_repo'

        repo = str(r.get('config_cmeta', {}).get(key) or '').strip()
        if repo == '':
            return none

        r = utils.names.parse_cmeta_name(repo, 'repo')
        if r['return'] >0: return r

        return {'return':0, 'repo_alias': r['name'].get('repo_alias'), 'repo_uid': r['name'].get('repo_uid')}

    ############################################################
    def create_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Tags to add to the artifact.
        meta: dict = {},  # Initial metadata dictionary.
        yaml: bool = False,  # Save metadata as YAML instead of JSON.
        virtual: bool = False,  # Virtual artifact created only in index (such as repo).
        path: str = None,  # Use this path for artifact (useful for virtual artifacts such as repo).
        index: bool = False, # If true and path exists but not index, just add to index
                             # Useful when AI agents create cMeta entries while bypassing cMeta
        desc: dict = None,  # Keys merged into the artifact's _desc.yaml (--desc.<key>=<value>, or a whole @file.yaml holding desc:).
        ai_uses = None,  # AI context: template aliases, artifact aliases or cRefs (comma-separated); True = ask.
        ai = None,  # The short form of ai_uses (-ai, -ai=cmeta,fgg).
        connect = None,  # Connect both ways: names or cRefs (";" between cRefs); True = ask.
        connect_to = None,  # Connect the new artifact to them (its own _desc only): the same forms.
        ct = None,  # The short form of connect_to (--ct=<cRef>).
        dt = None,  # The date in front of the alias: -dt today's (20261105.<alias>), --dt=<date> that one; nothing is added to an alias that starts with a date.
    ):
        """
            Create and index an artifact.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Tags to add to the artifact.
                meta (dict): Initial metadata dictionary.
                yaml (bool): Save metadata as YAML instead of JSON.
                virtual (bool): Virtual artifact created only in index (such as repo).
                path (str | None): Use this path for artifact (useful for virtual artifacts such as repo).
                index (bool): Index an artifact that already exists at `path` without creating it.
                desc (dict | None): Keys merged into the artifact's _desc.yaml.
                ai_uses, ai: The AI context (template aliases, artifact aliases, cRefs); True asks.
                connect: Artifacts to connect both ways - their cRefs go into the new artifact's `connections`
                    and its cRef into theirs; True asks.
                connect_to, ct: Artifacts to connect the new one to, in its own _desc.yaml only.
                dt (bool | str | None): The date in front of the alias: True today's, a text that date; nothing is
                    added to an alias that starts with a date (_alias_with_date).

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **path** (str): Path to the created artifact.
                    - **meta** (dict): Artifact metadata.
                    - **warnings** (list): The warning of a dated category (`dated_aliases: true` in its meta)
                      for an alias without a date, printed too unless quiet; empty otherwise.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx.get('control',{}).get('con', False)

        ctx['control']['con'] = False

        if tags is not None:
            if type(tags) != str and type(tags) != list:
                return {'return':1, 'error': f'"tags" should be str or list but got {type(tags).__name__}'}

        # meta and desc take keys: anything else is refused before anything is made
        meta, r = utils.cli.keys_param('meta', meta, {})
        if r: return r
        desc, r = utils.cli.keys_param('desc', desc, None)
        if r: return r

        # The alias with its date in front (-dt), and the warning of a dated category for an alias without one;
        # a folder that exists is indexed under its own name
        warnings = []

        if not index:
            r = self._alias_with_date(ctx, arg1, dt)
            if r['return'] >0: return r

            arg1 = r['arg1']
            warnings = r['warnings']

        # Use UID if arg1 is None
        if arg1 is None:
            artifact_obj_parts = {}

        else:
            # Parse artifact
            r = utils.names.parse_cmeta_obj(arg1, key = "artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            artifact_obj_parts = r['obj_parts']

        # Check artifact path
        artifact_alias = artifact_obj_parts.get('artifact_alias')
        artifact_uid = artifact_obj_parts.get('artifact_uid')

        if artifact_alias is not None or artifact_uid is not None:
            # Check that artifact doesn't have wildcards
            if artifact_alias is not None and ('*' in artifact_alias or '?' in artifact_alias):
                return {'return':1, 'error':f"artifact can't have wildcards during creation ({arg1})"}

            # Check if artifact already exists (relatively fast - should be in index)
            r = self.find_(ctx, arg1, tags, follow_migrated = False)
            if r['return'] == 0:
               artifacts = r['artifacts']
               if len(artifacts)>0:
                   if len(artifacts) == 1:
                       return {'return':8, 'error':f'artifact already exists in "{artifacts[0]["path"]}"'}
                   else:
                       paths = ', '.join([a['path'] for a in artifacts])
                       return {'return':8, 'error':f'artifacts already exist in "{paths}"'}
               
            elif r['return'] != 16:
               return r

        # Find path to target repository or local if not specified
        artifact_repo_alias = artifact_obj_parts.get('artifact_repo_alias')
        artifact_repo_uid = artifact_obj_parts.get('artifact_repo_uid')

        # The repository the default config names for the category's new artifacts, when the request names none
        if artifact_repo_uid is None and artifact_repo_alias is None and not virtual and not index:
            r = self._create_repo_of(ctx)
            if r['return'] >0: return r

            artifact_repo_alias = r['repo_alias']
            artifact_repo_uid = r['repo_uid']

        repo_cmeta_ref = {'category_alias': 'repo', 'category_uid': self.cm.cfg['category_repo_uid']}
        
        if artifact_repo_uid == None and artifact_repo_alias == None:
            repo_cmeta_ref['artifact_alias'] = 'local'
        else:
            if artifact_repo_uid != None: repo_cmeta_ref['artifact_uid'] = artifact_repo_uid
            if artifact_repo_alias != None: repo_cmeta_ref['artifact_alias'] = artifact_repo_alias

        r = self.cm.repos.find(repo_cmeta_ref)
        if r['return']>0: return r

        repo_artifacts = r['artifacts']

        if len(repo_artifacts)>1:
            paths = ', '.join([a['path'] for a in repo_artifacts])
            return {'return':1, 'error': f'more than one target repo found during artifact creation in "{paths}"'} 

        repo_artifact = repo_artifacts[0]
        repo_path = repo_artifact['full_path']

        repo_cmeta = repo_artifact['cmeta']

        repo_cmeta_ref_parts = repo_artifact['cmeta_ref_parts']

        artifact_repo_alias = repo_cmeta_ref_parts.get('artifact_alias')
        artifact_repo_uid = repo_cmeta_ref_parts['artifact_uid']

        if not virtual:
            # Need to check detached but kept repos (such as USB)
            keep = repo_cmeta.get('keep', False)
            try:
                os.makedirs(repo_path, exist_ok=True)
            except Exception as e:
                x = 'detachable ' if keep else ''
                err = f'can\'t access {x}repo (please check if plugged): {repo_path}'
                return _error(err, 1, e, self.fail_on_error)

        # Check category path
        category = ctx['category']
        category_alias = category['artifact_alias']
        category_uid = category['artifact_uid']

        category_cmeta = ctx['category_artifact']['cmeta']
        no_index = category_cmeta.get('no_index', False)

        category_path = os.path.join(repo_path, category_alias)

        if not virtual:
            os.makedirs(category_path, exist_ok=True)

        # Check artifact path
        if artifact_uid == None:
            artifact_uid = utils.names.generate_cmeta_uid()

        artifact_dir = artifact_alias if artifact_alias != None and artifact_alias != '' else artifact_uid

        if category_uid in repo_cmeta.get('sharding_slices', {}):
            sharding_slices = repo_cmeta['sharding_slices'][category_uid]
        else:
            sharding_slices = category_cmeta.get('sharding_slices')

        sharding_slices_num = 0
        if sharding_slices is not None:
            sharding_slices_num = len(sharding_slices)

            r = utils.files.apply_sharding_to_path(category_path, artifact_dir, sharding_slices)
            if r['return']>0: return r

            artifact_path = r['sharded_path']
        else:
            artifact_path = os.path.join(category_path, artifact_dir)

        cmeta_filename_json = os.path.join(artifact_path, self.cm.cfg['meta_filename_base'] + '.json')
        cmeta_filename_yaml = os.path.join(artifact_path, self.cm.cfg['meta_filename_base'] + '.yaml')

        # The meta file of an artifact that is indexed as it is (made or copied by hand)
        existing_meta_file = None

        # The AI context and the connections asked for are resolved (or asked) before anything is made, so
        # that a wrong name or an ambiguity makes no artifact
        plan = None
        if connect_to is None:
            connect_to = ct
        if not virtual and (ai_uses is not None or ai is not None or connect is not None or connect_to is not None):
            plan = self._desc_plan(ctx, ai_uses if ai_uses is not None else ai, connect, connect_to, {},
                                   f'{category_alias}::{artifact_alias or artifact_uid}')
            if plan['return']>0: return plan

        # The folder, the meta and the record of a new artifact are made under the index lock: a full
        # reindex running meanwhile never sees a half-made artifact, two creates of one artifact at once
        # end with one artifact (the second finds the folder of the first), and a create whose record
        # cannot be written removes what it made, so that nothing is left unindexed
        index_lock = None
        if not no_index:
            r = self.cm.repos.lock_index('the creation of an artifact')
            if r['return']>0: return r
            index_lock = r['lock']

        disk_path = artifact_path       # where the folder and the meta go (`path` may replace artifact_path for the index)
        made_folder = False             # the create made the folder itself
        written_meta_file = None        # the meta file the create wrote
        done = False

        try:
            if not virtual:
                if os.path.isdir(artifact_path):
                    if os.path.isfile(cmeta_filename_json) or os.path.isfile(cmeta_filename_yaml):
                        if index:
                            if os.path.isfile(cmeta_filename_json):
                                f = cmeta_filename_json
                            else:
                                f = cmeta_filename_yaml
                                yaml = True

                            # Do not use lock since it's not in the system and not in the index
                            r = utils.files.safe_read_file(f, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']>0: return r

                            meta = r['data']
                            existing_meta_file = f

                            # Index the artifact under the UID of its meta (an "alias,UID" too),
                            # not a new one, or alias,UID references to it would not resolve
                            meta_uid = str(meta.get('artifact') or '').split(',')[-1].strip()
                            if meta_uid and utils.names.is_valid_cmeta_uid(meta_uid):
                                artifact_uid = meta_uid

                        else:
                            return {'return':8, 'error':f'artifact already exists in "{artifact_path}"'}
                else:
                    made_folder = True

                os.makedirs(artifact_path, exist_ok=True)

            # Prepare meta
            cmeta = copy.deepcopy(meta)

            if 'artifact' not in cmeta:
                cmeta['artifact'] = artifact_uid

            if 'category' not in cmeta:
                r = utils.names.restore_cmeta_name(category, key='artifact', fail_on_error = self.fail_on_error)
                if r['return'] >0: return r

                cmeta['category'] = r['name']

            if tags is not None:
                meta_tags = cmeta.get('tags', [])

                r = utils.common.normalize_tags(tags)
                if r['return']>0: return r

                for t in r['tags']:
                    if t not in meta_tags:
                        meta_tags.append(t)

                cmeta['tags'] = meta_tags

            if existing_meta_file is None:
                from datetime import datetime, timezone

                if 'creation_timestamp' not in cmeta:
                    cmeta['creation_timestamp'] = datetime.now(timezone.utc).isoformat()
                else:
                    cmeta['last_update_timestamp'] = datetime.now(timezone.utc).isoformat()

                # Authors, copyright and generator: the meta, the environment and the repository defaults
                apply_artifact_defaults(cmeta, repo_meta=repo_cmeta, cfg=self.cm.cfg, creating=True)

            # Save meta
            if not virtual:
                if existing_meta_file is not None:
                    # Indexing leaves the meta file as it was written; only what the request adds (the tags,
                    # an identity key the file lacks) is added in place, without rewriting the rest
                    if cmeta != meta:
                        r = utils.files.safe_write_file(existing_meta_file, data=cmeta, fail_on_error = self.fail_on_error, logger=self.logger, preserve=True)
                        if r['return']>0: return r

                else:
                    tmp_cmeta_filename = cmeta_filename_yaml if yaml else cmeta_filename_json
                    written_meta_file = tmp_cmeta_filename

                    # A new YAML meta is written in the keep style (the key order of YAML_META_KEY_ORDER,
                    # nothing folded, lists indented), the style `update` keeps; a JSON meta is sorted as before
                    r = utils.files.safe_write_file(tmp_cmeta_filename, data=cmeta, fail_on_error = self.fail_on_error, keep=True)
                    if r['return']>0: return r

            if path is not None:
                artifact_path = path

            # Update index
            if not no_index:
                cmeta_ref_parts = {}

                if artifact_alias is not None:
                    cmeta_ref_parts['artifact_alias'] = artifact_alias
                    artifact_alias_lowercase = artifact_alias.lower()
                    if artifact_alias_lowercase != artifact_alias:
                        cmeta_ref_parts['artifact_alias_lowercase'] = artifact_alias_lowercase

                cmeta_ref_parts['artifact_uid'] = artifact_uid

                cmeta_ref_parts['category_alias'] = category_alias
                cmeta_ref_parts['category_uid'] = category_uid

                cmeta_ref_parts['repo_alias'] = artifact_repo_alias
                cmeta_ref_parts['repo_uid'] = artifact_repo_uid

                r = self.cm.repos.add_to_index(cmeta, cmeta_ref_parts, artifact_path, sharding_slices_num = sharding_slices_num, index_lock = index_lock)
                if r['return']>0: return r

            done = True

        finally:
            if not done and not virtual:
                self._undo_create(disk_path, made_folder, written_meta_file, sharding_slices)
            if index_lock is not None:
                index_lock.release()

        # The AI context, the connections and the other _desc keys of the new artifact (its folder exists now)
        desc_changes = []
        if not virtual and (desc or (plan and (plan['lists'] or plan['others']))):
            this = _cref_of({'category_alias': category_alias, 'category_uid': category_uid,
                             'artifact_alias': artifact_alias, 'artifact_uid': artifact_uid})
            r = self._apply_desc(artifact_path, this, desc, plan, con)
            if r['return']>0: return r
            desc_changes = r.get('lines') or []

        # Print artifact path, and the warning of a dated category (not under -q: a script reads the output)
        if con:
            x = 'Virtual a' if virtual else 'A'
            print (f'{x}rtifact was created in "{artifact_path}"')

            if not ctx['control'].get('quiet', False):
                for warning in warnings:
                    print (warning)

        return {'return':0, 'path':artifact_path, 'meta':cmeta, 'desc_changes':desc_changes, 'warnings':warnings}

    ############################################################
    def _find_all(
        self,
        cid: str,  # A CID with wildcards ("*::*": every artifact of every category; "*::name": an alias anywhere).
        match: dict = None,  # Meta keys the artifacts must match (nested dicts).
    ):
        """
            Every indexed artifact of every category that a CID with wildcards names (the index search
            of utils find_by_cid: every record keeps the artifact's meta, so no file is read).
            Returns:
                dict: {'return', 'artifacts': [...]} - an empty list when nothing matches.
        """
        return find_all(self.cm, cid, match)

    ############################################################
    def _ai_context_entries(
        self,
        purpose: str = AI_USES_KEY,  # The key under `template` in the meta.
    ):
        """The declared templates for a purpose, sorted (template_entries), from one index query."""
        return ai_context_entries(self.cm, purpose)

    ############################################################
    def _resolve_ai_context(
        self,
        names,  # Aliases separated by commas, cRefs separated by ";" (split_context_names), or a list.
        entries: list,  # The declared templates (_ai_context_entries).
    ):
        """
            The full cRefs of the names: a template's alias first, then an artifact alias in any category,
            then a cRef (cat::alias or cat,UID::alias,UID); more than one artifact for a name is an error that
            names them all, so the person picks one by its cRef.
            Returns:
                dict: {'return', 'crefs': [...]}
        """
        return resolve_ai_context(self.cm, names, entries)

    ############################################################
    @staticmethod
    def _choose(
        heading: str,  # The first line: what is chosen, and for which artifact.
        rows: list,  # [{'cref', 'name', 'title', 'used'}]: what the artifact has ('used') and what it may add.
        hint: str,  # The line under the table: how to choose, with an example of this list.
        how: str,  # What makes the question unnecessary (named in the error of a run without a terminal).
        name_header: str = 'name',  # The header of the names' column.
    ):
        """
            A list to choose from, as a table: what the artifact has first, numbered "-N" (chosen: removed), then
            what it may add, numbered "N" (chosen: added), and the question. The answer holds numbers, names or
            cRefs, comma-separated (";" between cRefs); a name with "-" in front is removed; Enter changes
            nothing. Plain text, so that it reads the same in any terminal, through a pipe and in any code page.
            Returns {'return', 'add': [cRefs], 'drop': [cRefs], 'names': [what was typed besides numbers]}.
        """
        rows = sorted(rows, key = lambda x: not x['used'])           # what it has first, in its order
        print ('')
        print (heading)
        if rows:
            labels = [('-' if x['used'] else '') + str(n) for n, x in enumerate(rows, 1)]
            titled = any(x['title'] for x in rows)
            mixed = any(x['used'] for x in rows) and not all(x['used'] for x in rows)
            wn = max(2, max(len(s) for s in labels))
            wa = max(len(name_header), max(len(x['name']) for x in rows))
            wt = min(60, max([5] + [len(x['title']) for x in rows]))
            print ('')
            print (('  ' + '#'.rjust(wn) + '  ' + name_header.ljust(wa) + ('  title' if titled else '')).rstrip())
            print ('  ' + '-' * wn + '  ' + '-' * wa + ('  ' + '-' * wt if titled else ''))
            for label, x in zip(labels, rows):
                title = x['title'] if len(x['title']) <= 60 else x['title'][:57] + '...'
                line = '  ' + label.rjust(wn) + '  ' + x['name'].ljust(wa) + ('  ' + title.ljust(wt) if titled else '')
                print ((line + ('  (in use)' if mixed and x['used'] else '')).rstrip())
        print ('')
        print ('  ' + hint)
        r = utils.common.ask('Your choice (Enter: no change): ', how = how, optional = True)
        if r['return']>0: return r
        add, drop, names = [], [], []
        for word in split_context_names((r.get('answer') or '').strip()):
            m = re.fullmatch(r'(-?)(\d+)', word)
            if not m:
                names.append(word)
                continue
            n = int(m.group(2))
            if not 1 <= n <= len(rows):
                return {'return':1, 'error': f'{word} is not in the list' + (f' (1..{len(rows)})' if rows else ' (it is empty)')}
            x = rows[n - 1]
            if x['used']:
                drop.append(x['cref'])
            elif m.group(1):
                return {'return':1, 'error': f'{word}: {x["name"]} is not in use ({n} adds it)'}
            else:
                add.append(x['cref'])
        return {'return':0, 'add':add, 'drop':drop, 'names':names}

    ############################################################
    @staticmethod
    def _choice_rows(
        current: list,  # What the artifact has (ai_uses or connections), or None when several artifacts are asked about.
        entries: list = None,  # What it may add: the declared templates (_ai_context_entries), or None.
    ):
        """The rows of _choose: what the artifact has (a template's alias and title where it is one), then the templates it lacks."""
        rows = []
        for c in current or []:
            e = next((e for e in entries or [] if cref_matches(e['cref'], c)), None)
            ca, _, aa, au = _cref_split(c)
            name = e['alias'] if e else ((ca + '::' if ca else '') + (aa or au or _cref_key(c)))
            rows.append({'cref': _cref_key(c), 'name': name, 'title': e['title'] if e else '', 'used': True})
        for e in entries or []:
            if not any(cref_matches(c, e['cref']) for c in current or []):
                rows.append({'cref': e['cref'], 'name': e['alias'], 'title': e['title'], 'used': False})
        return rows

    ############################################################
    def _ask_ai_context(
        self,
        entries: list,  # The declared templates (_ai_context_entries).
        current: list = None,  # The ai_uses of the artifact asked about, or None (several, or a new one).
        title: str = '',  # The artifact asked about (category::alias), or ''.
    ):
        """
            The AI contexts to choose from (_choose): what the artifact uses ("-N": removed when chosen), then the
            declared templates it does not use ("N": added); numbers, aliases or cRefs ("-alias" removes), Enter
            for no change. A run without a terminal gets the error of utils.common.ask.
            Returns:
                dict: {'return', 'crefs': [to add], 'drop': [cRefs or names to remove]}
        """
        if not entries and not current:
            print ('No AI context template is declared (template: ai_uses: {alias, title, sort} in an artifact\'s meta).')
            return {'return':0, 'crefs':[], 'drop':[]}
        rows = self._choice_rows(current, entries)
        used = [x for x in rows if x['used']]
        free = [x for x in rows if not x['used']]
        example = '; '.join(([f'-{rows.index(used[0]) + 1} removes {used[0]["name"]}'] if used else []) +
                            ([f'{rows.index(free[0]) + 1} adds {free[0]["name"]}'] if free else []))
        r = self._choose('AI context (ai_uses) of ' + (title or 'the artifact') + ':', rows,
                         (example + ' - ' if example else '') + 'numbers, aliases or cRefs, comma-separated ("-alias" removes)',
                         '-ai=<aliases> names them without a question ("-ai=-<alias>" removes); -q asks nothing')
        if r['return']>0: return r
        add_names, drop_names = split_changes(r['names'])
        rr = self._resolve_ai_context(add_names, entries)
        if rr['return']>0: return rr
        rd = resolve_artifacts(self.cm, drop_names, entries, missing_ok = True)
        if rd['return']>0: return rd
        return {'return':0, 'crefs': r['add'] + rr['crefs'], 'drop': r['drop'] + [a['cref'] or a['name'] for a in rd['artifacts']]}

    ############################################################
    def _ai_context_crefs(
        self,
        ctx: dict,  # cMeta context.
        ai,  # The ai_uses request: True (ask), a comma-separated string or a list, or None / False (nothing).
        current: list = None,  # The ai_uses of the artifact asked about (the question shows them), or None.
        title: str = '',  # The artifact asked about (category::alias), or ''.
    ):
        """
            The full cRefs of the AI contexts a create or an update asked for - the names resolved
            (_resolve_ai_context), or the numbered list asked when `ai` is True; a quiet run asks nothing
            and adds nothing. Called before anything is made or changed, so that a wrong name or an
            ambiguity stops the command without a side effect. Returns {'return', 'crefs'}.
        """
        if ai is None or ai is False:
            return {'return':0, 'crefs':[]}
        r = self._ai_context_entries()
        if r['return']>0: return r
        entries = r['entries']
        if ai is True:
            if ctx.get('control', {}).get('quiet', False):
                return {'return':0, 'crefs':[]}
            return self._ask_ai_context(entries, current, title)
        return self._resolve_ai_context(ai, entries)

    ############################################################
    def _desc_plan(
        self,
        ctx: dict,  # cMeta context.
        ai = None,  # The ai_uses request: names ("-name" removes), True = ask (_ai_context_crefs).
        connect = None,  # Artifacts to connect both ways: names or cRefs ("-name" disconnects); True = ask.
        connect_to = None,  # Artifacts to connect this one to, in its own _desc only: the same forms.
        current: dict = None,  # The _desc of the one artifact asked about (a question shows what it has), or None.
        title: str = '',  # That artifact (category::alias), or ''.
    ):
        """
            The changes of the lists in _desc.yaml that a create or an update asked for, resolved before anything
            is made or changed, so that a wrong name or an ambiguity stops the command without a side effect: the
            AI context (ai_uses), the connections of this artifact, and those of the artifacts --connect names
            (the other side). A name to add must name one artifact; a name to remove may name one that is gone
            (its entries are then found by what they say). A quiet run asks nothing.
            Returns {'return', 'lists': {key: (add, drop)}, 'others': [{'op', 'cref', 'path'}], 'asked'}.
        """
        quiet = ctx.get('control', {}).get('quiet', False)
        plan = {'return':0, 'lists':{}, 'others':[], 'asked':False}

        def listed(key):
            # what the artifact has under a key - None when several artifacts are asked about
            if current is None:
                return None
            value = current.get(key)
            return list(value) if isinstance(value, list) else ([value] if value else [])

        if ai is not None and ai is not False:
            if ai is True:
                r = self._ai_context_crefs(ctx, True, listed(AI_USES_KEY), title)
                if r['return']>0: return r
                plan['lists'][AI_USES_KEY] = (r['crefs'], r.get('drop') or [])
                plan['asked'] = not quiet
            else:
                add, drop = split_changes(ai)
                r = self._ai_context_entries()
                if r['return']>0: return r
                entries = r['entries']
                r = resolve_artifacts(self.cm, add, entries)
                if r['return']>0: return r
                adds = [a['cref'] for a in r['artifacts']]
                r = resolve_artifacts(self.cm, drop, entries, missing_ok = True)
                if r['return']>0: return r
                plan['lists'][AI_USES_KEY] = (adds, [a['cref'] or a['name'] for a in r['artifacts']])

        adds, drops = [], []
        for value, both in ((connect, True), (connect_to, False)):
            if value is None or value is False:
                continue
            chosen = []
            if value is True:
                if quiet:
                    continue
                flag = '--connect' if both else '--ct'
                rows = self._choice_rows(listed(CONNECTIONS_KEY))
                way = 'both ways' if both else 'this side only'
                hint = (f'-1 disconnects {rows[0]["name"]}; ' if rows else '') + \
                       'to connect, type aliases or cRefs (";" between cRefs, "-alias" disconnects)'
                r = self._choose(f'Connections of {title or "the artifact"} ({way}):' + ('' if rows or current is None else ' none yet'),
                                 rows, hint, f'{flag}=<names> names them without a question ("{flag}=-<name>" removes); -q asks nothing',
                                 name_header = 'connected to')
                if r['return']>0: return r
                chosen = r['drop']
                value = r['names']
                plan['asked'] = True
            add, drop = split_changes(value)
            drop = list(chosen) + drop
            r = resolve_artifacts(self.cm, add)
            if r['return']>0: return r
            for a in r['artifacts']:
                adds.append(a['cref'])
                if both:
                    plan['others'].append({'op': '+', 'cref': a['cref'], 'path': a['path']})
            r = resolve_artifacts(self.cm, drop, missing_ok = True)
            if r['return']>0: return r
            for a in r['artifacts']:
                drops.append(a['cref'] or a['name'])
                if both and a['cref'] and a['path']:
                    plan['others'].append({'op': '-', 'cref': a['cref'], 'path': a['path']})
        if adds or drops:
            plan['lists'][CONNECTIONS_KEY] = (adds, drops)
        return plan

    ############################################################
    def _apply_desc(
        self,
        artifact_path: str,  # The artifact's folder.
        cref: str,  # Its full cRef (what the other side of a connection gets).
        desc: dict,  # Keys to merge into its _desc.yaml, or None.
        plan: dict,  # The changes of the lists (_desc_plan), or None.
        con: bool,  # Whether the run prints what changed.
    ):
        """
            Writes the artifact's _desc.yaml (_edit_desc) and, for --connect, this artifact's cRef into the
            _desc.yaml of each artifact named (or out of it); an artifact is never connected to itself.
            Returns {'return', 'changed', 'lines'}.
        """
        plan = plan or {}
        lists = {}
        for key, (add, drop) in (plan.get('lists') or {}).items():
            if key == CONNECTIONS_KEY and cref:
                add = [a for a in add if not cref_matches(a, cref)]
            lists[key] = (add, drop)
        r = self._edit_desc(artifact_path, desc, lists, con)
        if r['return']>0: return r
        changed, lines = r.get('changed', False), list(r.get('lines') or [])
        for other in plan.get('others') or []:
            if not cref or not other.get('path') or cref_matches(other['cref'], cref):
                continue
            change = ([cref], []) if other['op'] == '+' else ([], [cref])
            r = self._edit_desc(other['path'], None, {CONNECTIONS_KEY: change}, con)
            if r['return']>0:
                return {'return':1, 'error': f'{artifact_path} was changed, but not the other side {other["cref"]}: {r.get("error")}'}
            lines += r.get('lines') or []
        return {'return':0, 'changed':changed, 'lines':lines}

    ############################################################
    def _write_desc(
        self,
        artifact_path: str,  # The artifact's folder (it exists).
        desc: dict,  # Keys to merge into _desc.yaml, or None.
        crefs: list,  # The full cRefs to append to its ai_uses (_ai_context_crefs), or [].
        con: bool,  # Whether the run prints.
    ):
        """
            Writes the artifact's _desc.yaml with `desc` merged in and `crefs` appended to its ai_uses
            (_edit_desc). Returns {'return', 'changed', 'crefs', 'desc_file', 'lines'}.
        """
        r = self._edit_desc(artifact_path, desc, {AI_USES_KEY: (list(crefs or []), [])}, con)
        if r['return']>0: return r
        r['crefs'] = list(crefs or [])
        return r

    ############################################################
    def _edit_desc(
        self,
        artifact_path: str,  # The artifact's folder (it exists).
        desc: dict,  # Keys to merge into _desc.yaml, or None.
        lists: dict,  # {key: (entries to append, names to remove)} for ai_uses and connections (merge_desc).
        con: bool,  # Whether the run prints what changed.
    ):
        """
            Writes the artifact's _desc.yaml with `desc` merged in and the `lists` changes made (merge_desc).
            A file written by hand keeps its text: changes of the lists alone are made on the lines of their
            blocks (edit_list_text) and the text is read back and compared before it replaces the file; other
            keys are edited in place (safe_write_file preserve), as is a list the lines cannot take. A
            _desc.json found there is read, written as YAML and removed.
            Returns {'return', 'changed', 'desc_file', 'lines'}: `lines` says what was added (+) and removed (-).
        """
        lists = {k: v for k, v in (lists or {}).items() if v and (v[0] or v[1])}
        if not lists and not (isinstance(desc, dict) and desc):
            return {'return':0, 'changed':False, 'desc_file':None, 'lines':[]}
        # the sidecar: YAML, else a JSON to convert, else a new YAML
        path_yaml = os.path.join(artifact_path, DESC_FILENAME_BASE + '.yaml')
        path_json = os.path.join(artifact_path, DESC_FILENAME_BASE + '.json')
        data = {}
        convert = None
        for p in (path_yaml, path_json):
            if os.path.isfile(p):
                r = utils.files.safe_read_file(p, fail_on_error = self.fail_on_error, logger = self.logger)
                if r['return']>0: return r
                if isinstance(r.get('data'), dict):
                    data = r['data']
                if p == path_json:
                    convert = p
                break
        new, changed = merge_desc(data, desc, None, lists)
        if changed or convert:
            written = False
            if changed and not convert and not (isinstance(desc, dict) and desc) and os.path.isfile(path_yaml):
                # only the lists changed in an existing YAML: its text stays as it is around them
                try:
                    import yaml
                    with open(path_yaml, 'r', encoding = 'utf-8', newline = '') as f:
                        text = f.read()
                    new_text = text
                    for key, (add, drop) in lists.items():
                        value = data.get(key)
                        old = list(value) if isinstance(value, list) else ([value] if value else [])
                        kept = [i for i in old if not any(cref_matches(i, d) for d in drop or [])]
                        appended = (new.get(key) or [])[len(kept):]
                        test = (lambda v, drop = drop: any(cref_matches(v, d) for d in drop)) if drop else None
                        new_text = edit_list_text(new_text, key, appended, test)
                        if new_text is None:
                            break
                    if new_text is not None and (yaml.safe_load(new_text) or {}) == new:
                        # written next to the file and put in place with one atomic replace, as the engine writes a meta
                        temp_path = path_yaml + '.tmp'
                        with open(temp_path, 'w', encoding = 'utf-8', newline = '') as f:
                            f.write(new_text)
                        utils.files._install_file(temp_path, path_yaml, self.logger)
                        written = True
                except OSError as e:
                    return {'return':1, 'error': f'cannot write {path_yaml}: {e}'}
                except Exception:
                    written = False                     # a text that does not read back: the in-place edit below
            if not written:
                r = utils.files.safe_write_file(path_yaml, data = new, fail_on_error = self.fail_on_error, logger = self.logger,
                                                sort_keys = False, preserve = True)
                if r['return']>0: return r
            if convert:
                try:
                    os.remove(convert)
                except OSError as e:
                    return {'return':1, 'error': f'cannot remove the converted {convert}: {e}'}
        lines = self._desc_change_lines(path_yaml, data, new)
        if con:
            for line in lines:
                print (line)
        return {'return':0, 'changed':changed, 'desc_file':path_yaml, 'lines':lines}

    ############################################################
    def _read_desc(
        self,
        artifact_path: str,  # The artifact's folder.
    ):
        """The artifact's _desc.yaml (else its _desc.json) as a dict; {} when it has none or it does not read."""
        for ext in ('yaml', 'json'):
            p = os.path.join(artifact_path, DESC_FILENAME_BASE + '.' + ext)
            if os.path.isfile(p):
                r = utils.files.safe_read_file(p, fail_on_error = False, logger = self.logger)
                return r['data'] if r['return'] == 0 and isinstance(r.get('data'), dict) else {}
        return {}

    ############################################################
    @staticmethod
    def _desc_change_lines(
        path: str,  # The _desc.yaml.
        before: dict,  # Its content before.
        after: dict,  # Its content after.
    ):
        """What a change of ai_uses and connections added (+) and removed (-), as lines to print."""
        lines = []
        for key, title in ((AI_USES_KEY, 'AI context (ai_uses)'), (CONNECTIONS_KEY, 'Connections')):
            old = before.get(key) if isinstance(before.get(key), list) else ([before[key]] if before.get(key) else [])
            new = after.get(key) if isinstance(after.get(key), list) else ([after[key]] if after.get(key) else [])
            plus = [x for x in new if not any(cref_matches(o, x) for o in old)]
            minus = [x for x in old if not any(cref_matches(n, x) for n in new)]
            if plus or minus:
                lines.append(f'{title} in {path}:')
                lines += ['  + ' + _cref_key(x) for x in plus] + ['  - ' + _cref_key(x) for x in minus]
        return lines

    ############################################################
    def _undo_create(
        self,
        artifact_path: str,  # The folder of the artifact that was being created.
        made_folder: bool,  # True when the create made the folder itself: it goes with everything in it.
        meta_file: str,  # The meta file the create wrote, or None.
        sharding_slices,  # The sharding of the category, to remove the empty parent folders too.
    ):
        """
            Remove what a create that failed made on disk - the folder when the create made it, else only
            the meta it wrote - so that a create whose record could not be written leaves nothing unindexed.

            Args:
                artifact_path (str): The folder of the artifact that was being created.
                made_folder (bool): True when the create made the folder itself.
                meta_file (str | None): The meta file the create wrote.
                sharding_slices (list | None): The sharding of the category.
        """
        import shutil

        if made_folder:
            shutil.rmtree(artifact_path, ignore_errors=True)
            utils.files.safe_delete_directory_if_empty_with_sharding(artifact_path, sharding_slices)

        elif meta_file is not None:
            try:
                os.remove(meta_file)
            except OSError:
                pass

    ############################################################
    def move_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str,  # cMeta artifact(s) with wildcards to be renamed or moved.
        arg2: str,  # New cMeta artifact name and/or new repository.
        tags: str = None,  # Prune source artifacts by tags.
        sort: bool = True,  # Sort artifacts by alias and UID when updating in batch.
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        ignore_errors: bool = False,  # Ignore errors when updating multiple artifacts.
        copy: bool = False,  # If True, copy artifact instead of moving.
    ):
        """
            Rename and/or move artifact(s).

            Args:
                ctx (dict): cMeta context.
                arg1 (str): cMeta artifact(s) with wildcards to be renamed or moved.
                arg2 (str): New cMeta artifact name and/or new repository.
                tags (str | list | None): Prune source artifacts by tags.
                sort (bool): Sort artifacts by alias and UID when updating in batch.
                skip_uids (bool): Skip UIDs when using wildcards.
                ignore_errors (bool): Ignore errors when updating multiple artifacts.
                copy (bool): If True, copy artifact instead of moving.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): All matched artifacts.
                    - **updated_artifacts** (list): Updated artifacts.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import shutil

        # First, find artifact(s)
        con = ctx.get('control',{}).get('con', False)

        ctx['control']['con'] = False

        r = self.find_(ctx, arg1, tags, sort, add_index_file=True, skip_uids=skip_uids, follow_migrated=False)
        if r['return']>0: return r

        artifacts = r['artifacts']

        num_found_artifacts = len(artifacts)

        # Process second argument to decide if it's one artifact to be renames 
        # or multiple artifacts to be moved somewhere ...

        r = utils.names.parse_cmeta_obj(arg2)
        if r['return'] >0: return r

        target_obj_parts = r['obj_parts']

        target_repo_alias = target_obj_parts.get('repo_alias')
        target_repo_uid = target_obj_parts.get('repo_uid')
        target_alias = target_obj_parts.get('alias')
        target_uid = target_obj_parts.get('uid')

        if target_alias is not None and ('*' in target_alias or '?' in target_alias):
            return {'return':1, 'error':'new artifact alias should not have wildcards'}

        if num_found_artifacts > 1 and (target_alias is not None or target_uid is not None):
            return {'return':1, 'error':'only new repository can be specified for multiple source artifacts'}

        if copy and num_found_artifacts > 1 and target_uid is not None:
            return {'return':1, 'error':'can\'t specify the same UID when copying multiple artifacts'}

        if copy:
            command = 'copy'
            command2 = 'copying'
        else:    
            if num_found_artifacts > 1 or target_alias is not None or target_uid is not None:
                command = 'move'
                command2 = 'moving' 
            else:
                command = 'rename'
                command2 = 'renaming'


        # Check if new target repo
        target_repo_path = None
        target_repo_cmeta = None
        if target_repo_alias is not None or target_repo_uid is not None:
            repo_cmeta_ref = {'category_alias': 'repo', 'category_uid': self.cm.cfg['category_repo_uid']}
            
            if target_repo_uid is not None: repo_cmeta_ref['artifact_uid'] = target_repo_uid
            if target_repo_alias is not None: repo_cmeta_ref['artifact_alias'] = target_repo_alias

            r = self.cm.repos.find(repo_cmeta_ref)
            if r['return']>0: return r

            repo_artifacts = r['artifacts']

            if len(repo_artifacts)>1:
                paths = '\n'.join(['* '+a['path'] for a in repo_artifacts])
                return {'return':1, 'error': f'more than one target repo found when {command2} artifacts:\n{paths}'} 

            target_repo_artifact = repo_artifacts[0]
            target_repo_path = target_repo_artifact['full_path']
            target_repo_cmeta = target_repo_artifact['cmeta']

            repo_cmeta_ref_parts = target_repo_artifact['cmeta_ref_parts']

            target_repo_alias = repo_cmeta_ref_parts.get('artifact_alias')
            target_repo_uid = repo_cmeta_ref_parts['artifact_uid']

        # Iterate over artifacts
        tmp_target_uid = None

        category_cmeta = ctx['category_artifact']['cmeta']
        sharding_slices = category_cmeta.get('sharding_slices')
        target_sharding_slices = category_cmeta.get('sharding_slices')
        no_index = category_cmeta.get('no_index', False)

        for artifact in artifacts:
            # Get path to the original original artifact
            path = os.path.normpath(artifact['path'])

            if not os.path.isdir(path):
                return {'return':1, 'error':f'artifact not found in path {path}'}

            cmeta = artifact['cmeta']

            # Copy next dict to update it further
            cmeta_ref_parts = artifact['cmeta_ref_parts'].copy()

            category_alias = cmeta_ref_parts['category_alias']
            category_uid = cmeta_ref_parts['category_uid']

            artifact_alias = cmeta_ref_parts.get('artifact_alias')
            artifact_uid = cmeta_ref_parts['artifact_uid']

            # Get meta of the current repository if no target to get sharding_slices per repo if needed
            if target_repo_cmeta is None:
                tmp_repo_cmeta_ref = {'category_alias': 'repo', 'category_uid': self.cm.cfg['category_repo_uid']}
                
                if cmeta_ref_parts.get('repo_uid') is not None: tmp_repo_cmeta_ref['artifact_uid'] = cmeta_ref_parts['repo_uid']
                if cmeta_ref_parts.get('repo_alias') is not None: tmp_repo_cmeta_ref['artifact_alias'] = cmeta_ref_parts['repo_alias']

                r = self.cm.repos.find(tmp_repo_cmeta_ref)
                if r['return']>0: return r

                tmp_repo_artifacts = r['artifacts']

                if len(tmp_repo_artifacts)>1:
                    paths = '\n'.join(['* '+a['path'] for a in tmp_repo_artifacts])
                    return {'return':1, 'error': f'more than one target repo found when {command2} artifacts:\n{paths}'} 

                tmp_target_repo_artifact = tmp_repo_artifacts[0]
                target_repo_cmeta = tmp_target_repo_artifact['cmeta']

            if category_uid in target_repo_cmeta.get('sharding_slices', {}):
                target_sharding_slices = target_repo_cmeta['sharding_slices'][category_uid]

            if copy:
                if tmp_target_uid is None and target_uid is not None:
                    tmp_target_uid = target_uid
                else:
                    tmp_target_uid = utils.names.generate_cmeta_uid()

                target_uid = tmp_target_uid

            update_uid = target_uid is not None and target_uid != artifact_uid

            if num_found_artifacts == 1:
                if target_repo_path is None and artifact_alias is not None and artifact_alias == target_alias:
                    if not update_uid:
                        return {'return':1, 'error':f"can't {command} artifact {artifact_alias} to itself"}

            # Find path to a category of the original artifact
            normal_path = os.path.normpath(path)

            path_parts = normal_path.split(os.sep)

            if category_alias not in path_parts:
                return {'return':1, 'error':f'category_alias "{category_alias}" not found in path "{path}"'}

            idx = path_parts.index(category_alias)
            path_to_category = os.sep.join(path_parts[:idx+1])

            # Prepare target path
            path_to_target_category = path_to_category if target_repo_path is None else os.path.join(target_repo_path, category_alias)

            if target_alias is not None:
                target_artifact_dir = target_alias
            else:
                if artifact_alias is not None:
                    target_artifact_dir = artifact_alias
                elif target_uid is not None:
                    target_artifact_dir = target_uid
                else:
                    target_artifact_dir = artifact_uid

            target_sharding_slices_num = len(target_sharding_slices) if target_sharding_slices else 0

            if target_sharding_slices is not None:
                r = utils.files.apply_sharding_to_path(path_to_target_category, target_artifact_dir, target_sharding_slices)
                if r['return']>0: return r

                path_to_target_artifact = r['sharded_path']
            else:
                path_to_target_artifact = os.path.join(path_to_target_category, target_artifact_dir)

            if path == path_to_target_artifact and not update_uid:
                return {'return':1, 'error':f"can't {command} artifact {artifact_alias} to itself"}

            if os.path.isdir(path_to_target_artifact) and (copy or not update_uid):
                return {'return':1, 'error':f"artifact already exists in path {path_to_target_artifact}"}

            if update_uid:
                cmeta_ref_parts['artifact_uid'] = target_uid
            if target_alias is not None:
                cmeta_ref_parts['artifact_alias'] = target_alias
            if target_repo_path is not None:
                for key in ['repo_alias', 'repo_uid']:
                    if key in cmeta_ref_parts:
                        del(cmeta_ref_parts[key])

                if target_repo_alias is not None:
                    cmeta_ref_parts['repo_alias'] = target_repo_alias
                if target_repo_uid is not None:
                    cmeta_ref_parts['repo_uid'] = target_repo_uid

            # Move/copy artifact
            if con:
                print (command2.capitalize() + f" {path} -> {path_to_target_artifact} ...")

            if not os.path.isdir(path_to_target_artifact):
                if target_sharding_slices is not None:
                    # Check if target sub-directories exists:
                    sub_path_to_target_artifact = os.path.dirname(path_to_target_artifact)
                    os.makedirs(sub_path_to_target_artifact, exist_ok=True)

                try:
                    if copy:
                        shutil.copytree(path, path_to_target_artifact, copy_function=shutil.copy2, ignore_dangling_symlinks=False)
                    else:
                        shutil.move(path, path_to_target_artifact)
                except Exception as e:
                    return {'return':1, 'error': f'error {command2} artifact {path} to {path_to_target_artifact} - {e}'}

            # Update meta if update_uid
            if update_uid:
                # Read real meta file
                found_cmeta_filename = None
                for ext in ['json', 'yaml']:
                    cmeta_filename = os.path.join(path_to_target_artifact, self.cm.cfg['meta_filename_base'] + '.' + ext)

                    if os.path.isfile(cmeta_filename):
                        found_cmeta_filename = cmeta_filename
                        break

                if found_cmeta_filename is None:
                    if not ignore_errors:
                        return {'return':1, 'error':f'artifact meta file not found in "{path_to_target_artifact}"'}

                if found_cmeta_filename is not None:
                   # Safe updating of meta data
                   r = utils.files.safe_read_file(found_cmeta_filename, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                   if r['return']>0: return r

                   cmeta = r['data']
                   cmeta_file_lock = r['file_lock']

                   cmeta['artifact'] = target_uid

                   from datetime import datetime, timezone

                   if 'creation_timestamp' not in cmeta:
                       cmeta['creation_timestamp'] = datetime.now(timezone.utc).isoformat()
                   else:
                       cmeta['last_update_timestamp'] = datetime.now(timezone.utc).isoformat()

                   r = utils.files.safe_write_file(found_cmeta_filename, cmeta, file_lock=cmeta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger, preserve=True)
                   if r['return']>0: return r

            # Delete root if empty
            if not copy:
                r = utils.files.safe_delete_directory_if_empty_with_sharding(path, sharding_slices)
                # Ignore errors when deleting empty directories during move

            # Update index
            if not no_index:
                artifact_index_file = artifact['index_file']

                kwargs = {}
                if not copy:
                    kwargs.update(original_alias=artifact_alias, original_uid=artifact_uid)

                if target_sharding_slices_num >0:
                    kwargs['sharding_slices_num'] = target_sharding_slices_num

                r = self.cm.repos.add_to_index(cmeta, cmeta_ref_parts, path_to_target_artifact, **kwargs)
                if r['return']>0: return r

        return {'return':0, 'artifacts': artifacts}

    ############################################################
    def copy__(
        self,
        params: dict,  # cMeta params.
    ):
        """
            Copy artifact(s).

            @base.move_(**params, copy=True)

            Args:
                params (dict): cMeta params.

            Returns:
                dict: A cMeta dictionary (see move_ for details).

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        p = self._prepare_input_from_params(params)

        p['command'] = 'move'
        p['copy'] = True

        return self.cm.access(p)

    ############################################################
    def migrate_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str,  # The artifact to migrate: alias, UID or alias,UID (one artifact, no wildcards).
        arg2: str,  # Its new alias, optionally in another repository: [repo:]alias.
        tags: str = None,  # Prune the source artifact by tags.
    ):
        """
            Rename an artifact (or move it to another repository under a new alias) and leave a
            stub under its old alias that points to it.

            The artifact keeps its UID, as with `move`, so `alias,UID` and UID references to it keep
            working. The stub gets the old alias, a new UID and two keys: `migrated_to`, the new
            `alias,UID`, and `migrated_when`, the date and time of the migration (ISO 8601, UTC).
            A lookup of the old alias alone - `cx task run <old>`, `cx <category> find <old>` - then
            follows the stub to the artifact and prints a notice once. Commands that change
            artifacts (update, tags, move, delete) act on the stub itself, so `cx <category> rm <old>`
            removes it when nobody uses the old alias any more.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): The artifact to migrate: alias, UID or alias,UID (one artifact, no wildcards).
                arg2 (str): Its new alias, optionally in another repository: [repo:]alias.
                tags (str | list | None): Prune the source artifact by tags.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifact** (dict): The migrated artifact (its new alias, the same UID).
                    - **stub_path** (str): Path of the stub left under the old alias.
                    - **stub_meta** (dict): Meta of the stub.
                    - **migrated_to** (str): The new `alias,UID`.
                    - **migrated_when** (str): When, ISO 8601 in UTC.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from datetime import datetime, timezone

        con = ctx.get('control',{}).get('con', False)
        ctx['control']['con'] = False

        if arg1 is None or arg1 == '' or arg2 is None or arg2 == '':
            return {'return':1, 'error':'migrate needs the artifact and its new alias: migrate <artifact> [repo:]<new alias>'}

        if '*' in arg1 or '?' in arg1:
            return {'return':1, 'error':'migrate takes one artifact - no wildcards'}

        # The source, exactly as named (a stub is not followed here)
        r = self.find_(ctx, arg1, tags, follow_migrated=False)
        if r['return']>0: return r

        artifacts = r['artifacts']
        if len(artifacts) != 1:
            return {'return':1, 'error':f'"{arg1}" names {len(artifacts)} artifacts - give its UID or repo:alias'}

        artifact = artifacts[0]
        cmeta = artifact.get('cmeta') or {}
        parts = artifact['cmeta_ref_parts']

        old_alias = parts.get('artifact_alias')
        artifact_uid = parts['artifact_uid']

        if cmeta.get('migrated_to'):
            return {'return':1, 'error':f'"{old_alias}" is already a migration stub (migrated to "{cmeta["migrated_to"]}")'}

        if old_alias is None or old_alias == '':
            return {'return':1, 'error':f'artifact {artifact_uid} has no alias, so there is no old alias to keep - use move'}

        # The target: a new alias, the same UID
        r = utils.names.parse_cmeta_obj(arg2)
        if r['return']>0: return r

        target_parts = r['obj_parts']
        new_alias = target_parts.get('alias')

        if target_parts.get('uid') is not None:
            return {'return':1, 'error':'migrate keeps the UID of the artifact - give the new alias without a UID'}

        if new_alias is None or new_alias == '':
            return {'return':1, 'error':'migrate needs a new alias: migrate <artifact> [repo:]<new alias>'}

        if '*' in new_alias or '?' in new_alias:
            return {'return':1, 'error':'the new alias should not have wildcards'}

        if new_alias.lower() == old_alias.lower():
            return {'return':1, 'error':'the new alias is the old one - to move the artifact to another repository under the same alias, use move'}

        # Move it with the category's own "move", so that the category's rules apply. The source is
        # given as alias,UID: the UID finds exactly this artifact, and the alias shows "move" that
        # this is a rename (the "category" category, for one, refuses to rename an alias)
        r = self.cm.access({'category': dict(ctx['category']),
                            'command': 'move',
                            'arg1': f'{old_alias},{artifact_uid}',
                            'arg2': arg2,
                            'con': False})
        if r['return']>0: return r

        r = self.find_(ctx, artifact_uid, follow_migrated=False)
        if r['return']>0: return r

        moved = r['artifacts'][0]
        moved_alias = moved['cmeta_ref_parts'].get('artifact_alias', new_alias)

        migrated_to = f'{moved_alias},{artifact_uid}'
        migrated_when = datetime.now(timezone.utc).isoformat(timespec='seconds')

        # The stub: the old alias, a new UID, in the repository the artifact was in, with the
        # base "create" (a category's own create may scaffold a full artifact)
        stub_repo = parts.get('repo_uid') or parts.get('repo_alias')
        stub_name = f'{stub_repo}:{old_alias}' if stub_repo else old_alias

        stub_yaml = os.path.isfile(os.path.join(moved['path'], self.cm.cfg['meta_filename_base'] + '.yaml'))

        r = self.cm.access({'category': dict(ctx['category']),
                            'command': 'create',
                            'base': True,
                            'arg1': stub_name,
                            'meta': {'migrated_to': migrated_to, 'migrated_when': migrated_when},
                            'yaml': stub_yaml,
                            'con': False})
        if r['return']>0:
            return {'return':1, 'error':f'"{old_alias}" was moved to "{migrated_to}" but its stub could not be created: {r["error"]}'}

        stub_path = r['path']
        stub_meta = r['meta']

        if con:
            print (f'Migrated "{old_alias}" to "{migrated_to}": {moved["path"]}')
            print (f'Stub left under "{old_alias}" (UID {stub_meta.get("artifact")}): {stub_path}')
            print (f'  migrated_to:   {migrated_to}')
            print (f'  migrated_when: {migrated_when}')

        return {'return':0, 'artifact': moved, 'stub_path': stub_path, 'stub_meta': stub_meta,
                'migrated_to': migrated_to, 'migrated_when': migrated_when}

    ############################################################
    def index(
        self,
        params: dict,  # cMeta params.
    ):
        """
            Index artifact(s).

            @base.create_(**params, index=True)

            Args:
                params (dict): cMeta params.

            Returns:
                dict: A cMeta dictionary (see move_ for details).

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        p = self._prepare_input_from_params(params)

        p['command'] = 'create'
        p['index'] = True

        return self.cm.access(p)

    ############################################################
    def reindex_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias, UID, alias,UID or repo:alias (wildcards allowed); nothing names every artifact of the category.
        tags: str = None,  # Prune the artifacts by tags, as in find (a tag with a leading "-" excludes).
        sort: bool = True,  # Sort the artifacts by alias and UID.
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        ignore_errors: bool = False,  # Go on past an artifact that cannot be reindexed and report it at the end.
    ):
        """
            Refresh the index record(s) of artifact(s) from their folders, changing no file.

            The meta file of each artifact is read from its folder on disk and the artifact's record in the
            index of the category is rewritten from it: the alias is the folder's name, every other alias
            that still pointed at the artifact's UID is dropped, and the path, the meta and the sharding
            depth are what a full `cx --reindex` records. The meta file is read, never written (an empty
            `update` rewrites it). Use it after a meta file was edited by hand, after a folder was renamed,
            moved or copied in from another machine, or when a lookup looks stale - instead of the whole
            `cx --reindex`.

            The artifact may be named by its alias, UID, alias,UID or repo:alias, with wildcards; nothing
            names every artifact of the category. A folder the index does not know yet (made or renamed by
            hand) is found on disk in the repositories; an artifact whose indexed folder is gone is looked
            for by its UID in its repository. No folder is touched, and the only record ever removed is
            that of an artifact whose folder, still there, holds another artifact now (replaced by hand) -
            said in the output. A folder that cannot be found, a meta without a valid `artifact` UID, or a
            UID found in two existing folders is an error, and the index is left as it was
            (`--ignore_errors` reindexes the other artifacts and reports these).

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias, UID, alias,UID or repo:alias (wildcards allowed); nothing
                    names every artifact of the category.
                tags (str | list | None): Prune the artifacts by tags, as in find (a leading "-" excludes).
                sort (bool): Sort the artifacts by alias and UID.
                skip_uids (bool): Skip UIDs when using wildcards.
                ignore_errors (bool): Go on past an artifact that cannot be reindexed and report it at the end.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error (16: nothing found).
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): The reindexed artifacts, as their new index records.
                    - **dropped_aliases** (dict): Per UID, the (lowercase) aliases dropped because they were not the folder's name.
                    - **dropped_records** (list): The records removed because their folder holds another artifact now (`ref`, `path`, `now`).
                    - **errors** (list): With `ignore_errors`, one dict per artifact that could not be reindexed (`ref`, `path`, `error`).

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx.get('control',{}).get('con', False)

        ctx['control']['con'] = False

        category_cmeta = ctx['category_artifact']['cmeta']
        category_cmeta_ref_parts = ctx['category_artifact']['cmeta_ref_parts']

        category_alias = category_cmeta_ref_parts['artifact_alias']
        category_uid = category_cmeta_ref_parts['artifact_uid']

        if category_cmeta.get('no_index', False):
            return {'return':1, 'error':f'category "{category_alias}" is not indexed (no_index) - there is nothing to reindex'}

        # The reference: an alias (with wildcards), a UID, both, a repository
        artifact_obj_parts = {}

        if arg1 is not None and str(arg1).strip() != '':
            r = utils.names.parse_cmeta_obj(arg1, key = "artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            artifact_obj_parts = r['obj_parts']

        artifact_alias = artifact_obj_parts.get('artifact_alias')
        artifact_uid = artifact_obj_parts.get('artifact_uid')
        artifact_repo_alias = artifact_obj_parts.get('artifact_repo_alias')
        artifact_repo_uid = artifact_obj_parts.get('artifact_repo_uid')

        if tags is not None:
            r = utils.common.normalize_tags(tags, fail_on_error = self.fail_on_error)
            if r['return']>0: return r

            tags = r['tags']

        # The repositories to look in: the one named, else all of them
        repo_uids = None

        if (artifact_repo_alias is not None and artifact_repo_alias != '') or (artifact_repo_uid is not None and artifact_repo_uid != ''):
            r = self.cm.repos.find_in_index('repo', self.cm.cfg['category_repo_uid'], artifact_repo_alias, artifact_repo_uid, only_uids=True, skip_uids=skip_uids)
            if r['return']>0: return r

            repo_uids = r['artifact_uids']

        def _norm(path):
            return os.path.normcase(os.path.normpath(os.path.abspath(path)))

        def _same_folder(path1, path2):
            # The same folder: the same path, or two spellings of one folder on a case-insensitive file system
            if _norm(path1) == _norm(path2):
                return True
            try:
                return os.path.isdir(path1) and os.path.isdir(path2) and os.path.samefile(path1, path2)
            except OSError:
                return False

        def _ref(parts):
            alias = parts.get('artifact_alias')
            uid = parts.get('artifact_uid', '')
            return f'"{alias}" ({uid})' if alias else uid

        def _uid_in_folder(path):
            # The UID the meta file of a folder names, or None (no folder, no meta, no valid UID)
            if not os.path.isdir(path):
                return None
            r = utils.files.safe_read_yaml_or_json(os.path.join(path, self.cm.cfg['meta_filename_base']), fail_on_error=False, logger=self.logger)
            if r['return']>0 or not isinstance(r.get('data'), dict):
                return None
            r = utils.names.parse_cmeta_name(r['data'].get('artifact'))
            if r['return']>0:
                return None
            uid = r['name'].get('uid')
            return uid if uid is not None and utils.names.is_valid_cmeta_uid(uid) else None

        # 1. The folders on disk that the reference names: the real folder name and the meta as it is now,
        #    built as the full reindex builds its records
        r = self.cm.repos.find_in_file_system(category_cmeta, category_alias, category_uid, artifact_alias, artifact_uid, repo_uids = repo_uids)
        if r['return']>0: return r

        entries = [e for e in r['artifacts'] if self._match_tags(e['cmeta'].get('tags', []), tags)]

        # 2. The records the index holds for the reference (a migration stub is reindexed as itself)
        r = self.find_(ctx, arg1, tags, sort=False, add_index_file=True, skip_uids=skip_uids, follow_migrated=False)
        if r['return']>0 and r['return']!=16: return r

        indexed = r.get('artifacts', []) if r['return'] == 0 else []

        if len(entries) == 0 and len(indexed) == 0:
            x = f'"{arg1}"' if arg1 is not None and str(arg1).strip() != '' else 'artifacts'
            return {'return':16, 'error':f'{category_alias} {x} not found in the index or on disk'}

        seen_paths = {}
        seen_uids = {}

        for e in entries:
            seen_paths[_norm(e['path'])] = e
            seen_uids.setdefault(e['cmeta_ref_parts']['artifact_uid'], []).append(e)

        errors = []
        stale = []

        # An indexed artifact that was not found on disk by the reference: its folder was renamed or moved
        # by hand, replaced by another artifact, or it is gone - look for its UID in its repository
        for a in indexed:
            parts = a['cmeta_ref_parts']
            uid = parts['artifact_uid']

            if uid in seen_uids:
                continue

            xrepo_uids = [parts['repo_uid']] if parts.get('repo_uid') else None

            r = self.cm.repos.find_in_file_system(category_cmeta, category_alias, category_uid, None, uid, repo_uids = xrepo_uids)
            if r['return']>0: return r

            found = r['artifacts']

            if len(found) == 0:
                other = seen_paths.get(_norm(a['path']))

                if other is not None:
                    # The folder is still there but holds another artifact now (replaced by hand): the record
                    # is provably stale, and a "delete" of it would remove the other artifact's folder - it is
                    # dropped, as a full reindex would drop it, and said so
                    stale.append({'ref': _ref(parts), 'path': a['path'], 'uid': uid,
                                  'index_file': a.get('index_file'),
                                  'alias_lowercase': parts.get('artifact_alias_lowercase', parts.get('artifact_alias')),
                                  'other': _ref(other['cmeta_ref_parts'])})
                elif os.path.isdir(a['path']):
                    # The folder is there, but its meta file cannot be read or has no valid artifact UID
                    errors.append({'ref': _ref(parts), 'path': a['path'],
                                   'error': f'{category_alias} artifact {_ref(parts)} is indexed at "{a["path"]}", and the folder is there, but its meta file '
                                            f'cannot be read or has no valid "artifact" UID - fix the file, then reindex'})
                else:
                    errors.append({'ref': _ref(parts), 'path': a['path'],
                                   'error': f'{category_alias} artifact {_ref(parts)} is indexed at "{a["path"]}" but no folder with its UID was found in its repository - '
                                            f'if it was moved elsewhere, reindex it by its new name; if it was deleted, remove it from the index with "delete"'})
                continue

            if len(found) > 1:
                paths = ', '.join('"' + f['path'] + '"' for f in found)
                errors.append({'ref': _ref(parts), 'path': a['path'],
                               'error': f'{category_alias} artifact {_ref(parts)} is in {len(found)} folders with the same UID: {paths} - give all but one a new UID first'})
                continue

            e = found[0]

            seen_paths[_norm(e['path'])] = e
            seen_uids.setdefault(uid, []).append(e)
            entries.append(e)

        # 3. Check everything before writing anything: one folder per UID, and a UID that the index holds at
        #    another folder that still exists is left alone (two folders with one UID)
        r = self.cm.repos.find_in_index(category_alias, category_uid, only_uids=True, skip_uids=True)
        if r['return']>0: return r

        index_uids = r.get('index', {}).get(self.cm.repos.KEY_INDEX_UIDS, {})

        to_write = []

        for uid in seen_uids:
            uid_entries = seen_uids[uid]
            parts = uid_entries[0]['cmeta_ref_parts']

            if len(uid_entries) > 1:
                paths = ', '.join('"' + x['path'] + '"' for x in uid_entries)
                errors.append({'ref': _ref(parts), 'path': uid_entries[0]['path'],
                               'error': f'{category_alias} artifact {_ref(parts)} is in {len(uid_entries)} folders with the same UID: {paths} - give all but one a new UID first'})
                continue

            e = uid_entries[0]

            record = index_uids.get(uid)
            if record is not None:
                old_path = record.get('path', '')

                # A conflict only when the folder the index knows still holds this very UID
                if old_path and not _same_folder(old_path, e['path']) and _uid_in_folder(old_path) == uid:
                    errors.append({'ref': _ref(parts), 'path': e['path'],
                                   'error': f'{category_alias} artifact {_ref(parts)} is indexed at "{old_path}", which still exists, while the same UID is in "{e["path"]}" - '
                                            f'two folders with one UID: give one of them a new UID (or remove it), then reindex'})
                    continue

            to_write.append(e)

        if len(errors) > 0 and not ignore_errors:
            if len(errors) == 1:
                return {'return':1, 'error': errors[0]['error']}
            return {'return':1, 'error': 'nothing was reindexed:\n' + '\n'.join('* ' + x['error'] for x in errors)}

        if sort:
            to_write.sort(key=lambda e: (str(e['cmeta_ref_parts'].get('artifact_alias', '')).lower(), e['cmeta_ref_parts']['artifact_uid']))

        # 4. Rewrite the records, each in one locked write that also drops the stale aliases of its UID
        reindexed = []
        dropped_aliases = {}

        for e in to_write:
            parts = e['cmeta_ref_parts']
            uid = parts['artifact_uid']

            r = self.cm.repos.add_to_index(e['cmeta'], parts, e['path'], original_uid = uid,
                                           sharding_slices_num = e.get('sharding_slices_num', 0), clean_aliases = True)
            if r['return']>0: return r

            record = {'path': e['path'], 'cmeta': e['cmeta'], 'cmeta_ref_parts': parts}
            if e.get('sharding_slices_num'):
                record['sharding_slices_num'] = e['sharding_slices_num']

            reindexed.append(record)

            if len(r.get('dropped_aliases', [])) > 0:
                dropped_aliases[uid] = r['dropped_aliases']

            if con:
                print (f'Reindexed {category_alias} {_ref(parts)}: {e["path"]}')
                for x in r.get('dropped_aliases', []):
                    print (f'  dropped the alias "{x}"')

        # 5. The records of artifacts whose folder now holds another artifact
        dropped_records = []

        for x in stale:
            if x['index_file']:
                r = self.cm.repos.remove_from_index(x['index_file'], x['uid'], x['alias_lowercase'])
                if r['return']>0: return r

            dropped_records.append({'ref': x['ref'], 'path': x['path'], 'now': x['other']})

            if con:
                print (f'Dropped the record of {category_alias} {x["ref"]}: its folder {x["path"]} now holds {x["other"]}')

        if con:
            for x in errors:
                print (f'Skipped: {x["error"]}')

        return {'return':0, 'artifacts': reindexed, 'dropped_aliases': dropped_aliases, 'dropped_records': dropped_records, 'errors': errors}

    ############################################################
    def _match_tags(
        self,
        ctags,  # The tags of an artifact's meta.
        tags,  # Normalized tags to match (a leading "-" excludes); None or empty matches everything.
    ):
        """
            Match the tags of an artifact as `find` does: every tag given must be present, none of the
            excluded ones (a leading "-"), case-insensitively.
        """

        if tags is None or len(tags) == 0:
            return True

        if type(ctags) != list:
            return False

        ctags_lower = [str(t).lower() for t in ctags]

        for tag in tags:
            tag = str(tag)
            if tag.startswith('-'):
                if tag[1:].lower() in ctags_lower:
                    return False
            elif tag.lower() not in ctags_lower:
                return False

        return True

    ############################################################
    def get_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Tags to add to the artifact (used during creation).
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        yaml: bool = False,  # Save/output metadata as YAML instead of JSON.
        meta: dict = {},  # Initial metadata dictionary (used during creation).
        virtual: bool = False,  # Virtual artifact created only in index (used during creation).
        path: str = None,  # Use this path for artifact (used during creation).
        show_path: bool = False,  # Print path instead of meta
        load_files = [],  # Value for load files.
        desc: dict = None,  # Keys merged into the artifact's _desc.yaml (as add / update).
        ai_uses = None,  # The AI context (as add / update): names, "-name" removes; True = ask.
        ai = None,  # The short form of ai_uses (-ai).
        connect = None,  # Connect both ways (as add / update).
        connect_to = None,  # Connect this artifact to them (its own _desc only).
        ct = None,  # The short form of connect_to (--ct).
        dt = None,  # The date in front of the alias (-dt today's, --dt=<date>): what is read, and what is made when nothing is read.
    ):
        """
            Get artifact meta. Read if exists, create and read if doesn't exist. The _desc.yaml options of add
            and update (desc, ai_uses / ai, connect, connect_to / ct) go to the create of a new artifact and to
            an update of one that exists (2026-11-03: the categories that made dated aliases added through get,
            and "cx work add <name> -ai" failed with "unexpected keyword argument 'ai'"). With `dt` the alias is
            read and made with its date in front (_alias_with_date): "get <name> -dt" reads 20261105.<name> or
            makes it, the same name whether it exists or not.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Tags to add to the artifact (used during creation).
                skip_uids (bool): Skip UIDs when using wildcards.
                yaml (bool): Save/output metadata as YAML instead of JSON.
                meta (dict): Initial metadata dictionary (used during creation).
                virtual (bool): Virtual artifact created only in index (used during creation).
                path (str | None): Use this path for artifact (used during creation).
                show_path (bool): Print path instead of meta
                load_files: Value for load files.
                dt (bool | str | None): The date in front of the alias: True today's, a text that date.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifact** (dict): Matched artifact.
                    - **cmeta** (dict): Artifact metadata.
                    - **created** (bool): True if artifact was created, False if it already existed.
                    - **warnings** (list): The warning of a dated category when the artifact was created with
                      an alias without a date (create_); empty otherwise.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # meta and desc take keys, whether the artifact is read or made (update_ and create_ say the same)
        meta, r = utils.cli.keys_param('meta', meta, {})
        if r: return r
        desc, r = utils.cli.keys_param('desc', desc, None)
        if r: return r

        # Try to read the artifact first
        con = ctx.get('control',{}).get('con', False)

        if con and show_path:
            import copy
            ctx = copy.deepcopy(ctx)
            ctx['control']['con'] = False

        # The alias with its date in front: read under that name, made under it when nothing is read
        if dt:
            r = self._alias_with_date(ctx, arg1, dt)
            if r['return'] >0: return r

            arg1 = r['arg1']

        r = self.read_(ctx, arg1, tags=tags, skip_uids=skip_uids, load_files=load_files)

        desc_options = {k: v for k, v in (('desc', desc), ('ai_uses', ai_uses), ('ai', ai), ('connect', connect),
                                          ('connect_to', connect_to), ('ct', ct)) if v is not None}

        # If artifact exists, return it (with the _desc.yaml options made on it)
        if r['return'] == 0:
            r['created'] = False
            r['warnings'] = []
            if desc_options:
                ru = self.update_(ctx, arg1, skip_uids=skip_uids, **desc_options)   # (tags: to add on a create, not a filter)
                if ru['return'] > 0:
                    return ru
                r['desc_changes'] = ru.get('desc_changes') or []

        else:

            # If error is not "artifact not found", return the error
            if r['return'] != 16:
                return r

            # Artifact doesn't exist, create it
            rc = self.create_(ctx, arg1, tags=tags, meta=meta, yaml=yaml, virtual=virtual, path=path, **desc_options)
            if rc['return'] > 0:
                return rc

            # Read the newly created artifact
            r = self.read_(ctx, arg1, tags=tags, skip_uids=skip_uids, yaml=yaml, load_files=load_files)
            if r['return'] > 0:
                return r

            r['created'] = True
            r['desc_changes'] = rc.get('desc_changes') or []
            r['warnings'] = rc.get('warnings') or []

        if con and show_path:
            print (r['artifact']['path'])

        return r

    ############################################################
    def set_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID.
        tags: str = None,  # Tags to add to the artifact (used during creation).
        skip_uids: bool = False,  # Skip UIDs when using wildcards.
        yaml: bool = False,  # Save/output metadata as YAML instead of JSON.
        meta: dict = {},  # Initial metadata dictionary (used during creation).
        virtual: bool = False,  # Virtual artifact created only in index (used during creation).
        path: str = None,  # Use this path for artifact (used during creation).
        show_path: bool = False,  # Print path instead of meta
        dt = None,  # The date in front of the alias (-dt today's, --dt=<date>): what is read, and what is made when nothing is read.
    ):
        """
            Set artifact meta. Update and read if exists, create and read if doesn't exist. With `dt` the alias
            is read and made with its date in front, as get.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID.
                tags (str | list | None): Tags to add to the artifact (used during creation).
                skip_uids (bool): Skip UIDs when using wildcards.
                yaml (bool): Save/output metadata as YAML instead of JSON.
                meta (dict): Initial metadata dictionary (used during creation).
                virtual (bool): Virtual artifact created only in index (used during creation).
                path (str | None): Use this path for artifact (used during creation).
                show_path (bool): Print path instead of meta
                dt (bool | str | None): The date in front of the alias: True today's, a text that date.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
                    - **artifact** (dict): Matched artifact.
                    - **cmeta** (dict): Artifact metadata.
                    - **created** (bool): True if artifact was created, False if it already existed.
                    - **warnings** (list): The warning of a dated category when the artifact was created with
                      an alias without a date (create_); empty otherwise.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # Try to read the artifact first
        con = ctx.get('control',{}).get('con', False)

        import copy
        ctx = copy.deepcopy(ctx)

        ctx['control']['con'] = False

        # The alias with its date in front: read under that name, made under it when nothing is read
        if dt:
            r = self._alias_with_date(ctx, arg1, dt)
            if r['return'] >0: return r

            arg1 = r['arg1']

        r = self.read_(ctx, arg1, tags=tags, skip_uids=skip_uids)

        # If artifact exists, return it
        created = False
        warnings = []

        if r['return'] == 0:
            # Artifact doesn't exist, create it
            r = self.update_(ctx, arg1, tags=tags, meta=meta)
            if r['return'] > 0:
                return r

        else:
            # If error is not "artifact not found", return the error
            if r['return'] != 16:
                return r

            # Artifact doesn't exist, create it
            r = self.create_(ctx, arg1, tags=tags, meta=meta, yaml=yaml, virtual=virtual, path=path)
            if r['return'] > 0:
                return r

            created = True
            warnings = r.get('warnings') or []

        # Read the newly created artifact
        if con and not show_path:
            ctx['control']['con'] = True

        r = self.read_(ctx, arg1, tags=tags, skip_uids=skip_uids, yaml=yaml)
        if r['return'] > 0:
            return r

        r['created'] = created
        r['warnings'] = warnings

        if con and show_path:
            print (r['artifact']['path'])

        return r
