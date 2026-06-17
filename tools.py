"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    Steps:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    # 1. Load all listings. If the data file can't be read, fail soft by
    #    returning [] so the planning loop's empty-result path handles it
    #    (per planning.md: the tool never raises).
    try:
        listings = load_listings()
    except Exception:
        return []

    # Tokenize the free-text query into lowercase keywords (drop 1-char noise).
    query_tokens = [
        tok for tok in re.findall(r"[a-z0-9]+", description.lower()) if len(tok) > 1
    ]

    # Normalize the requested size into comparable tokens, e.g. "M" -> {"M"},
    # so it can match listing sizes like "S/M" or "M/L" but not "XL".
    size_tokens = set()
    if size:
        size_tokens = {tok for tok in re.findall(r"[a-z0-9]+", size.lower())}

    results = []
    for listing in listings:
        # 2a. Price filter — skip anything above the ceiling (inclusive).
        if max_price is not None and listing.get("price", 0) > max_price:
            continue

        # 2b. Size filter — loose token match. A listing passes if any of its
        #     size tokens equals a requested size token (so "M" matches "S/M").
        if size_tokens:
            listing_size_tokens = {
                tok for tok in re.findall(r"[a-z0-9]+", str(listing.get("size", "")).lower())
            }
            if size_tokens.isdisjoint(listing_size_tokens):
                continue

        # 3. Score by keyword overlap. Style-tag hits count double since tags
        #    are the strongest signal of vibe; title/description hits count once.
        tags_text = " ".join(listing.get("style_tags", [])).lower()
        body_text = f"{listing.get('title', '')} {listing.get('description', '')}".lower()
        score = 0
        for tok in query_tokens:
            if tok in tags_text:
                score += 2
            elif tok in body_text:
                score += 1

        # 4. Drop listings with no relevant match.
        if score == 0:
            continue

        # Attach the score (used for ranking) and keep the full listing dict.
        results.append({**listing, "relevance_score": score})

    # 5. Sort by relevance, highest first, and return.
    results.sort(key=lambda item: item["relevance_score"], reverse=True)
    return results


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    Steps:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Describe the thrifted item for the prompt, pulling its key fields.
    item_desc = (
        f"{new_item.get('title', 'a thrifted item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    # 1. Check whether the wardrobe has any items.
    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    if not items:
        # 2. Empty wardrobe — ask the LLM for general styling advice for the
        #    item alone, since there are no owned pieces to pair with.
        prompt = (
            f"A user is considering buying this secondhand item: {item_desc}.\n"
            "They haven't told you what's in their wardrobe yet. "
            "Suggest how to style this piece in general — what kinds of bottoms, "
            "shoes, and layers pair well with it, and what overall vibe it suits. "
            "Keep it to 2-3 sentences, friendly and concrete. End by inviting them "
            "to add their wardrobe so you can tailor it to what they own."
        )
    else:
        # 3. Format the wardrobe into a readable list so the LLM can reference
        #    the user's actual pieces by name.
        wardrobe_lines = "\n".join(
            f"- {w.get('name', 'item')} (category: {w.get('category', '?')}, "
            f"colors: {', '.join(w.get('colors', [])) or 'n/a'}, "
            f"style: {', '.join(w.get('style_tags', [])) or 'n/a'})"
            for w in items
        )
        prompt = (
            f"A user is considering buying this secondhand item: {item_desc}.\n\n"
            f"Their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfit combinations that pair the new item with "
            "SPECIFIC pieces from their wardrobe, referring to those pieces by name. "
            "Include a short styling tip (how to wear/fit it). Keep it to 2-4 "
            "sentences, friendly and concrete."
        )

    # 4. Call the LLM and return its response. If the API call fails, fall back
    #    to a non-empty general suggestion rather than crashing (per planning.md).
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are FitFindr, a thrift-shopping stylist. "
                    "You give concise, specific, encouraging outfit advice.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        title = new_item.get("title", "this piece")
        return (
            f"I couldn't reach the styling service just now, but {title} pairs well "
            "with straight-leg or baggy denim and chunky sneakers or boots. "
            "Try again in a moment for tailored combinations."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    Steps:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty/whitespace-only outfit. Return a descriptive
    #    message string instead of crashing (per planning.md error handling).
    if not outfit or not outfit.strip():
        title = new_item.get("title", "this find") if isinstance(new_item, dict) else "this find"
        return (
            f"No outfit details to caption yet — but here's a starter: "
            f"new thrift find, {title}, styling soon ✨"
        )

    # 2. Build the prompt from the item details and the outfit suggestion.
    item_desc = (
        f"{new_item.get('title', 'a thrifted item')} "
        f"(${new_item.get('price', '?')}, from {new_item.get('platform', 'a resale app')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'})"
    )
    prompt = (
        f"Item: {item_desc}\n"
        f"Outfit idea: {outfit}\n\n"
        "Write a short, shareable caption for an OOTD post about thrifting this item.\n"
        "Guidelines:\n"
        "- Casual and authentic, like a real Instagram/TikTok caption (not a product description).\n"
        "- Mention the item name, its price, and the platform naturally — once each.\n"
        "- Capture the outfit's vibe in specific terms.\n"
        "- 2-4 sentences. An emoji or two is fine. Return ONLY the caption text."
    )

    # 3. Call the LLM. A high temperature keeps captions varied for the same
    #    input. On API failure, fall back to a non-empty caption built from the
    #    item details rather than crashing.
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are FitFindr, writing fun, authentic OOTD "
                    "captions for thrifted finds.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        title = new_item.get("title", "this thrift find")
        price = new_item.get("price", "?")
        platform = new_item.get("platform", "a resale app")
        return f"scored this {title} on {platform} for ${price} ✨"
