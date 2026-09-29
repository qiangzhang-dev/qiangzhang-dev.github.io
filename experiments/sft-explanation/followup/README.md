# Rewording and final-value evaluation follow-up

This is a post-hoc follow-up to the paired SFT pilot in the parent directory. It adds **no training**. All four saved final-epoch LoRA adapters are reused.

## What is controlled

- The same 48 question IDs, underlying quantities, answers and task categories are retained. The wording may express an equivalent quantity differently: for example, 25 percent becomes one quarter.
- Each question receives one alternative English wording. The shared instruction to end with `Answer: <number>` stays the same.
- This is one rewording, not new tasks or new numerical combinations. The questions are paired, not independent samples.
- All evaluation cells use greedy generation with a 512-new-token budget, four-item batches, the same system/chat template, and the original CPU environment.
- The baseline/original cell reuses `../results/baseline-512-posthoc.json`. The baseline/reworded and eight trained-model cells are generated afresh (432 responses).
- `protocol.json` and `reworded.json` were written before the new inference run. Their hashes and all adapter checksums are recorded. Prior pilot results were already known: this is not an independent, blind, or preregistered study.

## Two different questions

1. **Terminal Answer format:** Is there an unambiguous explicit `Answer: <number>` near the end, with only closing punctuation/markup or permitted units afterward (including Markdown bold and quoted fields)? Conflicting explicit Answer values and an expression such as `Answer: 230 - 46 = 184` do not pass this check. This is a narrow format check, not a complete instruction-following metric.
2. **Final numerical value:** What number does the model ultimately claim? An ending boxed number or closing declarative sentence can count even without an Answer field. This grades the final number, not the correctness of every reasoning step.

`score.py` extracts the final value **without receiving the reference answer**. Ambiguous cases go to `pending_reviews.json`; the `--complete` gate requires a documented decision in `reviews.json`, with an exact quote and reason. These reviews are not blind to model identity or previous results and are not independently annotated. A response cut off at 512 tokens is marked incomplete for the final-value metric.

The older parser and its scores remain in the raw records. It can incorrectly take the first number of an expression after `Answer:`. The new terminal-format check is stricter; the final-value result can instead use a quoted review of the complete expression. Definitions were made explicit during this follow-up's scoring review, not retroactively applied to overwrite the first report.

## Reproduce

First follow the parent README to download the pinned base model and reproduce the four adapters. Keep the resulting `../results/*-adapter/` folders. Use the same environment as the parent experiment.

```sh
# From the parent experiment directory:
.venv/bin/python followup/prepare.py
.venv/bin/python followup/run.py --model-dir ../qwen-model
.venv/bin/python followup/score.py
# Inspect pending_reviews.json. Existing reviews contain exact quotes;
# a changed response must not be silently assigned an old decision.
.venv/bin/python followup/score.py --complete
.venv/bin/python followup/report.py
```

`prepare.py` regenerates inputs and records the checksums of the local adapters; it does not recreate the original archived adapter identities. Exact numerical reproducibility can depend on the hardware and library environment. The published protocol retains the hashes of the artifacts used for this run.

`results/` contains the ten raw evaluation cells, environment and completion records. `scored.json` preserves each extraction/review decision and source-file hashes. `summary.json` contains the paired counts used by the report. The first pilot's raw outputs, protocol and results remain unchanged.

The token-budget difference between explained and answer-only training remains. This follow-up cannot isolate why their behavior differs, measure speaking quality, or establish broad capability retention.


## Observed final-number results

| Model | Original / 36 | Reworded / 36 |
| --- | ---: | ---: |
| Original instruction model | 17 | 24 |
| Explained, seed 17 | 32 | 17 |
| Answer-only, seed 17 | 16 | 10 |
| Explained, seed 29 | 35 | 17 |
| Answer-only, seed 29 | 17 | 5 |

All four adapter original-input outputs exactly match their earlier 128-token outputs (48/48 each). None of the 480 responses reached 512 tokens. Six records required quoted review; one baseline/reworded response gave only an uninstantiated symbolic expression and was not counted as a final numerical answer. The scores above include that unresolved case in the denominator.

On this particular rewording set, all four fine-tuned checkpoints score below the original instruction model, even though the explained checkpoints retain an advantage over answer-only checkpoints. High scores on the original templates therefore did not carry over intact. This does not establish the mechanism or generalize beyond this narrow experiment.


## Article

A Chinese walkthrough of both rounds: [SFT 原题高分，换个问法会怎样？一次小模型实测](https://zhuanlan.zhihu.com/p/2088312597007409375).

The publication source is preserved in `zhihu-article.html`; raw experiment records remain unchanged.
