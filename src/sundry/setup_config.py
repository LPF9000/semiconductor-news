"""Preserve existing TOML settings and confirm an atomic configuration update."""

from __future__ import annotations

import copy
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import ParseError
from tomlkit.toml_document import TOMLDocument

from .config import load_config
from .setup import _terms, category_rows


def validated_document(text: str) -> TOMLDocument:
    try:
        document = tomlkit.parse(text)
    except ParseError as exc:
        raise ValueError(f"Invalid TOML: {exc}") from exc
    with tempfile.TemporaryDirectory(prefix="sundry-review-") as directory:
        path = Path(directory) / "feeds.toml"
        path.write_text(text, encoding="utf-8")
        load_config(path)
    return document


def category_value(row: Any) -> tuple[str, str, str, str, str]:
    return (
        row["key"],
        row["title"],
        ", ".join(row.get("keywords", [])),
        ", ".join(row.get("required_keywords", [])),
        ", ".join(row.get("exclude_keywords", [])),
    )


class ConfigurationDraft:
    def __init__(self, path: Path) -> None:
        if path.is_symlink():
            raise ValueError("Choose the actual config file rather than a symbolic link")
        self.path = path
        self.original = path.read_bytes()
        self.document = validated_document(self.original.decode("utf-8"))
        self.initial = self.values()

    def values(self) -> dict[str, str]:
        document = self.document
        ranking = document.get("ranking", {})
        values = {"name": document.get("digest_name", "Daily Digest")}
        for field, table, attribute in (("rss", "rss_sources", "url"), ("arxiv", "arxiv_sources", "query")):
            values[field] = "\n".join(f"{row['name']} | {row[attribute]}" for row in document.get(table, []))
        for field, terms in (
            ("hn", document.get("hn_queries", [])),
            ("preferred", ranking.get("preferred_keywords", [])),
            ("demoted", ranking.get("demoted_keywords", [])),
        ):
            values[field] = "\n".join(terms)
        values["categories"] = "\n".join(
            " | ".join(category_value(row)) for row in document.get("categories", []) if row["key"] != "general"
        )
        return values

    def preview(self, values: dict[str, str], origins: dict[str, dict[str, str]], *, validate: bool = True) -> str:
        document = copy.deepcopy(self.document)
        if not values["name"].strip():
            raise ValueError("Give your digest a title")
        if values["name"] != self.initial["name"]:
            document["digest_name"] = values["name"].strip()
        if values["hn"] != self.initial["hn"]:
            document["hn_queries"] = values["hn"].splitlines()
        for field, table, attribute in (("rss", "rss_sources", "url"), ("arxiv", "arxiv_sources", "query")):
            if values[field] == self.initial[field]:
                continue
            selected = [tuple(part.strip() for part in line.split("|", 1)) for line in values[field].splitlines()]
            initial_names = {
                value.strip(): name.strip()
                for name, value in (line.split("|", 1) for line in self.initial[field].splitlines())
            }
            rows = tomlkit.aot()
            for name, value in selected:
                identity = origins.get(field, {}).get(value, value)
                originals = [row for row in document.get(table, []) if row[attribute] == identity]
                for old in originals or [{}]:
                    row = copy.deepcopy(old) if old else tomlkit.table()
                    if not old or name != initial_names.get(identity):
                        row["name"] = name
                    if row.get(attribute) != value:
                        row[attribute] = value
                    rows.append(row)
            document[table] = rows
        if values["categories"] != self.initial["categories"]:
            existing_keys = {row["key"] for row in document["categories"]}
            selected_categories = {
                row[0]: row for row in category_rows(values["categories"], existing_keys=existing_keys)
            }
            rows = tomlkit.aot()
            catch_all = None
            for old in document["categories"]:
                key = old["key"]
                if key == "general":
                    if document["categories"][-1]["key"] == "general":
                        catch_all = copy.deepcopy(old)
                    else:
                        rows.append(copy.deepcopy(old))
                elif key in selected_categories:
                    desired = selected_categories.pop(key)
                    row = copy.deepcopy(old)
                    for index, attribute in enumerate(
                        ("key", "title", "keywords", "required_keywords", "exclude_keywords")
                    ):
                        if desired[index] != category_value(old)[index]:
                            row[attribute] = desired[index] if index < 2 else _terms(desired[index])
                    rows.append(row)
            for key, title, keywords, required, excluded in selected_categories.values():
                row = tomlkit.table()
                row.update(
                    key=key,
                    title=title,
                    keywords=_terms(keywords),
                    required_keywords=_terms(required),
                    exclude_keywords=_terms(excluded),
                )
                rows.append(row)
            if catch_all is not None:
                rows.append(catch_all)
            document["categories"] = rows
        for field, attribute in (("preferred", "preferred_keywords"), ("demoted", "demoted_keywords")):
            if values[field] != self.initial[field]:
                if "ranking" not in document:
                    document["ranking"] = tomlkit.table()
                document["ranking"][attribute] = values[field].splitlines()
        text = tomlkit.dumps(document)
        if validate:
            validated_document(text)
        return text

    def adopt(self, text: str) -> None:
        """Accept advanced edits in memory while retaining the original file guard."""
        self.document = validated_document(text)
        self.initial = self.values()

    def save(self, text: str) -> None:
        validated_document(text)
        if self.path.is_symlink() or self.path.read_bytes() != self.original:
            raise ValueError("The config changed while editing. Reopen it before saving; no changes were written")
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            os.fchmod(descriptor, stat.S_IMODE(self.path.stat().st_mode))
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.is_symlink() or self.path.read_bytes() != self.original:
                raise ValueError("The config changed while editing. Reopen it before saving; no changes were written")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
