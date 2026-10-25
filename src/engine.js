/* ==========================================================================
   RasoiMatch engine: recommender + evaluation. Plain JavaScript, no DOM.
   The same file is inlined into the HTML and loaded by Node for testing.
   ========================================================================== */

/* ---- tiny seeded random generator (mulberry32) so every run gives the same numbers ---- */
function mulberry32(seed) {
  let a = seed | 0;
  return function () {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffled(arr, rnd) {            // Fisher-Yates, returns a copy
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
function meanSd(xs) {
  const m = xs.reduce((s, x) => s + x, 0) / xs.length;
  const v = xs.reduce((s, x) => s + (x - m) * (x - m), 0) / xs.length;
  return { mean: m, sd: Math.sqrt(v) };
}
function levenshtein(a, b) {
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let last = prev[0]; prev[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const tmp = prev[j];
      prev[j] = Math.min(prev[j] + 1, prev[j - 1] + 1, last + (a[i - 1] === b[j - 1] ? 0 : 1));
      last = tmp;
    }
  }
  return prev[b.length];
}

const START_WEIGHTS = { cov: 0.6, use: 0.3, few: 0.1 };   // starting point from the project brief
const DIET_NAMES = ["Veg", "Egg", "Non-veg"];

function createEngine(DATA) {
  const V = DATA.vocab, IDF = DATA.idf;
  const ALIAS = new Map(Object.entries(DATA.aliases));      // Map avoids odd keys like "constructor"
  const recipes = DATA.recipes.map(r => ({
    id: r[0], name: r[1], url: DATA.meta.url_prefix + r[2],
    img: r[3] ? DATA.meta.img_prefix + r[3] : "", time: r[4], longPrep: !!r[5],
    region: r[6], diet: r[7], jain: !!r[8], vegan: !!r[9], core: r[10], lines: r[11], assumed: r[12] || []
  }));
  const N = recipes.length;
  const assumedFlag = new Uint8Array(V.length), masalaFlag = new Uint8Array(V.length);
  DATA.staples.assumed.forEach(i => assumedFlag[i] = 1);
  DATA.staples.masala.forEach(i => masalaFlag[i] = 1);

  /* inverted index: ingredient id -> recipe indexes (built once, so a query never scans all recipes) */
  const inv = Array.from({ length: V.length }, () => []);
  const df = new Int32Array(V.length);
  recipes.forEach((r, ri) => r.core.forEach(i => { inv[i].push(ri); df[i]++; }));
  const assumedInv = Array.from({ length: V.length }, () => []);   // only used by the "no staple removal" ablation
  recipes.forEach((r, ri) => r.assumed.forEach(i => assumedInv[i].push(ri)));

  const subsById = new Map();
  DATA.subs.forEach(([id, tryText, note]) => {
    if (!subsById.has(id)) subsById.set(id, []);
    subsById.get(id).push({ try: tryText, note });
  });
  const hindiById = new Map();                                // id -> list of Hindi aliases
  Object.entries(DATA.hindi).forEach(([a, id]) => { if (!hindiById.has(id)) hindiById.set(id, []); hindiById.get(id).push(a); });

  const E = { recipes, vocab: V, idf: IDF, df, N, weights: { ...START_WEIGHTS }, regions: DATA.regions, meta: DATA.meta,
              assumedFlag, masalaFlag, hindiById, subsById };

  /* ------------------------------------------------------------------ text -> ingredient id */
  function norm(text) {
    return text.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z' -]+/g, " ").replace(/\s+/g, " ").trim();
  }
  function singularCandidates(w) {                            // same idea as the Python script
    const c = [];
    if (w.endsWith("ies")) c.push(w.slice(0, -3) + "y", w.slice(0, -3) + "i");
    if (w.endsWith("oes") || w.endsWith("es")) c.push(w.slice(0, -2));
    if (w.endsWith("s") && !/(ss|us|is)$/.test(w)) c.push(w.slice(0, -1));
    return c;
  }
  function resolveText(text) {
    const t = norm(text);
    if (!t) return -1;
    if (ALIAS.has(t)) return ALIAS.get(t);
    for (const c of singularCandidates(t)) if (ALIAS.has(c)) return ALIAS.get(c);
    return -1;
  }
  /* "aloo, pyaz jeera" -> comma chunks; a chunk with spaces is tried whole, then word-by-word (longest span first) */
  function parseInput(str) {
    const found = [], unknown = [];
    for (const chunk of String(str).split(/[,;\n]+/)) {
      const t = norm(chunk);
      if (!t) continue;
      const whole = resolveText(t);
      if (whole >= 0) { found.push({ text: t, id: whole }); continue; }
      const words = t.split(" ");
      let i = 0;
      while (i < words.length) {
        let hit = false;
        for (let n = Math.min(3, words.length - i); n >= 1; n--) {
          const piece = words.slice(i, i + n).join(" ");
          const id = resolveText(piece);
          if (id >= 0) { found.push({ text: piece, id }); i += n; hit = true; break; }
        }
        if (!hit) { unknown.push(words[i]); i++; }
      }
    }
    return { found, unknown };
  }

  /* suggestions use only reasonably common names (seen in 3+ recipes) or Hindi names */
  const hindiKeys = new Set(Object.keys(DATA.hindi));
  const popKeys = [...ALIAS.keys()].filter(k => (df[ALIAS.get(k)] >= 3 || hindiKeys.has(k)) && !/\d/.test(k))
    .sort((a, b) => df[ALIAS.get(b)] - df[ALIAS.get(a)] || a.localeCompare(b));
  E.suggestFor = function (word) {
    const t = norm(word), out = [], seen = new Set();
    const add = key => {
      const id = ALIAS.get(key);
      if (!seen.has(id) && out.length < 3) { seen.add(id); out.push({ alias: key, id, name: V[id] }); }
    };
    if (t.length >= 2) for (const k of popKeys) if (k.startsWith(t)) add(k);
    const maxD = t.length <= 4 ? 1 : 2, close = [];
    for (const k of popKeys) {
      if (Math.abs(k.length - t.length) > maxD) continue;
      const d = levenshtein(t, k);
      if (d <= maxD) close.push([d, k]);
    }
    close.sort((a, b) => a[0] - b[0]);
    close.forEach(([, k]) => add(k));
    return out;
  };
  E.autocomplete = function (text, limit = 8) {                // for the type-ahead list
    const t = norm(text);
    if (t.length < 1) return [];
    const starts = [], inside = [];
    for (const k of popKeys) {
      if (k.startsWith(t)) starts.push(k);
      else if (k.includes(" " + t)) inside.push(k);
      if (starts.length >= limit) break;
    }
    const seen = new Set();
    return starts.concat(inside).filter(k => { const id = ALIAS.get(k); if (seen.has(id + k)) return false; seen.add(id + k); return true; })
      .slice(0, limit).map(k => ({ key: k, id: ALIAS.get(k), name: V[ALIAS.get(k)] }));
  };
  E.parseInput = parseInput; E.resolveText = resolveText; E.norm = norm;

  /* ------------------------------------------------------------------ scoring */
  // opts: { masalaOn (bool), useIdf (bool, default true), countAssumed (bool, ablation) }
  function prepareQuery(qIds, opts) {
    const flag = new Uint8Array(V.length), eff = [];
    for (const i of qIds) {
      if (flag[i]) continue;
      if (assumedFlag[i] && !opts.countAssumed) continue;       // typing "salt" must not change the result
      if (masalaFlag[i] && opts.masalaOn) continue;
      flag[i] = 1; eff.push(i);
    }
    let idfSum = 0, idf2Sum = 0;
    for (const i of eff) { const w = opts.useIdf === false ? 1 : IDF[i]; idfSum += w; idf2Sum += w * w; }
    return { eff, flag, size: eff.length, idf2Sum };
  }
  const seenStamp = new Int32Array(N); let stamp = 0;
  function candidateIndexes(q, opts) {
    stamp++;
    const out = [];
    for (const i of q.eff) {
      const lists = opts.countAssumed ? [inv[i], assumedInv[i]] : [inv[i]];
      for (const list of lists) for (const ri of list) if (seenStamp[ri] !== stamp) { seenStamp[ri] = stamp; out.push(ri); }
    }
    return out;
  }
  /* score one recipe. Returns null when the recipe has nothing left to cook with (empty C) */
  function scoreOne(ri, q, method, w, opts) {
    const r = recipes[ri], useIdf = opts.useIdf !== false;
    let cSize = 0, inter = 0, cIdf = 0, interIdf = 0, cIdf2 = 0, interIdf2 = 0;
    const visit = i => {
      if (masalaFlag[i] && opts.masalaOn) return;                // user has basic masalas: not part of C
      const wt = useIdf ? IDF[i] : 1;
      cSize++; cIdf += wt; cIdf2 += wt * wt;
      if (q.flag[i]) { inter++; interIdf += wt; interIdf2 += wt * wt; }
    };
    r.core.forEach(visit);
    if (opts.countAssumed) r.assumed.forEach(visit);
    if (cSize === 0 || inter === 0) return null;
    const missing = cSize - inter;
    const coverage = inter / cSize, usage = inter / q.size, wcov = interIdf / cIdf;
    let score;
    if (method === "A") score = inter / (q.size + cSize - inter);                       // Jaccard
    else if (method === "B") score = interIdf2 / (Math.sqrt(q.idf2Sum) * Math.sqrt(cIdf2)); // cosine of idf-weighted binary vectors
    else score = w.cov * wcov + w.use * usage + w.few * (1 / (1 + missing));
    return { ri, id: r.id, score, missing, coverage, usage, wcov, inter, cSize };
  }
  const timeKey = ri => recipes[ri].time == null ? 1e9 : recipes[ri].time;
  /* stable order: score high -> missing low -> time low (unknown last) -> id low */
  function better(a, b) {
    if (Math.abs(a.score - b.score) > 1e-12) return a.score > b.score;
    if (a.missing !== b.missing) return a.missing < b.missing;
    const ta = timeKey(a.ri), tb = timeKey(b.ri);
    if (ta !== tb) return ta < tb;
    return a.id < b.id;
  }
  const cmp = (a, b) => (better(a, b) ? -1 : better(b, a) ? 1 : 0);

  /* ------------------------------------------------------------------ filters */
  function passes(r, f) {
    if (f.indianOnly !== false && (r.region === 5 || r.region === 6)) return false;
    if (f.regions && f.regions.length && !f.regions.includes(r.region)) return false;
    switch (f.diet) {
      case "veg": if (r.diet !== 0) return false; break;
      case "egg": if (r.diet === 2) return false; break;            // veg or egg, no meat/fish
      case "nonveg": if (r.diet !== 2) return false; break;
      case "jain": if (!r.jain) return false; break;
      case "vegan": if (!r.vegan) return false; break;
    }
    if (f.maxTime && r.time != null && r.time > f.maxTime) return false;   // unknown time stays visible
    return true;
  }

  /* explanation object so the UI can show every part of the score */
  function whyOf(s, q, method, w, opts) {
    const r = recipes[s.ri], have = [], miss = [];
    const visit = i => { if (masalaFlag[i] && opts.masalaOn) return; (q.flag[i] ? have : miss).push(i); };
    r.core.forEach(visit);
    if (opts.countAssumed) r.assumed.forEach(visit);
    return { method, qSize: q.size, coverage: s.coverage, usage: s.usage, missing: s.missing, weighted_coverage: s.wcov,
             parts: method === "C" ? { cov: w.cov * s.wcov, use: w.use * s.usage, few: w.few * (1 / (1 + s.missing)) } : null,
             weights: method === "C" ? { ...w } : null, have, miss };
  }

  /* ------------------------------------------------------------------ main API */
  /* recommend(userItems, filters, topK, method): userItems = array of text (or numeric ids) */
  E.recommend = function (userItems, filters = {}, topK = 10, method = "C", opts = {}) {
    const t0 = performance.now();
    const o = { masalaOn: filters.masalaOn !== false, useIdf: opts.useIdf, countAssumed: !!opts.countAssumed };
    const ids = [], recognized = [], unrecognized = [];
    for (const it of userItems) {
      if (typeof it === "number") { ids.push(it); recognized.push({ text: V[it], id: it }); continue; }
      const p = parseInput(it);
      p.found.forEach(f => { ids.push(f.id); recognized.push(f); });
      p.unknown.forEach(u => unrecognized.push({ word: u, suggestions: E.suggestFor(u) }));
    }
    const q = prepareQuery(ids, o);
    const out = { groups: { now: [], almost: [], shop: [] }, counts: { now: 0, almost: 0, shop: 0 }, results: [],
                  recognized, unrecognized, onlyStaples: ids.length > 0 && q.size === 0, took_ms: 0, total: 0 };
    if (q.size > 0) {
      const scored = [];
      for (const ri of candidateIndexes(q, o)) {
        if (!passes(recipes[ri], filters)) continue;
        const s = scoreOne(ri, q, method, E.weights, o);
        if (s) scored.push(s);
      }
      scored.sort(cmp);
      out.total = scored.length;
      for (const s of scored) {
        const g = s.missing === 0 ? "now" : s.missing <= 2 ? "almost" : "shop";
        out.counts[g]++;
        if (out.groups[g].length < topK) out.groups[g].push(s);
      }
      out.results = scored.slice(0, topK);
      for (const g of Object.values(out.groups)) g.forEach(s => { s.why = whyOf(s, q, method, E.weights, o); });
      out.results.forEach(s => { if (!s.why) s.why = whyOf(s, q, method, E.weights, o); });
    }
    out.took_ms = Math.round((performance.now() - t0) * 100) / 100;
    return out;
  };

  /* rank of one target recipe among ALL recipes (no filters). Used by the evaluation. */
  E.rankOf = function (qIds, targetRi, method, weights, opts) {
    const q = prepareQuery(qIds, opts);
    if (q.size === 0) return Infinity;
    const target = scoreOne(targetRi, q, method, weights, opts);
    if (!target) return Infinity;
    let rank = 1;
    for (const ri of candidateIndexes(q, opts)) {
      if (ri === targetRi) continue;
      const s = scoreOne(ri, q, method, weights, opts);
      if (s && better(s, target)) rank++;
    }
    return rank;
  };
  E.topIds = function (qIds, method, weights, opts, k) {          // top-k recipe indexes, for failure analysis
    const q = prepareQuery(qIds, opts), list = [];
    for (const ri of candidateIndexes(q, opts)) { const s = scoreOne(ri, q, method, weights, opts); if (s) list.push(s); }
    return list.sort(cmp).slice(0, k).map(s => s.ri);
  };
  E.subsFor = id => subsById.get(id) || [];
  return E;
}

/* ==========================================================================
   Evaluation (runs as a generator so the browser can do it in small slices)
   ========================================================================== */
const EVAL_SEEDS = [42, 43, 44, 45, 46];
const SIZE_BINS = [["5-7", 5, 7], ["8-11", 8, 11], ["12+", 12, 99]];

function* evaluationSteps(E, cfg = {}) {
  const testCap = cfg.testCap || 500, devCap = cfg.devCap || 300;
  const OPT = { masalaOn: false };                                  // masalas count as normal ingredients in the test
  const jac = (a, b) => { const sb = new Set(b); let i = 0; for (const x of a) if (sb.has(x)) i++; return i / (a.length + b.length - i); };
  const popular = []; for (let i = 0; i < E.vocab.length; i++) if (E.df[i] >= 5 && !E.assumedFlag[i]) popular.push(i);

  /* ---- 1. split 70/30 by region group, seed 42 ---- */
  const rnd = mulberry32(42), dev = [], test = [];
  const byRegion = new Map();
  E.recipes.forEach((r, ri) => { if (r.core.length >= 5) { if (!byRegion.has(r.region)) byRegion.set(r.region, []); byRegion.get(r.region).push(ri); } });
  for (const [, list] of [...byRegion.entries()].sort((a, b) => a[0] - b[0])) {
    const s = shuffled(list, rnd), cut = Math.round(s.length * 0.7);
    dev.push(...s.slice(0, cut)); test.push(...s.slice(cut));
  }
  const pick = (list, cap) => shuffled(list, mulberry32(42)).slice(0, cap);
  const devSample = pick(dev, devCap), testSample = pick(test, testCap);
  const eligible = dev.length + test.length;

  /* ---- query builders ---- */
  const hide = (ri, r) => {                                         // random 70% of the core ingredients
    const core = E.recipes[ri].core, k = Math.max(1, Math.round(core.length * 0.7));
    return shuffled(core, r).slice(0, k);
  };
  const makeQuery = (ri, kind, r) => {
    const ids = hide(ri, r);
    if (kind === "A") return ids;
    if (kind === "B") {                                              // swap some names for Hindi, then go through the TEXT path
      const out = [];
      for (const i of ids) {
        const h = E.hindiById.get(i);
        const text = h && r() < 0.5 ? h[Math.floor(r() * h.length)] : E.vocab[i];
        const id = E.resolveText(text);
        if (id >= 0) out.push(id);
      }
      return out;
    }
    const core = new Set(E.recipes[ri].core), extra = [];           // kind C: add 2 ingredients that are NOT in the recipe
    while (extra.length < 2) { const x = popular[Math.floor(r() * popular.length)]; if (!core.has(x) && !extra.includes(x)) extra.push(x); }
    return ids.concat(extra);
  };
  const metrics = ranks => ({
    top1: ranks.filter(x => x <= 1).length / ranks.length, top5: ranks.filter(x => x <= 5).length / ranks.length,
    top10: ranks.filter(x => x <= 10).length / ranks.length, mrr: ranks.reduce((s, x) => s + (isFinite(x) ? 1 / x : 0), 0) / ranks.length });
  let done = 0, total = 0;
  const gridCombos = [];
  for (let c = 3; c <= 9; c++) for (let u = 0; u <= 5; u++) { const f = 10 - c - u; if (f >= 0) gridCombos.push({ cov: c / 10, use: u / 10, few: f / 10 }); }
  const draws = EVAL_SEEDS.length;
  total = gridCombos.length * devSample.length + 3 * draws * testSample.length + 6 * 3 * testSample.length + testSample.length;
  const tick = function* (n) { done += n; yield { done, total, phase: "running" }; };

  /* ---- 2. weight tuning on DEVELOPMENT recipes only ---- */
  const devQueries = devSample.map(ri => ({ ri, q: makeQuery(ri, "A", mulberry32(42 + ri)) }));
  let best = null, startDev = null;
  for (const w of gridCombos) {
    const ranks = devQueries.map(x => E.rankOf(x.q, x.ri, "C", w, OPT));
    const m = metrics(ranks);
    if (w.cov === START_WEIGHTS.cov && w.use === START_WEIGHTS.use && w.few === START_WEIGHTS.few) startDev = m;
    if (!best || m.mrr > best.m.mrr + 1e-12) best = { w, m };
    yield* tick(devQueries.length);
  }
  const tuned = best.w;

  /* ---- 3. tests A / B / C on TEST sample, method C with tuned weights ---- */
  const results = { tests: {}, breakdownSize: {}, breakdownRegion: {}, ablation: [], failures: null };
  const recA = [];                                                  // per-query records of test A (for breakdowns)
  for (const kind of ["A", "B", "C"]) {
    const perDraw = [];
    for (const seed of EVAL_SEEDS) {
      const r = mulberry32(seed), ranks = [];
      for (const ri of testSample) {
        const q = makeQuery(ri, kind, r);
        const rank = E.rankOf(q, ri, "C", tuned, OPT);
        ranks.push(rank);
        if (kind === "A") recA.push({ ri, rank, seed, qsize: q.length });
      }
      perDraw.push(metrics(ranks));
      yield* tick(testSample.length);
    }
    const agg = {};
    for (const k of ["top1", "top5", "top10", "mrr"]) agg[k] = meanSd(perDraw.map(m => m[k]));
    results.tests[kind] = agg;
  }
  /* ---- 4. breakdowns (pooled over the 5 draws of test A) ---- */
  const pool = rows => { const m = metrics(rows.map(x => x.rank)); m.n = rows.length / draws; return m; };
  for (const [label, lo, hi] of SIZE_BINS)
    results.breakdownSize[label] = pool(recA.filter(x => { const n = E.recipes[x.ri].core.length; return n >= lo && n <= hi; }));
  E.regions.forEach((name, ri) => {
    const rows = recA.filter(x => E.recipes[x.ri].region === ri);
    if (rows.length) results.breakdownRegion[name] = pool(rows);
  });

  /* ---- 5. ablation on Test A, seeds 42-44 ---- */
  const arms = [
    ["A: Jaccard overlap", "A", tuned, OPT], ["B: TF-IDF cosine", "B", tuned, OPT],
    ["C: weighted score, starting weights", "C", START_WEIGHTS, OPT], ["C: weighted score, tuned weights", "C", tuned, OPT],
    ["C without IDF weights (all weights = 1)", "C", tuned, { ...OPT, useIdf: false }],
    ["C without staple removal (salt, water, oil, sugar count)", "C", tuned, { ...OPT, countAssumed: true }],
  ];
  for (const [label, method, w, o] of arms) {
    const ranks = [];
    for (const seed of EVAL_SEEDS.slice(0, 3)) {
      const r = mulberry32(seed);
      for (const ri of testSample) ranks.push(E.rankOf(makeQuery(ri, "A", r), ri, method, w, o));
      yield* tick(testSample.length);
    }
    results.ablation.push({ label, ...metrics(ranks) });
  }

  /* ---- 6. failure analysis: Test A, seed 42, method C tuned ---- */
  // Rebuild the exact draw-42 queries (same random stream order as in the loop above).
  const rr = mulberry32(42), rows42 = [];
  for (const ri of testSample) {
    const q = makeQuery(ri, "A", rr), rank = E.rankOf(q, ri, "C", tuned, OPT);
    if (rank > 1) {
      const top = E.topIds(q, "C", tuned, OPT, 1)[0];
      const dup = jac(E.recipes[top].core, E.recipes[ri].core) >= 0.8;   // same dish, different title
      rows42.push({ ri, rank, qsize: q.length, top, dup });
    }
  }
  rows42.sort((a, b) => b.rank - a.rank);
  results.failures = {
    misses: rows42.length, nearDup: rows42.filter(x => x.dup).length, n: testSample.length,
    worst: rows42.slice(0, 20).map(x => ({
      name: E.recipes[x.ri].name, rank: x.rank, qsize: x.qsize, coreSize: E.recipes[x.ri].core.length,
      winner: E.recipes[x.top].name, dup: x.dup }))
  };
  yield* tick(testSample.length);

  results.config = { eligible, devN: dev.length, testN: test.length, devSample: devSample.length, testSample: testSample.length,
                     draws, seeds: EVAL_SEEDS, tuned, tunedDev: best.m, startDev, startWeights: { ...START_WEIGHTS }, grid: gridCombos.length };
  yield { done: total, total, phase: "finished", results };
  return results;
}
