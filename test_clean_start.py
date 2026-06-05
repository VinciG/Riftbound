import os, json, re, urllib.request
from collections import defaultdict

# === Step 1: Start from nothing ===
json_file = "cartas.json"
if os.path.exists(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        datos_actuales = json.load(f)
else:
    datos_actuales = {"sets": {}, "pull_rates": {}}
print("1. cartas.json loaded/created:", "existing" if os.path.exists(json_file) else "fresh empty")

# === Step 2: Fetch DotGG ===
DOTGG_API_URL = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"
print("\n2. Fetching DotGG API...")
req = urllib.request.Request(DOTGG_API_URL, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})
with urllib.request.urlopen(req, timeout=30) as resp:
    raw = json.loads(resp.read().decode("utf-8"))
api_names, api_rows = raw["names"], raw["data"]
print(f"   {len(api_rows)} cards fetched")

# === Step 3: Auto-discover sets ===
COLOR_PALETTE = ["#4a9eff", "#3ecf8e", "#f4a535", "#e879a0", "#a78bfa", "#f97316", "#06b6d4", "#84cc16"]
DOTGG_SET_NAMES = set()

set_names = set()
abbr_from_id = {}
for row in api_rows:
    card = dict(zip(api_names, row))
    sn = card.get("set_name", "")
    if not sn: continue
    set_names.add(sn)
    aid = card.get("id", "")
    m = re.match(r"^([A-Z]+)", aid)
    if m and sn not in abbr_from_id:
        abbr_from_id[sn] = m.group(1)

DOTGG_SET_NAMES = set_names

for i, sn in enumerate(sorted(set_names)):
    sid = sn.lower().replace(" ", "_")
    if sid not in datos_actuales["sets"]:
        abbr = abbr_from_id.get(sn, sn[:3].upper())
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
        datos_actuales["sets"][sid] = {
            "id": sid, "abbr": abbr, "set_number": i + 1, "color": color,
            "date": "", "cartas_reveladas": 0, "total": 0, "total_base": 0, "total_ovr": 0,
            "imgBase": "", "legend_count": 0, "leyendas": [],
            "productos": [], "champion_decks": [], "ovr_breakdown": [], "mecanicas": []
        }
    else:
        s = datos_actuales["sets"][sid]
        defaults = {"date":"","cartas_reveladas":0,"total":0,"total_base":0,"total_ovr":0,
                    "imgBase":"","legend_count":0,"leyendas":[],"productos":[],
                    "champion_decks":[],"ovr_breakdown":[],"mecanicas":[]}
        for k, v in defaults.items():
            if k not in s: s[k] = v

print(f"\n3. Sets discovered from DotGG: {len(datos_actuales['sets'])}")
for sid, s in sorted(datos_actuales["sets"].items()):
    print(f"   {sid}: abbr={s['abbr']}, color={s['color']}, set_number={s['set_number']}")

# === Step 4: Build maps ===
SET_NAME_MAP = {}
EPIC_SUFFIX = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    SET_NAME_MAP[s_name] = sid
    tb = s_data.get("total_base", 0)
    if tb:
        EPIC_SUFFIX[sid] = str(tb)

for dotgg_name in DOTGG_SET_NAMES:
    sid = dotgg_name.lower().replace(" ", "_")
    SET_NAME_MAP[dotgg_name] = sid

legends_per_set = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    names = []
    for leg in s_data.get("leyendas", []):
        n = leg.get("name") if isinstance(leg, dict) else (leg if isinstance(leg, str) else None)
        if n:
            names.append(n)
    legends_per_set[sid] = names

print(f"\n4. Maps built: {len(SET_NAME_MAP)} name mappings, {len(EPIC_SUFFIX)} suffix mappings")

# === Step 5: Seed totals from DotGG ===
set_data = defaultdict(lambda: {"total": 0, "legends": set(), "ovr": 0, "abbr": None, "ids": set()})
for row in api_rows:
    card = dict(zip(api_names, row))
    sn = card.get("set_name", "")
    sid = SET_NAME_MAP.get(sn)
    if not sid: continue
    set_data[sid]["abbr"] = sid
    aid = card.get("id", "")
    base_id = re.sub(r'(?i)(-p|-a|-star|-promo)$', '', aid)
    set_data[sid]["ids"].add(base_id)
    if card.get("type") == "Legend":
        cn = re.split(r' - |, ', card.get("name", ""), maxsplit=1)[0].strip()
        if cn:
            set_data[sid]["legends"].add(cn)
    if card.get("rarity") == "Showcase":
        set_data[sid]["ovr"] += 1

for sid, d in set_data.items():
    for s_name, s_val in datos_actuales.get("sets", {}).items():
        if s_val.get("id") == sid:
            uid_count = len(d["ids"])
            if s_val.get("total", 0) == 0 and uid_count > 0:
                s_val["total"] = uid_count
                s_val["total_base"] = uid_count - d["ovr"]
                s_val["total_ovr"] = d["ovr"]
                s_val["legend_count"] = len(d["legends"])
                s_val["leyendas"] = [{"name": n, "img": None} for n in sorted(d["legends"])]
            break

print("\n5. Seeded from DotGG:")
for s_name, s_val in sorted(datos_actuales["sets"].items()):
    print(f"   {s_name}: total={s_val['total']}, base={s_val['total_base']}, ovr={s_val['total_ovr']}, legends={s_val['legend_count']}")

# Save seeded cartas.json
with open(json_file, "w", encoding="utf-8") as f:
    json.dump(datos_actuales, f, indent=4, ensure_ascii=False)
print("   cartas.json saved")

# === Step 6: Build final suffix + regenerate everything ===
# (Simulating what update_web.py does after Gemini, or without Gemini)
EPIC_SUFFIX_FINAL = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    tb = s_data.get("total_base", 0)
    if tb:
        EPIC_SUFFIX_FINAL[sid] = str(tb)

SET_NAME_MAP_FINAL = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    SET_NAME_MAP_FINAL[s_name] = s_data.get("id")
for dotgg_name in DOTGG_SET_NAMES:
    sid = dotgg_name.lower().replace(" ", "_")
    SET_NAME_MAP_FINAL[dotgg_name] = sid

legends_per_set.clear()
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    names = []
    for leg in s_data.get("leyendas", []):
        n = leg.get("name") if isinstance(leg, dict) else (leg if isinstance(leg, str) else None)
        if n:
            names.append(n)
    legends_per_set[sid] = names

def make_key(api_id, set_id):
    k = api_id.lower()
    if k.endswith("-star"):
        k = k[:-5] + "*"
    suffix = EPIC_SUFFIX_FINAL.get(set_id)
    if suffix:
        k = f"{k}-{suffix}"
    return k

# cardmarket_prices.json
print("\n6. Generating output files...")
prices = {}
legend_min = {}
for row in api_rows:
    card = dict(zip(api_names, row))
    sn = card.get("set_name", "")
    sid = SET_NAME_MAP_FINAL.get(sn)
    if not sid: continue
    cm = card.get("cmPrice")
    if not cm or cm == 0 or cm == "0" or cm == "0.000000": continue
    cm_f = float(cm)
    if sid not in prices: prices[sid] = {}
    prices[sid][make_key(card.get("id",""), sid)] = f"\u20ac{cm_f:.2f}"
    if card.get("type") == "Legend":
        for cn in legends_per_set.get(sid, []):
            if cn in (card.get("tags") or []):
                if sid not in legend_min: legend_min[sid] = {}
                e = legend_min[sid].get(cn)
                if e is None or cm_f < e: legend_min[sid][cn] = cm_f
for sid, champs in legend_min.items():
    if sid not in prices: prices[sid] = {}
    for cn, mp in champs.items():
        prices[sid][cn] = f"\u20ac{mp:.2f}"
with open("cardmarket_prices.json", "w", encoding="utf-8") as f:
    json.dump(prices, f, indent=4, ensure_ascii=False)
print(f"   cardmarket_prices.json: {sum(len(v) for v in prices.values())} prices")

# id_to_name.json
id_name_map = {}
for row in api_rows:
    card = dict(zip(api_names, row))
    sn = card.get("set_name", "")
    sid = SET_NAME_MAP_FINAL.get(sn)
    if not sid: continue
    cm = card.get("cmPrice")
    if not cm or cm == 0 or cm == "0" or cm == "0.000000": continue
    k = make_key(card.get("id",""), sid)
    if sid not in id_name_map: id_name_map[sid] = {}
    id_name_map[sid][k] = card.get("name", k)
for sid, champs in legend_min.items():
    if sid not in id_name_map: id_name_map[sid] = {}
    for cn in champs:
        id_name_map[sid][cn] = cn
with open("id_to_name.json", "w", encoding="utf-8") as f:
    json.dump(id_name_map, f, indent=4, ensure_ascii=False)
print(f"   id_to_name.json: {sum(len(v) for v in id_name_map.values())} mappings")

# legend_data.json
legend_data_save = {}
legend_data_min = {}
for row in api_rows:
    card = dict(zip(api_names, row))
    if card.get("type") != "Legend": continue
    sn = card.get("set_name", "")
    sid = SET_NAME_MAP_FINAL.get(sn)
    if not sid: continue
    tags = card.get("tags") or []
    champ = None
    for cn in legends_per_set.get(sid, []):
        if cn in tags:
            champ = cn
            break
    if not champ: continue
    if sid not in legend_data_save: legend_data_save[sid] = {}
    if sid not in legend_data_min: legend_data_min[sid] = {}
    cm = card.get("cmPrice")
    cm_f = float(cm) if (cm and cm != 0 and cm != "0" and cm != "0.000000") else None
    prev = legend_data_min[sid].get(champ)
    if champ in legend_data_save[sid] and prev is not None and (cm_f is None or cm_f >= prev):
        continue
    if cm_f is not None:
        legend_data_min[sid][champ] = cm_f
    api_id = card.get("id", "")
    num_m = re.search(r"-(\d+)", api_id)
    number = num_m.group(1) if num_m else ""
    full_name = card.get("name", "")
    title = (full_name.split(" - ", 1)[1] if " - " in full_name else (full_name.split(", ", 1)[1] if ", " in full_name else ""))
    legend_data_save[sid][champ] = {"img": card.get("image") or "", "title": title, "number": number}
with open("legend_data.json", "w", encoding="utf-8") as f:
    json.dump(legend_data_save, f, indent=4, ensure_ascii=False)
print(f"   legend_data.json: {sum(len(v) for v in legend_data_save.values())} entries")

# epic-cards.js
sn_to_code = {}
for sn in DOTGG_SET_NAMES:
    sid = sn.lower().replace(" ", "_")
    abbr = datos_actuales.get("sets", {}).get(sid, {}).get("abbr")
    if abbr:
        sn_to_code[sn] = abbr
result = {}
for row in api_rows:
    card = dict(zip(api_names, row))
    rarity = card.get("rarity", "")
    if rarity not in {"Epic", "Showcase"}: continue
    sn = card.get("set_name", "")
    sc = sn_to_code.get(sn)
    if not sc: continue
    if sc not in result: result[sc] = []
    nm = card.get("name", "")
    aid = card.get("id", "")
    our_id = make_key(aid, SET_NAME_MAP_FINAL.get(sn, ""))
    nm_lower = nm.lower()
    aid_lower = aid.lower()
    num_m = re.search(r"-(\d+)", aid)
    number = int(num_m.group(1)) if num_m else 0
    alt = "alternate art" in nm_lower or (aid_lower.endswith("a") and rarity == "Showcase")
    ovr = "overnumbered" in nm_lower or ("ovr" in nm_lower and "alternate" not in nm_lower)
    sig = "signature" in nm_lower or "signed" in nm_lower
    if rarity == "Showcase" and not alt and not sig: ovr = True
    color_raw = card.get("color") or []
    domain = " / ".join(c.title() for c in color_raw if c) if isinstance(color_raw, list) else (str(color_raw).title() if color_raw else "")
    result[sc].append({
        "name": nm, "number": number, "id": our_id, "rarity": rarity,
        "type": card.get("type", ""), "domain": domain,
        "image": card.get("image", ""), "alt": alt, "ovr": ovr, "signature": sig
    })
for sc in result:
    result[sc].sort(key=lambda c: c["id"])
with open("epic-cards.js", "w", encoding="utf-8") as f:
    f.write("window.EPIC_CARD_DATA = " + json.dumps(result, ensure_ascii=False) + ";")
print(f"   epic-cards.js: {sum(len(v) for v in result.values())} premium cards")

# === Final summary ===
print("\n" + "="*50)
print("CLEAN START TEST COMPLETE")
print("="*50)
for fname in ["cartas.json", "cardmarket_prices.json", "epic-cards.js", "id_to_name.json", "legend_data.json"]:
    sz = os.path.getsize(fname) if os.path.exists(fname) else 0
    print(f"   {fname}: {sz} bytes")
