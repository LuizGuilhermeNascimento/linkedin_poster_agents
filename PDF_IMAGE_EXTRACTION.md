# arXiv Figure Extraction — Spec

Describes the current implementation of figure extraction from arXiv PDFs, including reconstruction, ranking, and integration with the image pipeline.

---

## Overview

When a research result has an `arxiv_id`, the image pipeline takes a fast path: it downloads the paper's PDF, extracts all figures using layout-aware reconstruction, ranks them by relevance to the post context, and saves the best one. Only if no suitable figure is found does it fall back to the multi-source web search.

---

## Pipeline Flow

```
image_pipeline.run()
  └─ research.arxiv_id present?
       ├─ YES → _select_arxiv_figure()
       │          ├─ extract_figures_with_captions()   # download PDF, extract XObjects
       │          │    └─ _extract_page_figures()      # per-page: filter → reconstruct
       │          │         └─ reconstruct_page_figures()
       │          │              ├─ _extract_captions()
       │          │              ├─ _cluster_images()  # union-find
       │          │              ├─ _assign_caption()
       │          │              ├─ _render_page()     # lazy — only for multi-image clusters
       │          │              ├─ _crop_from_page()
       │          │              └─ _compute_confidence()
       │          ├─ figure_ranker.rank_and_select()   # reject noise, score, sort
       │          └─ save best figure as image.png
       └─ NO (or no valid figure) → multi-source web search fallback
```

---

## Components

### `domain/image.py` — `ArxivFigure`

Domain type carrying everything needed downstream.

| Field | Type | Notes |
|---|---|---|
| `image_data` | `bytes` | Raw PNG bytes of the figure |
| `width`, `height` | `int` | Pixel dimensions |
| `page_number` | `int` | 1-indexed |
| `figure_index` | `int` | Sequential 0-indexed across the full PDF |
| `caption` | `str` | Extracted caption text (may be empty) |
| `confidence` | `float [0,1]` | Reconstruction quality score |
| `element_count` | `int` | Number of raw XObjects merged into this figure |

---

### `components/scraping/image_extractor.py` — PDF download and XObject extraction

**`extract_figures_with_captions(arxiv_id)`**

1. Downloads `https://arxiv.org/pdf/{arxiv_id}` with a 60s timeout.
2. Opens the PDF with PyMuPDF (`fitz`).
3. Iterates each page, calling `_extract_page_figures()` and accumulating results.
4. Returns `list[ArxivFigure]` ordered by page then position within page.

**`_extract_page_figures(doc, page, page_num, figure_index_start, config)`**

1. Collects text blocks from the page (block type 0).
2. Iterates all image XObjects on the page via `page.get_images(full=True)`.
3. Filters out XObjects smaller than **200×200 px** (removes icons, thumbnails, decorations).
4. Builds `list[PageImage]` with each XObject's bytes and PDF-coordinate rect.
5. Delegates to `reconstruct_page_figures()`.

---

### `components/scraping/figure_reconstruction.py` — Layout-aware reconstruction

**`reconstruct_page_figures(page_images, text_blocks, page_rect, page, page_num, figure_index_start, config)`**

Core logic. Handles the gap between "raw image XObjects" and "coherent figures": a figure with subfigures (a), (b), (c) is stored in a PDF as multiple independent XObjects. This function merges them back.

#### Step 1 — Caption extraction

`_extract_captions()` filters text blocks matching:

```
Fig(?:ure)?\.?\s*\d+[a-z]?[:.)]    (case-insensitive)
```

Examples matched: `Figure 1:`, `Fig. 2a.`, `Figure 3)`

#### Step 2 — Spatial clustering (union-find)

`_cluster_images()` groups XObjects that are spatially adjacent.

Two XObjects are neighbours when **both** conditions hold:
- horizontal gap ≤ `distance_threshold × page_width` (default: 8% of page width)
- vertical gap ≤ `distance_threshold × page_height` (default: 8% of page height)

Uses union-find with path compression for O(n α(n)) grouping.

Clustering is skipped (passthrough) when:
- `config.enabled = False`, or
- `len(page_images) < config.min_elements_per_figure` (default: 2)

#### Step 3 — Figure assembly per cluster

**Single-image cluster**: uses raw XObject bytes directly. No rendering.

**Multi-image cluster**:
1. Merges cluster bboxes into a union bounding box.
2. Lazily renders the full page to a PIL image at `rendering_dpi` (default: 300 DPI). Page rendering is deferred and shared across all multi-image clusters on the same page.
3. Maps PDF coordinates → pixel coordinates and crops the union bbox with a **1% margin** on each side.
4. Fallback: if rendering fails, uses the largest XObject in the cluster by pixel area.

#### Step 4 — Caption assignment

`_assign_caption()` looks for captions that:
- Start at or below the figure's bottom edge (with 10pt tolerance).
- Are within `caption_max_distance × page_height` (default: 15% of page height).

Returns the closest qualifying caption text, or `""` if none found.

#### Step 5 — Confidence scoring

`_compute_confidence()` produces a score in `[0, 1]` used later during ranking.

| Signal | Weight | Details |
|---|---|---|
| Element count | 40% | `min(1.0, 0.5 + 0.25 × (count − 1))` — more fragments merged → higher confidence, saturates at count ≥ 3 |
| Caption presence | 40% | 1.0 if caption found, 0.6 if not |
| Area coverage | 20% | Ideal range 5%–40% of page area; ramps up below 5%, penalised above 40% |

---

### `ranking/figure_ranker.py` — Relevance ranking and selection

**`rank_and_select(figures, post_summary, post_angle, min_score=0.0)`**

Returns `(best_figure | None, list[FigureScore])`.

#### Visual noise filter (pre-score rejection)

Figures are rejected before scoring if their caption matches:

```
car, cars, street, streets, building, buildings, person, people, human,
pedestrian, traffic, road, vehicle, face, faces, crowd, outdoor, indoor,
cityscape, landscape, photograph, photo, real.world, autonomous, driving,
object detection, segmentation mask
```

Rejected figures receive `total=0.0` and are excluded from selection.

#### Scoring formula

```
score = 0.40 × semantic
      + 0.27 × keyword
      + 0.22 × position
      + 0.11 × reconstruction_confidence
```

| Component | How it's computed |
|---|---|
| **semantic** | BoW cosine similarity between caption and `post_summary + post_angle` (words ≥ 4 chars, lowercased). Returns 0.4 for empty captions (slight penalty). |
| **keyword** | Positive ML/architecture keywords boost (+1 per match); negative result/benchmark keywords penalise (−0.5 per match). `max(0, min(1, (pos − 0.5×neg + 1) / 4))`. |
| **position** | Linear decay: page 1 → 1.0, last page → 0.3. Earlier figures preferred. |
| **reconstruction** | `ArxivFigure.confidence` computed during reconstruction. |

**Positive keywords**: `architecture, framework, method, pipeline, model, memory, attention, transformer, encoder, decoder, layer, module, block, mechanism, network, overview, system, approach, design, structure, workflow, diagram`

**Negative keywords**: `dataset, scene, results, reconstruction, baseline, comparison, ablation, performance, accuracy, metric, evaluation, benchmark, table, plot, curve, visualization, qualitative, quantitative`

The figure with the highest total score above `min_score` is returned. With `min_score=0.0` (the current default), the best non-rejected figure is always returned.

---

### `pipelines/image_pipeline.py` — Orchestration

**`_select_arxiv_figure(research, output_path, debug)`**

1. Calls `extract_figures_with_captions(research.arxiv_id)`.
2. Calls `figure_ranker.rank_and_select()` with the post summary and suggested angle as context.
3. In debug mode: saves all ranked figures to `images_rank/top_NN.png` (sorted by score, best first).
4. Saves best figure as `image.png`, runs `postprocess_image()`.
5. Returns `ImageResult(source="arxiv", score=1.0, credit="arXiv:{id}")`.
6. Returns `None` on any failure, triggering the web-search fallback.

---

### `app/config.py` — `FigureReconstructionConfig`

All reconstruction parameters in one place, instantiated as a module-level singleton.

| Parameter | Default | Meaning |
|---|---|---|
| `enabled` | `True` | Master switch for spatial clustering |
| `distance_threshold` | `0.08` | Max inter-image gap as fraction of page dimension |
| `vertical_tolerance` | `0.05` | (currently unused by clustering — reserved) |
| `caption_enabled` | `True` | Enable caption extraction and assignment |
| `caption_max_distance` | `0.15` | Max caption-to-figure gap as fraction of page height |
| `rendering_fallback` | `True` | Allow page rendering for multi-image crops |
| `rendering_dpi` | `300` | DPI for page rendering |
| `min_elements_per_figure` | `2` | Minimum cluster size to trigger reconstruction |
| `low_coverage_threshold` | `0.3` | (currently unused — reserved) |

---

## Debug Output

When `--debug` is passed, `images_rank/` is written alongside `image.png`:

```
output/YYYY-WW/post_N/
  image.png          ← selected figure
  images_rank/
    top_01.png       ← highest-scored (or non-rejected) figure
    top_02.png
    ...
```

For arXiv posts, the ranking is by composite score descending, with rejected figures at the end.

---

## Failure Modes and Fallbacks

| Failure | Behaviour |
|---|---|
| PyMuPDF not installed | Logs a warning, returns `[]`, falls back to web search |
| PDF download fails (timeout / HTTP error) | Logs a warning, returns `[]`, falls back to web search |
| All figures rejected by noise filter | `rank_and_select` returns `None`, falls back to web search |
| Page rendering fails for multi-image crop | Falls back to the largest raw XObject in the cluster |
| Saving best figure fails | Logs a warning, returns `None`, falls back to web search |
