# FitFindr 🛍️

FitFindr is a thrift-shopping stylist agent. You describe a secondhand piece you're after (and, optionally, your wardrobe), and it finds a matching listing, suggests how to style it with what you already own, and writes a shareable caption for the look.

It runs as a small planning-loop agent over three tools, with a Gradio web UI.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tools.py                   # The 3 tools (search / suggest / fit card)
├── agent.py                   # Planning loop + session state (run_agent)
├── app.py                     # Gradio UI (handle_query)
├── tests/
│   └── test_tools.py          # Pytest tests — one per failure mode
├── planning.md                # Design doc: tools, loop, state, error handling
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

The two LLM-backed tools (`suggest_outfit`, `create_fit_card`) use Groq's
`llama-3.3-70b-versatile`. If the key is missing or the API is unreachable, the
tools fall back to non-empty default text rather than crashing.

## Running It

**Web UI (recommended):**
```bash
python3 app.py
```
Then open the URL printed in your terminal (usually http://localhost:7860).
Pick "Example wardrobe" or "Empty wardrobe (new user)", type a request, and hit **Find it**.

**Command line (happy path + no-results path):**
```bash
python3 agent.py
```

## The Three Tools

Each tool has a defined signature and handles its own failure mode.

| Tool | Signature | Returns |
|------|-----------|---------|
| `search_listings` | `(description, size=None, max_price=None) -> list[dict]` | Listings ranked by relevance (each dict + a `relevance_score`); `[]` if nothing matches |
| `suggest_outfit` | `(new_item: dict, wardrobe: dict) -> str` | A styling suggestion string pairing the item with wardrobe pieces |
| `create_fit_card` | `(outfit: str, new_item: dict) -> str` | A short, casual, shareable caption for the look |

- **`search_listings`** is pure data work — it loads listings via `load_listings()`, filters by price and (loosely) by size, scores each listing by keyword overlap with the description (style-tag matches count double), drops zero-score listings, and returns the rest sorted best-first.
- **`suggest_outfit`** calls the LLM. With a populated wardrobe it references specific owned pieces by name; with an empty wardrobe it gives general styling advice and invites the user to add their closet.
- **`create_fit_card`** calls the LLM at high temperature so captions vary for the same input, weaving in the item's name, price, and platform.

## How the Planning Loop Works

The loop lives in `run_agent()` in [agent.py](agent.py) and is **state-driven**, not a
fixed sequence. A single `session` dict is the source of truth for one interaction:

```python
session = {
    "query", "parsed",            # raw query + extracted description/size/max_price
    "search_results",             # output of search_listings
    "selected_item",              # top result, carried into suggest_outfit
    "wardrobe",                   # the user's closet
    "outfit_suggestion",          # output of suggest_outfit
    "fit_card",                   # output of create_fit_card
    "error",                      # set only on the early-exit path
}
```

On each pass, the loop inspects which slot is still empty and picks the next tool:

1. **Parse** the natural-language query into `description`, `size`, `max_price` (regex, in `_parse_query`).
2. **`selected_item` is empty →** call `search_listings`.
   - **If results are empty:** set `session["error"]` with advice on how to loosen the search, and **break** — `suggest_outfit` and `create_fit_card` are never called.
   - **Otherwise:** store `results[0]` as `selected_item`.
3. **Have an item but no `outfit_suggestion` →** call `suggest_outfit(selected_item, wardrobe)`.
4. **Have an outfit but no `fit_card` →** call `create_fit_card(outfit_suggestion, selected_item)`.
5. **Done** when `fit_card` is set (success) or `error` is set (early exit).

Because each step is chosen by reading state, an empty search short-circuits the rest
and the agent reacts to what each tool returns instead of always running all three.

## State Management

No value is ever re-entered by the user between steps. Each tool reads its inputs from
`session` and writes its output back: `search_listings` writes `search_results`; the loop
copies `search_results[0]` into `selected_item`; `suggest_outfit` reads `selected_item` +
`wardrobe` and writes `outfit_suggestion`; `create_fit_card` reads `outfit_suggestion` +
`selected_item` and writes `fit_card`. The item found in step 1 flows all the way to the
caption automatically.

## Error Handling Strategy

Every tool handles its own failure mode — nothing fails silently or crashes the agent.

| Tool | Failure mode | Response |
|------|-------------|----------|
| `search_listings` | No match (`[]`), or the data file fails to load (caught → `[]`) | The loop sets `session["error"]` with a message naming what to relax (budget, size, broader style words) and **stops before the other tools**. |
| `suggest_outfit` | Empty wardrobe, or LLM/API error | Returns non-empty general styling advice (empty wardrobe) or a safe fallback suggestion (API error) instead of crashing; the loop still proceeds to the fit card. |
| `create_fit_card` | Empty/whitespace outfit, or LLM/API error | Returns a descriptive starter caption (empty outfit) or an item-only caption built from title/price/platform (API error) — never an empty string or exception. |

## A Complete Interaction

Query: *"looking for a vintage graphic tee under $30"* with the example wardrobe.

1. `search_listings("vintage graphic tee", max_price=30.0)` → ranked tees; top result selected.
2. `suggest_outfit(<tee>, <wardrobe>)` → "Pair it with your baggy straight-leg jeans and chunky white sneakers…"
3. `create_fit_card(<outfit>, <tee>)` → "just scored this … off depop for $… 🌸"

The UI shows all three: the listing, the outfit idea, and the fit card.
Try the deliberate no-results example (*"designer ballgown size XXS under $5"*) to see the
error path: the first panel shows the message and the other two stay empty.

## Testing

```bash
python3 -m pytest tests/
```
(`python3 -m pytest` puts the project root on `sys.path` so `from tools import ...` resolves.)

The suite covers each tool's failure mode: empty search results, the price filter, the
empty-wardrobe fallback, and the empty-outfit guard.

## Data

- **`data/listings.json`** — 40 mock listings across categories (tops, bottoms, outerwear,
  shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, …). Fields:
  `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`,
  `colors`, `brand`, `platform`. Load with `load_listings()`.
- **`data/wardrobe_schema.json`** — the wardrobe format, an `example_wardrobe` (10 items),
  and an `empty_wardrobe` template. Load with `get_example_wardrobe()` / `get_empty_wardrobe()`.
