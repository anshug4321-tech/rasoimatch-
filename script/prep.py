"""
RasoiMatch - Phase A: data preparation.

Reads the raw CSV (read-only) and writes:
  build/data.json            compact data that gets embedded into the HTML
  build/merge_review.csv     every merge that was APPLIED (before, after, recipe count)
  build/fuzzy_suggestions.csv  merge ideas from fuzzy matching - NEVER applied, for human review
  build/keywords_review.txt  diet / jain / vegan keyword lists, for you to review

Run:  python3 -I scripts/prep.py data/Cleaned_Indian_Food_Dataset.csv build
Seed 42 is not needed here because nothing in this script is random.
"""
import csv, json, math, re, sys, unicodedata, difflib, collections, os

RAW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# --------------------------------------------------------------------------
# 1. Text cleaning helpers
# --------------------------------------------------------------------------
def clean_text(s):
    """Lowercase, drop hidden characters and accents, collapse spaces."""
    s = s.replace("﻿", "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()

NOISE_WORDS = {"pressure", "such", "approximately", "approx", "optional", "preference", "based", "ed"}
BRACKET_RE = re.compile(r"\(([^()]*)\)")

def parse_item(raw):
    """Split one raw ingredient string into (base_name, [bracket_texts])."""
    # cut junk that follows a dash / quote (quantities leaked into the name)
    s = re.split(r"[–—”“’\"]| - | plus ", raw.replace("﻿", ""))[0]
    s = clean_text(s)
    brackets = []
    while True:  # repeat so nested / multiple brackets are all handled
        found = BRACKET_RE.findall(s)
        if not found:
            break
        brackets += found
        s = BRACKET_RE.sub(" ", s)
    s = s.replace("(", " ").replace(")", " ")
    words = [w for w in re.split(r"[^a-z']+", s) if w and w not in NOISE_WORDS]
    if len(words) > 4:   # explanatory text leaked into the name: keep the longest known prefix, else 3 words
        known = [" ".join(words[:n]) for n in (4, 3, 2, 1) if " ".join(words[:n]) in VARIANT2CANON]
        words = (known[0] if known else " ".join(words[:3])).split()
    base = " ".join(words)
    clean_brackets = []
    for b in brackets:
        bw = [w for w in re.split(r"[^a-z]+", b) if w and w not in NOISE_WORDS]
        if bw and len(bw) <= 3 and bw[0] not in {"or", "for", "if", "and", "plus", "approximately", "optional"}:
            clean_brackets.append(" ".join(bw))
    return base, clean_brackets

# --------------------------------------------------------------------------
# 2. Hand-written canonical groups  (canonical name -> variants seen in the data)
#    These are the ONLY merges beyond plural handling. Easy to review.
# --------------------------------------------------------------------------
GROUPS_TXT = """
onion: onion, onions, red onion, big onion, white onion, yellow onion, medium onion
garlic: garlic, cloves garlic, garlic cloves, garlic clove, cloves of garlic, garlic pods, cloves garlic cloves
ginger: ginger, fresh ginger, ginger root
green chilli: green chilli, green chillies, green chili, green chilies, green chilli pepper, hot green chilli
dry red chilli: dry red chilli, dry red chillies, red chilli, red chillies, dried red chilli, whole red chilli, dry red chili
red chilli powder: red chilli powder, red chili powder, chilli powder, chili powder, lal mirch powder
kashmiri red chilli powder: kashmiri red chilli powder, kashmiri chilli powder, kashmiri mirch powder
turmeric powder: turmeric powder, turmeric, haldi, haldi powder, ground turmeric
cumin seeds: cumin seeds, cumin seed, cumin, jeera, whole cumin
cumin powder: cumin powder, jeera powder, ground cumin, roasted cumin powder
coriander powder: coriander powder, dhania powder, ground coriander, dhaniya powder
coriander seeds: coriander seeds, coriander seed, dhania seeds, sabut dhania
coriander leaves: coriander leaves, coriander, cilantro, fresh coriander, coriander leaf, cilantro leaves, hara dhania
curry leaves: curry leaves, curry leaf, kadi patta, kadhi patta
mustard seeds: mustard seeds, mustard seed, rai, black mustard seeds
cooking oil: sunflower oil, oil, vegetable oil, refined oil, cooking oil, refined sunflower oil, canola oil, rice bran oil, refined vegetable oil
olive oil: olive oil, virgin olive oil, extra virgin olive oil
sugar: sugar, white sugar, granulated sugar, caster sugar, castor sugar, cheeni
salt: salt, table salt, sea salt, namak, iodised salt
water: water, warm water, hot water, cold water, ice water, lukewarm water, luke warm water, boiling water, pani
ghee: ghee, clarified butter, desi ghee
butter: butter, unsalted butter, salted butter, white butter, makhan
curd: curd, yogurt, yoghurt, dahi, plain yogurt, plain curd, thick curd, whisked curd, natural yogurt
milk: milk, full fat milk, whole milk, doodh, toned milk, low fat milk, full cream milk
wheat flour: wheat flour, whole wheat flour, atta, wheat atta, whole wheat atta, chapati atta
all purpose flour: all purpose flour, maida, refined flour, plain flour, all-purpose flour
gram flour: gram flour, besan, chickpea flour, besan flour
corn flour: corn flour, cornflour, corn starch, cornstarch
sooji: sooji, semolina, rava, rawa, suji, bombay rava
rice: rice, cooked rice, steamed rice, boiled rice, basmati rice, chawal, cooked basmati rice, long grain rice
potato: potato, potatoes, aloo, boiled potato, boiled potatoes, baby potatoes
tomato: tomato, tomatoes, tamatar, ripe tomato, ripe tomatoes
green peas: green peas, peas, matar, frozen peas, fresh green peas, frozen green peas
spinach: spinach, spinach leaves, palak, palak leaves, fresh spinach
fenugreek leaves: methi leaves, fresh methi leaves, methi, fenugreek leaves, fresh fenugreek leaves
fenugreek seeds: methi seeds, methi dana, fenugreek seeds, fenugreek seed
cauliflower: cauliflower, gobi, gobhi, phool gobi, cauliflower florets
cabbage: cabbage, patta gobi, shredded cabbage
okra: okra, bhindi, lady finger, ladies finger, lady's finger
brinjal: brinjal, eggplant, aubergine, baingan, baigan, purple brinjal
carrot: carrot, carrots, gajar
lemon: lemon, lemon juice, nimbu, lime, lime juice, lemon wedges
asafoetida: asafoetida, hing, heeng, asafetida
black pepper: black pepper, pepper, black pepper powder, peppercorns, black peppercorns, kali mirch, freshly ground black pepper, crushed black pepper, whole black peppercorns, ground black pepper, crushed pepper
cinnamon stick: cinnamon stick, cinnamon sticks, dalchini, cinnamon, cinnamon bark
cloves: cloves, clove, laung, whole cloves
cardamom: cardamom pods, cardamom pod, green cardamom, elaichi, cardamom, cardamom podsseeds, cardamom seeds, cardamom pods seeds
fennel seeds: fennel seeds, fennel seed, saunf, fennel, sauf
bay leaf: bay leaf, bay leaves, tej patta, tejpatta
mint leaves: mint leaves, mint, pudina, fresh mint, mint leaf, fresh mint leaves
bottle gourd: bottle gourd, lauki, doodhi, ghia, dudhi
bitter gourd: bitter gourd, karela
pumpkin: pumpkin, red pumpkin, kaddu, yellow pumpkin
coconut: coconut, fresh coconut, grated coconut, nariyal, fresh grated coconut
peanuts: peanuts, groundnuts, moongfali, roasted peanuts, peanut
cashew nuts: cashew nuts, cashews, kaju, cashew, cashew nut
almonds: almonds, badam, almond
raisins: raisins, kishmish, sultanas
jaggery: jaggery, gur, powdered jaggery, grated jaggery
tamarind: tamarind, imli, tamarind pulp
paneer: paneer, cottage cheese, indian cottage cheese
toor dal: toor dal, arhar dal, tur dal, pigeon pea, toovar dal, tuvar dal
urad dal: urad dal, white urad dal, split urad dal, urad dhuli, skinned urad dal
moong dal: moong dal, yellow moong dal, split moong dal, moong dal split, mung dal
masoor dal: masoor dal, red lentils, red masoor dal, split red lentils
chickpeas: chickpeas, kabuli chana, chole, chana, boiled chickpeas, white chickpeas
kidney beans: kidney beans, rajma, red kidney beans
spring onion: spring onion, spring onions, scallion, scallions, spring onion greens, spring onion whites
green bell pepper: green bell pepper, capsicum, shimla mirch, green capsicum
garam masala: garam masala powder, garam masala
mango powder: amchur, amchoor, dry mango powder, mango powder
carom seeds: ajwain, carom seeds, ajwain seeds
nigella seeds: kalonji, nigella seeds, black onion seeds
poppy seeds: poppy seeds, khus khus, khus khus seeds, posto
egg: eggs, egg, whole eggs, whole egg, anda
heavy whipping cream: heavy whipping cream, cream, fresh cream, malai, heavy cream, whipping cream
banana: banana, bananas, kela, ripe banana, raw banana
beetroot: beetroot, chukandar, beet
radish: radish, mooli, white radish, daikon
cucumber: cucumber, kheera, cucumbers
flattened rice: poha, flattened rice, thick poha, thin poha, beaten rice
sesame seeds: sesame seeds, til, white sesame seeds, sesame seed
vinegar: vinegar, white vinegar
"""

# Hindi / alternative names that point to an existing canonical name.
HINDI_TXT = """
jeera: cumin seeds
aloo: potato
dhania: coriander leaves
dhaniya: coriander leaves
haldi: turmeric powder
hing: asafoetida
besan: gram flour
atta: wheat flour
maida: all purpose flour
dahi: curd
pyaz: onion
pyaaz: onion
tamatar: tomato
adrak: ginger
lehsun: garlic
lahsun: garlic
palak: spinach
methi: fenugreek leaves
gobi: cauliflower
gobhi: cauliflower
bhindi: okra
baingan: brinjal
matar: green peas
gajar: carrot
nimbu: lemon
chawal: rice
doodh: milk
namak: salt
elaichi: cardamom
laung: cloves
dalchini: cinnamon stick
saunf: fennel seeds
pudina: mint leaves
lauki: bottle gourd
karela: bitter gourd
kaddu: pumpkin
mirch: green chilli
hari mirch: green chilli
lal mirch: dry red chilli
kali mirch: black pepper
tej patta: bay leaf
kadi patta: curry leaves
rai: mustard seeds
sarson: mustard seeds
kaju: cashew nuts
badam: almonds
kishmish: raisins
gur: jaggery
imli: tamarind
nariyal: coconut
makhan: butter
malai: heavy whipping cream
chana: chickpeas
chole: chickpeas
rajma: kidney beans
arhar: toor dal
toor: toor dal
urad: urad dal
moong: moong dal
masoor: masoor dal
rava: sooji
suji: sooji
poha: flattened rice
shimla mirch: green bell pepper
mooli: radish
chukandar: beetroot
kheera: cucumber
cheeni: sugar
shakkar: sugar
anda: egg
tel: cooking oil
pani: water
kela: banana
til: sesame seeds
moongfali: peanuts
khus khus: poppy seeds
ajwain: carom seeds
kalonji: nigella seeds
amchoor: mango powder
sooji: sooji
"""

# --------------------------------------------------------------------------
# 3. Staples (see section 5 trap 5)
# --------------------------------------------------------------------------
ASSUMED_STAPLES = ["salt", "water", "cooking oil", "olive oil", "sugar"]        # always assumed
MASALA_STAPLES = ["turmeric powder", "red chilli powder", "kashmiri red chilli powder",
                  "coriander powder", "cumin powder", "garam masala"]           # user can switch on/off

# --------------------------------------------------------------------------
# 4. Diet keywords (whole-word match on the cleaned ingredient text)
# --------------------------------------------------------------------------
NONVEG_WORDS = set("""chicken mutton lamb goat fish prawn prawns shrimp shrimps crab beef pork bacon ham sausage sausages
salami turkey duck tuna salmon anchovy anchovies squid lobster oyster oysters mussels clam clams keema meat
pomfret rohu basa tilapia sardine sardines octopus pepperoni gelatin gelatine lard cod prosciutto""".split())
EGG_WORDS = {"egg", "eggs", "yolk", "yolks"}
# dairy / honey -> not vegan. Plant "milks" and "butters" are removed first (see PLANT_PHRASES).
DAIRY_WORDS = set("""milk curd yogurt yoghurt dahi paneer cheese butter ghee cream malai khoya mawa whey honey buttermilk
mozzarella parmesan cheddar ricotta chaas khowa condensed""".split())
PLANT_PHRASES = ["coconut milk", "coconut cream", "almond milk", "soy milk", "soya milk", "oat milk", "cashew milk",
                 "rice milk", "peanut butter", "almond butter", "cocoa butter", "cream of tartar", "coconut yogurt",
                 "cashew cream", "shea butter", "milk chocolate"]
JAIN_AVOID = set("""onion onions shallot shallots garlic potato potatoes carrot carrots beetroot radish turnip yam
ginger mushroom mushrooms arbi colocasia suran mooli""".split())

def words_of(text):
    return set(re.findall(r"[a-z]+", text))

def diet_of(ingredient_texts):
    """Return 'nonveg' | 'egg' | 'veg' using whole-word matching ('eggplant' is NOT 'egg')."""
    ws = set()
    for t in ingredient_texts:
        ws |= words_of(t)
    if ws & NONVEG_WORDS:
        return "nonveg"
    if ws & EGG_WORDS:
        return "egg"
    return "veg"

def is_vegan(ingredient_texts, diet):
    if diet != "veg":
        return False
    for t in ingredient_texts:
        for p in PLANT_PHRASES:
            t = t.replace(p, " ")
        if words_of(t) & DAIRY_WORDS:
            return False
    return True

def is_jain(ingredient_texts, diet):
    if diet != "veg":
        return False
    for t in ingredient_texts:
        if "dry ginger" in t or "sonth" in t:       # dry ginger powder is usually allowed
            t = t.replace("dry ginger", " ").replace("sonth", " ")
        if words_of(t) & JAIN_AVOID:
            return False
    return True

# --------------------------------------------------------------------------
# 5. Region map: all 82 labels -> 7 groups
# --------------------------------------------------------------------------
REGIONS = ["North Indian", "South Indian", "East Indian", "West Indian", "Pan-Indian", "International", "Meal type / unknown"]
REGION_MAP = {
 "North Indian": ["North Indian Recipes", "Punjabi", "Kashmiri", "Awadhi", "Mughlai", "Himachal", "Uttar Pradesh",
                  "Lucknowi", "Uttarakhand-North Kumaon", "Haryana"],
 "South Indian": ["South Indian Recipes", "Karnataka", "Tamil Nadu", "Kerala Recipes", "Andhra", "Chettinad",
                  "Mangalorean", "Udupi", "Coorg", "North Karnataka", "Coastal Karnataka", "South Karnataka",
                  "Malabar", "Kongunadu", "Hyderabadi"],
 "East Indian": ["Bengali", "Bengali Recipes", "Assamese", "Oriya Recipes", "North East India Recipes", "Nagaland", "Bihari", "Jharkhand"],
 "West Indian": ["Maharashtrian", "Maharashtrian Recipes", "Gujarati Recipes", "Rajasthani", "Goan Recipes", "Konkan", "Malvani", "Parsi Recipes", "Sindhi"],
 "Pan-Indian": ["Indian", "Indo Chinese"],
 "International": ["Continental", "Italian Recipes", "Fusion", "Mexican", "Asian", "Thai", "Chinese", "French",
                   "Middle Eastern", "Mediterranean", "European", "African", "Greek", "Sri Lankan", "Japanese",
                   "Vietnamese", "Pakistani", "Indonesian", "Cantonese", "Nepalese", "Sichuan", "American", "British",
                   "Arab", "Caribbean", "Malaysian", "Korean", "Hunan", "Afghan", "Shandong", "Jewish", "Burmese"],
 "Meal type / unknown": ["World Breakfast", "Appetizer", "Snack", "Side Dish", "Dessert", "Dinner", "Brunch", "Lunch"],
}
LABEL2REGION = {clean_text(l): r for r, ls in REGION_MAP.items() for l in ls}

# --------------------------------------------------------------------------
# 6. Substitution hints (~40 safe, common pairs). Notes make NO health/allergy claims.
# --------------------------------------------------------------------------
SUBS = [
 ("curd", "buttermilk or thick coconut milk", "Slightly thinner; use a little less water elsewhere."),
 ("curd", "sour cream", "Similar tang; works in gravies and marinades."),
 ("heavy whipping cream", "cashew paste", "Soak cashews, grind smooth with water."),
 ("heavy whipping cream", "milk plus a little butter", "Lighter result."),
 ("all purpose flour", "wheat flour", "Works for many breads and snacks; texture will be denser."),
 ("wheat flour", "all purpose flour", "Softer and paler result."),
 ("butter", "ghee", "Use slightly less; stronger flavour."),
 ("butter", "cooking oil", "Fine for sauteing, not for baking."),
 ("ghee", "butter", "Melt it; it browns faster than ghee."),
 ("lemon", "tamarind paste or vinegar", "Use a smaller amount; both are sharper."),
 ("tamarind", "lemon juice", "Add near the end; less deep colour."),
 ("coriander leaves", "mint leaves or curry leaves", "Different flavour but keeps the fresh green note."),
 ("mint leaves", "coriander leaves", "Fresh and green but less cooling."),
 ("curry leaves", "bay leaf", "Not the same taste; use only a small amount."),
 ("green chilli", "red chilli powder or dry red chilli", "Adjust heat to taste."),
 ("dry red chilli", "red chilli powder", "About a pinch per chilli."),
 ("red chilli powder", "dry red chilli or green chilli", "Heat level varies; add gradually."),
 ("garlic", "ginger garlic paste or garlic powder", "Garlic powder is milder; use about a pinch."),
 ("ginger", "dry ginger powder", "Use about a quarter of the amount."),
 ("onion", "spring onion", "Milder and a little sweet."),
 ("tomato", "tomato puree or tomato ketchup", "Ketchup adds sugar; reduce other sweetness."),
 ("coconut milk", "cashew paste or thin cream", "Result is less coconutty."),
 ("coconut", "desiccated coconut", "Soak briefly in warm water first."),
 ("jaggery", "sugar or brown sugar", "Slightly less flavour depth."),
 ("sugar", "jaggery or honey", "Taste and adjust."),
 ("cornflour" if False else "corn flour", "rice flour or arrowroot", "Both thicken similarly."),
 ("gram flour", "chickpea flour or rice flour", "Rice flour gives a crisper but less rich result."),
 ("sooji", "rice flour or oats", "Texture changes; adjust water."),
 ("paneer", "tofu", "Press and pan-fry first so it holds its shape."),
 ("egg", "mashed banana or yogurt", "For baking only; texture is softer."),
 ("milk", "water plus milk powder, or coconut milk", "For gravies and tea; flavour is lighter."),
 ("cashew nuts", "almonds or melon seeds", "Soak and grind for gravies."),
 ("almonds", "cashew nuts or peanuts", "Similar crunch or paste body."),
 ("garam masala", "cinnamon, cloves and cardamom ground together", "A small pinch of each."),
 ("kasuri methi" , "fenugreek leaves or a pinch of fenugreek seeds", "Use sparingly; can taste bitter."),
 ("cumin seeds", "cumin powder", "Add with the other powders, about half the amount."),
 ("mustard seeds", "cumin seeds", "Different flavour; keep the same tempering step."),
 ("asafoetida", "garlic or onion", "Skip if the recipe is meant to be Jain."),
 ("spinach", "fenugreek leaves or kale", "Cooking time may differ."),
 ("cooking oil", "ghee or butter", "Fine for most pan cooking."),
 ("basil leaves", "mint leaves or oregano", "Different taste; use less."),
 ("vinegar", "lemon juice", "Use slightly more."),
 ("baking powder", "baking soda plus lemon juice or curd", "Use a pinch of soda with a spoon of acid."),
 ("black pepper", "green chilli or red chilli powder", "For heat only."),
 ("cheese", "paneer", "Grated or crumbled; less melt."),
]

# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
rows = list(csv.DictReader(open(RAW, encoding="utf-8-sig", newline="")))
N = len(rows)
print("rows:", N)

# group and hindi tables -------------------------------------------------------
VARIANT2CANON = {}
for line in GROUPS_TXT.strip().splitlines():
    canon, variants = line.split(":", 1)
    canon = clean_text(canon)
    VARIANT2CANON[canon] = canon
    for v in variants.split(","):
        v = clean_text(v)
        if v in VARIANT2CANON and VARIANT2CANON[v] != canon:
            print("WARNING: variant in two groups:", v, VARIANT2CANON[v], canon)
        VARIANT2CANON[v] = canon
HINDI = {}
for line in HINDI_TXT.strip().splitlines():
    a, c = line.split(":", 1)
    HINDI[clean_text(a)] = clean_text(c)

# pass 1: parse every raw ingredient ---------------------------------------------
parsed_rows = []                      # per recipe: list of (raw, base, brackets)
raw_vocab, bracket_free_vocab = collections.Counter(), collections.Counter()
for r in rows:
    items = []
    for raw in r["Cleaned-Ingredients"].split(","):
        if not raw.strip():
            continue
        base, br = parse_item(raw)
        if not base:
            continue
        items.append((clean_text(raw), base, br))
    parsed_rows.append(items)
    for rawc, base, br in items:
        pass
for items in parsed_rows:
    for rawc in {i[0] for i in items}:
        raw_vocab[rawc] += 1
    for base in {i[1] for i in items}:
        bracket_free_vocab[base] += 1
print("vocabulary BEFORE cleaning: raw strings =", len(raw_vocab), "| after removing brackets =", len(bracket_free_vocab))

observed = set(bracket_free_vocab)

def singular(w):
    """Plural -> singular, only if the singular form is itself seen in the data (safe)."""
    if w in VARIANT2CANON or len(w) < 4:
        return w
    cands = []
    if w.endswith("ies"): cands.append(w[:-3] + "y"); cands.append(w[:-3] + "i")   # chillies -> chilli
    if w.endswith("oes"): cands.append(w[:-2])
    if w.endswith("es"): cands.append(w[:-2])
    if w.endswith("s") and not w.endswith(("ss", "us", "is")): cands.append(w[:-1])
    for c in cands:
        if c in observed and c != w:
            return c
    return w

def canonical_of(base, brackets):
    """base name + bracket texts -> canonical name. Order: group table, Hindi bracket, plural."""
    if base in VARIANT2CANON:
        return VARIANT2CANON[base]
    for b in brackets:                        # e.g. "flour (maida)" -> all purpose flour
        if b in HINDI:
            return HINDI[b]
    s = singular(base)
    return VARIANT2CANON.get(s, s)

# pass 2: canonical names, bracket aliases, merge review ---------------------
canon_rows = []
merge_log = collections.Counter()        # (before_base, after) -> recipes
bracket_votes = collections.defaultdict(collections.Counter)
for items in parsed_rows:
    ids = []
    for rawc, base, br in items:
        c = canonical_of(base, br)
        ids.append((c, base, br))
        if base != c:
            merge_log[(base, c)] += 1
        for b in br:
            bracket_votes[b][c] += 1
    canon_rows.append(ids)

# add Hindi targets that may not exist yet
for a, c in HINDI.items():
    VARIANT2CANON.setdefault(a, c)

vocab_names = sorted({c for ids in canon_rows for c, _, _ in ids})
vid = {n: i for i, n in enumerate(vocab_names)}
for a, c in HINDI.items():
    if c not in vid:
        print("WARNING: Hindi alias target not in vocabulary:", a, "->", c)
print("vocabulary AFTER cleaning (canonical names) =", len(vocab_names))

# alias table: alias string -> canonical id
aliases = {}
for v, c in VARIANT2CANON.items():
    if c in vid: aliases[v] = vid[c]
for n in vocab_names: aliases[n] = vid[n]
for ids in canon_rows:                                 # every raw base form seen in the data
    for c, base, _ in ids: aliases.setdefault(base, vid[c])
for a, c in HINDI.items():
    if c in vid: aliases[a] = vid[c]                   # hand-written Hindi list always wins
for b, votes in bracket_votes.items():                 # bracket aliases: majority vote, never override
    if b not in aliases and len(b) > 2:
        aliases[b] = vid[votes.most_common(1)[0][0]]

# recipe-level processing ----------------------------------------------------------
assumed_ids = {vid[n] for n in ASSUMED_STAPLES if n in vid}
masala_ids = {vid[n] for n in MASALA_STAPLES if n in vid}
for n in ASSUMED_STAPLES + MASALA_STAPLES:
    if n not in vid: print("WARNING: staple not in vocab:", n)

aliases_by_id = collections.defaultdict(set)
for a, i in aliases.items(): aliases_by_id[i].add(a)

def split_lines(txt):
    """Split TranslatedIngredients at top-level commas; glue 'finely chopped' style fragments back."""
    out, depth, cur = [], 0, ""
    for ch in txt.replace("﻿", ""):
        if ch == "(": depth += 1
        if ch == ")": depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    lines = []
    for p in out:
        if not p: continue
        if lines and " - " in lines[-1] and p[:1].islower():
            lines[-1] += ", " + p
        else:
            lines.append(p)
    return lines

def line_id(line, id_set):
    """Best-effort: which ingredient id does this display line talk about? (longest alias wins)"""
    head = clean_text(re.split(r" - ", line)[0])
    best, best_len = -1, 0
    for i in id_set:
        for a in aliases_by_id[i]:
            if len(a) > best_len and re.search(r"\b" + re.escape(a) + r"(s|es)?\b", head):
                best, best_len = i, len(a)
    return best

recipes, region_counter, diet_counter = [], collections.Counter(), collections.Counter()
unmapped = set()
df = collections.Counter()
core_sets = []
DIET_CODE = {"veg": 0, "egg": 1, "nonveg": 2}
for idx, (r, ids) in enumerate(zip(rows, canon_rows)):
    all_ids = []
    for c, _, _ in ids:
        if vid[c] not in all_ids: all_ids.append(vid[c])
    core = [i for i in all_ids if i not in assumed_ids]
    texts = [clean_text(r["Cleaned-Ingredients"].split(",")[k]) for k in range(len(r["Cleaned-Ingredients"].split(",")))]
    texts += [vocab_names[i] for i in all_ids]
    diet = diet_of(texts)
    label = clean_text(r["Cuisine"])
    region = LABEL2REGION.get(label)
    if region is None:
        unmapped.add(r["Cuisine"]); region = "Meal type / unknown"
    t = int(float(r["TotalTimeInMins"]))
    time_min = t if t > 0 else None                    # 0 means unknown
    lines = split_lines(r["TranslatedIngredients"])
    line_pairs = [[l, line_id(l, set(all_ids))] for l in lines]
    name = re.sub(r"\s+Recipe$", "", r["TranslatedRecipeName"].replace("﻿", "").strip())
    recipes.append([
        idx, name,
        r["URL"].replace("https://www.archanaskitchen.com/", ""),
        r["image-url"].replace("https://www.archanaskitchen.com/images/archanaskitchen/", ""),
        time_min, 1 if (t > 240) else 0, REGIONS.index(region), DIET_CODE[diet],
        1 if is_jain(texts, diet) else 0, 1 if is_vegan(texts, diet) else 0,
        core, line_pairs, [i for i in all_ids if i in assumed_ids]])
    core_sets.append(core)
    region_counter[region] += 1; diet_counter[diet] += 1
    for i in set(core): df[i] += 1
print("unmapped cuisine labels:", sorted(unmapped) or "none")

idf = [round(math.log((N + 1) / (df.get(i, 0) + 1)) + 1, 3) for i in range(len(vocab_names))]

meta = {"rows": N, "vocab_raw": len(raw_vocab), "vocab_no_brackets": len(bracket_free_vocab),
        "vocab_final": len(vocab_names), "source": "archanaskitchen.com",
        "url_prefix": "https://www.archanaskitchen.com/",
        "img_prefix": "https://www.archanaskitchen.com/images/archanaskitchen/"}
subs_out, bad = [], []
for m, t, note in SUBS:
    if m in vid: subs_out.append([vid[m], t, note])
    else: bad.append(m)
if bad: print("WARNING: substitution keys not in vocab:", bad)

data = {"meta": meta, "regions": REGIONS, "vocab": vocab_names, "aliases": aliases, "idf": idf,
        "staples": {"assumed": sorted(assumed_ids), "masala": sorted(masala_ids)},
        "subs": subs_out, "hindi": {a: vid[c] for a, c in HINDI.items() if c in vid}, "recipes": recipes}
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
open(os.path.join(OUT, "data.json"), "w", encoding="utf-8").write(blob)
print("data.json size: %.2f MB" % (len(blob.encode()) / 1e6))

# review files ---------------------------------------------------------------------
with open(os.path.join(OUT, "merge_review.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["before", "after", "recipe_count"])
    for (b, a), n in sorted(merge_log.items(), key=lambda x: -x[1]): w.writerow([b, a, n])
common = [n for n in vocab_names if df[vid[n]] >= 5]
rare = [n for n in vocab_names if df[vid[n]] <= 2]
byletter = collections.defaultdict(list)
for n in common: byletter[n[0]].append(n)
sugg = []
for n in rare:
    for m in difflib.get_close_matches(n, [x for x in byletter[n[0]] if abs(len(x) - len(n)) <= 4], n=1, cutoff=0.88):
        sugg.append((n, m, df[vid[n]], df[vid[m]]))
with open(os.path.join(OUT, "fuzzy_suggestions.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["rare_name", "maybe_same_as", "rare_count", "common_count"])
    w.writerows(sugg)
print("fuzzy suggestions written (NOT applied):", len(sugg))
with open(os.path.join(OUT, "keywords_review.txt"), "w") as f:
    for title, s in [("NON-VEG words", NONVEG_WORDS), ("EGG words", EGG_WORDS), ("DAIRY words (not vegan)", DAIRY_WORDS),
                     ("PLANT phrases ignored for dairy", set(PLANT_PHRASES)), ("JAIN-avoid words", JAIN_AVOID)]:
        f.write(title + ":\n  " + ", ".join(sorted(s)) + "\n\n")
    f.write("ALWAYS-ASSUMED staples: " + ", ".join(ASSUMED_STAPLES) + "\nCOMMON MASALAS: " + ", ".join(MASALA_STAPLES) + "\n")

# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
print("\n== TESTS ==")
assert vocab_names[aliases["jeera"]] == "cumin seeds"; print("PASS jeera -> cumin seeds")
assert "﻿" not in blob; print("PASS no U+FEFF in data.json")
assert diet_of(["eggplant", "brinjal"]) == "veg" and diet_of(["egg", "salt"]) == "egg"; print("PASS eggplant is not egg")
assert all(len(x[10]) > 0 and len(x[11]) > 0 for x in recipes), "empty ingredient list"; print("PASS no recipe has an empty ingredient list")
assert "TranslatedInstructions" not in blob and rows[0]["TranslatedInstructions"][:60] not in blob; print("PASS instructions are not in data.json")
assert vocab_names[aliases["aloo"]] == "potato" and vocab_names[aliases["pyaz"]] == "onion"; print("PASS aloo, pyaz")
for h in "jeera aloo dhania haldi hing besan atta maida dahi pyaz tamatar adrak lehsun palak methi gobi bhindi baingan matar gajar nimbu chawal doodh namak elaichi laung dalchini saunf pudina lauki karela kaddu".split():
    assert h in aliases, h
print("PASS all 32 required Hindi names present")

# --------------------------------------------------------------------------
# Checkpoint
# --------------------------------------------------------------------------
print("\n== CHECKPOINT ==")
print("top 30 ingredients (recipes):", [(vocab_names[i], c) for i, c in df.most_common(30)])
print("diet counts:", dict(diet_counter))
print("region counts:", dict(region_counter))
print("jain:", sum(x[8] for x in recipes), "vegan:", sum(x[9] for x in recipes),
      "unknown time:", sum(1 for x in recipes if x[4] is None), "long prep:", sum(x[5] for x in recipes))
print("recipes with empty core after staple removal:", sum(1 for x in recipes if not x[10]))
core_sizes = sorted(len(x[10]) for x in recipes)
print("core size min/median/max:", core_sizes[0], core_sizes[len(core_sizes)//2], core_sizes[-1])
print("vocab BEFORE: %d raw -> %d without brackets;  AFTER: %d canonical" % (len(raw_vocab), len(bracket_free_vocab), len(vocab_names)))
print("vocab entries in >=5 recipes:", len(common), "| in exactly 1 recipe:", sum(1 for n in vocab_names if df[vid[n]] == 1))
# sanity: titles that look non-veg / egg but were labelled veg
TITLE_FLAGS = ("chicken", "mutton", "fish", "prawn", "lamb", "egg ")
susp = [(x[1], ) for x in recipes if x[7] == 0 and any(k in (x[1].lower() + " ") for k in TITLE_FLAGS) and "eggless" not in x[1].lower() and "eggplant" not in x[1].lower()]
print("title says meat/egg but labelled veg:", len(susp), susp[:10])
print("longest 12 canonical names:", sorted(vocab_names, key=len)[-12:])
