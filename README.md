# LottoApp (LottoGen v2.3.1)

Standalone Windows app (and source) that generates Lotto 6/49 and Lotto Max lines, with **Smart Picks** (hot/cold/overdue) and a **Bonus (Top Prob)** line.
It auto-fetches past results with fallback: **WCLC → OLG → ALC**, and includes a frequency chart and copy/export tools.

## Recommended: Cloud Build (GitHub Actions)
1. Commit these files to this repo (root):
   - `LottoGen.py`
   - `requirements.txt`
   - `.github/workflows/build.yml`
   - `.github/workflows/release.yml` (optional, for tagged releases)
2. In GitHub → **Actions → Build LottoGen EXE (Windows)** → **Run workflow**.
3. When it finishes, open the run → **Artifacts** → download **LottoGen-windows-exe** → `LottoGen.exe`.

### Auto Release on tags
- Create a tag like `v2.3.1` and push it. The workflow builds and attaches `LottoGen.exe` to a GitHub Release automatically.

## Local run (Python required)
```bash
pip install -r requirements.txt
python LottoGen.py
```

**About**
- Copyright © 2025 SERC Professional Services  
- Built with ChatGPT-5
