# Common commands and tips

A short, practical cheatsheet for everyday work with the `cx` CLI. Full
explanations live in [using-cmeta.md](using-cmeta.md); this page is the
"what do I type?" reference.

`cx` is the short alias for `cmeta` — both accept the same arguments.

---

## Discovery — finding your way around

```bash
cx --help                        # framework help + all global flags
cx repo list                     # which content repositories are plugged in
cx category list                 # which categories (plugins) exist
cx <category> --help             # commands available in a category
cx <category> <command> --help   # flags/args for one command
cx --version                     # version + check for a newer release
```

Global CLI aliases: `add→create`, `rm→delete`, `ls→list`, `search→find`,
`mv→move`, `cp→copy`, `ren`/`rename`→`move`, `load→read`.

---

## `cx .` — work from the current directory

**The single biggest everyday time-saver.** Put `.` where the category would
go, and cMeta walks up from the current directory to detect the enclosing
**repo**, the **category**, and — if you are inside one — the **artifact**. No
more typing repo and category names when you are already standing in them.

Inside a **category** directory:

```bash
cd <repo>/log
cx . add xyz                 # create artifact 'xyz' here
cx . find                    # list artifacts in this category/repo
cx . find --tags=demo        # ...filtered by tags
```

Inside an **artifact** directory:

```bash
cd <repo>/log/xyz
cx . info                    # what am I standing in? (see below)
cx . load                    # print this artifact's meta
cx . update --meta.description="..."
cx .                         # no command -> defaults to 'info'
```

Pass an explicit category after `.` to override detection:
`cx . <category> <command>`.

### `cx . info` — the "where am I?" command

Prints the artifact path, the full **cRef**, and the alias + UID of the
artifact, its category and its repo — and copies the cRef to your clipboard:

```console
$ cx . info
Artifact path: ...\cmeta\internal-repo\category\config

cRef=category,dd9ea50e7f76467f::config,cc6bfe174be847ed

artifact_alias: config
artifact_uid:   cc6bfe174be847ed
category_alias: category
category_uid:   dd9ea50e7f76467f
repo_alias:     internal
repo_uid:       21f6ce28893e4de8
```

| Flag | Effect |
|------|--------|
| *(default)* | Copy the **cRef** to the clipboard. |
| `--clip-` | Don't touch the clipboard. |
| `--url` | Also print and copy a shareable **cRef URL**. |
| `--name` | Copy the artifact **name** instead of the cRef. |
| `--jf=<file>` | Write the full result (including complete metadata) as JSON. |

`cx <category> info <alias>` does the same without `cd`-ing anywhere.

---

## Artifacts

```bash
cx <category> ls                       # list all artifacts
cx <category> ls --tags=demo,gpu       # tag filter (AND-match)
cx <category> find <alias-or-uid>      # resolve from the index
cx <category> read <alias>             # print the artifact's meta
cx <category> info <alias>             # path + cRef (+ clipboard)

cx <category> add <alias> --tags=t1,t2 --yaml
cx <category> add <repo>:<alias> --meta.owner="me"
cx <category> update <alias> --meta.description="..."
cx <category> tags <alias> --add=t1,t2 --remove=t3
cx <category> mv <alias> <new-alias>
cx <category> rm <alias>
```

`find` is the best universal lister — unlike a bare `ls` it also prunes by tags
and other filters.

### Searching *across* categories

`cx <category> find` only looks in one category. To search everywhere — or when
you don't know which category something lives in — use a cRef with wildcards:

```bash
cx utils find_by_cid "config"            # bare name -> implicit '*::' -> search all categories
cx utils find_by_cid "*::*server*"       # any artifact containing 'server', any category
cx utils find_by_cid "cserver*::*"       # everything in categories starting with 'cserver'
cx utils find_by_cid "*::*" --tags=demo  # ...and filter by tags
```

Prints the path of each match. Handy flags: `--tags=`, `--skip_non_indexed`
(skip `no_index` categories — faster), `--web` (decode a `cmeta:///?…` link),
`--ask` (prompt for the CID), `--far` (open the first hit in FAR).

This is how you find **related artifacts across categories** — e.g. a task, a
tool and a result sharing an alias or tag.

---

## UIDs

```bash
cx utils uid                 # 16-hex cMeta UID, also copied to the clipboard
cx utils uid --clipboard-    # print only
cx utils uuid                # UUID4
cx utils hash_password       # asks without echo -> the digest for a config password
```

Needed when you create an artifact by hand (`mkdir` + `_cmeta.yaml`) rather
than with `cx <category> add`. Afterwards, register it so it enters the index:

```bash
cx <category> index <repo>:<artifact>
```

---

## Repositories

```bash
cx repo list
cx repo get cmeta://<name>                       # default cTuning zip mirror
cx repo get <alias> --url=https://github.com/<org>/<repo>
cx repo get <alias> --url=<git-url> --checkout=main
cx repo get <alias> --path=<local-path> --local  # register an existing folder
cx repo pull <alias>
cx repo status <alias>
cx repo unplug <alias>                           # detach without deleting
cx repo space                                    # disk usage
```

---

## Configuration

```bash
cx config show                                   # all config artifacts
cx config get <name>
cx config set <name> --meta.<key>=<value>        # deep-merges, creates if missing
cx config unset <name> --meta.<key>
```

Common ones: `default` (framework defaults), `task` (caches, version checks),
`cserver` (local web app), `ctuning_server` (platform access). See
[configuration.md](configuration.md).

---

## Index and cache

```bash
cx <category> index <repo>:<artifact>   # register ONE hand-made artifact
cx <category> update <repo>:<artifact>  # refresh index after editing its meta
cx --reindex                            # rebuild everything (slow — last resort)

cx cache show
cx cache clean
cx cache delete <alias-or-uid>
```

Payload-only edits (`api/`, `files/`, `src/`, `_desc.yaml`) need **no** reindex
— the index tracks meta, not content.

Categories holding very many artifacts can spread them into sub-directories
(`sharding_slices`) and/or skip the index entirely (`no_index: true`) — see
[using-cmeta.md §12](using-cmeta.md#12-scaling-a-category-to-very-many-artifacts).

---

## Output, scripting and debugging

```bash
cx <cat> <cmd> --json                   # print the return dict (console output first!)
cx <cat> <cmd> --jf=out.json            # clean JSON to a file — use this in scripts
cx <cat> <cmd> --quiet                  # auto-accept prompts (unattended)
cx <cat> <cmd> --verbose                # verbose progress

cx <cat> <cmd> --debug                  # DEBUG logging + raise on first error
cx <cat> <cmd> --fail                   # raise on first error only
cx <cat> <cmd> --log_file=cmeta.log
cx <cat> <cmd> --pause_if_error         # keep the console open (double-clicked .bat)

cx <cat> <cmd> --repro                  # write cmeta-repro-input/-output.json
cx <cat> <cmd> --dump                   # write cmeta-ctx.json (full context)
cx <cat> <cmd> --home=<path>            # one-shot <CMETA_HOME> override
```

The **exit code equals the call's `return` value**; `16` is a soft "not found",
not a failure. Details and shell examples in
[error-handling.md](error-handling.md).

---

## Flag syntax

- Booleans: `--flag` (True), `--flag-` or `--no-flag` (False).
- Strings: `--key=value` or `--key value` (last wins).
- Lists: `--key,=v1,v2,v3` (note the comma on the *key*).
- Nested: `--parent.child=value` → `{'parent': {'child': value}}`.
- Param files: `@input.yaml` / `@input.json` deep-merge into the params
  (`@@input.yaml` also deletes the file after reading).
- Hyphens and underscores are interchangeable (`--log-level` == `--log_level`).

---

## Handy one-liners

```bash
# Where am I, and copy the cRef to paste elsewhere
cx . info

# Everything in a category, newest metadata included
cx <category> find --json

# Point cMeta at your own git org for `cx repo get <name>` short-hand
cx config set default --meta.default_git=git@github.com:

# Move the big file/build cache off the system drive
cx config set task --meta.file_cache=/path/to/large/cache

# Run the local web app
cx app run cserver

# Serve it to your own devices, behind one shared password
cx config set cserver --meta.password="a passphrase of your own"
cx app run cserver --param.host=0.0.0.0 --param.port=8004
```

---

Related: [using-cmeta.md](using-cmeta.md) (full guide) ·
[error-handling.md](error-handling.md) · [configuration.md](configuration.md) ·
[documentation index](README.md)
