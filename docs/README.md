# SmartVille — GitHub Pages site

This folder holds the public project page for the SmartVille testbed, presented as the
**proof-of-concept implementation** of the paper *“SmartVille: An Open-Source Testbed for
Online-Learning Intrusion Detection over Software-Defined Networking.”*

- `index.html` — the entire single-page site (self-contained: CSS + JS are inlined, no external CDNs).
- `assets/` — figures taken from the paper and the repository README.
- `.nojekyll` — tells GitHub Pages to serve the files as-is (no Jekyll processing).

## How it is served

A GitHub Actions workflow (`.github/workflows/pages.yml`) publishes this folder to GitHub
Pages **automatically on every push** to the default branch (`new_smartville`). The workflow's
`configure-pages` step enables Pages on first run, so no manual dashboard setup is required.

Once merged into the default branch and the first workflow run finishes, the site is live at:

```
https://dista-iot.github.io/insubria-smartville/
```

### Alternative: serve directly from a branch (no Actions)

If you prefer not to use Actions, go to **Settings → Pages**, choose
**Source: Deploy from a branch**, pick the branch, and set the folder to **`/docs`**.
GitHub will then build and serve this folder on every push to that branch.

## Editing

Edit `index.html` (and swap/add images in `assets/`), commit, and push — the workflow redeploys.
The page is theme-aware (light/dark) and responsive; no build step is needed.
