# Reliability implementation

This stage implements the approved reliability lab. It does not establish production readiness or superiority to Cluely. The original [feasibility](RESULTS.md) and [live benchmark](LIVE_RESULTS.md) reports remain historical records.

## Implemented behavior

- **Source selection:** document identity/title/kind is independent of microphone/system capture. Retrieval filters explicit source scope, ranks informative term coverage, preserves negation and Unicode, and asks for clarification on missing or ambiguous selected sources. Provisional speech is a separate snapshot field and is excluded from model facts.
- **Transcript finalization:** a persistent CPU Whisper worker uses Silero VAD, 224 ms onset, 608 ms silence endpointing, 300 ms trailing padding, one-second decoding, a 30-second audio window, and rolling commitment with two seconds of retained overlap. The current v2 router requires a unique lexical handoff anchor; v1 used timestamp-only deletion. Endpoints trigger a fresh final decode. Prefix agreement is never promoted as a final.
- **Source recovery:** each microphone/system source has its own decoder epoch and a producer queue below two seconds. Timestamp discontinuities and overload emit explicit gaps, retire affected provisional text, restart only that source, and reject late callbacks. Native audio resampling/capture is not connected to this router yet.
- **Generation:** immutable final evidence enters the Gemini adapter. Citation IDs must belong to supplied evidence; a shared optional request gate cancels superseded requests and rejects responses when final facts, source identity, gaps or lifecycle change. Unrelated provisional updates do not cancel generation. Snapshot mode is the current default. Citation validity does not prove factual support.
- **Names:** a fixed prior roster can guide transcription. A separate name-review helper preserves literal spelling and presents suggestions requiring explicit identity confirmation. Exact roster spelling is not identity proof. This helper does not yet gate every generated ownership claim in an application.
- **Budget:** existing ledger rows migrate additively and retain their historical classification. Confirmed Gemini free access and AssemblyAI $50 credits permit up to $10 nominal usage while preserving a $2 possible-cash ceiling. Missing usage, incomplete sessions and ambiguous failures retain reservations. Hosted evaluation failures write a shared halt file. No account billing settings are changed.

## Reproducible evaluation

VCTK 0.92 supplies 144 licensed clips: 24 speakers, six utterances each, 12 development and 12 held-out speakers. Selection cycles through publisher accent labels and includes Indian speakers. Twelve labels are represented, one being `Unknown`; small per-accent counts are not population-level evidence. Attribution: Yamagishi, Veaux and MacDonald (2019), [CSTR VCTK Corpus 0.92](https://doi.org/10.7488/ds/2645), University of Edinburgh, CC BY 4.0.

The separate name set contains 12 fictional cases in two installed TTS voices: 24 clips, six development and six held-out cases per voice. These are case-held-out, not voice-held-out. Cases include negation, corrected ownership, unknown names, and similar spellings. The fixed vocabulary is not derived from reference transcripts.

`frozen-evaluation.json` seals local model hashes, decoder C++ source, manifests and recognition parameters before held-out inference. Supplemental VAD/binary/Python hashes were recorded during execution, rather than claiming they were sealed beforehand. Whole-file CLI comparisons use segment timestamps; VAD and token timestamps belong to the streaming worker. Whole-file timings include startup and ran concurrently, so they cannot satisfy streaming latency gates.

Raw WER uses lowercased Unicode words without spoken-number normalization. A separately labeled, narrow dollar-amount normalization is diagnostic only. Names use exact mention matching; owners use a conservative literal `NAME owns` scorer with negation/correction fixtures. Grammar and identity still need semantic review. Reports include sample coverage and false roster substitutions so incomplete groups cannot pass the 95% name/owner target.

## Run and inspect

```sh
make test
make local-engine
python3 -m spikes.audio_fixtures names
python3 -m spikes.dataset prefetch
python3 -m spikes.dataset fetch
make reliability-freeze
python3 -m spikes.evaluation run --engine local --split development
python3 -m spikes.evaluation run --engine local --split held_out
make reliability-report
make router-probe
python3 -m spikes.audio_fixtures sustained
python3 -m spikes.streaming --wav spikes/results/local/sustained-30m.wav --paced --out spikes/results/local/stream-sustained-30m.json
python3 -m spikes.stress_report --input spikes/results/local/stream-sustained-30m.json --out spikes/results/local/stress-summary.json
```

The recognizer checkout, models and VAD artifact must already exist at the documented local paths. Speech generation and public subset downloads may need macOS/network permission. Dataset transfer uses bounded ZIP ranges and rejects servers that return the full archive; archive-entry CRCs and clip SHA-256 are verified. No full-archive checksum is claimed.

Hosted comparisons use `.venv/bin/python -m spikes.evaluation run --engine assemblyai --split development` or `--split held_out`. They are currently halted after incomplete sessions; reconcile the saved failure and provider usage before removing the halt file. Do not delete the usage ledger or replay successful calls to recover budget. Status remains readable with `python3 -m spikes.providers status`.

All raw fixtures, provider traces, JSONL checkpoints and the ledger live in ignored local directories. Published results contain aggregates and fictional source cases. Interruptions before the hardened checkpoint path may lack recoverable event traces; those remain explicitly incomplete.

## Rolling handoff repair

The frozen v1 worker’s first continuous development block lost five words after the explicitly declared dollar-amount normalization (5/188 word edits). “Raw audio” and “annual budget is” disappeared at rolling handoffs despite no transport gap. This is an accuracy failure, not a passed continuity gate.

The v2 worker keeps the same recognition settings but requires a unique lexical suffix anchor near the physical overlap. Approximate timestamps bound the search rather than deleting new words. An unresolved final handoff emits an explicit gap. Six native regression scenarios cover timestamp drift, missing anchors, repetition outside the handoff, insufficient context, ambiguous anchors and punctuation. The v1 source/configuration/results remain intact. The v2 development configuration was recorded before testing. Its accelerated 73.21-second comparison completed with two rolling boundaries and no gaps: all 188 words matched after the declared narrow dollar-amount normalization, compared with five lost words in v1. Raw WER is 6.12% because the recognizer renders spoken amounts as currency numerals. This targeted development result does not establish general meeting accuracy.

```sh
make overlap-test
python3 -m spikes.audio_fixtures continuous
python3 -m spikes.streaming --worker-version v2 --wav spikes/results/local/continuous-clean.wav --out spikes/results/local/rolling-v2-development.json
```

This continuous fixture uses the controlled Samantha clip prepared in the earlier experiment instructions. The new source router selects v2; the general replay/evaluation path keeps v1 by default to preserve frozen comparisons. Always label the selected worker. The v2 repair does not retune the held-out recognizer or establish long-session/annotated-latency acceptance.

## Remaining acceptance boundaries

A completed paced stress replay can establish bounded audio/queue behavior and explicit transport outcomes for that workload. It cannot establish meeting accuracy, dual-source capacity, actual billing, or end-of-utterance latency. Queue bounds exclude kernel pipe buffers and recognizer model memory. Rolling alignment requires independent transcript/alignment validation before promising zero duplicated or omitted words; v1 already failed the development continuity check.

`latency.py` evaluates independent speech-start/end annotations, keeps missing finals in coverage, and labels cold-start exclusions. Recognizer word ends are diagnostic proxies and cannot pass the two-second p95 target. Native audible capture, microphone leakage, sleep/device transitions and conferencing exclusion remain separate gates. Hindi acceptance is deferred.

The current stage intentionally leaves the full copilot UI behind these gates. The measured outcomes below determine the next repair work.

## Measured outcomes (2026-10-08)

All 60 tests pass. All 672 local recognitions completed: 168 clips × two models × two vocabulary conditions. The public subset contains about 503 seconds of short read speech; held-out speaker separation does not establish unseen training data or conversational generalization.

| Held-out condition | Public speech WER (72 clips) | Exact names (16 mentions / 12 clips) | Owner accuracy (12 clips) | False roster-name substitutions |
| --- | ---: | ---: | ---: | ---: |
| base.en / unbiased | 0.38% | 56.25% | 58.33% | 1 |
| base.en / vocabulary | 0.77% | 68.75% | 75.00% | 2 |
| small.en / unbiased | 0.77% | 62.50% | 66.67% | 2 |
| small.en / vocabulary | 0.58% | 81.25% | 83.33% | 2 |

Every complete name/owner condition fails the 95% target. Vocabulary guidance improves the controlled names but changes both held-out “Meera” examples to “Mira” in small.en. Correct spelling can be acoustically ambiguous; do not apply roster replacement automatically or claim ownership identity from dictation confidence.

All 12 source-selection cases retrieved the intended evidence or requested clarification. Ten generated replies and two clarifications were adequate against the fictional fixture criteria on agent review; independent human review remains pending. Correct IDs alone do not establish support.

The isolated source-router probe preserved microphone epoch 0 while resetting the system to epoch 1. It retained an explicit gap for the discarded unfinalized region and delivered the next finalized budget to the context store. Microphone input was controlled silence, so this does not prove dual-source speech capacity or acoustic isolation.

Only seven hosted comparison results completed before two batches stopped without confirmed usage. Their cause is unestablished; the earlier exception path did not save transport-stage diagnostics. A preceding sandbox DNS failure also retained its reservation. New runs save failure traces and a shared halt prevents continuing after unresolved hosted failures. No hosted aggregate has complete coverage, and none can pass acceptance.

Current nominal estimated/reserved exposure is $0.1678978333333333333333333332; possible-cash exposure is $0.1624135. These include retained reservations and historical unknown classifications, not an invoice. No ledger rows were deleted or retroactively reclassified. `BudgetLedger.reconcile` requires a verified usage reference, keeps an audit record, and does not clear the hosted halt automatically.

The initial paced sustained attempt failed on overload/shutdown under competing recognition work and lost its pre-hardening in-memory event trace. It is preserved as incomplete. The isolated v1 rerun completed all 1,800 seconds in 1,800.445 seconds, with a maximum retained window of 29.996 seconds and a maximum producer queue of 0.064 seconds. It produced 82 nonempty final segments, crossed 28 rolling boundaries, and reported no transport gaps/errors or duplicate final segment IDs. Its continuity accuracy still failed on the first development block. Transport completion and word preservation are separate outcomes.

## Validation completion (2026-10-09)

The v2 silence fixture contained five seconds of silence and emitted no transcript, with zero recognition decodes. The repaired source-router probe preserved microphone epoch 0 and reset only the system to epoch 1, retaining the explicit discontinuity gap and delivering final budget evidence. Both runs completed. Sixty Python tests and six native overlap scenarios pass; Python compilation also succeeds.

The v2 repaired-fixture paced confirmation completed 73.2115 seconds of audio in 73.238 seconds, crossed two rolling boundaries, and preserved all 188 words after the declared narrow dollar-amount normalization. It reported no gaps/errors, a maximum retained window of 29.986 seconds, and a maximum producer queue of 0.032 seconds. Raw WER remains 6.12% from spoken-amount rendering. The three recognized-word-end delay proxies were approximately 3.72, 3.61 and 2.41 seconds; two are rolling boundaries, and none is an independently annotated utterance endpoint. They cannot pass the latency gate. A 30-minute paced run of v2, independently annotated latency, native audible capture and broader conversational/name acceptance remain open. The v1 long-run measurement cannot be relabeled as v2 validation.

The machine-readable [published aggregate](results/2026-10-08-reliability.json) preserves both the failure and repair, fixture/configuration hashes, source review, coverage, and budget accounting. Raw traces remain in the ignored local results directory. No further cloud calls were made during the final validation.
