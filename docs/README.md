# SmartVille — GitHub Pages site

This folder holds the public project page for the SmartVille testbed, presented as the
**proof-of-concept implementation** of the paper *“SmartVille: An Open-Source Testbed for
Online-Learning Intrusion Detection over Software-Defined Networking.”*

- `index.html` — the entire single-page site (self-contained: CSS + JS are inlined, no external CDNs).
- `assets/` — figures. `architecture.png`, `topology.png`, `grafana.png`, `wandb.png` and
  `trio.png` are taken directly from the paper; `sdn.png` and `formula.png` are the authors'
  own diagrams from the repository README.
- `.nojekyll` — tells GitHub Pages to serve the files as-is (no Jekyll processing).

## How it is served

The site is published with GitHub Pages' **Deploy from a branch** source:

**Settings → Pages → Source: _Deploy from a branch_ → Branch: `new_smartville` → Folder: `/docs`.**

With that setting, GitHub rebuilds and serves this folder **automatically on every push** to
`new_smartville`. The site is live at:

```
https://dista-iot.github.io/insubria-smartville/
```

> **Note:** a GitHub Actions workflow was intentionally *not* used, because this organization's
> default `GITHUB_TOKEN` is not allowed to create a Pages site
> (`configure-pages` fails with *"Resource not accessible by integration"*). The branch-deploy
> source above needs no special token and works out of the box.

## Editing

Edit `index.html` (and swap/add images in `assets/`), commit, and push to `new_smartville` —
GitHub redeploys automatically. The page is theme-aware (light/dark) and responsive; no build
step is needed.

If a change doesn't appear, it's browser/CDN caching: hard-refresh (Ctrl/Cmd + Shift + R) or
append a dummy query string such as `?v=2` to the URL.
