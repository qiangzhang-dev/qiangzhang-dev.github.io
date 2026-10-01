# Qiang (Nate) Zhang — Personal website

[Website](https://qiangzhang-dev.github.io/) · [GitHub profile](https://github.com/qiangzhang-dev) · [Zhihu](https://www.zhihu.com/people/cai-hua-si-yi-ru-wo)

This repository hosts my personal website, technical notes and small reproducible experiments.

## Start here

| Topic | Read the work | Inspect the sources |
| --- | --- | --- |
| Preparing a speech-input SFT sample | [From text question to speech input](https://qiangzhang-dev.github.io/notes/speech-sft-sample/) | [Article source](https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/notes/speech-sft-sample) · Constructed example; no audio generation or training run |
| SFT training targets and question rewording | [First training comparison](https://qiangzhang-dev.github.io/experiments/sft-explanation/results/) · [Rewording and scoring follow-up](https://qiangzhang-dev.github.io/experiments/sft-explanation/followup/) | [Training code, data and raw outputs](https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/experiments/sft-explanation) |
| Reviewing rewritten SFT answers | [Browser checker](https://qiangzhang-dev.github.io/tools/sft-rewrite-checker/) · [Quick start](https://qiangzhang-dev.github.io/tools/sft-rewrite-checker/guide/) · [Worked examples](https://qiangzhang-dev.github.io/notes/sft-rewrite-review/) | [Tool code and examples](https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/tools/sft-rewrite-checker) · [Article source](https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/notes/sft-rewrite-review) |
| Whisper beam-size comparison | [Experiment](https://qiangzhang-dev.github.io/notes/whisper-beam/) · [All 40 recordings](https://qiangzhang-dev.github.io/notes/whisper-beam/report/) | [Scripts](https://github.com/qiangzhang-dev/speech-eval-demo/tree/main/experiments/librispeech-beam) · [Records](https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/notes/whisper-beam) |
| AIR-Fusion · IJCAI 2026 | [Project page](https://qiangzhang-dev.github.io/air-fusion/) · [Author's note](https://qiangzhang-dev.github.io/notes/air-fusion/) | [Paper repository](https://github.com/qiangzhang-dev/AIR-Fusion) |

The SFT and ASR experiments use open models and public or synthetic data. They are personal studies, with their scope and limitations described in each report.

The SFT Rewrite Checker is a separate browser utility for lexical review cues and human decisions. It does not judge answer correctness or estimate model capability. Imported records stay in page memory; export them before refreshing.

AIR-Fusion's paper, method figure and citation are available. Its implementation and weights are not currently available.

## Website maintenance

A responsive, dependency-free website hosted on GitHub Pages.

- Edit `index.html` to update the introduction, project links, or styles.
- Keep professional claims and project descriptions tied to verified public information.
- Preview locally with `python3 -m http.server 8000`, then open `http://localhost:8000`.
- GitHub Pages publishes from the root of the `main` branch.
- `.nojekyll` keeps deployment as plain static files.

The site uses system fonts and no analytics, external scripts, or cookies.

### Offline integrity checks

Run from the repository root with Python 3.9 or newer; no packages or network access are required:

```sh
python3 scripts/check_site.py
python3 -m unittest discover -s tests -v
```

The checker exits nonzero and prints the source path when a check fails. It checks:

- Local HTML `href`, `src` and `poster` targets, including relative links, same-host absolute links, downloads and HTML fragment IDs (or legacy named anchors).
- One nonempty document title and one self-canonical per public page, with no duplicate titles or canonical URLs.
- Sitemap coverage of standalone `.html` pages, including articles and generated reports, and stale or duplicate sitemap entries. Pages marked `noindex` are not included in the sitemap; their local links are still checked.
- The published AIR-Fusion author order in Highwire citation tags, JSON-LD and visible BibTeX, using the [official IJCAI record](https://www.ijcai.org/proceedings/2026/105). This check is scoped to `air-fusion/index.html`, not future publications.

Page discovery excludes hidden directories, Python/Node dependency and cache directories, and the preserved `experiments/sft-explanation/followup/zhihu-article.html` publication fragment documented in its adjacent README. New standalone pages are discovered automatically. Add deliberate source-fragment exclusions with a reason in `EXCLUDED_HTML`; do not exclude a public article to silence a missing sitemap entry.

`/subtracker` and its child routes are served by the separate [SubTracker repository](https://github.com/qiangzhang-dev/subtracker), so they are the only same-host route exception. Other external sites are skipped. The check does not verify remote availability, run JavaScript, inspect dynamically generated links, parse CSS URLs or `srcset`, or replace browser/accessibility tests. It does not run the model experiments.

The script resolves the repository from its own location; `--root /path/to/site` can check another source tree. Mutation tests use temporary fixtures to prove that missing paths/anchors, metadata errors and sitemap omissions fail, while intended exclusions and valid link forms pass. No GitHub workflow is installed or changed by this local command.
