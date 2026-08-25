<!--
Thank you for contributing to bioforklift!

Fill in the sections below and delete anything that doesn't apply. Text inside

-->

<!-- Indicate the issue number if applicable; otherwise, delete -->
This PR closes #

<!-- Delete the < > around "NOT" if your branch should be retained after merging -->
🗑️ This dev branch should <NOT> be deleted after merging to main.

## :brain: Summary

<!-- What does this PR do, and why? A paragraph or two is plenty. -->

## :hammer_and_wrench: Technical

### Impacted areas
<!-- Check every area this PR touches -->

- [ ] `terra/` — client, entity / submission / method ops, transfer, merge
- [ ] `basespace/` — client, endpoints, dataset / file ops, models
- [ ] `bigquery/` — client, config ops, sample ops
- [ ] `terra2bq/` — orchestration, config builder
- [ ] `data_processing/` — config processor, sample processor
- [ ] `file_transfers/` — GCS
- [ ] `alerting/` — Sentry, Slack
- [ ] `main.py` / CLI (`configure`, `download`, `launch`, `upload`, `version`)
- [ ] `scripts/`
- [ ] Packaging / infra — `pyproject.toml`, `poetry.lock`, `Dockerfile`, workflows
- [ ] Docs — `docs/`, `mkdocs.yml`

### Changes
<!-- Describe your changes. Bullets are fine. Call out anything a reviewer would
     otherwise have to reverse-engineer from the diff. -->

Existing configs or BigQuery tables need changes to keep working: **Yes/No**

### Behavior changes
<!-- Could this change what an existing pipeline pulls, pushes, or launches?
     Anything that alters data landing in BigQuery/Terra, changes which samples
     get selected, or changes submission behavior needs an explicit callout here. -->

This PR may lead to different results for existing pipelines: **Yes/No**

This PR is backwards incompatible for current users: **Yes/No**

### Dependencies
<!-- New or bumped dependencies? Confirm `poetry.lock` was regenerated with
     `poetry lock` and committed. Write "None" if unchanged. -->

## :test_tube: Testing

<!-- Describe how you tested this. Include the commands you ran and what you ran
     them against: mocked fixtures, a real Terra workspace, a scratch BigQuery
     dataset, a BaseSpace project, etc. -->

### Verification
<!-- Mark each box [X]. Where a check genuinely doesn't apply, write "N/A —
     <reason>" next to it rather than leaving it unchecked. -->

- [ ] **Pytests** — `poetry run pytest tests/ --cov=src/bioforklift --cov-report=term-missing` passes locally, and the *Bioforklift Tests* check is green on this PR
  <!-- That workflow only triggers on changes under src/bioforklift/**, tests/**,
       poetry.lock, or pyproject.toml. If it didn't run for this PR, say so here. -->
- [ ] **Test coverage** — new or updated tests added under `tests/test_<module>/` for the changed behavior
- [ ] **Doc rendering** — `poetry run mkdocs serve` renders the affected pages without warnings, links and code blocks look right, and any new page is registered in the `nav:` block of `mkdocs.yml`
- [ ] **Version bump** — `version` in `pyproject.toml` bumped, or intentionally left alone because the release is being cut in a separate PR (state which)
  <!-- `bioforklift.__version__` is read from installed package metadata, so
       pyproject.toml is the only place the version lives. -->
- [ ] **Docker build** — `docker build -t bioforklift:pr .` succeeds and `docker run --rm bioforklift:pr bioforklift version` prints the expected version
  <!-- There is no CI job for the image yet, so this one has to be run locally. -->
- [ ] **Live run** — exercised end to end against a real Terra workspace / BigQuery dataset / BaseSpace project, where applicable (describe above)

### Suggested scenarios for the reviewer to test
<!-- Edge cases, test data, or configs the reviewer should try. -->

## :microscope: Final Developer Checklist

- [ ] The change has been run and the results, including any rows written to BigQuery or entities written to Terra, are as anticipated
- [ ] All verification boxes above are checked or explicitly marked N/A
- [ ] Code is formatted and linted: `poetry run black src tests` and `poetry run ruff check src tests`
- [ ] No credentials, service-account keys, workspace names, or sample identifiers were committed (including in logs, fixtures, and example configs)
- [ ] Documentation in `docs/` has been updated for any user-facing change
- [ ] All CI checks are passing

## 🎯 Reviewer Checklist
<!-- Indicate NA when not applicable -->

- [ ] The change does what the summary claims and the approach is sound
- [ ] Test coverage is adequate for the change
- [ ] Confirmed that changes work as expected with existing deployments
- [ ] You have pulled the branch and verified the changes appropriately
- [ ] Documentation is accurate and renders correctly
- [ ] The PR author has addressed all comments
