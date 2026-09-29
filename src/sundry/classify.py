"""Keyword-based topic classification."""

from __future__ import annotations

import re

from .models import Article, Category, DigestConfig

GENERAL_CATEGORY_KEY = "general"


def matches(term: str, text: str) -> bool:
    """Match whole terms, including acronyms at title boundaries."""
    term = term.strip()
    return bool(term and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE))


def category_score(article: Article, category: Category) -> float:
    text = f"{article.title} {article.summary}"
    if any(matches(term, text) for term in category.exclude_keywords):
        return 0
    if category.required_keywords and not any(matches(term, text) for term in category.required_keywords):
        return 0
    terms = {term.strip().lower(): 1.0 for term in category.keywords}
    terms.update({term.strip().lower(): weight for term, weight in category.keyword_weights.items()})
    return sum(
        weight * (2 if matches(term, article.title) else 1) for term, weight in terms.items() if matches(term, text)
    )


def classify(article: Article, categories: tuple[Category, ...]) -> str:
    """Return the best-matching category key for `article`.

    A source-forced category wins if its contextual rules allow the item.
    Otherwise every non-general
    category scores itself by keyword hits against the article's title and
    summary — a title hit counts double a summary-only hit — and the
    highest eligible score wins. Ties use configured category order;
    unmatched articles fall through to the ``general`` catch-all.
    """
    best_key, best_score = GENERAL_CATEGORY_KEY, 0.0
    for category in categories:
        text = f"{article.title} {article.summary}"
        allowed = not any(matches(term, text) for term in category.exclude_keywords)
        allowed &= not category.required_keywords or any(matches(term, text) for term in category.required_keywords)
        if article.forced_category == category.key and allowed:
            return category.key
        if category.key == GENERAL_CATEGORY_KEY:
            continue
        score = category_score(article, category)
        if score >= category.min_score and score > best_score:
            best_key, best_score = category.key, score
    return best_key


def rank_score(article: Article, category: Category, config: DigestConfig) -> float:
    text = f"{article.title} {article.summary}"
    return (
        category_score(article, category)
        + config.source_weights.get(article.source, 0)
        + 3 * sum(matches(term, text) for term in config.preferred_keywords)
        - 6 * sum(matches(term, text) for term in config.demoted_keywords)
    )
