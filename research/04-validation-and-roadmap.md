# Validation and delivery gates

The purpose of this plan is to turn the public-source findings into verified engineering and a defensible claim of better value. No results in this document have been measured yet. Targets are provisional acceptance criteria.

## 1. Define “better” before choosing models

| Dimension | Measurement | Initial proposed gate |
| --- | --- | --- |
| Audio reliability | Lost/duplicated finalized words and unexplained capture gaps | No silent capture failures in the release device matrix; gaps always surfaced |
| Live usefulness | Hotkey to first complete useful sentence | P50 ≤1.5 s, P95 ≤3 s on the defined simple-task cohort |
| Complex assistance | Useful coding/vision answer and correctness | Separate quality/deadline cohort; do not conceal it in the simple-task latency average |
| Grounding | Factual claims supported by cited evidence | ≥95% support on an annotated evaluation set; zero fabricated commitments in release-blocking examples |
| Retrieval | Relevant authorized evidence in top results | Recall@5 ≥90% on the initial company-document set |
| Transcription | WER plus names/numbers/domain-term correctness | Match or outperform the selected reference on each launch language; set numeric gates after baseline |
| Notes | Decisions/action precision and recall against reviewed transcript | ≥95% precision for decisions/actions; recall threshold set with pilot users |
| Long meetings | Latency, memory and context correctness over 2–3 hours | No unbounded memory growth or loss of later corrections |
| Session stability | Completed sessions without unrecovered fatal error | ≥99% during a sufficiently sized pilot; report count and confidence |
| Privacy | Deletion, permission isolation and retention behavior | No unauthorized cross-user/team retrieval in targeted tests |
| Screen-share behavior | Remote-side captured overlay visibility | Pass every advertised OS/app/share-mode combination |
| Cost | Actual invoice-reconciled variable cost at P50/P95 usage | Supports proposed entitlements and margin target without quality degradation |

These are internal gates, not warranties. A small pilot cannot statistically prove rare-failure rates. An isolated unsupported claim or permission breach may warrant blocking a release even if aggregate averages pass.

## 2. Build the evaluation set

Create an initial development set of roughly 100–150 task episodes with controlled or consented audio, screenshots, documents, expected sources, and reviewed outputs. Keep a separate held-out set; prevent prompt/model tuning against it. This size finds obvious failures but is not enough to establish broad superiority or rare-event reliability.

Cover sales objections, technical customer questions, product explanations, negotiation preparation, ordinary team meetings, screen/code questions, and document/history lookup. Include answerable and deliberately unanswerable questions. The assistant must recognize absent pricing, unknown feature commitments, and contradictory evidence.

Vary accents, speech rate, quiet/noisy conditions, mic quality, headphones/speakers, overlap, names, amounts, dates, negation, acronyms, technical terminology, language changes, and code-switching. Include representative Indian English and Hindi/English examples if chosen as launch cohorts; the user’s timezone alone is not proof of market focus.

For transcripts, annotate exact words, corrections, source/speaker labels where established, and time boundaries. Normalize text consistently before WER calculation. Report entity accuracy separately: a low overall error rate can still corrupt a price or due date.

For answers, annotate the latest question, source spans, acceptable alternatives, forbidden unsupported claims, expected uncertainty, and readability. Score task success, helpfulness, factual support, and time to usefulness independently. A concise wrong answer should fail; a slow correct answer should not receive an excellent live-assistance score.

For notes, annotate key decisions, owners/dates actually stated, unresolved questions, and later reversals. Do not award recall for inventing plausible tasks. For coding, evaluate functional correctness in an isolated harness where feasible and separately judge readability and assumptions.

## 3. Comparative protocol

Use identical tasks and input conditions for our candidates and any authorized competitive trial. Log exact app/model versions, OS, device, location/network, audio routing, language settings, plan, and test date. Compare similar product modes; local STT on a high-end device and a cloud competitor under degraded network are separate experiments.

Replay a controlled meeting through the same output device and provide a controlled mic source. Avoid feedback loops. Capture timings with monotonic clocks and a reference recording; observe the actual remote recording for screen-share tests. Do not claim screen-share success from the local preview alone.

Randomize task order, warm/cold-start conditions, and product order. Use blinded output review where possible. Conduct repeated trials to expose tail variability. Report sample counts, failures, P50/P95 distributions, paired win/loss results, and confidence intervals. Separate model-generation delay from transcript endpointing delay and network delay.

If a competitive trial is unavailable or not authorized under applicable terms, compare against provider/reference baselines and clearly limit the claim. Cluely’s published terms contain a competitor-access restriction; this research has not created or used a product account. Arrange an authorized trial or obtain advice on applicable access terms before a hands-on competitive test. This is a specific unresolved testing dependency, not a barrier to independent implementation. [Cluely terms](https://cluely.com/terms)

## 4. Capture and exclusion matrix

Test actual target macOS releases on Apple Silicon and at least one Intel system if supporting Intel; Windows 11 Home/Pro on representative hardware. Older platforms need their own explicit scope decision. Vary display scaling, one/multiple displays, full-screen apps, external displays, sleep/wake, and device changes.

For Zoom, Teams, Google Meet in supported browsers, and any additionally advertised conferencing app, test full-display sharing, selected-window sharing, local recording, and a remote recipient’s recording. Include native screen recording and an independent capture application where the compatibility claim covers them. Retest after OS, conferencing-app, capture-library, GPU, and desktop-framework updates.

Record: OS build, capture app/version, share mode, protection setting, rendering acceleration, remote visibility, artifact path/hash, and pass/fail. Classify unsupported combinations explicitly. Do not conflate hiding the widget with exclusion while the widget remains visible locally.

## 5. Failure tests that matter

| Failure | Expected behavior |
| --- | --- |
| Permission denied/revoked | Explain which source is unavailable; no fake active recording |
| Bluetooth/headphone unplug | Rebind or ask for selection; show any capture gap |
| Screen source changed/monitor removed | Clear stale capture, recover placement, preserve usable controls |
| Network interrupted/roaming | Buffer only within policy; retry; surface loss; avoid duplicate segments |
| STT provider throttled/unavailable | Controlled fallback or pause; independent transcript health indicator |
| LLM timeout | Transcript continues; cancel/retry answer with cost accounting |
| Rapid repeated hotkeys | Latest request wins; old output cannot overwrite newer context |
| Partial transcript revised | No duplicated words; answer snapshot version remains auditable |
| Late numerical correction | Updated state and summary; older fact marked superseded |
| Long conversation | Bounded prompt/memory; earlier evidence remains retrievable |
| Conflicting documents | Surface conflict/freshness; do not choose a convenient price silently |
| Prompt injection in screenshot/document | Does not change authority, reveal secrets, or execute actions |
| Membership revoked | Immediate retrieval/cache denial within defined propagation window |
| User deletes meeting | History retrieval, share links, and caches no longer expose it |
| Duplicate webhook or summary job | Idempotent results and exactly one intended external activity |
| OAuth expired/revoked | Stop connector jobs cleanly; clear remediation flow |
| Update interrupted | Recoverable app; no corrupted local transcript/session |

## 6. First technical spikes

| Spike | Deliverable | Decision it resolves |
| --- | --- | --- |
| Native mic/system capture | Small signed app/helper and health display; device-switch logs | Feasible OS scope and capture cost tradeoff |
| Overlay compatibility | Remote capture artifacts for app/OS/share-mode combinations | Which exclusion claims are supportable |
| STT comparison | Same audio corpus through two cloud candidates and local path | Accuracy/latency/device/cost frontier |
| Context manager | Replayable long meeting with revisions and retrieved evidence | Whether summaries/retrieval preserve task correctness |
| Model/vision evaluation | Short-answer tasks across economical and premium candidates | Router policy and escalation ratio |
| Metering reconciliation | Billable sessions/tokens versus provider invoice sample | Whether economic assumptions survive real billing |

Do these before polishing a dashboard or implementing many connectors. They address the unknowns most capable of invalidating the product and price.

## 7. Staged delivery with exit criteria

**Stage 0 — feasibility and scope.** Complete spikes above; establish launch audience, minimum OS, language coverage, and allowed capture workflows. Exit with evidence-backed decisions, an updated cost model, and clear exclusions. macOS-first is a sequencing proposal; both desktop targets remain in the parity scope.

**Stage 1 — a reliable single-user session.** Installable desktop app, explicit capture control, live transcript, on-demand screen context, streamed short answers, custom instructions, notes/actions, basic export, failure handling, and usage metering. Exit when the core evaluation and device tests pass. Avoid describing this stage as full Cluely parity.

**Stage 2 — knowledge and memory.** File ingestion, source-linked retrieval, bounded long-meeting state, history/search/chat, editable summaries, deletion, mode versions, and local/BYOK options where validated. Exit on grounding, retrieval, isolation, and cost gates.

**Stage 3 — before/after workflow.** Google and Microsoft calendar, sourced preparation, identity resolution, reminders, session detection controls, email drafts, scoped sharing, and one direct CRM connector. Exit on sync recovery, reviewable drafts, and deduplicated writes.

**Stage 4 — business administration.** Teams/roles, shared knowledge, organization policies, SSO/provisioning if needed, billing reports, connector administration, coaching, and pilot metrics. Exit on tenant security tests and reviewed coaching usefulness. Integration/support cost belongs in this tier’s model.

**Stage 5 — mobile and expanded parity.** In-person recording/voice memos, mobile notes/history, secure sync, and expanded platform/language coverage. Verify phone-call and background limitations separately. Reassess the capability map against Cluely’s then-current product.

No calendar dates or engineering staffing estimates are promised here. Time depends heavily on platform experience, native capture compatibility, and the scope selected from experiments.

## 8. Product discovery without losing engineering focus

Interview a small initial cohort across technical founders, sales/customer success, and frequent technical collaborators. Ask them to replay recent difficult meetings, show preparation and follow-up workflows, and identify costly mistakes. Observe whether they need live wording, document lookup, recall, notes, or coaching. Do not ask only whether they “like AI assistance.”

Run a consented pilot after Stage 1. Track repeated use, capture failures, time saved on notes/follow-ups, rejected suggestions, useful-answer rate, escalation rate, support load, and willingness to pay at specified entitlements. Measure outcomes rather than treating token use as value. A few enthusiastic users establish a direction, not a general conversion forecast.

The initial product thesis should be revised if users value reliable meeting memory more than live answers, or if local setup friction outweighs its price advantage. Preserve the broader goal, while choosing a first segment whose repeated tasks can be evaluated.

## 9. Research gaps to keep visible

| Open question | Why it matters | How to resolve |
| --- | --- | --- |
| Current Cluely checkout/usage limits | Accurate price comparison | Verify checkout without purchase and current published terms |
| Current mobile behavior and languages | Parity inventory | Current official app listing/docs and authorized device evaluation |
| Cluely measured answer/transcript quality | Competitive claims | Authorized controlled trials |
| Current capture-exclusion mechanism | Feasibility and compatibility | Public disclosures plus our own OS experiments; private internals may remain unknowable |
| Actual provider billing for chosen channel/session mode | Subscription margin | Contract docs and invoice reconciliation |
| Local STT quality across devices/languages | Hardware eligibility | Controlled device corpus and long-session tests |
| Customer demand and usage distribution | Product/pricing | Interviews and pilot telemetry with consent |
| Launch-market recording/data rules | Product controls/contracts | Jurisdiction-specific primary-law review and professional advice |
| Connector schema/permissions and costs | Enterprise completeness | Provider-specific implementation research before each connector |
| Repository provenance/licensing | Safe code reuse | Pin commits, dependency/license audit, notices |

## 10. Decisions to carry forward

Keep a full before/during/after capability map. Build reliable capture and context before feature volume. Optimize for the first useful sentence and supported claims. Use local/BYOK or honest cloud quotas to support low prices. Treat screen-share exclusion as a tested compatibility feature. Keep evidence, inference, and design proposals separate. Re-run the cost and quality evaluations when models, prompts, routing, devices, or capture paths change.
