---
name: fetch-paper
description: Use when fetching a paper/academic text the user references - arxiv id or URL, title, or a link in conversation context. Covers "download this paper", "get the full text of X", converting papers to markdown, or any mention of trafilatura/docling for paper conversion.
---

# fetch-paper

Fetch a paper the user references and save it as readable markdown. One
command per paper, no custom scripts - trafilatura and docling via `uvx`
already do everything. Do not hand-write HTML-to-markdown converters,
BeautifulSoup preprocessors, pandoc pipelines, or cross-validation
scripts; those are the documented failure mode of this task, not the
solution.

## Resolve the paper

From the user's message or conversation context, in order:

1. **arxiv id** (`2605.05586`, `1706.03762v7`, old-style `hep-ph/9905351`)
   → use directly.
2. **arxiv URL** (`.../abs/<id>`, `.../pdf/<id>`, `.../html/<id>`) →
   extract the id.
3. **Other URL** (OpenReview, PMLR, NeurIPS proceedings, a lab page) →
   try that URL directly in the fetch step.
4. **Title or description only** → the built-in web search tool. If you
   get the id, continue; if you get a direct PDF link, use the PDF
   fallback. Only fall back to asking the user when search is genuinely
   inconclusive.
   - Web search unavailable/exhausted → arxiv search UI:
     `https://arxiv.org/search/?searchtype=all&query=<title>` (works
     with curl; match the title in the returned abs links).
   - Do NOT use `export.arxiv.org/api/query` - it rate-limits hard
     (429s for minutes at a time, observed with a single call).
5. **v1-only caveat**: the id alone fetches the latest version; if the
   user needs a specific version, keep the `v` suffix.

## Fetch (HTML first, PDF only as fallback)

HTML is the source of truth for conversion quality - LaTeX-derived
arxiv HTML (native `arxiv.org/html/<id>` or ar5iv) converts to markdown
far better than PDF extraction. Try in order:

1. `https://arxiv.org/html/<id>` - native, now covers most papers
   including old ones. Check the response is real content, not a 404
   page (status 200 and > 10 KB).
2. `https://ar5iv.labs.arxiv.org/html/<id>` - LaTeXML mirror, catches
   what native misses.
3. Search for a publisher/author HTML version (web search:
   `"<title>" html`).
4. **PDF fallback** (`https://arxiv.org/pdf/<id>`, or any publisher
   PDF): `uvx --from docling docling <file> --to md --output <dir>`.
   Slow (~35 s + model download first run) but reliable for any PDF.
   Docling embeds figures as base64 in the markdown (output ~500 KB -
   1 MB); if the user only needs text, strip `data:image/...` image
   lines, or keep the PDF alongside for figures. Output file is named
   after the input file, so name the PDF `<slug>.pdf` first.

Both fetch and convert in one step - trafilatura downloads the URL
itself:

```bash
uvx trafilatura -u "https://arxiv.org/html/<id>" --markdown --links \
  > <slug>.md
```

- `--links` keeps citation links and figure references. Add `--images`
  if the user wants figure URLs kept.
- Stdout redirect, not `-o` (the `-o` flag names output by content hash
  with a `.txt` extension, ignoring your filename).
- `-i` is for a list of URLs, never a local HTML file.
- Empty output with exit 0 = extraction found nothing; try the next
  source rather than retrying the same URL.
- trafilatura strips MathML math and data-URI appendix blobs in
  LaTeXML pages - acceptable for reading; if the user needs exact
  equations, fetch the PDF too and say so.

## Save

- File name: `<slug>.md` from the paper title (short, kebab-case),
  in the directory the user named or the project's papers convention
  (`docs/papers/`); ask only if neither exists.

## Verify

- File exists and > 5 KB (abstract-only failures are ~1-2 KB).
- Headings visible: `grep -c '^#' <file>.md` returns several.
- Spot-check: title matches the requested paper.

Report: source URL used (html vs ar5iv vs pdf), file path, size, and
one-line quality note (e.g. "math stripped", "figures as links").

## Common mistakes

| Mistake | Reality |
|---|---|
| Writing a BeautifulSoup/pandoc conversion script | One trafilatura command replaces the whole pipeline |
| `trafilatura -o <dir>` | Names files by content hash, `.txt` ext - use stdout redirect |
| `trafilatura -i <file.html>` | `-i` expects a URL list; local HTML files are not supported |
| PDF-first because PDFs feel canonical | HTML conversion is strictly better when it exists; PDF is the fallback, not the default |
| Retrying the same empty-output URL | Empty output means the page didn't extract - move to the next source |
| `export.arxiv.org/api/query` for title lookup | Hard rate-limits (429 for minutes); use the arxiv search UI instead |
| Accepting an abstract-only result from a landing page | Landing pages (PMLR, OpenReview) extract to ~1-2 KB; that means "go get the PDF" |
