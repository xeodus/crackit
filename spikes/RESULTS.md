# Measured feasibility results — October 8, 2026

Follow-up: [the live provider results](LIVE_RESULTS.md) now measure ten model requests and one hosted speech session. The table below preserves the earlier local-only snapshot; its hosted-pending status is historical.

The basic local pipeline is feasible enough to continue. It does not yet establish production transcription quality, universal screen-share exclusion, or an advantage over Cluely. The most useful result is that recognition throughput is inexpensive locally while names and provisional transcript correctness remain substantial risks.

Machine: Apple M1, arm64, macOS 26.5.1. Context tests used Python 3.9.6/SQLite. Recognition used whisper.cpp v1.9.5, pinned commit `d1be6fde11ac6e0407606b4e42fe72d34add8037`, `base.en`, four CPU threads, English, greedy decoding. [Recorded measurements](results/2026-10-08-feasibility.json) include fixture hashes, model checksum, complete hypotheses, method limitations, and aggregate native diagnostics. Original local logs are retained under the ignored results directory.

## Results and implications

| Experiment | Observed result | Implication |
| --- | --- | --- |
| Correctness suite | 32 tests pass | Revision, scoping, bounded context, deletion, stale-output rejection, budget accounting and model-stream parsing work on the tested cases |
| Long-history context | 1,801 synthetic segments; 200 snapshots; corrected old evidence retrieved 200/200; snapshot median 2.72 ms, nearest-rank p95 2.91 ms | Simple scoped lexical retrieval is fast enough to prototype; relevance beyond this repeated synthetic corpus is unproven |
| Context size | Maximum observed snapshot context 1,696 UTF-8 bytes against a 5,400-byte bound; database 749,568 bytes | The fixture stays bounded; this excludes complete provider payload overhead and real tokenization |
| Clean Samantha speech, CPU | 17.55-second clip; three whole-file runs, median 0.542 s; WER 6.12% | Whole-file throughput is comfortably faster than audio duration on this fixture |
| Same speech, Metal | Three aligned whole-file runs, median 0.600 s; same transcript | GPU did not improve this small workload; use a persistent engine and benchmark actual production workloads before choosing a backend |
| Initial Metal setup | First measured whole-file run 7.85 s; later runs about 0.62 s; initial causal model load 6.62 s | GPU initialization/compilation materially affects cold startup; these timings alone do not isolate every cause |
| Seeded additive noise | One CPU run, global target SNR 10 dB; WER 12.24%; two agreed-prefix retractions | Previously agreed text can change; the application needs explicit revision handling |
| Tara Indian English TTS | One CPU run, 17.28 seconds; WER 14.29%; wrong launch-owner phrase | Entity accuracy can fail even when most words and throughput look good |
| Digital silence | Five seconds; recognizer emitted `[BLANK_AUDIO]` | Non-speech markers need explicit handling; empty-reference WER is undefined and must not be reported as an accuracy percentage |
| Native capture | 15.47-second user-started run; 758 system buffers, 748 microphone buffers; no errors, backwards timestamps, or gaps over 100 ms detected | Buffer delivery works in this run; audible signal, correct content, source separation, and sustained operation are not established |
| Own-overlay capture | Two local runs: baseline magenta ratio 0.67045; restricted ratio 0 | Marker not observed with `.none` on this selected-window path; no conferencing/full-display/Windows claim follows |
| Hosted benchmarks | Zero requests; $0 estimated spend; $2 total authorized | Adapters are implemented and tested with simulated transport; live latency, quality, and billing await locally configured keys |

The long-history run takes about 1.49 seconds wall time because it is accelerated synthetic ingestion, not three hours of continuous operation. It does not measure capture reliability, thermals, battery, background interruptions, or an LLM’s quality over three-hour meetings. Retrieval queries and fixture content are development data, not held-out evaluation data.

The native audio report contains zero `peak_rms` for both channels, but the initial diagnostic did not count successful RMS measurements. That cannot distinguish silence from an unsupported buffer representation. The updated diagnostic reports format flags, bit depth and measured-buffer counts. A controlled audible-signal run remains required. No raw audio was saved/uploaded by the native diagnostic, and overlay screenshots were discarded after calculating ratios.

## What changed after a failure

The first causal replay used timestamp-free decoding with default temperature fallback. At 12, 14 and 16 seconds, hypotheses collapsed to essentially “The” on the clean fixture, then recovered at the full clip. Both CPU and Metal reproduced this behavior. The whole-file CLI used different settings, so the speed/accuracy comparison was not sufficient to validate the replay.

We aligned causal decoding with deterministic whole-file settings: timestamp tokens enabled, temperature increment zero, greedy best-of one. The clean fixture then preserved its growing transcript through all nine checkpoints, with zero lexical agreed-prefix retractions. Two decoding settings changed together; this experiment does not isolate a single causal mechanism. Original failing traces are retained in the measurements rather than discarded.

We also corrected the replay’s retraction metric to compare normalized words, so punctuation/case changes alone do not count as lexical retractions. This means the initial raw retraction counts and revised counts are not directly comparable. Even the revised metric ignores semantic punctuation changes: some prefixes joined “must not save raw audio” to “if the network disconnects,” which could change the meaning despite stable words.

The noise run still produced two genuine agreed-prefix retractions. The Tara fixture sometimes agreed on a wrong phrase, ultimately producing “Meet our approval” where the reference says “Mira owns the launch approval.” Agreement is therefore neither correctness nor finality. Prompting an answer model with that mistaken transcript could invent an owner or omit one. This is an engineering acceptance gate, not a cosmetic issue.

WER on the clean fixture penalizes the recognizer’s numerical rendering of “twelve thousand dollars” as “$12,000.” That accounts for the observed three word edits under our unnormalized metric. The speech contains 49 reference words; the percentage is too small-sample and format-sensitive to generalize. The added-noise fixture uses seeded Gaussian samples (seed 20261008, target global SNR 10 dB) and clipping; it is not a real meeting room. Voices, accents, speakers, channel overlap, Hindi/code-switching, technical names, and realistic interruptions need representative evaluation.

## Decisions for the next stage

Continue with macOS native capture plus a small local orchestration core. SQLite is sufficient for the isolated experiment and should remain behind a store interface. Production authorization, encryption, synchronization, multi-user access, and remote search are separate work; these tests do not establish security of a deployed service.

Keep both local and hosted transcription adapters. `base.en` is a baseline rather than a selected production recognizer. Compare larger/multilingual local engines and hosted recognition on the same held-out tasks, then choose by entity accuracy, bounded streaming latency, resource use, and cost. CPU is the default experimental backend for now because the tested clip showed no Metal advantage. No general CPU superiority is claimed.

Build a rolling, bounded recognizer next with voice activity detection, provisional revisions, explicit segment finalization, silence/non-speech handling, and source identity. Test corrections end-to-end through retrieval and answer cancellation before adding more UI features. Do not promote simple two-pass prefix agreement into immutable evidence.

Complete the hosted tests once both keys are configured: five grounded model cases and one paced transcription session, reserving at most $0.13 initially against the shared $2 ceiling. Review actual answers/citations and failed cases, retain ambiguous reservations, and reconcile provider billing. Then test generation with retrieved context rather than all fixture evidence. The current experiments isolate components and do not measure end-to-end answer latency.

Finish audible capture and screen-share compatibility tests before product claims. Selected-window exclusion here is useful evidence but does not settle behavior in a conferencing app, full-display sharing, another OS build, or a remote recording. Windows parity and the complete preparation/live-assistance/transcript/summary/history/knowledge/integration workflow remain required by the project objective.

## Current acceptance status

| Gate | Status |
| --- | --- |
| Independent research and feature/economics map | Completed baseline; unknown proprietary behavior remains labeled |
| Local context correctness and bounded synthetic replay | Passed the current development cases |
| Native buffer delivery | Passed one short run; signal/device/sustained reliability pending |
| Selected-window local overlay marker test | Passed this path in two runs; broader compatibility pending |
| Local short-clip recognition throughput | Measured; enough to continue |
| Representative recognition and safe finalization | Not passed; name error and noisy retractions observed |
| Live hosted latency, quality and cost | Pending local credentials |
| Integrated working copilot and Cluely comparison | Not implemented/tested |

Commands and prerequisites are in [the lab instructions](README.md). The [research delivery plan](../research/04-validation-and-roadmap.md) remains the roadmap for full parity.
