# Complex & Intelligent Systems — double-blind submission package

The journal uses **double-blind peer review**. Upload these files to the submission system:

| File | Purpose |
|------|---------|
| `main_blind.pdf` | Blind-reviewed manuscript (no author names, affiliations, or declarations) |
| `title_page.pdf` | Authors, affiliations, and all **Declarations** (required by Springer) |
| `supplementary_blind.zip` | Optional: artifacts + `tic_monitor/` without identifying metadata (see below) |

## Build

```bash
cd "Real_Time_Intelligence_and_Scalable_Architecture_for_Robotics (2)"
latexmk -pdf main_blind.tex    # -> main_blind.pdf
latexmk -pdf title_page.tex     # -> title_page.pdf
./package_supplementary.sh      # -> supplementary_blind.zip
```

Camera-ready version (with authors and declarations in one file):

```bash
latexmk -pdf main.tex           # -> main.pdf
```

## What the blind PDF removes

- Author names, emails, and affiliations (replaced with “Anonymous Author(s)”)
- `\date{Received / Accepted}` line
- **Statements and Declarations** section (moved to `title_page.pdf`)
- Table header “TIC (this paper)” → “TIC (present work)”

## Reviewer-facing code and data

Do **not** link to a public GitHub account with author-identifying history during review. Either:

1. Upload `supplementary_blind.zip` (recommended), or  
2. State in the submission cover letter that code is available on request.

After acceptance, restore the public repository URL in the final manuscript.

## Editorial Manager checklist

- [ ] Main document: `main_blind.pdf`
- [ ] Title page: `title_page.pdf`
- [ ] Supplementary: `supplementary_blind.zip` (optional)
- [ ] Cover letter notes blind supplementary material
- [ ] Funding/competing interests entered in the submission form (not only on title page)
