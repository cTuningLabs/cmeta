# Working with configs

cMeta keeps tunable values — server URLs, API keys, default repositories, cache
locations, tool paths, and so on — in **`config` artifacts**: named artifacts of
the built-in `config` category whose values live in a `data.json` sidecar under
`<repo>/config/<name>/`.

Categories and apps read these configs at runtime, so you can change behavior
without editing any code. Multiple named configs coexist; conventions the shipped
code already uses include `default` (framework defaults), `task` (cache / version
checks), `cserver` (the local web app), and `ctuning_server` (external API
access).

---

## Commands

| Command | Behavior |
|---------|----------|
| `cx config set <name> --meta.<key>[.<child>]=<value>` | Deep-merge keys into the config (creates it if missing). |
| `cx config get <name>` | Return the config values. |
| `cx config show <name>` | Pretty-print as flat `--meta.a.b=c` lines — ready to copy into a `set`. |
| `cx config unset <name> --meta.<key>[.<child>]` | Deep-remove the given keys. |

Configs are ordinary artifacts, so the usual commands work too: `cx config ls`,
`cx config find <name>`, `cx config info <name>`, `cx config rm <name>`.

---

## Examples

```bash
# Point cMeta at your own git org for `cx repo get <name>` short-hand:
cx config set default --meta.default_git_repo=my-org --meta.default_git=git@github.com:

# Move the large file / build cache off the system drive, and enable version checks:
cx config set task --meta.file_cache=D:\cmeta-file-cache --meta.tool.check_versions

# Configure access to the cTuning.ai platform (see cplatform.md):
cx config set ctuning_server --meta.url={your API Access URL}
cx config set ctuning_server --meta.api_key={your API Access Token}

# Where the local web app listens, and one shared password in front of it:
cx config set cserver --meta.param.host=0.0.0.0 --meta.param.port=8004
cx config set cserver --meta.password="a passphrase of your own"
cx config set cserver --meta.login_email=you@example.com      # or a code by e-mail (with the login_smtp_* keys)

# What its home page "/" shows (/projects by default; none = a plain welcome),
# and repositories to leave off that list on a shared server:
cx config set cserver --meta.default_page=/projects
cx config set cserver --meta.hide_repos=my-private-repo

# Inspect and confirm:
cx config show default
cx config show ctuning_server

# Remove a single key:
cx config unset default --meta.default_git_repo
```

Values are stored as JSON, but you set and remove them from the CLI using
dot-notation (`--meta.a.b=c`).

A `param:` subtree of the `cserver` config is special: the `app` category
exports every key in it to the app as an environment variable
(`param.port` becomes `CSERVER_PORT`), and `cx app run cserver --param.<key>=`
overrides it for one run.

---

## Every config and key of this machine: `/cmeta.configs`

The page `/cmeta.configs` of the cMeta server (`cx app run cserver`, then
`http://127.0.0.1:8004/cmeta.configs`) lists every config artifact and every key
that the artifacts plugged into this machine read: what each key does, its type
and default, which artifacts read it (with links to the lines of their code), its
value here, and the `cx config set` / `unset` lines that change it. A machine
with fewer repositories shows fewer configs: nothing is listed that no plugged
artifact knows. It also lists the keys set here that no plugged artifact reads -
a typo, a leftover, or a key of an artifact that is not plugged here.

It works both ways. A map on the left lists the artifacts that use configs (by
category: `category::cserver.*`, `task::...`, `tool::...`) beside the configs, with
a line from each artifact to each config it uses - solid when its code reads it,
dashed when it declares its keys, dotted when its docs show them. Point at an
artifact to light the configs it uses (with how many of their keys), or at a
config to light the artifacts that use it; click to show only that - an artifact
and what it uses, a config and who uses it, or both. The address keeps the choice
(`?art=...&cfg=...`), so the view can be shared.

A key is known from three places of the artifacts (their categories, tasks,
tools, apps, programs ...):

- **declared** - a `configs` block in the artifact's `_desc.yaml` (below);
- **code** - the Python files of the artifact, parsed: a call of the config
  category and what the code then takes from its answer (`cfg.get('key', 5)`);
- **docs** - the `cx config set <name> --meta.<key>=<value>   # what it does`
  lines of its README, comments and `_desc`, and Markdown tables with the
  columns Key and Meaning (or Description).

The values of keys that look like secrets (passwords, tokens, API keys) are
never shown, and the values set here are shown to a browser on the server's own
machine only (or one past its password; `configs_values` in the `cserver` config
says otherwise). The same list in a terminal:

```bash
cx cserver.cmeta.configs list                  # every config and key
cx cserver.cmeta.configs list "config:task"    # the search of the page: words, config:, key:, art:, repo:, cat:, is:
cx cserver.cmeta.configs list is:unread        # set here, read by no plugged artifact
cx cserver.cmeta.configs list art:run-ai       # the keys one artifact uses
cx cserver.cmeta.configs artifacts             # the other way round: each artifact and the configs it uses
cx cserver.cmeta.configs scan                  # look at the artifacts again (what changed)
```

## Declare the keys your artifact reads

An artifact that reads a config describes its keys in its `_desc.yaml`, so that
the page (and anyone reading the artifact) knows what each key does:

```yaml
configs:
  my-tool:                                   # the config artifact: cx config set my-tool --meta.<key>=<value>
    desc: the settings of my tool on this machine
    keys:
      cache_dir:
        desc: where the downloads are kept
        type: path                           # text, number, yes/no, list, dict, path, url ...
        default: ~/.cache/my-tool
        example: D:\my-tool-cache
      token:
        desc: the API token of the service
        secret: true                         # its value is never shown
      retries: how many times a download is tried     # a text alone is the description
```

Name a config of your own distinctly (`task-<task alias>`, `<tool>-<purpose>`):
config artifacts are shared by every artifact of a machine.

---

## Keep secrets private

API keys and tokens set via `config` are written to your local cMeta
configuration. Treat them like passwords: do not commit them to Git or paste
them into shared scripts, issues or logs. If a secret is exposed, revoke and
reissue it at its source.

The same applies to `cserver`'s `password`. If you would rather not keep the
plain text on disk, store its digest instead — the server accepts either.
`cx utils hash_password` asks for the password without echoing it and prints
the line to paste:

```bash
cx utils hash_password
cx config set cserver --meta.password_sha256=<the digest it printed>
```

---

## See also

- [cplatform.md](cplatform.md) — connecting to the cTuning.ai platform.
- [using-cmeta.md](using-cmeta.md#821-a-shared-password-in-front-of-cserver)
  §8.2.1 — every `cserver` password key, and what that protection is and is not.
- [using-cmeta.md](using-cmeta.md#822-the-home-page-every-page-of-the-server)
  §8.2.2 — the `cserver` home page, `default_page` and `hide_repos`.
- [using-cmeta.md](using-cmeta.md) §8 — full `config` reference, including the
  `uses_categories:` pattern for reading a config from your own category in
  Python.
