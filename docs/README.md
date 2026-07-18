# SmartVille — GitHub Pages site

This folder holds the public project page for **SmartVille**, presented as the paper describes it:
a **framework** for realistic, deep-learning-based *online* network intrusion detection — a scientific
instrument for formulating, training and benchmarking neural NID models, together with its open-source
proof-of-concept implementation.

The page is an explainer of the paper *"SmartVille: A Framework for Realistic Deep Learning-based Online
Network Intrusion Detection"* (Cevallos M., Rizzardi, Sicari, Coen-Porisini — Università degli Studi
dell'Insubria). It deliberately avoids "we-are-the-best" product framing: SmartVille is not a stand-alone
detector chasing leaderboard accuracy, and the software is one concrete realisation of the framework, not
the primary contribution.

- `index.html` — the entire single-page site (self-contained: CSS + JS are inlined, no external CDNs).
- `assets/paper/` — **the figures from the paper itself** (reproduced from the manuscript):
  - `framework.png` — the framework's degrees of freedom (Fig. 1)
  - `neural_pipeline.png` — the Encode–Process–Decode pipeline (Fig. 2)
  - `implementation.png` — the technology-stack lifecycle (Fig. 3)
  - `webgui.png` — the SmartVille WebGUI (Fig. 4)
  - `curricula.png` — Use Case 1: meta-training curricula baselines (Fig. 5)
  - `modalities.png` — Use Case 2: input-modality baselines (Fig. 6)
  - `confmat.png` — aggregated confusion matrices by modality (Fig. 7)
  - `arch_baselines.png` — Use Case 3: neural-operator baselines (Fig. 8)
  - `hdims.png`, `r_layers.png` — scaling-limit findings (Appendix)
  - `sampling_intervals.png` — sampling-interval analysis (Appendix)
- `assets/*.png` — the legacy figures from the previous version of the page (kept for reference; no longer
  used by `index.html`).
- `.nojekyll` — tells GitHub Pages to serve the files as-is (no Jekyll processing).

## How it is served

The site is published with GitHub Pages' **Deploy from a branch** source:

**Settings → Pages → Source: _Deploy from a branch_ → Branch: `new_smartville` → Folder: `/docs`.**

With that setting, GitHub rebuilds and serves this folder **automatically on every push** to the configured
branch. The site is live at:

```
https://dista-iot.github.io/insubria-smartville/
```

> **Note:** the overhaul in this commit was developed on branch `claude/github-page-paper-overhaul-isyv7h`.
> For the new page (and the paper figures under `assets/paper/`) to render on the live site, merge this branch
> into the branch GitHub Pages deploys from, or point Pages at this branch.

> A GitHub Actions workflow was intentionally *not* used, because this organization's default `GITHUB_TOKEN`
> is not allowed to create a Pages site (`configure-pages` fails with *"Resource not accessible by integration"*).
> The branch-deploy source above needs no special token and works out of the box.

## Editing

Edit `index.html` (and swap/add images in `assets/`), commit, and push — GitHub redeploys automatically. The
page is theme-aware (light/dark) and responsive; no build step is needed.

If a change doesn't appear, it's browser/CDN caching: hard-refresh (Ctrl/Cmd + Shift + R) or append a dummy
query string such as `?v=2` to the URL.
