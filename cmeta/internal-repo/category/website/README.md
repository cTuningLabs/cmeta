# Website artifacts

`cx website build <entry>` retains the static builder based on `_build.yaml` or `_build.json`, a template and page metadata. Static entries can use `--subdir` and `--ignore_dirs` as before.

An executable website can instead ship a Python manager and declare it in `_desc.yaml`:

```yaml
website:
  runner: manage.py
```

Invoke an action through the same category:

```sh
cx website run my-site status

cx website run my-site start -- --port 8120

cx website build my-site
```

The manager receives the action followed by literal arguments after `--`. It runs with the current cMeta Python, inherited environment and the website artifact as its working directory. The runner path must name a Python file inside the artifact. Its exit code is returned to the caller. The manager defines the available actions and their effects; the category does not install dependencies, change proxy configuration or choose a website's CMETA automatically.

For entries declaring `website.runner`, `build` invokes the manager's `build` action. Use `website run <entry> build -- <options>` to pass manager options. Static-build options are rejected for runner entries.
