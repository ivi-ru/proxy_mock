# Notes for AI agents

Context for coding agents working in this repository. Humans should read
[CONTRIBUTING.md](CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md) — this file only collects the
rules that are not visible from the code itself. Everything here is a summary; where the two
disagree, CONTRIBUTING and ROADMAP win.

proxy-mock is a small HTTP mock and proxy server for automated tests, shipped both as a service
and as a Python package with sync and async clients.

## Commands

The project uses uv; `make install` creates the environment.

- `make test` — the full suite
- `make lint` — ruff check and format check, exactly as CI runs them
- `make lint_fix` — apply the fixes
- `make run` — start the service locally on port 5000

## Rules that are easy to get wrong

- **Do not add a runtime dependency.** The dependency budget in ROADMAP.md allows one only when
  a hand-written version would take more than ~100 lines, or when it is protocol code. Under
  that threshold, write the code. If you believe a dependency is genuinely warranted, say so and
  let a human decide instead of adding it.
- **English everywhere**: code, comments, docstrings, log messages, API error texts, docs.
- **The public API is narrow.** Stable: the HTTP API, `proxy_mock.client`,
  `proxy_mock.app:create_app`, the `proxy-mock` console script. Everything else
  (`services/`, `repositories/`, `core/`, `utils.py`, `any_catcher.py`) is internal and may be
  changed freely — but changing the stable surface needs a CHANGELOG entry, and breaking it is a
  3.0 decision, not a pull request.
- **One process, in-memory state.** Mocks and traffic live in the memory of a single process, so
  the service never runs with more than one worker. Do not "fix" that by adding shared storage.
- **Service endpoints must not be shadowed by user mocks.** The isolation currently depends on
  how FastAPI nests routers, which is why the floor is `fastapi>=0.137`; see the docstring in
  `tests/test_service_routes.py` before touching routing or that lower bound.
- **Tests are required**: new behaviour gets a test, a bug fix gets a regression test that fails
  without it. Do not weaken or delete an existing test to make a change pass.
- **User-visible changes get a CHANGELOG.md entry** under the upcoming version.
- **Dependencies are locked**: after editing `pyproject.toml`, run `uv lock` and commit the
  updated `uv.lock` in the same change.

## Do not

- Push, tag, create releases or publish anything. Releases are a maintainer action, described at
  the end of CONTRIBUTING.md.
- Rewrite released sections of CHANGELOG.md.
- Add per-tool configuration files for other assistants. One file — this one — is the whole
  convention here.
