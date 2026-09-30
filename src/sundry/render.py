"""HTML (for the email) and Markdown (for the repo archive) rendering."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from .models import Article, Category
from .text import truncate

ARCHIVE_INDEX_HEADER = "# Digest archive\n\nOne file per day, newest first.\n"


def _format_date(published: datetime | None) -> str:
    return published.strftime("%b %d") if published else ""


def _meta_line(article: Article) -> str:
    return " · ".join(part for part in (article.source, _format_date(article.published)) if part)


def _has_any_items(categorized: dict[str, list[Article]], categories: tuple[Category, ...]) -> bool:
    return any(categorized.get(category.key) for category in categories)


def render_html(
    run_date: str,
    categorized: dict[str, list[Article]],
    categories: tuple[Category, ...],
    failures: list[str],
    digest_name: str = "Daily Digest",
) -> str:
    """Render the digest as a self-contained, inline-styled HTML email body."""
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'></head>",
        '<body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,'
        'Segoe UI,Helvetica,Arial,sans-serif;color:#18181b;">',
        '<div style="max-width:680px;margin:0 auto;padding:24px 16px;">',
        f'<h1 style="font-size:20px;margin:0 0 4px;">{html.escape(digest_name)}</h1>',
        f'<p style="margin:0 0 24px;color:#71717a;font-size:13px;">{html.escape(run_date)}</p>',
    ]

    if not _has_any_items(categorized, categories):
        parts.append(
            "<p style='font-size:14px;'>Quiet day — no new items across any tracked source "
            "since the last run. The pipeline is alive and will keep checking.</p>"
        )

    for category in categories:
        items = categorized.get(category.key, [])
        if not items:
            continue
        parts.append(
            '<h2 style="font-size:16px;margin:28px 0 4px;border-bottom:2px solid #e4e4e7;'
            f'padding-bottom:6px;">{html.escape(category.title)}</h2>'
        )
        parts.append(f'<p style="margin:0 0 12px;color:#52525b;font-size:12.5px;">{html.escape(category.blurb)}</p>')
        for article in items:
            parts.append(
                '<div style="margin:0 0 14px;">'
                f'<a href="{html.escape(article.link)}" style="font-size:14.5px;font-weight:600;'
                f'color:#1d4ed8;text-decoration:none;">{html.escape(article.title)}</a><br>'
                f'<span style="font-size:11.5px;color:#71717a;">{html.escape(_meta_line(article))}</span><br>'
                f'<span style="font-size:13px;color:#3f3f46;">{html.escape(truncate(article.summary))}</span>'
                "</div>"
            )

    if failures:
        parts.append(
            '<p style="margin-top:28px;font-size:11px;color:#a1a1aa;">'
            f"Source and selection warnings: {html.escape('; '.join(failures))}</p>"
        )

    parts.append(
        '<p style="margin-top:24px;font-size:11px;color:#a1a1aa;">Generated automatically by the '
        "GitHub Actions workflow in this repo. Tune sources/keywords in config/feeds.toml, "
        "or browse the archive in digests/.</p>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)


def render_markdown(
    run_date: str,
    categorized: dict[str, list[Article]],
    categories: tuple[Category, ...],
    failures: list[str],
    digest_name: str = "Daily Digest",
) -> str:
    """Render the digest as Markdown, for the repo's browsable archive."""
    lines = [f"# {digest_name} — {run_date}", ""]

    if not _has_any_items(categorized, categories):
        lines.append("_Quiet day — no new items across any tracked source since the last run._")

    for category in categories:
        items = categorized.get(category.key, [])
        if not items:
            continue
        lines.append(f"## {category.title}")
        lines.append(f"_{category.blurb}_")
        lines.append("")
        for article in items:
            lines.append(f"- **[{article.title}]({article.link})** — {_meta_line(article)}")
            if article.summary:
                lines.append(f"  {truncate(article.summary)}")
        lines.append("")

    if failures:
        lines.append(f"_Source and selection warnings: {'; '.join(failures)}_")
        lines.append("")

    return "\n".join(lines)


def update_archive_index(archive_dir: Path, run_date: str) -> None:
    """Keep `digests/README.md` as a newest-first index of archived digests."""
    index_path = archive_dir / "README.md"
    content = index_path.read_text(encoding="utf-8") if index_path.exists() else ARCHIVE_INDEX_HEADER
    entry = f"- [{run_date}](./{run_date}.md)"

    lines = content.splitlines()
    if entry in lines:
        return

    insert_at = next((i for i, line in enumerate(lines) if line.startswith("- [")), len(lines))
    lines.insert(insert_at, entry)
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
