<!--
Thank you for contributing to bioforklift's documentation!

This template is for PRs that change only `docs/` and/or `mkdocs.yml`. If you
also changed anything under `src/bioforklift/`, use the Code Changes template
instead.
-->

<!-- Indicate the issue number if applicable; otherwise, delete -->
This PR closes #

<!-- Delete the < > around "NOT" if your branch should be retained after merging -->
🗑️ This dev branch should <NOT> be deleted after merging to main.

## :brain: Summary

<!-- What does this PR document or correct, and why? -->

## :hammer_and_wrench: Pages changed
<!-- List the pages you touched, e.g.
     - docs/interfaces/basespace_interface.md — new section on dataset filtering
     - mkdocs.yml — added the new page to nav
-->

## :test_tube: Verification

- [ ] **Doc rendering** — `poetry run mkdocs serve` was run and every changed page renders correctly: headings, admonitions, tabbed blocks, mermaid diagrams, tables, and code fences
- [ ] Any new page is registered in the `nav:` block of `mkdocs.yml`
- [ ] Internal links and image paths resolve (no broken links or missing `docs/assets/` images)
- [ ] Code snippets and CLI examples were actually run, or are copied from a working run
- [ ] Checked for typos and for wording consistent with the surrounding docs
- [ ] No credentials, service-account keys, workspace names, or real sample identifiers appear in the examples
- [ ] All CI checks are passing

## 🎯 Reviewer Checklist
<!-- Indicate NA when not applicable -->

- [ ] All changes have been confirmed to be technically accurate against the current code
- [ ] You have served the docs locally and verified everything renders correctly
- [ ] Wording and structure are consistent with the rest of the documentation
- [ ] The PR author has addressed all comments
