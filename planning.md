# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (loaded via `load_listings()`) for secondhand items matching a free-text style description, an optional size, and an optional price ceiling. It scores each listing for relevance against the description, filters by size and price, and returns the matches ranked best-first.

**Input parameters:**
- `description` (str): a free-text style query, e.g. `"vintage graphic tee"`. Matched against each listing's `title`, `description`, and `style_tags` (case-insensitive, word/substring matching).
- `size` (str, optional): the user's size, e.g. `"M"`. Matched loosely against the listing's `size` field via substring/normalization (so `"M"` matches `"S/M"` and `"M/L"`). If omitted or empty, size is not filtered.
- `max_price` (float, optional): the highest price the user will pay. Listings with `price > max_price` are excluded. If omitted or `None`, price is not filtered.

**What it returns:**
A `list[dict]`, sorted by descending relevance score. Each dict is a full listing carrying every dataset field — `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform` — plus an added `relevance_score` (int/float) used for the ranking. An empty list `[]` means nothing matched.

**What happens if it fails or returns nothing:**
If the list is empty, the tool does not raise — it returns `[]`. The planning loop detects the empty result, writes a user-facing message into session state suggesting how to loosen the query (raise `max_price`, drop or change `size`, try broader style words), and returns early without calling `suggest_outfit`. If the underlying data file cannot be loaded, the tool catches the exception and returns `[]` so the same early-exit path handles it.

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific found item and the user's wardrobe, builds one or more complete outfit combinations by picking complementary wardrobe pieces (a bottom + shoes to go with a top, etc.) based on shared/compatible `style_tags` and `colors`, and returns styling guidance.

**Input parameters:**
- `new_item` (dict): the listing selected by the planning loop (the top result from `search_listings`), with all its fields (`category`, `style_tags`, `colors`, `title`, etc.). Determines which wardrobe categories are needed to complete the look.
- `wardrobe` (dict): the user's closet in the schema format `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}`, from `get_example_wardrobe()` / `get_empty_wardrobe()` or user input.

**What it returns:**
A `dict` describing one suggested outfit:
- `new_item` (dict): the item being styled (echoed back).
- `pieces` (list[dict]): the wardrobe items chosen to complete the outfit, each with at least `name` and `category` (e.g. baggy jeans + chunky sneakers).
- `styling_note` (str): a short human-readable styling tip (e.g. "roll the sleeves once and tuck the front corner").
- `is_fallback` (bool): `True` when the wardrobe was empty/minimal and only general advice could be given.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty (or no piece pairs well), the tool does not crash — it returns a result with `pieces: []`, `is_fallback: True`, and a `styling_note` giving general advice for the item ("pairs well with straight-leg denim and chunky sneakers"). The planning loop still proceeds to `create_fit_card`, which can caption the new item alone.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual, shareable caption (Instagram-style) for a completed look, weaving in the new item's vibe, price/platform, and the wardrobe pieces it's paired with. Designed to produce different output for different inputs.

**Input parameters:**
- `outfit` (dict): the result returned by `suggest_outfit` — contains `new_item`, `pieces`, `styling_note`, and `is_fallback`.
- `new_item` (dict): the found listing being featured (used for its `title`, `price`, `platform`, `colors`, `style_tags`). Passed explicitly so a card can still be produced even if `outfit` is incomplete.

**What it returns:**
A `str` — a single caption line (1–2 sentences, lowercase casual tone, may include an emoji), e.g. `"thrifted this faded band tee off depop for $22 and it was made for my baggy jeans 🖤"`. Varies by input because it pulls from the specific item title, price, platform, and paired pieces, and selects from templated phrasings keyed to the item's `style_tags`.

**What happens if it fails or returns nothing:**
If `outfit` is missing, empty, or has no `pieces`, the tool falls back to captioning the `new_item` alone (title + price + platform) rather than crashing. If even `new_item` is missing required fields, it returns a generic safe caption ("new thrift find, styling soon") so the agent always has something to show the user.

---

### Additional Tools (if any)

None for the core build. (Possible stretch: `add_to_wardrobe(item, wardrobe)` to persist the new find into the user's closet for future sessions.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is driven by what's currently present in session state, not a fixed sequence. On each pass it inspects the session and branches:

1. **Start (have a query, no results yet):**
   Parse the user's message into `description`, `size`, `max_price` and call `search_listings(description, size, max_price)`. Store the returned list in `session["results"]`.

2. **After `search_listings` — check `results`:**
   - **If `results` is empty:** set `session["error"]` to a message telling the user how to loosen the search (raise `max_price`, change/drop `size`, broaden style words), then **return early.** Do **not** call `suggest_outfit` or `create_fit_card`.
   - **If `results` is non-empty:** set `session["selected_item"] = results[0]` (highest relevance) and proceed to step 3.

3. **Have `selected_item`, no outfit yet:**
   Call `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])` and store the result in `session["outfit"]`.
   - If `outfit["is_fallback"]` is `True` (empty/minimal wardrobe), the loop notes this but still proceeds — `create_fit_card` can caption the item alone. (Optionally it can ask the user to add wardrobe items first; default is to proceed with general advice.)

4. **Have `outfit`, no fit card yet:**
   Call `create_fit_card(outfit=session["outfit"], new_item=session["selected_item"])` and store the string in `session["fit_card"]`.

5. **Done condition:**
   The loop terminates when either `session["error"]` is set (early exit) or all three of `selected_item`, `outfit`, and `fit_card` are present. It then renders the final response from session state.

The key point: each step's action is chosen by reading state (`results`, `selected_item`, `outfit`), so an empty search short-circuits the rest, and a fallback outfit still flows forward — the agent reacts to what each tool returns rather than always calling all three in order.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (one per conversation) holds everything the tools share, so no value has to be re-entered by the user:

```python
session = {
    "query":         {"description": str, "size": str|None, "max_price": float|None},
    "wardrobe":      {"items": [...]},   # from get_example_wardrobe() or user input
    "results":       [ ...listings... ], # output of search_listings
    "selected_item": { ...listing... },  # results[0], chosen by the planning loop
    "outfit":        { ...outfit... },   # output of suggest_outfit
    "fit_card":      "caption string",   # output of create_fit_card
    "error":         None,               # set only on the early-exit path
}
```

Flow of data between tools:
- `search_listings` writes `results`; the loop copies `results[0]` into `selected_item`.
- `suggest_outfit` reads `selected_item` and `wardrobe`, writes `outfit`.
- `create_fit_card` reads `outfit` and `selected_item`, writes `fit_card`.

Because each tool reads its inputs from `session` and writes its output back, the band tee found in step 1 automatically flows into styling and the caption — the user never re-types it. `error` is the one field that, when set, stops the loop before later tools run.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (returns `[]`); or the data file fails to load (caught, returns `[]`) | Loop detects empty `results`, sets `session["error"]`, and returns early without calling the other two tools. The agent says what it searched and names which filter to relax, echoing the actual values: *"I couldn't find a vintage graphic tee in size M under $30. Want me to bump the budget to $40, open it up to size L, or broaden the style (e.g. 'band tee' or 'grunge')? Tell me which and I'll search again."* If the failure was a data-load error rather than an empty match, it says *"I'm having trouble reaching the listings right now — try again in a moment."* |
| suggest_outfit | Wardrobe is empty or no piece pairs well | Returns `{pieces: [], is_fallback: True, styling_note: <general advice for the item>}` instead of crashing. The agent flags the fallback and invites input: *"Your closet's empty so I can't pull exact pairings, but this faded band tee styles best with baggy or straight-leg denim and chunky sneakers or combat boots. Add a few wardrobe pieces and I'll tailor it to what you own."* Loop still proceeds to `create_fit_card`. |
| create_fit_card | `outfit` is missing/incomplete (no `pieces`); or `new_item` missing fields | Falls back to captioning the `new_item` alone using its title/price/platform: *"scored this faded band tee on depop for $19 ✨"* — and notes to the user that styling pairings weren't available so the caption features just the find. If even `new_item` lacks the needed fields, it returns a generic safe caption (*"new thrift find, styling soon ✨"*) so the agent always has something to show rather than erroring. |

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │             SESSION STATE (dict)             │
                    │  query · wardrobe · results · selected_item  │
                    │           outfit · fit_card · error          │
                    └─────────────────────────────────────────────┘
                           ▲  reads/writes every step  ▲
                           │                            │
   user message            │                            │
  (query + wardrobe)       ▼                            │
        │          ┌───────────────┐                    │
        └─────────▶│ PLANNING LOOP │────────────────────┘
                   │ (branch on    │
                   │  state)       │
                   └───────────────┘
                     │     │     │
        description, │     │     │ outfit + selected_item
        size,        │     │     │
        max_price    ▼     │     ▼
            ┌──────────────┐│ ┌──────────────────┐
            │search_listings││ │  create_fit_card │
            └──────────────┘│ └──────────────────┘
                   │        │          │
          results  │        │          │ caption (str)
                   ▼        │          ▼
        ┌──────────────────┐│   ┌──────────────────┐
        │ results empty?   ││   │  FINAL OUTPUT     │
        └──────────────────┘│   │  listing + style  │
           │YES       │NO    │   │  + fit card       │
           │          │      │   └──────────────────┘
   ┌───────▼──────┐   │      │
   │ set error,   │   │ selected_item = results[0]
   │ tell user to │   │      │ (new_item) + wardrobe
   │ loosen query │   ▼      │
   │ RETURN EARLY │ ┌──────────────────┐
   │ (no further  │ │  suggest_outfit  │
   │  tool calls) │ └──────────────────┘
   └──────────────┘        │
        ▲                  │ outfit {pieces, styling_note,
        │ ERROR BRANCH     │         is_fallback}
        │ terminates flow  ▼
        └──────────  (back to loop → create_fit_card)
```

**How to read it:** 

The user's message plus wardrobe enter the **planning loop**, which reads and writes the shared **session state** at every step. The loop calls `search_listings` first. The **error branch** (left): if `results` is empty, the loop sets `error`, tells the user how to loosen the query, and terminates — `suggest_outfit` and `create_fit_card` are never called. The happy path (right): `selected_item = results[0]` flows into `suggest_outfit`, whose `outfit` flows with `selected_item` into `create_fit_card`, producing the caption shown in the final output. All inter-tool data travels through session state, never re-entered by the user.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

- **AI tool:** Claude (Claude Code in the IDE), since it can read the repo directly and call the existing `utils/data_loader.py` helpers.
- **Input I'll give it:** One tool at a time, I'll paste the matching spec from the **Tools** section above — for `search_listings` that's its *What it does / Input parameters / What it returns / What happens if it fails* block — plus the field reference from the **Tools** intro and the `load_listings()` / `get_example_wardrobe()` / `get_empty_wardrobe()` signatures from [utils/data_loader.py](utils/data_loader.py). I'll explicitly tell it to use those loaders rather than re-reading the JSON.
- **What I expect it to produce:** Three standalone Python functions with the exact signatures `search_listings(description, size=None, max_price=None) -> list[dict]`, `suggest_outfit(new_item, wardrobe) -> dict`, and `create_fit_card(outfit, new_item) -> str`, each implementing the documented matching/fallback logic and its own error handling (empty list, `is_fallback`, safe caption) — no crashes on bad input.
- **How I'll verify before using it:** Test each function against concrete cases drawn from the dataset I read:
  - `search_listings("vintage graphic tee", "M", 30.0)` → returns a non-empty ranked list whose top items are band/graphic tees under $30 (e.g. `lst_006`, `lst_033`); `search_listings("neon ski boots", None, 5.0)` → returns `[]` (confirms the empty path, no exception).
  - `suggest_outfit(<a tee>, get_example_wardrobe())` → returns a dict with non-empty `pieces` and `is_fallback=False`; same call with `get_empty_wardrobe()` → `pieces=[]`, `is_fallback=True`, still a valid `styling_note`.
  - `create_fit_card(...)` → two different items produce two different strings; calling it with `outfit=None` still returns a caption (not an error).
  I only keep the code once these match the **What it returns** and **Error Handling** specs.

**Milestone 4 — Planning loop and state management:**

- **AI tool:** Claude (Claude Code), so it can wire the loop against the three functions already in the repo.
- **Input I'll give it:** The **Planning Loop** section (the numbered branch logic), the **State Management** section (the `session` dict shape and data-flow rules), and the **Architecture** ASCII diagram showing the error branch — plus the example trace in **A Complete Interaction**. I'll tell it the loop must branch on session state, not call the tools in a fixed order.
- **What I expect it to produce:** A `session`-dict-driven controller that parses the user query into `description/size/max_price`, calls `search_listings`, and then branches exactly as specified — early-exit with an `error` message when `results` is empty (never calling the later tools), otherwise `selected_item = results[0]` → `suggest_outfit` → `create_fit_card` — reading/writing each value through the shared `session` so nothing is re-entered.
- **How I'll verify before using it:** Run two end-to-end scenarios:
  - **Happy path:** the example query → confirm `selected_item`, `outfit`, and `fit_card` all get populated and the band tee found in step 1 flows into the caption without re-entry.
  - **Error path:** an impossible query → confirm `session["error"]` is set, the user sees the "loosen your search" message, and `suggest_outfit`/`create_fit_card` are **never called** (e.g. by asserting `session["outfit"]` stays unset).
  I'll also confirm the empty-wardrobe fallback still flows through to a fit card. Code is accepted only when both paths behave as the diagram and loop spec describe.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr does:** 

FitFindr is a thrift-shopping stylist agent that takes a user's natural-language request for a secondhand clothing item plus a description of their wardrobe, finds a real matching listing, and tells them how to style it. A search request triggers `search_listings`; once a listing is found, that item flows into `suggest_outfit` to generate a styling combination from the user's wardrobe, and the resulting outfit flows into `create_fit_card` to write a shareable caption. If `search_listings` finds no matches, the agent stops and asks the user to loosen their criteria (higher price, different size or style) instead of calling the later tools; if the wardrobe is empty, `suggest_outfit` falls back to general styling advice rather than referencing nonexistent pieces; and if `create_fit_card` receives incomplete outfit data, it captions only the new item rather than crashing.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse + search.**
The planning loop parses the message into `description="vintage graphic tee"`, `size="M"`, `max_price=30.0`, and loads the user's wardrobe (here the example wardrobe with baggy jeans and chunky sneakers). It calls:

```python
search_listings(description="vintage graphic tee", size="M", max_price=30.0)
```

This returns a ranked, non-empty `list[dict]`. The top matches are the graphic/band tees under $30 — e.g. `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style", $24, depop, graphic-tee/band-tee tags) and `lst_033` ("Vintage Band Tee — Faded Grey", $19, depop). The loop stores the list in `session["results"]`.

**Step 2 — Branch on results, then suggest outfit.**
The loop checks `results`: it's non-empty, so it sets `session["selected_item"] = results[0]` (the top-ranked tee, e.g. `lst_006`) and calls:

```python
suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])
```

Because `new_item` is a top, the tool completes the look from the wardrobe's bottoms/shoes by matching style tags. It returns a dict like:
`{ new_item: <lst_006>, pieces: [<baggy straight-leg jeans>, <chunky white sneakers>], styling_note: "Tuck the front hem and roll the sleeves once for shape — let the baggy jeans balance the boxy tee.", is_fallback: False }`. The loop stores it in `session["outfit"]`.

**Step 3 — Create fit card.**
With an outfit in state, the loop calls:

```python
create_fit_card(outfit=session["outfit"], new_item=session["selected_item"])
```

It returns a single caption string, e.g. `"thrifted this bootleg graphic tee off depop for $24 and it was made for my baggy jeans 🖤 chunky sneakers to finish"`. The loop stores it in `session["fit_card"]`. All three of `selected_item`, `outfit`, and `fit_card` are now present, so the loop's done-condition is met and it terminates.

**Final output to user:**
The agent renders one combined response from session state:

**Found it:** *Graphic Tee — 2003 Tour Bootleg Style* — **$24**, Good condition, on Depop.

**How to style it:** Pair it with your baggy straight-leg jeans and chunky white sneakers. Tuck the front hem and roll the sleeves once for shape — let the baggy jeans balance the boxy tee.

**Caption for the post:** *"thrifted this bootleg graphic tee off depop for $24 and it was made for my baggy jeans 🖤 chunky sneakers to finish"*

The user sees the listing, a wardrobe-specific styling tip, and a ready-to-share caption — without ever re-entering the item between steps.
