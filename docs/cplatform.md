# Connecting to the cTuning.ai platform

cMeta can connect to the **cTuning.ai platform** to access its hosted API and
services. This page shows how to configure access and run a quick connectivity
test.

---

## Prerequisites

- cMeta installed (see [installation.md](installation.md)).
- A cTuning.ai account.
- Your **API Access URL** and **API Access Token**, both available from
  [https://ctuning.ai/settings](https://ctuning.ai/settings).

---

## Configure access

Set the platform URL and your API token for the `ctuning_server` configuration:

```bash
cx config set ctuning_server --meta.url={your API Access URL from https://ctuning.ai/settings}
cx config set ctuning_server --meta.api_key={your API Access Token from https://ctuning.ai/settings}
```

Replace the `{...}` placeholders with the values from your settings page.

---

## Test the connection

```bash
cx utils access_ctuning_server --query.command=test-api
```

A successful call confirms that cMeta can reach the platform and that your token
is valid.

---

## Keep your API token private

Your token is written to the local cMeta configuration on your machine. Treat it
like a password:

- **Do not commit it** to Git or paste it into shared scripts, issues or logs.
- If a token is ever exposed, revoke and reissue it from
  [https://ctuning.ai/settings](https://ctuning.ai/settings).

---

## See also

- [installation.md](installation.md) — installing cMeta.
- [using-cmeta.md](using-cmeta.md) — everyday usage (repos, plugins, artifacts).
