# Releasing CodeCraft

[简体中文](RELEASING.zh-CN.md)

CodeCraft uses PEP 440 package versions and matching Git tags. Alpha releases use
versions such as `0.1.0a3` and tags such as `v0.1.0a3`.

## Prepare

1. Start from a clean `develop` branch rebased onto the latest `main`.
2. Update `project.version` in `pyproject.toml` and run `uv lock`.
3. Add the user-facing changes to `CHANGELOG.md` and `CHANGELOG.zh-CN.md`, then
   create the bilingual release notes at `docs/releases/vX.Y.Z.md` and
   `docs/releases/vX.Y.Z.zh-CN.md`. The English version is the canonical GitHub
   Release body and must link to the Chinese version.
4. Run the local release gates:

   ```zsh
   uv run ruff format --check .
   uv run ruff check .
   uv run pytest
   uv build
   uvx twine check dist/*
   ```

5. Commit the preparation as `chore(release): prepare vX.Y.Z` and push
   `develop`.
6. Wait for the `develop` CI run to pass.

## Publish

1. Merge `develop` into `main`, push `main`, and wait for its CI run to pass.
2. Run the Release workflow manually on `main` as a package dry-run.
3. Create an annotated tag on the verified `main` commit:

   ```zsh
   git tag -a vX.Y.Z -m "CodeCraft vX.Y.Z"
   git push origin vX.Y.Z
   ```

4. Wait for the tag-triggered Release workflow to pass.
5. Verify that the GitHub release has both wheel and source-distribution assets.
   PEP 440 pre-release versions must appear as GitHub Pre-releases.
6. Rebase `develop` onto the released `main` and push it.

The Release workflow rejects mismatched version/tag pairs, missing or empty
English or Chinese release notes, and tags whose commits are not contained in
`origin/main`. The English versioned document is the canonical GitHub Release
body; the bilingual changelogs remain the concise cross-version history.
