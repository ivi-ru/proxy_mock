# 🤝 Contributing

Thanks for considering a contribution. proxy-mock is a small project on purpose, so the most
useful thing you can do before writing code is to check that the change fits — the scope and the
non-goals are in [ROADMAP.md](ROADMAP.md).

---

## Getting set up

The project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync            # or: make install
make test          # pytest --cov -v
make lint          # ruff check + ruff format --check
make lint_fix      # ruff check --fix + ruff format
make run           # start the service on http://localhost:5000
```

Optionally, install the hooks so formatting never reaches CI:

```bash
uv run pre-commit install
```

Python 3.11 or newer is required. CI runs the test suite on 3.11, 3.12, 3.13 and 3.14.

---

## What gets merged

- **Bug fixes** — always welcome. A fix should come with a regression test that fails without it.
- **Features already on the roadmap** — welcome; comment on the issue first so two people do not
  write the same thing.
- **Features outside the roadmap** — open an issue before writing code. If it falls under the
  non-goals it will be declined with a link, and it is better to hear that before the work than
  after.
- **Refactors without a behavioural reason** — usually declined. The code is small enough that
  churn costs more review time than it saves.

### Dependencies

Adding a runtime dependency needs an argument against the dependency budget in
[ROADMAP.md](ROADMAP.md#dependency-budget): it is acceptable only if writing the same thing here
would take more than roughly 100 lines, or if it is protocol code. Projects install proxy-mock
into their own test environments, so every dependency we take is one they inherit.

Development-only dependencies belong in `[dependency-groups] dev`. Regenerate and commit the lock
file with `uv lock` in the same commit.

### Public API

`ROADMAP.md` lists which modules are stable and which are internal. A pull request that changes
the stable surface needs a CHANGELOG entry describing the change and, if it breaks anything, a
note in the migration section.

---

## Style

- **English everywhere**: code, comments, docstrings, log messages, API error texts, commit
  messages, documentation. Consistency matters more than any individual preference here.
- **ruff** handles formatting and linting: line length 120, double quotes. Run `make lint_fix`
  before pushing; `make lint` is what CI runs.
- Type hints on public functions; the existing modules show the expected level of detail.
- Docstrings explain *why*, not *what* — the code already says what it does.

---

## Tests

- New behaviour needs a test; a bug fix needs a test that fails before the fix.
- Tests live in `tests/`, run against a real application instance through the client, and must
  not depend on each other's order.
- `make test` reports coverage. There is no hard threshold, but a pull request that lowers
  coverage should say why.

---

## Pull requests

- One subject per pull request. Two unrelated fixes are two pull requests.
- The title is a single line in the imperative mood, in English.
- The description says what changes for a user of the service or of the client — that text
  usually becomes the CHANGELOG entry.
- Add the CHANGELOG entry under the upcoming version when the change is user-visible.
- CI must be green: ruff, the test matrix, and the image build.

---

## Reporting a security issue

Do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting on
this repository, or email <aryabokon@ivi.ru>.

Note the security model described in the README before reporting: proxy-mock has no
authentication, will proxy to any host unless an allowlist is configured, and records request
bodies and headers in memory. Those are documented properties of a testing tool, not
vulnerabilities. An instance is meant to run in a test environment, not on the public internet.

---

## What to expect

Issues and pull requests are reviewed weekly. A change that fits the roadmap and arrives with
tests usually lands in the next release; anything larger will get a discussion first. If a pull
request has had no response for two weeks, a ping in the thread is entirely fair.

---

## Releasing (maintainers)

1. Bump `version` in `pyproject.toml`.
2. Add the release section to `CHANGELOG.md`, with a migration section for a major.
3. Merge to `main` with CI green.
4. Tag the commit with the exact version (`git tag 2.11.0`) and push the tag. The release
   workflow verifies that the tag matches `pyproject.toml` and publishes to PyPI through trusted
   publishing — no token is involved.
