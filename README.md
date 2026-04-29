# LinkedIn Poster Agents

Automated pipeline that generates weekly LinkedIn posts about ML/DS topics. Given a week, it researches trending content, writes post text via LLM, and fetches a relevant illustration — producing ready-to-publish drafts.

## How it works

```
research_service          → fetch + rank topics
  ├── Tavily (web search)
  └── arXiv (recent papers)
        ↓
linkedin_post_pipeline    → per topic
  ├── writer_service      → LLM text generation
  └── image_service
        ↓
        image_pipeline
          ├── arXiv PDF figure extraction (if paper)
          ├── visual intent determination
          ├── multi-query generation
          ├── parallel fetch (GitHub / HuggingFace / Web / Unsplash)
          └── scoring + selection
```

**Output per post** (`output/<YYYY-WW>/post_N/`):
- `post.txt` — final LinkedIn text
- `image.png` — selected illustration
- `meta.json` — full metadata (research, image credit, scores)
- `image_candidates.json` — all ranked image candidates
- `logs/` — LLM prompt + raw output logs

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # for code screenshot generation
```

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `TAVILY_API_KEY` | yes | Tavily web search |
| `UNSPLASH_ACCESS_KEY` | no | Unsplash image fallback |
| `GITHUB_TOKEN` | no | Higher GitHub API rate limits |
| `LMSTUDIO_BASE_URL` | yes | LM Studio endpoint (default: `http://localhost:1234/v1`) |
| `LMSTUDIO_MODEL` | yes | Model ID (default: `qwen/qwen3.5-9b`) |
| `POSTS_PER_WEEK` | no | Posts to generate per run (default: `5`) |

The LLM runs locally via LM Studio — start it before running the pipeline.

## Usage

```bash
# Generate posts for the current week
python main.py --generate

# Force regeneration if this week's directory already exists
python main.py --generate --force

# Skip data collection — use a previously saved raw results file
python main.py --generate --raw-results-file output/raw_results/raw_results_20240415_120000.json

# Save debug artefacts (ranked image candidates)
python main.py --generate --debug
```

## Project structure

```
├── main.py                         # CLI entry point
├── app/
│   ├── config.py                   # Settings, paths, runtime config
│   └── pipeline.py                 # Weekly pipeline orchestration
├── services/
│   ├── research_service.py         # Topic collection + LLM ranking
│   ├── writer_service.py           # Post text generation
│   └── image_service.py            # Image selection facade
├── pipelines/
│   ├── linkedin_post_pipeline.py   # Per-post pipeline
│   └── image_pipeline.py           # Full image fetch/rank/select pipeline
├── components/
│   ├── llm/                        # LM Studio client + prompts
│   ├── search/                     # Tavily + arXiv clients
│   ├── image_sources/              # GitHub, HuggingFace, Web, Unsplash
│   ├── scraping/                   # Figure extraction from PDFs/HTML
│   └── generation/                 # Code screenshot via carbon.now.sh
├── ranking/
│   ├── scorer.py                   # Image scoring (dimensions, source, relevance)
│   ├── figure_ranker.py            # arXiv figure ranking
│   └── classifier.py
├── domain/                         # Pydantic models (ResearchResult, PostDraft, ImageResult)
└── utils/                          # Text parsing, image post-processing
```

## Image selection logic

For arXiv papers, the pipeline extracts figures directly from the PDF and ranks them by relevance to the post angle. For all other sources, it determines a **visual intent** (`diagram`, `screenshot`, `conceptual`, `real_world`) from the topic metadata, generates multiple search queries, and fetches candidates in parallel from GitHub, HuggingFace, Web scraping, and Unsplash. Candidates are scored on resolution, aspect ratio, source priority, and keyword relevance. The top candidate above a 0.3 score threshold is downloaded and resized for LinkedIn.
