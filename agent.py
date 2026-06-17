"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract a description, size, and max_price from the natural-language query
    using regex. Returns a dict whose keys match search_listings' parameters:
    {"description": str, "size": str | None, "max_price": float | None}.
    """
    lower = query.lower().strip()

    # max_price: "under $30", "below 30", "less than $25", "up to 40", or bare "$30".
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|max|up to)\s*\$?\s*(\d+(?:\.\d+)?)", lower
    )
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", lower)
    if price_match:
        max_price = float(price_match.group(1))

    # size: explicit "size M" / "size XXS", else a standalone uppercase size token.
    size = None
    size_match = re.search(r"\bsize\s+([a-zA-Z0-9/]+)", lower)
    if size_match:
        size = size_match.group(1).upper()
    else:
        token_match = re.search(r"\b(XXS|XS|S|M|L|XL|XXL)\b", query)
        if token_match:
            size = token_match.group(1).upper()

    # description: strip the matched price/size phrases and common filler words,
    # leaving the style keywords for search_listings to score against.
    description = lower
    if price_match:
        description = description.replace(price_match.group(0), " ")
    if size_match:
        description = description.replace(size_match.group(0), " ")
    description = re.sub(
        r"\b(i'?m|im|looking|for|a|an|the|find|me|some|want|to|buy|under|below|in|my)\b",
        " ",
        description,
    )
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        description = lower

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    Steps — implements the planning loop designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session — the single source of truth for this interaction.
    session = _new_session(query, wardrobe)

    # Step 2: parse the natural-language query into search parameters (regex).
    session["parsed"] = _parse_query(query)

    # The planning loop is STATE-DRIVEN: on each pass it inspects which session
    # slots are still empty and picks the next tool accordingly. It does NOT call
    # the three tools in a fixed sequence — an empty search short-circuits the
    # rest (see the branch in Step 3 below).
    while session["error"] is None and session["fit_card"] is None:

        # Step 3: no item selected yet -> we still need to search.
        if session["selected_item"] is None:
            results = search_listings(**session["parsed"])
            session["search_results"] = results

            # Branch: if nothing matched, set a helpful error and STOP. We never
            # fall through to suggest_outfit / create_fit_card with empty input.
            if not results:
                parsed = session["parsed"]
                constraints = []
                if parsed.get("size"):
                    constraints.append(f"size {parsed['size']}")
                if parsed.get("max_price") is not None:
                    constraints.append(f"under ${parsed['max_price']:.0f}")
                where = (" in " + ", ".join(constraints)) if constraints else ""
                session["error"] = (
                    f'I couldn\'t find anything matching "{parsed["description"]}"{where}. '
                    "Try raising your budget, changing or dropping the size, or using "
                    "broader style words (e.g. 'band tee' or 'grunge')."
                )
                break

            # Step 4: select the top-ranked result to carry into styling.
            session["selected_item"] = results[0]

        # Step 5: have an item but no outfit yet -> suggest one from the wardrobe.
        elif session["outfit_suggestion"] is None:
            session["outfit_suggestion"] = suggest_outfit(
                session["selected_item"], session["wardrobe"]
            )

        # Step 6: have an outfit but no caption yet -> write the fit card.
        elif session["fit_card"] is None:
            session["fit_card"] = create_fit_card(
                session["outfit_suggestion"], session["selected_item"]
            )

    # Step 7: return the completed (or early-terminated) session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
