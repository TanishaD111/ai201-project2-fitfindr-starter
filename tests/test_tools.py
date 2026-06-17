"""
Pytest tests for the three FitFindr tools.

At least one test per failure mode:
- search_listings: returns results, empty result (no match), price filter
- suggest_outfit: empty wardrobe (must not crash)
- create_fit_card: empty/whitespace outfit (must not crash)

The LLM-backed tools (suggest_outfit, create_fit_card) are written to degrade
gracefully, so these tests assert on contract (non-empty string, no exception)
rather than exact wording — they pass with or without a live GROQ_API_KEY.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Tool 1: search_listings ──────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches -> empty list, never an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    # "M" should match listings sized M / S/M / M/L, never XL-only sizes.
    results = search_listings("vintage", size="M", max_price=100)
    for item in results:
        size = item["size"].upper()
        assert "M" in size and "XL" not in size


def test_search_results_sorted_by_relevance():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    scores = [item["relevance_score"] for item in results]
    assert scores == sorted(scores, reverse=True)


# ── Tool 2: suggest_outfit ───────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe must not crash; returns a non-empty string.
    new_item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(new_item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_with_wardrobe():
    new_item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(new_item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── Tool 3: create_fit_card ──────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: empty outfit string -> descriptive message, no exception.
    new_item = {"title": "Faded Band Tee", "price": 19.0, "platform": "depop"}
    result = create_fit_card("", new_item)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_whitespace_outfit():
    new_item = {"title": "Faded Band Tee", "price": 19.0, "platform": "depop"}
    result = create_fit_card("   \n  ", new_item)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_returns_string():
    new_item = {"title": "Faded Band Tee", "price": 19.0, "platform": "depop",
                "colors": ["grey"], "style_tags": ["vintage", "grunge"]}
    outfit = "Pair it with baggy jeans and chunky sneakers."
    result = create_fit_card(outfit, new_item)
    assert isinstance(result, str)
    assert result.strip() != ""
