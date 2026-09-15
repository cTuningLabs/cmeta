# Contributing to cMeta

Thank you for your interest in contributing to **cMeta** (also known as **cX**).
Contributions of all kinds are welcome — bug reports, fixes, tests, documentation
and new functionality.

cMeta is released under the **Apache License 2.0** (see [`LICENSE`](LICENSE)). By
contributing, you agree that your contribution is licensed under the same terms.

---

## The short version

```bash
git clone https://github.com/cTuningLabs/cmeta && cd cmeta
pip install -e ".[dev]"
git checkout -b my-fix
# ... make your change, add a test ...
python -m pytest tests && flake8 cmeta
git commit -s -m "Short imperative summary"      # -s is the whole agreement
git push && gh pr create
```

That is the entire process. **Apache 2.0, no CLA to sign, no account to
register** — the `-s` flag on `git commit` is the sign-off, and an automated
check confirms it on the pull request. Everything below is detail.

---

## Sign-off: the Developer Certificate of Origin (DCO)

This project uses the **Developer Certificate of Origin (DCO) 1.1** as its
contribution agreement. There is **no separate CLA to sign**. Instead, you
certify that you have the right to submit your contribution by adding a
`Signed-off-by` line to every commit.

Read the full text in the [`DCO`](DCO) file. In short, signing off certifies that
you wrote the contribution, or otherwise have the right to submit it under the
project's open source licence.

### How to sign off

Add the `-s` (or `--signoff`) flag when you commit:

```bash
git commit -s -m "Fix repo resolution for mixed-case aliases"
```

This appends a line to your commit message using your configured `user.name` and
`user.email`:

```
Signed-off-by: Jane Doe <jane@example.com>
```

Use your real name and a valid email address. Set them once with:

```bash
git config user.name "Jane Doe"
git config user.email "jane@example.com"
```

### If you forget to sign off

- Amend the most recent commit:
  ```bash
  git commit --amend -s --no-edit
  ```
- Sign off several commits (the last N, or a whole branch):
  ```bash
  git rebase --signoff HEAD~N
  ```
- Then update your pull request:
  ```bash
  git push --force-with-lease
  ```

A DCO check runs on every pull request; it must pass before a change can be
merged. Passing the check is necessary but not sufficient — a maintainer still
reviews and approves each pull request.

### If you are contributing from a job

This is the part the sign-off is really for. Clause (a) of the DCO is a
statement that you **have the right to submit** the contribution under the
project's licence — so if your employer owns the intellectual property you
create, get their permission before you sign off. For most companies a short
confirmation from your manager or legal contact is enough, and it costs the
project nothing to administer, which is exactly why this project uses a DCO
rather than a contributor licence agreement.

Employers whose staff contribute regularly can put a single **Corporate CLA** in
place instead; see the [`cTuningLabs/cla`](https://github.com/cTuningLabs/cla)
repository or contact **gfursin@gmail.com**.

---

## Development setup

```bash
pip install -e ".[dev]"            # editable install with dev extras (or [all])
python -m pytest tests             # run the test suite
python -m pytest tests/test_utils_obj_parse_cmeta_core.py::test_name   # single test
flake8 cmeta                       # lint
python -m build                    # build wheel + sdist
```

cMeta supports **Python 3.9–3.14**; please avoid newer-only syntax. Runtime
dependencies are intentionally minimal — justify any new one in your pull
request. See [`AGENTS.md`](AGENTS.md) for architecture and conventions.

---

## Submitting changes

1. Open an issue first for anything beyond a small fix, so the approach can be
   agreed before you invest time.
2. Create a branch, make your change, and add or update tests.
3. Ensure `python -m pytest tests` and `flake8 cmeta` pass locally.
4. Commit with `-s` (DCO sign-off).
5. Open a pull request describing the change and referencing any related issue.

Please do not include local paths, credentials, API keys, or personal workflow
scripts in commits. Interactive/manual test scratch belongs outside the
repository.

---

## Future contribution terms

The project may, at the maintainer's discretion, require a signed Contributor
License Agreement for future contributions — for example for contributions above
a certain size, or if the project's governance changes. Any such change would
apply to new contributions only and would be announced here before taking effect.
The current terms are DCO sign-off as described above.

---

## Reporting security issues

Please do **not** open a public issue for a security vulnerability or a leaked
secret. Email **gfursin@gmail.com** directly.

---

## Questions

- General questions and design discussion: open a GitHub issue.
- Contributor agreements and licensing: **gfursin@gmail.com**.
