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
cx config set task --meta.file_cache=D:\cmeta-file-cache --meta.check_versions

# Configure access to the cTuning.ai platform (see cplatform.md):
cx config set ctuning_server --meta.url={your API Access URL}
cx config set ctuning_server --meta.api_key={your API Access Token}

# Where the local web app listens, and one shared password in front of it:
cx config set cserver --meta.param.host=0.0.0.0 --meta.param.port=8004
cx config set cserver --meta.password="a passphrase of your own"

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
- [using-cmeta.md](using-cmeta.md) §8 — full `config` reference, including the
  `uses_categories:` pattern for reading a config from your own category in
  Python.
