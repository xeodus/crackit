# Economics: can we charge a fraction of Cluely’s price?

Provider figures were retrieved on 2026-10-08. All values are USD, before tax. They are public list prices, not Cluely’s negotiated costs. Our workload assumptions are estimates and must be replaced with pilot measurements.

## 1. Current references and their limits

| Component | Published reference | How to use it |
| --- | --- | --- |
| AssemblyAI Universal Streaming | $0.15/hour; multilingual variant lists the same rate | Low-cost hosted STT candidate; verify actual language set and billable session behavior |
| AssemblyAI Pro Realtime | $0.45/hour | Higher-priced quality candidate; add-ons must be inspected separately |
| Deepgram Nova-3 monolingual streaming | Promotional $0.0048/minute = $0.288/hour; regular $0.0077/minute = $0.462/hour | Model both promotional and ordinary rates |
| Deepgram Nova-3 multilingual streaming | Promotional $0.0058/minute = $0.348/hour; regular $0.0092/minute = $0.552/hour | Do not price multilingual usage at English-only rates |
| Recall desktop capture | $0.50/recording hour | Separate from built-in transcription at $0.15/hour |
| Gemini 2.5 Flash-Lite standard text/image input and output | $0.10 and $0.40 per million tokens | Illustrative economical model, not a quality recommendation without evaluation |
| Claude Sonnet 4.6 input/output | $3 and $15 per million tokens | Illustrative premium reasoning tier; cheaper/newer models also listed |
| Merge Unified launch | 3 production accounts free; $650/month up to 10, then $65/account | Strong reason to separate business integrations from a cheap consumer plan |

Sources: [AssemblyAI pricing](https://www.assemblyai.com/pricing), [streaming product](https://www.assemblyai.com/products/streaming-speech-to-text), [Deepgram pricing](https://deepgram.com/pricing), [Recall pricing](https://www.recall.ai/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-lite), [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Merge pricing](https://www.merge.dev/pricing/unified).

Provider latency/accuracy claims are not directly comparable. Different endpoints, language coverage, add-ons, context windows, and billing definitions matter. Reconfirm availability and prices at procurement. In particular, Deepgram’s page marks some streaming rates as promotional. Trial credits are excluded from sustainable unit economics.

The Gemini page distinguishes free and paid data-use treatment. Do not use free developer quotas as the assumed production economics or privacy configuration. Premium reasoning may incur thinking/output tokens; cap and meter all billable categories. Images are not costed here as “one text token.” Their actual billable token count enters the input budget.

## 2. The equation

```text
Monthly STT = meeting_hours × cloud_share × billable_stream_multiplier × STT_rate
Monthly capture = meeting_hours × cloud_share × capture_rate
Monthly answers = meeting_hours × answers_per_hour × weighted_answer_cost
Per-answer cost = input_tokens × input_price / 1e6
                + output_tokens × output_price / 1e6
Total variable cost = (STT + capture + answers + summary + retrieval/search)
                      × retry_reserve_multiplier
                    + hosting/support_allowance + payment_cost
Contribution = subscription_price - total_variable_cost
```

Use actual billable audio/session duration. For two simultaneous mono provider streams, the billable multiplier can be two. A stereo/multichannel request may have different pricing; verify its contract rather than inferring that one WebSocket means one charge. Mixing mic/system into mono can reduce provider work but harms source separation and overlapping-speaker quality. Deepgram supports separate channel transcripts, which is a functionality disclosure, not a billing guarantee. [Multichannel behavior](https://developers.deepgram.com/docs/multichannel)

The default calculator charges cloud STT for full meeting duration. It assumes **no VAD billing discount**. Removing silent packets may save bandwidth without reducing session billing. Local processing shifts compute/battery costs to the user; it removes that cloud inference fee, not every operational cost.

## 3. Illustrative answer costs

Assume 6,000 input tokens and 250 output tokens per answer, uncached. This is a target context size, not a measured average. It must include screenshots and retrieved content as actually billed.

| Model reference | Cost per answer | 20 answers per meeting hour |
| --- | --- | --- |
| Flash-Lite at $0.10/$0.40 | $0.0007 | $0.014/hour |
| Sonnet 4.6 at $3/$15 | $0.02175 | $0.435/hour |
| 90% economical + 10% premium | $0.002805 average | $0.0561/hour |

The premium escalation ratio is decisive. If every request needs the premium model to match quality, the mixed scenario is invalid. A 20,000-token average input makes the same premium answer $0.06375, almost three times the assumed cost. Long context, search, repeated retries, and long reasoning can dominate small-model text inference.

At one economical generation every five seconds, there are 720 calls/hour, or $0.504/hour at this prompt size. At one per second the figure is $2.52/hour. These calculations ignore additional detector/transcription costs. Proactive assistance must use event filtering, not unbounded polling.

## 4. Modeled monthly scenarios

Calculator assumptions: subscription $6; 20 answers/hour; 90/10 economical/premium mix; 6,000/250 tokens per answer; $0.02/hour post-call analysis allowance; $0.01/hour retrieval/search allowance; 15% reserve on metered API costs; $1/user/month hosting/support allowance; illustrative payment allowance of 3% + $0.30. Hosting/support and payment figures are planning inputs, not researched quotes, and exclude engineering, acquisition, legal, tax, refunds, and fixed overhead.

| Configuration | Meeting hours | Estimated variable cost | Contribution at $6 |
| --- | --- | --- | --- |
| Local STT; cloud answers | 10 | $2.47 | $3.53 |
| Local STT; cloud answers | 40 | $5.44 | $0.56 |
| Native capture + one $0.15/hour cloud STT stream | 10 | $4.20 | $1.80 |
| Native capture + one $0.15/hour cloud STT stream | 40 | $12.34 | -$6.34 |
| Native capture + two $0.15/hour cloud streams | 10 | $5.92 | $0.08 |
| Native capture + two $0.15/hour cloud streams | 40 | $19.24 | -$13.24 |
| Recall capture + built-in STT | 10 | $9.95 | -$3.95 |
| Recall capture + built-in STT | 40 | $35.34 | -$29.34 |

These are contribution estimates, not business profitability. A $1 support allowance may be too low, especially during audio troubleshooting or enterprise onboarding. Search/profile enrichment and integrations need their own limits. Heavy users and concurrent meeting peaks are more informative than average usage alone.

At $6 with a 60% contribution-margin target under these assumptions, the maximum included usage is approximately 9.3 hours with local STT/cloud answers, 3.4 hours with one low-cost cloud stream, and 2.1 hours with two. This is why local/BYOK operation or bounded cloud entitlements matter. Treat these breakpoints as sensitivity results, not recommended launch caps before validation.

## 5. Proposed commercial design

| Product mode | Proposed offer structure | What must be clear |
| --- | --- | --- |
| Local/BYOK | Low-cost client subscription or one-time license, price to test | User pays provider inference separately; local STT hardware suitability |
| Affordable hosted | $6–9 price experiment with an explicit hour/answer budget | Included cloud hours, premium credits, fair overages, usage meter |
| Heavy hosted usage | Higher included allowance or prepaid usage packs | Hours and models drive cost; no hidden downgrade on exhaustion |
| Teams/business | Separate seat + integration/workflow package | Connector accounts, administration, support and retention costs |
| Fully local | Optional advanced-device configuration | Benchmark quality/latency; no promise of frontier reasoning on every laptop |

The $6–9 price is a hypothesis, not an approved business decision. A $6 price is not a comparable cheaper product if it offers only a few cloud hours while the reference offers unlimited meetings. We should show capability and usage comparisons side by side.

Avoid paywalling basic privacy controls. Screen-share exclusion can be included where verified; its engineering/support cost must still be covered. Separate paid cloud compute from capture, retention, and transparency so product trust does not depend on the highest tier.

## 6. Cost reduction priorities

1. Own native capture once the compatibility spike demonstrates reliability. This removes a recurring SDK capture fee but increases engineering/support work.
2. Evaluate local STT on capable devices, with explicit fallback. Avoid forcing a low-quality local path solely to make a spreadsheet attractive.
3. Bound context and output. Preserve exact evidence outside the prompt in retrieval storage.
4. Route by task using measured acceptance rates. Report escalation share and billed reasoning tokens.
5. Cache stable prompts and repeated preparation, respecting ACLs, TTL/storage charges, and invalidation.
6. Filter proactive triggers and cancel obsolete work where provider billing supports cancellation.
7. Batch asynchronous tasks only when their deadline permits it. Batch pricing does not solve live-answer latency.
8. Start with direct connectors and Postgres-based retrieval; expand paid infrastructure when measured needs justify it.

## 7. Self-hosting is not automatically cheap

For server STT, estimate effective cost as GPU hourly cost divided by **measured concurrent real-time streams**, plus idle capacity, CPU, networking, storage, monitoring, and engineering. Do not use offline batch throughput as a live concurrency guarantee. Streams with low latency requirements may need more headroom and prevent efficient batching.

Compare provider bills at observed P50/P95 user usage, then include reserved peak capacity, regional latency, and operational load. For local inference, measure real-time factor, battery draw, model download size, memory contention with conferencing apps, and thermal throttling. Optimizing one invoice while breaking meetings is not a price advantage.
