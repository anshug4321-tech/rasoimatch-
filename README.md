# RasoiMatch

Type the ingredients you have (English or Hindi names such as *jeera, aloo, dhania*) and get Indian recipes ranked by how much of each recipe you can already cook.

- One self-contained `index.html`. No backend, no server, no API, no LLM. Runs offline in the browser.
- **Not AI.** It is simple, explainable matching with TF-IDF style weights. Every score can be opened with "Why this recipe?".
- Includes a re-runnable **Evaluation** tab that measures the matching inside the browser (seed 42).

## How the score works

```
score = 0.6 × weighted_coverage + 0.3 × usage + 0.1 × 1/(1 + missing)
```

| Part | Meaning |
|---|---|
| coverage | ingredients you have ÷ ingredients the recipe needs |
| weighted_coverage | same, but each ingredient counts by its IDF weight (rare items matter more) |
| usage | ingredients you have that the recipe uses ÷ ingredients you listed |
| missing | items still to buy |

Methods A (Jaccard) and B (TF-IDF cosine) are also available for comparison. Weights can be tuned on development recipes in the Evaluation tab.

## Project layout

```
src/template.html     UI, How it works tab, Evaluation tab (data inserted at build time)
src/engine.js         recommender + evaluation, plain JavaScript, no DOM
scripts/prep.py       cleans the CSV into compact JSON (standard library only)
scripts/build.py      inserts the JSON and engine into the template -> index.html
tests/                Node engine test and a headless-browser check
docs/                 merge review, fuzzy-match suggestions (never applied), diet keyword lists
index.html            the built app (what GitHub Pages serves)
```

## Rebuild from the raw data

1. Download `Cleaned_Indian_Food_Dataset.csv` (5,938 recipes from archanaskitchen.com) into `data/`. The raw CSV is not in this repo.
2. Run `make` (needs Python 3). This runs `prep.py` (with its tests) and then `build.py`.
3. Optional tests: `make test` (needs Node 18+). The browser check needs Playwright: `NODE_PATH=$(npm root -g) node tests/check_browser.js index.html`.

## Data preparation in short

- Hidden characters removed, ingredient names lowercased, bracket text used as aliases, simple plurals merged, a hand-written Hindi alias table applied.
- Fuzzy matching only **suggests** merges (`docs/fuzzy_suggestions.csv`). Nothing is merged automatically.
- Diet (veg / egg / non-veg) is estimated by whole-word keywords, so "eggplant" is not egg. Jain and vegan are estimates too, not certified.
- 82 cuisine labels are grouped into 7 regions. Time 0 is treated as unknown.
- Salt, water, oil and sugar are always assumed. Basic masalas can be switched on or off.
- Cooking instructions are dropped and never published.

## Limits

- Diet labels are estimates.
- All recipes come from one site.
- Results depend on ingredient names and the alias table.
- The evaluation builds queries from the recipes themselves, so it is optimistic and does not measure real user satisfaction.

## Credit and licence

- Code: MIT (see `LICENSE`).
- Recipe titles, ingredient lists, photos and links belong to [Archana's Kitchen](https://www.archanaskitchen.com/). This is an educational, non-commercial project and is not affiliated with that site. Check the dataset's licence on its source page before publishing. `index.html` contains that recipe data.
