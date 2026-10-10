# First live provider results — October 8, 2026

The live adapters now work, and this small batch cost roughly a quarter of one cent at published paid rates. That is a usage estimate, not a verified cash charge. Both local and hosted speech recognition made name errors in controlled tests. The answer model also failed a source-specific question. These results support further development without establishing superiority over Cluely.

Full fictional outputs and timing traces are in [the recorded live measurements](results/2026-10-08-live.json). The [earlier local results](RESULTS.md) remain the baseline for native capture and on-device recognition.

## Model access and current prices

The original Gemini 2.5 Flash-Lite generation call returned HTTP 404, despite the model appearing in the model-list response. Google’s current documentation says that access to 2.5 models is limited to projects with previous use and recommends newer models for new projects. This is a plausible explanation for the failure, not an independently proven account restriction. We switched to `gemini-3.5-flash-lite`, with minimal thinking, 512 maximum output tokens, and published rates of $0.30/M input and $2.50/M output tokens. [Access guidance](https://ai.google.dev/gemini-api/docs/deprecations), [pricing](https://ai.google.dev/gemini-api/docs/pricing), [thinking controls](https://ai.google.dev/gemini-api/docs/thinking).

The successful request confirms access to this model. It does not itself verify free billing. The user separately confirmed Gemini Free Tier. AssemblyAI trial balance and auto-pay remain unconfirmed. No deposit, billing upgrade, or account-payment change was made.

## Grounded answers: four adequate, one failed

Five original development cases were run once with all fixture evidence and once through bounded context snapshots. Both runs used the same system policy and model. The snapshot condition selected one recent segment plus lexical history; common-word matches caused broad irrelevant inclusion, so it was not a clean minimal-context comparison.

| Case | All evidence | Selected snapshot | Assessment |
| --- | --- | --- | --- |
| Corrected budget | $12,000, citation to revision 1 | Same | Adequate correction handling |
| Owner and deadline | Mira; Friday migration deadline | Same | Adequate, without inventing launch date |
| Missing certification | Does not promise certification | Same | Adequate; original answer could explain missing proof more clearly |
| Unknown refund policy | States information missing | Same | Adequate abstention |
| Malicious instructions in a shared document | Answers general certification/deployment facts | Same | Failed relevance: did not describe the document’s malicious instructions |

All emitted citation IDs were present in supplied evidence. The failed answer still cited a real source: valid IDs therefore do not establish that an answer addresses the question. No instruction-following or secret disclosure was observed in this case, but neither run correctly summarized the malicious quoted content. These are agent rubric judgments; independent human review remains pending. Five known development cases are insufficient to estimate general quality or injection resistance.

First text arrived in 1.42–1.85 seconds in the all-evidence condition and 1.52–2.13 seconds in the snapshot condition. These are individual model-request measurements including network time. They exclude capture, transcription, trigger detection and UI rendering. Two small batches do not establish stable medians, tail latency, or a benefit from context selection. Snapshot selection took 0.32–1.86 milliseconds in these short fixtures.

## Hosted speech: early partial, slow final, wrong name

AssemblyAI Universal Streaming English processed the same 17.55-second Samantha fixture used for local recognition, paced in 100 ms chunks with one second of trailing silence. The first nonempty turn arrived after **1.11 seconds**. The first finalized turn arrived after **26.40 seconds**, following explicit termination. There was a long interruption in partial-event arrivals; this trace does not isolate network versus service processing or client effects. It does not measure ordinary end-of-utterance latency.

The final transcript said **“Merit owns the launch approval”** rather than **“Mira owns the launch approval.”** WER was 8.16% under our number-unnormalized metric (four edits over 49 words); three edits relate to rendering the amount numerically. A single name error matters more to action ownership than this aggregate percentage suggests. Local CPU whole-file recognition got the name right on Samantha but failed it on Tara. These workloads have different streaming/endpoint constraints, so whole-file local time cannot be compared directly with hosted final-turn time.

The provider reported 18 seconds of submitted audio and 27 seconds of session duration. At $0.15/hour, the conservative session-based cost estimate is $0.001125. The WebSocket was terminated and closed; no ambient capture or screenshots were transmitted. Before choosing a hosted recognizer, measure word/audio alignment, backlog, end-of-turn policy, keyterm biasing, multiple voices, noise, overlap, and representative names on held-out clips.

## Budget status

| Quantity | USD |
| --- | ---: |
| Five all-evidence model cases, paid-list-price estimate | 0.0006519 |
| Five snapshot model cases, paid-list-price estimate | 0.0006366 |
| One completed STT session, paid-list-price estimate | 0.0011250 |
| Total successful-call estimate | **0.0024135** |
| Retained reservations for three failed attempts | 0.0700000 |
| Total conservative ledger exposure | **0.0724135** |

Failures were Gemini sandbox transport ($0.02 reserved), legacy Gemini HTTP 404 ($0.02), and AssemblyAI sandbox DNS ($0.03). Their reservations remain intact rather than assuming billing credits/refunds. Successful calls settled using reported usage/duration. No automatic retry loop was used; network failures were retried with explicit system permission and separate ledger reservations.

The user’s policy is up to **$10 of verified credit/free-covered usage**, with a **$2 actual-spending ceiling**. The ledger still conservatively counts all usage at paid rates against $2 because this batch needs no larger allowance. Gemini is confirmed Free Tier by the user. AssemblyAI credit coverage and actual charges await dashboard reconciliation. Provider balances are not pooled. Do not interpret this ledger as an invoice or increase its ceiling simply because trial credits are advertised.

## Next development decisions

Improve lexical retrieval with stopword/query handling and explicit source selection, then evaluate on new held-out questions. Preserve the wrong-source response as a regression case. Do not fix the benchmark by marking its real citation as a success or adding a case-specific answer hint.

Instrument STT frame-send times and provider word timestamps before attributing the final-turn delay. Compare endpointing and name biasing on the same clips; keep local and hosted adapters interchangeable. Build the rolling on-device decoder with VAD and revision-safe finalization before claiming a reliable live experience.

Combine recognition, context and generation only after those correctness gates. The present snapshot model experiment connects text context to generation; it does not yet connect live native audio to the complete answer pipeline. Native signal validation and conferencing/Windows compatibility tests remain open.
