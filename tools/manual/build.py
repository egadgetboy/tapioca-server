"""Build tapiOca's manual: manual/src/*.md -> manual/<name>.pdf (and an .html beside it, not committed).

Usage: python3 tools/manual/build.py manual

  manual/manual.json  the cover: {"file", "title", "subtitle", "releases": [["Server", "1.44.3"]], "date", "label"}
  manual/src/NN-*.md  the chapters, in order; each starts with one "# " heading.

Conventions inside a chapter (docs only; see tools/manual/README.md):
  > **Tip:** / > **Note:** / > **Important:** ...     a callout
  [[screenshot: what it will show]]                  a placeholder box, until screenshots are added
  Term                                               a definition (the glossary)
  : what it means

A dev tool only (Python's Markdown and WeasyPrint, from tools/manual/requirements.txt): never in the image or an app.
"""
import hashlib
import html
import json
import re
import sys
from pathlib import Path

import markdown
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

HERE = Path(__file__).resolve().parent


def slug(text: str, seen: dict) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-") or "section"
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def chapter_html(md_text: str, seen: dict, toc: list) -> str:
    # screenshot placeholders, before Markdown sees them
    def shot(m):
        return ('\n<figure class="shot"><div class="shot-box"><span class="shot-label">Screenshot to come</span>'
                f'<span class="shot-what">{html.escape(m.group(1).strip())}</span></div></figure>\n')
    md_text = re.sub(r"^\[\[screenshot:\s*(.+?)\]\]\s*$", shot, md_text, flags=re.M)
    body = markdown.markdown(md_text, extensions=["tables", "def_list", "attr_list", "fenced_code", "sane_lists"])

    # callouts: a blockquote whose first word is Tip, Note or Important
    def callout(m):
        # adjacent quotes merge in Markdown: each paragraph that starts with a label is its own callout
        parts = re.split(r"(?=<p><strong>(?:Tip|Note|Important|Warning):?</strong>)", m.group(1).strip())
        out = []
        for inner in filter(str.strip, parts):
            k = re.match(r"\s*<p><strong>(Tip|Note|Important|Warning)", inner)
            if not k and out:
                out[-1] = out[-1][:-len("</aside>")] + inner + "</aside>"
                continue
            kind = k.group(1).lower() if k else "note"
            out.append(f'<aside class="callout {kind}">{inner}</aside>')
        return "".join(out)
    body = re.sub(r"<blockquote>(.*?)</blockquote>", callout, body, flags=re.S)

    # ids on headings, and the contents (h1 and h2)
    def head(m):
        lvl, inner = int(m.group(1)), m.group(2)
        hid = slug(inner, seen)
        if lvl <= 2:
            toc.append((lvl, hid, html.unescape(re.sub(r"<[^>]+>", "", inner))))
        return f'<h{lvl} id="{hid}">{inner}</h{lvl}>'
    body = re.sub(r"<h([1-4])>(.*?)</h\1>", head, body, flags=re.S)
    return f'<section class="chapter">{body}</section>'


def source_digest(manual_dir: Path) -> str:
    """One hash of everything the PDF is made from: the chapters, the cover and this kit."""
    h = hashlib.sha256()
    for f in [manual_dir / "manual.json", *sorted((manual_dir / "src").glob("*.md")), HERE / "build.py", HERE / "manual.css"]:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def build(manual_dir: Path) -> Path:
    meta = json.loads((manual_dir / "manual.json").read_text())
    seen, toc = {}, []
    chapters = [chapter_html(f.read_text(), seen, toc) for f in sorted((manual_dir / "src").glob("*.md"))]
    digest = source_digest(manual_dir)
    rel = "".join(f'<div class="rel"><span>{html.escape(a)}</span><b>{html.escape(b)}</b></div>' for a, b in meta["releases"])
    rels_line = " · ".join(f"{a} {b}" for a, b in meta["releases"])
    toc_html = "".join(
        f'<li class="toc{lvl}"><a href="#{hid}">{html.escape(t)}</a></li>' for lvl, hid, t in toc)
    logo = (HERE / "lockup-on-dark.svg").read_text()
    doc = f"""<!doctype html><html lang="en-US"><head><meta charset="utf-8">
<title>{html.escape(meta['title'])}</title>
<meta name="description" content="{html.escape(meta['subtitle'])}">
<meta name="keywords" content="tapioca-manual; {html.escape(rels_line)}; {html.escape(meta['date'])}; src-{digest}">
<meta name="author" content="egadgetboy">
</head><body>
<section class="cover">
  <div class="logo">{logo}</div>
  <h1 class="cover-title">{html.escape(meta['title'])}</h1>
  <p class="cover-sub">{html.escape(meta['subtitle'])}</p>
  <div class="rels">{rel}</div>
  <p class="cover-date">{html.escape(meta['date'])}</p>
  <p class="cover-label">{html.escape(meta.get('label', ''))}</p>
</section>
<section class="contents"><h1 class="contents-title">Contents</h1><ol class="toc">{toc_html}</ol>
<p class="edition">This manual covers {html.escape(rels_line)}, as released on {html.escape(meta['date'])}. It replaces every earlier edition.</p></section>
{''.join(chapters)}
</body></html>"""
    out = manual_dir / meta["file"]
    (manual_dir / (out.stem + ".html")).write_text(doc)
    css = (HERE / "manual.css").read_text().replace("__FONTS__", (HERE / "fonts").as_uri()) \
        .replace("__RUNNING__", html.escape(f"{meta['title']} · {rels_line}"))
    fonts = FontConfiguration()
    HTML(string=doc, base_url=str(manual_dir)).write_pdf(out, stylesheets=[CSS(string=css, font_config=fonts)], font_config=fonts)
    # the lock: ties the PDF's bytes to the chapters and cover it was built from (tools/manual/check.py reads it)
    lock = {"pdf_sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "src": digest,
            "releases": meta["releases"], "date": meta["date"]}
    (manual_dir / "manual.lock").write_text(json.dumps(lock, indent=1) + "\n")
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1] if len(sys.argv) > 1 else "manual")))
