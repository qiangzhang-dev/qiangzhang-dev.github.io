# SFT Rewrite Checker

A small browser tool for reviewing rewritten SFT answers alongside their complete input and original answer.

[Open the tool](https://qiangzhang-dev.github.io/tools/sft-rewrite-checker/) · [Quick start in Chinese](https://qiangzhang-dev.github.io/tools/sft-rewrite-checker/guide/) · [Review method and examples](https://qiangzhang-dev.github.io/notes/sft-rewrite-review/)

The tool flags lexical differences and leaves the decision to the reviewer. It does not score answer quality, judge semantic equivalence, or infer a training effect.

## Input

Import JSONL (one object per line), a JSON array, or a previously exported review report. Each record uses:

```json
{
  "id": "shipping-1",
  "input": "完整训练输入：周末商品实付满 200 元减 20 元，运费不计入门槛。商品实付 190 元，运费 15 元，能参加吗？请说明原因。",
  "original": "不能。运费不计入门槛，商品实付只有 190 元，没满 200 元。",
  "rewrite": "不能，你这单没满 200 元。",
  "must_keep": ["运费不计入门槛"]
}
```

`input`, `original` and `rewrite` are required nonempty strings. Include the actual system instructions, conversation history and source material in `input` when they are part of the training input. No chat-template or dataset-specific conversion is performed.

`id` is optional; absent IDs become `row-1`, `row-2`, etc. Duplicate IDs are rejected. `must_keep` is an optional list of up to 20 literal phrases. Synonyms can trigger its warning. Limits: 5000 records, 5 MiB UTF-8 for ordinary data, 100000 characters per text field. Exported reports bearing this tool's schema may be reimported up to 64 MiB, allowing room for findings and review notes. Invalid input rejects the batch and keeps the current review intact.

The eight records in [sample.jsonl](sample.jsonl) are constructed teaching examples, not measured model outputs. They include a harmless unit conversion and an unflagged rewording to illustrate the limits of the rules.

## Review cues

| Rule | What it compares | Important limit |
| --- | --- | --- |
| Numbers and units | Arabic digits with adjacent supported units, including repetition | No unit conversion, fact checking or reasoning about a number's role; Chinese numerals and unrecognized units can be missed |
| Required phrases | User-provided `must_keep` substrings | Literal matching; the phrase may already be absent from the original |
| Condition cues | Groups of common conditional, exclusion and range words | A missing cue does not prove a missing condition |
| Certainty cues | Uncertainty words present before and absent after | Context, negation and scope may not be captured |
| Clarification cues | Common requests for missing information | Does not establish whether the input is sufficient |
| Length | Non-whitespace character count below half the original, when the original has at least 24 characters | Short answers can be appropriate; this is not reasoning assessment |
| Markdown | Common headings, lists, fences, bold text and table separators | Does not parse all Markdown or check the task's format requirements |

Number comparison applies NFKC, lowercases Latin letters, normalizes the Unicode minus sign, removes commas and whitespace, and retains the number/unit string. It compares multisets, so order changes alone do not trigger it. Decimal notation, currency prefixes, dates, identifiers, implicit quantities and unit equivalence need human review. `20%` and `20 个百分点` remain different. `1000 米` and `1 公里` are flagged even when equivalent.

Inspect the complete input and both answers. The original is a comparison point, not an assumed correct answer. No cues does not mean approval.

## Human review and export

Set each record to `pending`, `keep`, `revise` or `hold` and add an optional note. Search and filters do not change the underlying data. Export generates a download link and a read-only JSON field for copying. It always contains all records, the current findings and the human decisions. Editing a decision or note invalidates the previous export so a new one can be generated. Reimport the export to continue; findings are recalculated rather than trusted from the file. Text is displayed as text, never interpreted as HTML.

Records are kept in page memory only. There is no backend, model call, analytics, localStorage or IndexedDB. Refreshing or closing the page discards the current review unless it was exported. A page-level Content Security Policy disallows script network connections. Loading the page and its static assets still makes ordinary requests to GitHub Pages.

## Run locally

From the website repository root:

```sh
python3 -m http.server 8000
```

Open `http://localhost:8000/tools/sft-rewrite-checker/`. Serve over HTTP; opening the HTML directly as a `file://` URL will not reliably load ES modules.

There is no build step or third-party dependency. With Node.js 20 or newer:

```sh
cd tools/sft-rewrite-checker
npm test
```

Tests cover benign rewrites, unit equivalence warnings, percentage-point changes, Unicode numbers, cue boundaries, invalid inputs, size limits and review export/import. They do not measure precision or recall on a human-labeled dataset; the example results are demonstrations of these rules.
