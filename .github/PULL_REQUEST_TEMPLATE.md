<!--
Thanks for contributing to cMeta. This template is a checklist, not a form to
fill in exhaustively — a one-line description and the boxes ticked is plenty for
a small fix.
-->

## What this changes

<!-- One or two sentences. Link the issue if there is one, e.g. "Fixes #123". -->

## Why

<!-- The problem it solves, or the behaviour it improves. Skip for a typo fix. -->

---

### Checklist

- [ ] **Every commit is signed off** (`git commit -s`). This is the project's
      whole contribution agreement — there is no CLA to sign. It certifies you
      wrote the change, or otherwise have the right to submit it under Apache 2.0.
      Forgot? `git rebase --signoff <base>..HEAD && git push --force-with-lease`
- [ ] **If your employer owns the IP you create, you have their permission** to
      contribute this. (That is what clause (a) of the [DCO](../DCO) certifies.)
- [ ] `python -m pytest tests` passes.
- [ ] `flake8 cmeta` is clean.
- [ ] Any new runtime dependency is justified below (cMeta keeps these minimal
      on purpose), or there is none.
- [ ] No local paths, credentials, API keys or personal scratch files included.

<!--
Python 3.9–3.14 is supported, so please avoid newer-only syntax.
Full details: CONTRIBUTING.md. Architecture and conventions: AGENTS.md.
Security issue or a leaked secret? Do NOT open a PR or issue — email gfursin@gmail.com.
-->
