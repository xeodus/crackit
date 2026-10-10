# Crackit interview-assistant feasibility lab

The first implementation stage for a lower-cost, real-time desktop interview assistant. Launch scope is macOS, then Windows and selected Linux distributions; a web app will handle accounts and subscriptions. This is an experimental harness and macOS diagnostic app, not a finished product or evidence of interview outcomes. See the [current interview-first plan](research/05-interview-first-plan.md).

Start with [the native interview-capture validation](spikes/LIVE_CAPTURE.md), [the reliability implementation and measured gates](spikes/RELIABILITY.md), [the research baseline](research/README.md), and [the experiment instructions](spikes/README.md).

```sh
make test
make replay
make native
.build/CrackitProbe.app/Contents/MacOS/CrackitProbe --capabilities
```

`make test` and `make replay` use only synthetic text and local computation. The native build has no third-party dependencies. Opening the app does not start capture; its controls explicitly start and stop experiments. Cloud benchmarks require locally configured credentials and an explicit budget.

Use `make report` for the repeatable offline experiment report. Native capture, live model quality, provider costs and Windows behavior remain separate gates until measured.
