<!--
Thank you for cutting a bioforklift release!

Use this template for version-bump / release-prep PRs. Once this PR is merged to
main, tag that commit with the SAME bare semver version to trigger the Release
workflow (test -> build -> PyPI via Trusted Publishing -> GitHub Release):

    git checkout main && git pull
    git tag 0.X.Y && git push origin 0.X.Y

The Release workflow fails fast if the tag doesn't match `poetry version -s`.
-->

## :label: Release

Bumping `0.X.Y` → `0.X.Y`

## :brain: What's in this release
<!-- Short list of the user-facing changes since the last release, with PR
     numbers. The GitHub Release notes are auto-generated, so this is the
     human-readable summary. -->

Breaking changes for existing users or deployments: **Yes/No**
<!-- If yes, list them and the migration steps. -->

## :test_tube: Verification

- [ ] **Version bump** — `version` in `pyproject.toml` is the new version and nothing else was changed in this PR
  <!-- `bioforklift.__version__` is read from installed package metadata, so
       pyproject.toml is the only place the version lives. -->
- [ ] **Pytests** — `poetry run pytest tests/` passes locally and the *Bioforklift Tests* check is green on this PR
- [ ] **Docker build** — `docker build -t bioforklift:0.X.Y .` succeeds and `docker run --rm bioforklift:0.X.Y bioforklift version` prints the new version
- [ ] **Doc rendering** — `poetry run mkdocs serve` renders cleanly and the docs reflect everything shipping in this release
- [ ] **Build** — `poetry build` produces a wheel and sdist without warnings
- [ ] `poetry.lock` is in sync with `pyproject.toml` (`poetry check --lock`)
- [ ] Every PR intended for this release is already merged to main

## :rocket: Post-merge steps
<!-- Leave these unchecked until after the merge; check them off as you go. -->

- [ ] Tagged the merge commit with the matching bare semver version and pushed the tag
- [ ] Release workflow completed: tests, build, PyPI publish, and GitHub Release all green
- [ ] Verified the new version on [PyPI](https://pypi.org/project/bioforklift/) and installs cleanly (`pip install bioforklift==0.X.Y`)

## 🎯 Reviewer Checklist

- [ ] The version bump is correct and follows semver given the changes included
- [ ] The change list matches what actually landed on main since the last release
- [ ] All CI checks are passing
