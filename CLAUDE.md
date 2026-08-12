# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repo.

## Project

Local-first grid carbon-intensity tracker: a Pico W + e-ink display (`pico/`)
that fetches grid carbon intensity from several providers and shows a
run/wait recommendation, plus a desktop dashboard (`web/`) and a mock Pico
(`mock/`) for developing the dashboard without hardware. Python 3.10+.

## Commands

```sh
# test: pytest -q
# lint: pre-commit run --all-files   (ruff + gitleaks + editorconfig etc.)
# run:  ./start.sh                   (mock Pico + dashboard together)
make help    # Show this help
make setup   # Install the pre-commit hook
make lint    # Run all pre-commit checks on the whole tree
make test    # Run tests
```

## Tooling

- `make setup` installs the pre-commit hook, and that is the whole of it.
  Don't add a `.githooks/` directory: `core.hooksPath` replaces `.git/hooks/`
  wholesale, so setting it silently stops every pre-commit hook from running.
- Hooks are pinned by commit SHA with the tag in a trailing comment. A tag can
  be moved, a SHA cannot.
- CI runs this same `.pre-commit-config.yaml` through `pre-commit/action`, so
  what passes locally is what gates the pull request.

## Conventions

- Match existing style; don't reformat unrelated code.
- Conventional Commits for messages (see CONTRIBUTING.md).
- Update CHANGELOG.md (`## [Unreleased]`), docs/, and examples/ with behavior changes.
- Never commit secrets; CI runs gitleaks. Keep `.env` out of git (`.env.dist` is the template).
- `pico/*.py` files import each other by bare module name (e.g. `from config
  import CONFIG`, not `from pico.config import CONFIG`) because that's how
  they're laid out once flashed to the Pico's flat filesystem. Don't
  package/import them as `pico.*` — see docs/architecture.md.

## Guardrails

- Don't add dependencies without a clear reason; prefer stdlib. `pico/`
  additionally must stay within what MicroPython ships.
- Don't touch generated files or lockfiles by hand.
- Ask before large refactors or destructive operations.
