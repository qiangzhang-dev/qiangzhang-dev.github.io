# Explained vs. answer-only SFT: a small CPU pilot

This experiment asks what happens when correct training answers keep their explanation or retain only their final number. It uses public model weights and programmatically constructed English problems. It is not a speech-model experiment or evidence about an employer's models.

## Published results

- [First training comparison](https://qiangzhang-dev.github.io/experiments/sft-explanation/results/) — the original 128-token protocol, all raw responses, and a separate baseline-only length diagnostic.
- [Question-rewording and scoring follow-up](https://qiangzhang-dev.github.io/experiments/sft-explanation/followup/) — no additional training; all five models compared with a 512-token budget, final-value accuracy reported separately from terminal format.
- [Follow-up code and reproduction steps](followup/README.md).
- [Chinese walkthrough on Zhihu](https://zhuanlan.zhihu.com/p/2088312597007409375).

On the 36 original test questions, the explained-target models returned correct final values in 32 and 35 cases. With one alternate wording per question, both returned 17 correct values; the original Instruct model returned 24 on that rewording set. **The first round's high within-template scores did not fully carry over to these alternate wordings.**

The same 512-token baseline outputs score 2/36 under the legacy Answer-based rule and 17/36 by final claimed numeric value. Neither score alone identifies a training mechanism. Supervised-token budgets also differ: 13,974 versus 2,349.

## Design

- Model: [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), pinned to `7ae557604adf67be50417f59c2c2f167def9a775` (Apache 2.0).
- Training: 96 problems, 32 each for inventory arithmetic, a discount threshold with shipping excluded, and successive percentage changes.
- Held-out test: 36 different parameter combinations from the same templates. This tests within-template transfer, not new task generalization.
- Additional probes: 12 elementary factual/arithmetic questions, excluded from training. These are far too few to establish preservation of general capabilities.
- Each arm starts from the same frozen original model, with newly initialized LoRA adapters. Two paired seeds: 17 and 29. Rank 8 / alpha 16 / dropout 0, `q_proj` and `v_proj` only.
- Three epochs, batch size 4, 72 optimizer steps per arm, AdamW at 0.0002, no weight decay, gradient norm clipped to 1.
- CPU execution with float32 parameters and bfloat16 autocast; four threads. Assistant tokens only contribute to loss. No sequence truncation is allowed during training.
- Greedy generation, 128 new tokens maximum, final checkpoint only. No selection using test scores.

The same prompts, sample counts, optimizer settings and sample order are used in each paired comparison. **Supervised token budgets differ.** Explanations also repeat numbers and task-relevant intermediate information. This is not an isolated test of wording style, and no causal claim about large-model reasoning should be drawn from it.

`protocol.json` and both data files were generated before any baseline output was inspected. The four-item smoke run checks execution, gradients and performance only; it is not used for model selection. All pilot outcomes, including negative/null results, should be retained.

## Run

Use Python 3.12. Install the CPU wheel of PyTorch 2.6.0 from its official index, then install `requirements.txt`. `requirements-lock.txt` records the environment actually used; it is not a promise that every transitive version works on every platform.

```sh
python -m venv .venv
.venv/bin/pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/python download_model.py --output ../qwen-model
.venv/bin/python check_inputs.py --model-dir ../qwen-model
.venv/bin/python experiment.py --model-dir ../qwen-model --smoke
.venv/bin/python experiment.py --model-dir ../qwen-model
.venv/bin/python summarize.py
```

The checked-in data files are the canonical inputs. `python experiment.py --prepare-only` deterministically recreates them. The runner verifies their hashes before training, loads locally with remote code disabled, and disables socket connections after model loading. It does not use an inference API.

## What to inspect

`results/baseline.json` and each arm's JSON contain every raw response, expected value, parsed value, token count and length-cap flag. The parser accepts an explicit `Answer: <number>` when all such occurrences agree; missing or conflicting answer values count as unparsed. Report parsing failures separately: strict score changes need not be capability changes.

Each `*-training.json` records step losses, supervised-token counts, timing, trainable parameters and adapter changes. Adapters are saved locally for re-evaluation; the public repository contains text records, not base weights.

Input checks count 4,658 supervised tokens per epoch for explained targets and 783 for answer-only targets: 13,974 versus 2,349 over three epochs. These include the assistant closing tokens. Both arms see exactly 288 examples and 72 optimizer steps. The loss averages over unmasked tokens in each batch, so adding an explanation changes both the target distribution and the token weighting.

The original protocol's phrase “Last Answer” is shorthand: the implemented parser reads every explicit `Answer:` number and accepts it only if all occurrences agree. `check_inputs.py` includes a conflicting-answer case. The protocol and training runner are preserved as used; this clarification does not change any scores.

Do not treat reduced output length as measured speaking quality. Do not generalize 12 probes to a capability benchmark. Training loss across these two different target distributions is not directly comparable.


## Post-hoc length diagnostic

The primary baseline often failed the required output format or reached 128 new tokens. After noticing this in its raw responses, a separate **baseline-only** diagnostic raises `max_new_tokens` to 512. It does not retrain or change the original protocol, and is not a new matched comparison of all five models.

```sh
.venv/bin/python check_length.py --model-dir ../qwen-model
.venv/bin/python summarize.py
```

The diagnostic output is `results/baseline-512-posthoc.json`. Both budgets remain public. The original strict score must not be interpreted as content accuracy or used to claim reasoning was learned from zero.
