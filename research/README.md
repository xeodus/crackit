# Crackit research and interview-first plan

**Current scope (2026-10-09):** Build a production-grade, real-time interview assistant, launching on macOS, then Windows, then selected Linux distributions. A web app handles accounts and subscriptions; the desktop app handles live capture and assistance. Broad Cluely feature parity, mobile, CRM, and enterprise workflows are no longer launch goals. Read the [interview-first product plan](05-interview-first-plan.md) for the current delivery sequence. The material below preserves the earlier broad competitive research as a baseline.

Research date: 2026-10-08. This workspace began empty; these documents establish the project’s research baseline.

## Findings that should guide the project

Cluely is a desktop meeting assistant with a complete before/during/after workflow. Its preparation, transcripts, summaries, history, coaching, integrations, and administration informed the original broad-parity research, but are not all required for the interview-first launch. See the [capability and evidence review](01-cluely-evidence.md).

The core experience is technically reproducible with public APIs and commercially available models. Cluely’s private prompts, routing policies, negotiated prices, training assets, and current production internals are unknown. Public documentation discloses some dependencies, but does not expose a complete design. Our [architecture](02-architecture.md) is an independent implementation proposal, not a reconstruction of proprietary source code.

The difficult engineering sits in reliable audio capture, correct transcript revisions, bounded and relevant context, low latency, and a usable overlay. Buying a larger model does not solve those problems. Screen-share exclusion also depends on capture software and OS behavior; Electron explicitly documents a macOS limitation. Treat it as a compatibility feature with tested boundaries. [Electron documentation](https://www.electronjs.org/docs/latest/api/browser-window#winsetcontentprotectionenable-macos-windows)

Lower prices are plausible for bounded usage and for local/BYOK operation. Cheap unlimited cloud transcription and unlimited premium reasoning are not economically established. Read the [economics](03-economics.md) and run the [calculator](cost_model.py) before setting entitlements.

For the interview-first product, the proposed advantages are accurate question capture, timely and useful answers across interview types, a discreet and tested overlay, explicit privacy controls, and transparent cost. These are hypotheses until compared against real tasks. The original [validation and delivery plan](04-validation-and-roadmap.md) supplies general gates; the [interview-first plan](05-interview-first-plan.md) sets current priorities.

## Reading order

1. [Cluely evidence, capabilities, contradictions, and market](01-cluely-evidence.md)
2. [Independent end-to-end technical architecture](02-architecture.md)
3. [Provider prices, usage economics, and pricing options](03-economics.md)
4. [Evaluation design, technical spikes, and delivery gates](04-validation-and-roadmap.md)
5. [Interview-first product plan and release gates](05-interview-first-plan.md)
6. [Source register](sources.json)

Run `python3 research/cost_model.py` to regenerate scenario costs. Prices and assumptions are separate in the script. The numbers are modeled, not observed product usage or measured provider invoices.

## Method and confidence

We read Cluely’s public product/pricing pages, mapped its documentation, inspected feature and troubleshooting guides, and read the changelog, privacy policy, terms, and a public subprocessors page. We verified implementation constraints against Apple, Microsoft, Electron, speech-provider, calendar-provider, and open-source project documentation. We inspected competing product pages and public reference implementations. Firecrawl was used first; its rate limits required fallback to the built-in web tool. Failed requests and stale/conflicting pages are recorded rather than treated as findings.

Evidence labels throughout this work:

- **Documented:** a primary source describes it; this verifies publication, not actual performance.
- **Historical:** dated disclosure; current use or availability is unverified.
- **Inferred:** a plausible explanation based on evidence, not a confirmed Cluely implementation.
- **Proposed:** our design or product decision, subject to validation.
- **Unknown:** not established by the available sources.

The latest dated entry in the retrieved public Cluely changelog is December 18, 2025. We accessed it in October 2026. That makes it valuable historical evidence, but not a guarantee of the current release. Several feature guides still describe older interfaces. Sources can disagree because products and policies evolve.

## What this research does and does not settle

This is a broad public-source research pass across the complete product and technical pipeline. It does not establish Cluely’s measured latency, accuracy, retention practices, active model versions, or infrastructure cost. No Cluely account was created; no installer was executed; no private endpoints were probed; no comparative benchmark was run. We also have no customer interview or representative market-demand data yet.

Remaining empirical work is part of the first delivery gates, not hidden behind confident prose. A competitive research baseline can be completed now; claims of product superiority require working software and controlled comparisons.

## Earlier project intent (superseded for launch)

The original goal was a broad Cluely alternative with full workflow parity. The 2026-10-09 interview-first decision narrows launch scope and confirms macOS-first sequencing. Windows and selected Linux distributions follow; mobile and enterprise parity are no longer committed roadmap stages. Preserve the reliability, context, and cost lessons from this baseline.

The application stack remains provisional. The proposed starting architecture is a cross-platform desktop shell with native capture helpers, a small backend, Postgres-based retrieval, provider adapters, and local transcription as an optional path. Implementation has now begun in the [feasibility lab](../spikes/README.md): a native macOS diagnostic, SQLite context harness, local recognition experiments, and budgeted provider adapters. These are validation tools rather than a complete application.
