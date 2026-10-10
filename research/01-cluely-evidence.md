# Cluely: capabilities, evidence, and competitive implications

Accessed 2026-10-08. “Documented” below means publicly described by its publisher, not independently tested.

## 1. The actual product

Cluely’s homepage describes a bot-free meeting assistant that listens to conversations, uses screen context, presents responses through a movable desktop interface, and generates meeting notes. It advertises over twelve transcription languages, 300 ms response time for transcription, and 95% accuracy. No reproducible protocol is supplied on the page; these are marketing claims, not established baseline measurements. Crucially, transcription response time is not answer generation time. [Product page](https://cluely.com/)

Think of the product as four connected systems: a desktop sensor and interface; a live transcription/context/answer pipeline; a persistent meeting and relationship database; and a business workflow layer. The business workflow expands the useful product beyond the initial live-answer moment.

## 2. Capability inventory and parity scope

| Capability | Public evidence and confidence | Independent implementation requirement | Phase |
| --- | --- | --- | --- |
| macOS/Windows desktop client | Quickstart documents both; historical minimum requirements vary with capture behavior | Signed installation, permissions, updates, native platform capture | Desktop core |
| Microphone and system audio | Audio troubleshooting describes both and WebSocket requirements | Separate capture paths, clock alignment, health checks, reconnect | Desktop core |
| Live transcript | Product and newer changelog describe transcript display and speaker labels | Mutable partials, stable final segments, timestamps, corrections | Desktop core |
| Screen-aware assistance | Product and settings describe screenshots and a capture toggle | On-demand capture, selected screen/window/region, visual reasoning | Desktop core |
| Hotkey-triggered answers | Settings documents Cmd/Ctrl+Enter | Cancelable streamed answers based on frozen context | Desktop core |
| Suggested replies, questions, recaps, fact checks | Live guide documents actions; its UI predates later changes | Task-specific prompts and source/tool policies | Desktop core |
| Coding and screen problem help | Older live guide describes Smart Mode | Visual context, code rendering, task-aware output | Desktop core |
| Movable/hideable widget | Live guide and settings | Placement, multi-monitor/DPI behavior, readable short answers | Desktop core |
| Screen-share exclusion | Published claim with documented qualifications | Platform-specific behavior and capture-app test matrix | Separate technical gate |
| Custom instructions and files | Pricing/settings | Versioned modes, secure document ingestion, retrieval | Knowledge phase |
| Multiple output/audio languages | Settings | Explicit language configuration and per-language evaluation | Desktop core, then expansion |
| Meeting notes/actions | Post-call guide | Idempotent finalization, structured extraction, editing | Desktop core |
| Follow-up emails | Post-call guide and changelog | Draft creation with grounded recipients/content | Workflow phase |
| Transcript copy/export; sharing; deletion | Post-call guide | Export, scoped links, revocation, deletion propagation | Workflow phase |
| Resume meeting | Post-call guide | Session continuation with bounded live context | Workflow phase |
| Search/chat over past meetings | Pricing and changelog | Permission-scoped transcript retrieval with citations | Knowledge phase |
| Participant and company preparation | Pre-call guide | Calendar attendees, identity resolution, sourced briefs | Workflow phase |
| Google Calendar | Calendar troubleshooting | OAuth, incremental sync, notifications, reminders | Workflow phase |
| Automatic meeting detection | November 2025 changelog | Signals with user-visible control and ambiguity handling | Reliability phase |
| Mobile recording/voice memos | December 2025 changelog; older limitations contradict it | Native recording lifecycle, offline queue, sync | Mobile phase |
| Company knowledge and live sources | Knowledge-base guide | Team-scoped files/URLs, refresh/deletion, provenance | Knowledge phase |
| CRM/ATS synchronization | Integration guide describes Merge.dev | Read/write connectors, mapping, deduplication, retries | Enterprise phase |
| Sales coaching and scorecards | Coaching guide | Evidence-based rubrics and reviewed scoring | Enterprise phase |
| Org/team roles and prompts | Role-management guide | Membership, authorization, predictable policy inheritance | Enterprise phase |
| Enterprise onboarding and reporting | Customization suite | Provisioning, usage analytics, pilot outcome reporting | Enterprise phase |

Sources: [Quickstart](https://docs.cluely.com/quickstart), [audio](https://docs.cluely.com/debugging/audio), [settings](https://docs.cluely.com/feature/settings), [live assistance](https://docs.cluely.com/feature/liveinsights), [post-call](https://docs.cluely.com/feature/postcall), [pre-call](https://docs.cluely.com/feature/precall), [calendar](https://docs.cluely.com/debugging/calendar), [knowledge](https://docs.cluely.com/enterprise/knowledgebase), [integrations](https://docs.cluely.com/enterprise/integrations), [coaching](https://docs.cluely.com/feature/coaching), [roles](https://docs.cluely.com/enterprise/rolemanagement), [customization](https://docs.cluely.com/enterprise/customizationsuite).

The phase labels are proposals for our product. They do not imply which Cluely subscription includes a feature. Consumer pricing does not establish enterprise feature entitlement.

## 3. What public evidence reveals about implementation

The public changelog historically mentions Recall.ai partial transcripts, Supermemory integration fixes, Claude experiments, WorkOS/RBAC, Stripe, Cloudflare Workers/Hyperdrive, PostHog, prompt versioning, and streaming changes. These disclose components or experiments at those dates; they do not prove a single unchanged production stack today. The integration guide independently names Merge.dev for CRM/ATS access. [Changelog](https://docs.cluely.com/changelog), [integration guide](https://docs.cluely.com/enterprise/integrations)

A subprocessors page on `new.cluely.com` lists AWS, Cloudflare, Vercel, Neon, Pinecone, Pusher, WorkOS, Stripe, PostHog, several model providers, Deepgram, and AssemblyAI among others. The page is a public vendor disclosure on an alternate Cluely subdomain; it does not establish each service’s current workload, routing frequency, or configuration. Recall.ai and Supermemory are not present in that retrieved list. This is an unresolved difference in public disclosures. [Subprocessors](https://new.cluely.com/subprocessors)

The knowledge guide describes retrieval-augmented generation from a third-party memory provider. Its advertised million-token context capacity should not be interpreted as evidence that each request loads a million tokens or that retrieval quality improves up to that length. The guide also says some live sources and integrations require team-assisted setup. [Knowledge-base guide](https://docs.cluely.com/enterprise/knowledgebase)

**Inferred pipeline:** local microphone/system capture → streaming transcription → accumulated session context → task selection → relevant file/history retrieval → language/vision model → streamed desktop response → post-call analysis and saved records. This follows the observable inputs and outputs. Exact transport boundaries, prompt construction, model policies, screenshot cadence, and summarization strategy remain unknown.

**Unknown:** whether the current desktop shell is Electron or another framework; exact native audio implementation; which provider handles a given session; model fine-tuning; embedding/chunking/reranking choices; full cloud regions; internal SLAs; actual gross margins; usage distribution; mechanisms beyond standard capture exclusion; and negotiated vendor rates. Third-party “how Cluely works” posts and clone repositories cannot establish those facts.

## 4. Pricing: compare the correct product

| Tier | Published reference | Confidence |
| --- | --- | --- |
| Starter | Free; limited meeting notes and AI responses | Current public pricing confirms limits without stable numeric quantities |
| Pro | $19.99 monthly; $11.99/month with annual billing | Cluely’s public 2026 comparison article, not a checkout verification |
| Pro + Undetectability | $75/month or $500/year disclosed at introduction | Historical October 22, 2025 changelog; current checkout price unverified |
| Enterprise | Scope and onboarding documented | No public price established here |

The retrieved pricing page’s animated price digits rendered as number sequences, preventing reliable extraction of the current dollar values. The official comparison article supplies Pro figures. The premium figures are historical and must not be silently presented as a current quote. [Pricing](https://cluely.com/pricing), [official Pro comparison](https://cluely.com/blog/cluely-vs-otter), [dated premium disclosure](https://docs.cluely.com/changelog#oct-22-2025)

There are also conflicting free-limit descriptions: older disclosures mention daily messages; newer marketing mentions a meeting allowance. Verify actual current entitlements separately. “Unlimited” needs inspection of applicable usage terms before a like-for-like commercial comparison.

At a proposed $6 monthly entry price, the arithmetic reduction is approximately 70% relative to the published $19.99 monthly Pro reference, but 50% relative to the $11.99 annual-equivalent reference. Relative to a historical $75 tier it is 92%, but that is neither a current verified comparison nor proof of matching screen-share behavior. Pricing comparisons must disclose included hours and premium-model limits.

## 5. Source contradictions and what they imply

| Discrepancy | Evidence | Research treatment |
| --- | --- | --- |
| No mobile app vs mobile launch | Limitations page vs Dec 10, 2025 changelog | Mobile is later documented; its current exact behavior is untested |
| Dynamic keyword insights vs their retirement | Older live guide vs Oct 21, 2025 changelog | Historical interface; do not assume automatic suggestions remain identical |
| Transcripts in widget vs dashboard | Live guide vs Dec 18, 2025 changelog | Later changelog changes placement |
| Translation configuration vs unreliable live translation | Settings vs limitations | Language selection is documented; quality live translation parity is unverified |
| Universal invisibility vs device/capture exceptions | Homepage vs live guide and Electron docs | Marketing wording is broader than tested/technical evidence |
| No training vs training authorization | Privacy policy vs consumer terms §3.2 | Contract/public-policy discrepancy; actual training is not established |
| Transcript-only storage vs broader collection language | Limitations vs privacy policy | Do not infer current retention of audio/screenshots from either alone |

The privacy policy also offers end-to-end encryption by contacting support, but does not supply an architectural description sufficient to assess how that interacts with cloud inference. We cannot verify which parties decrypt which data or what is covered. Our product must distinguish encryption in transit/at rest, client-controlled archival encryption, and cloud processing. [Privacy policy](https://cluely.com/privacy-policy), [consumer terms](https://cluely.com/terms), [limitations](https://docs.cluely.com/feature/limitations)

## 6. Screen-share exclusion: narrow the promise

Cluely’s own guide describes OS capture/privacy behavior comparable to avoiding recursive conferencing overlays, while older guides disclose device and screen-sharing exceptions. That does not mean an app is absent from processes, permissions, device management, or physical observation. [Cluely guide](https://docs.cluely.com/feature/undetectability)

Electron documents Windows capture exclusion and a macOS limitation where applications using ScreenCaptureKit can still capture a protected window. Microsoft documents `WDA_EXCLUDEFROMCAPTURE`, introduced in Windows 10 version 2004, and explicitly limits it to supported OS capture behavior rather than guaranteeing protection. [Electron](https://www.electronjs.org/docs/latest/api/browser-window#winsetcontentprotectionenable-macos-windows), [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)

Proposed policy: test concrete OS/app/share-mode combinations, present their supported status, offer a selected-window or second-display workflow when appropriate, and let the user hide the overlay. An API returning success is not proof that the remote recording omitted the window. This feature is a release gate, not a slogan.

## 7. Competitive context

| Reference | Verified published scope | Lesson for our product |
| --- | --- | --- |
| Cluely | Live screen/audio assistance plus meeting workflow | Integrate context and action at the moment of need |
| Granola | Bot-free capture; meeting chat, briefs, follow-ups, integrations, APIs/MCP and administration; Business $14/user/month | Notes and meeting memory already have substantial competition |
| Otter | Homepage describes live transcript/chat, summaries, insights and action items | Avoid outdated claims that other assistants work only after meetings |
| OpenCluely | Public project demonstrates an overlay, screenshot reasoning, configurable voice capture, and session context | Basic overlay functionality is commoditized; repository claims are not validation |
| Glass-related public fork | Describes provider choices and audio processing work | Useful implementation reference; provenance and current upstream unresolved |

Sources: [Granola current pricing/features](https://www.granola.ai/pricing), [Otter product](https://otter.ai/), [OpenCluely upstream](https://github.com/TechyCSR/OpenCluely), [Glass-related fork](https://github.com/gouthamravella/cheatingdaddy_glass).

OpenCluely’s retrieved README describes an MIT release, while the inspected upstream LICENSE is Apache-2.0. That discrepancy alone makes copying based on README text inappropriate. Pin a commit and inspect source/dependency notices before reuse. We have not audited its code or run it. The Glass upstream URL tried during research was unavailable; the discovered fork is a reference, not a vetted foundation. [Inspected license](https://github.com/TechyCSR/OpenCluely/blob/main/LICENSE)

## 8. Where we can plausibly be better

These are proposals, not demonstrated Cluely deficiencies:

1. **Grounded answers:** click through to the exact transcript sentence, document section, or external source. Mark uncertainty and missing evidence rather than fabricating product commitments.
2. **Long-meeting reliability:** bounded live context with indexed history, avoiding cost and latency growth from repeated full transcripts.
3. **Privacy consistency:** identical no-training commitments across product settings, contracts, and provider configurations; explicit retention and complete deletion propagation.
4. **Cost transparency:** local/cloud modes, visible included usage, budget caps, and BYOK without implying inference is free.
5. **Self-service business context:** direct document/URL setup, freshness indicators, and revocation without waiting for manual onboarding.
6. **Multilingual quality:** evaluate actual accents, code-switching, names, numbers, and technical vocabulary rather than counting supported languages.
7. **Useful restraint:** short responses, optional proactive alerts, cooldowns, and relevance thresholds. Silence can be preferable to an irrelevant suggestion.
8. **Workflow breadth:** native Microsoft calendar support and reviewed CRM drafts, while retaining an easy no-integration path.

A launch hypothesis is a private meeting copilot for technical founders and small customer-facing teams. They have repeated technical questions, accessible product documentation, and measurable follow-up work. This is not validated demand. Interviews and pilot behavior must determine whether to narrow toward sales, customer success, technical collaboration, or another audience.
