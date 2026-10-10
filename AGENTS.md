# Repository Guidelines

## Project Structure & Module Organization

`research/` holds product analysis and costs. `spikes/` is the implementation lab: `core.py` manages transcript evidence, `streaming.py` and `transport.py` handle recognition events, `providers.py` contains hosted benchmarks, and `native/` holds the macOS probe and C++ workers. Put fixtures in `spikes/fixtures/` and Python tests in `spikes/tests/`. Published aggregates belong in `spikes/results/`; raw audio, traces, credentials, models, and build output stay in the ignored `spikes/results/local/`, `.cache/`, `.env`, and `.build/` paths.

## Build, Test, and Development Commands

- `make test` runs the Python `unittest` suite.
- `make replay` and `make report` run the synthetic context replay and offline measurement.
- `make native` builds the macOS diagnostic; `make capabilities` checks its permissions without starting capture.
- `make local-engine` builds the pinned whisper.cpp workers after preparing the checkout and models per `spikes/README.md`.
- `make overlap-test` compiles and runs the C++ rolling-alignment checks. `make reliability-report` summarizes saved recognition comparisons.

## Coding Style & Naming Conventions

Use four-space indentation in Python and follow the surrounding style in Swift and C++. Name Python modules and functions in `snake_case`, classes in `PascalCase`, and tests `test_*.py` with `test_*` methods. Keep benchmark inputs, model settings, and fixture hashes explicit so results can be reproduced. There is no configured formatter or linter; review diffs for consistent style and readable error handling.

## Testing Guidelines

Add focused regression tests for changed behavior, especially transcript revisions, source isolation, budget accounting, and rolling commitment. Run `make test`; run `make overlap-test` when changing `spikes/native/overlap_alignment.h` or the streaming workers. Do not treat synthetic speech, a successful transport run, or valid citation IDs as proof of meeting accuracy. Record failed gates and incomplete provider sessions in the results instead of silently retrying them.

## Commit & Pull Request Guidelines

This repository has no commits yet, so no convention is established. Use a short imperative subject. In a pull request, explain the changed behavior, motivating evidence, validation outcomes, and remaining limits. Link an issue when one exists; include screenshots for visible probe changes.

## Security & Configuration

Copy `.env.example` to `.env` for local API keys; never commit keys or raw customer data. Hosted benchmarks share a usage ledger and are currently halted pending reconciliation. Respect the documented $10 covered-usage and $2 possible-cash limits; do not reset the ledger or change billing settings to continue a run.
