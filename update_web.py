import os
import json
import time
import re
import urllib.request
import urllib.error
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# ==========================================
# Leer base de datos actual (JSON)
# ==========================================
json_file = "cartas.json"
if os.path.exists(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        datos_actuales = json.load(f)
else:
    datos_actuales = {"sets": {}, "pull_rates": {}}

# ==========================================
# Configuración de Gemini
# ==========================================
client = None
gemini_available = False
try:
    client = genai.Client()
    gemini_available = True
except (ValueError, Exception):
    print("⚠️ Gemini no configurado (sin API key) — se usará solo DotGG.")

# Leer precios actuales de cardmarket_prices.json (si existe)
cardmarket_prices_file = "cardmarket_prices.json"

# ==========================================
# Obtener todos los datos desde DotGG API
# ==========================================
DOTGG_API_URL = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"

def fetch_dotgg_all():
    req = urllib.request.Request(DOTGG_API_URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return raw["names"], raw["data"]

api_names, api_rows = [], []
try:
    api_names, api_rows = fetch_dotgg_all()
    print(f"  → {len(api_rows)} cartas desde DotGG API")
except Exception as e:
    print(f"  ⚠️ Error fetching DotGG: {e}")

# ==========================================
# Auto-descubrir colecciones desde DotGG
# ==========================================
COLOR_PALETTE = ["#4a9eff", "#3ecf8e", "#f4a535", "#e879a0", "#a78bfa", "#f97316", "#06b6d4", "#84cc16"]

DOTGG_SET_NAMES = set()  # Original DotGG set names for mapping

# Merge known subset names into their parent sets (avoids duplicate entries)
# Maps internal id forms to parent internal id
DOTGG_SET_MERGE = {
    "proving_grounds": "origins",
    "origins_proving_grounds": "origins",
    "arcane_box_set": "origins",
}

def discover_sets(rows, names):
    """Detect new sets from DotGG and add them to datos_actuales."""
    global DOTGG_SET_NAMES
    DOTGG_SET_NAMES.clear()
    set_names = set()
    abbr_from_id = {}
    for row in rows:
        card = dict(zip(names, row))
        sn = card.get("set_name", "")
        if not sn: continue
        set_names.add(sn)
        aid = card.get("id", "")
        m = re.match(r"^([A-Z]+)", aid)
        if m and sn not in abbr_from_id:
            abbr_from_id[sn] = m.group(1)

    DOTGG_SET_NAMES = set_names.copy()  # Save ALL original DotGG names

    for i, sn in enumerate(sorted(set_names)):
        sid = sn.lower().replace(" ", "_")
        if sid in DOTGG_SET_MERGE:
            continue  # skip merged subsets — their cards go to the parent set
        if sid not in datos_actuales["sets"]:
            abbr = abbr_from_id.get(sn, sn[:3].upper())
            color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            datos_actuales["sets"][sid] = {
                "id": sid, "abbr": abbr, "set_number": i + 1, "color": color,
                "date": "", "cartas_reveladas": 0, "total": 0, "total_base": 0, "total_ovr": 0,
                "imgBase": "", "legend_count": 0, "leyendas": [],
                "productos": [], "champion_decks": [], "ovr_breakdown": [], "mecanicas": [],
                "released": True
            }
        else:
            s = datos_actuales["sets"][sid]
            s["released"] = True
            defaults = {"date":"","cartas_reveladas":0,"total":0,"total_base":0,"total_ovr":0,
                        "imgBase":"","legend_count":0,"leyendas":[],"productos":[],
                        "champion_decks":[],"ovr_breakdown":[],"mecanicas":[]}
            for k, v in defaults.items():
                if k not in s:
                    s[k] = v

if api_rows:
    discover_sets(api_rows, api_names)

# Ensure ALL existing sets have defaults (including those not in DotGG)
for i, (s_name, s_data) in enumerate(datos_actuales.get("sets", {}).items()):
    sid = s_data.get("id")
    defaults = {"color": COLOR_PALETTE[i % len(COLOR_PALETTE)],
                "date":"","cartas_reveladas":0,"total":0,"total_base":0,"total_ovr":0,
                "imgBase":"","legend_count":0,"leyendas":[],"productos":[],
                "champion_decks":[],"ovr_breakdown":[],"mecanicas":[]}
    for k, v in defaults.items():
        if k not in s_data or s_data[k] is None:
            s_data[k] = v

# Build maps from datos_actuales (after discovery)
SET_NAME_MAP = {}
EPIC_SUFFIX = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    SET_NAME_MAP[s_name] = sid
    tb = s_data.get("total_base", 0)
    if tb:
        EPIC_SUFFIX[sid] = str(tb)

# Also map DotGG original set names to internal ids
# Also map DotGG original set names to internal ids
for dotgg_name in DOTGG_SET_NAMES:
    sid = dotgg_name.lower().replace(" ", "_")
    # Redirect merged subsets to their parent set
    if sid in DOTGG_SET_MERGE:
        SET_NAME_MAP[dotgg_name] = DOTGG_SET_MERGE[sid]
    else:
        SET_NAME_MAP[dotgg_name] = sid

# Build legend name list per set
legends_per_set = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    names = []
    for leg in s_data.get("leyendas", []):
        n = leg.get("name") if isinstance(leg, dict) else (leg if isinstance(leg, str) else None)
        if n:
            names.append(n)
    legends_per_set[sid] = names

# Dynamic lists for validation
EXPANSIONES = list(datos_actuales.get("sets", {}).keys())
SET_CODE_MAP = {s_data["abbr"]: sid for sid, s_data in datos_actuales["sets"].items()}

# ==========================================
# Seed totals from DotGG data
# ==========================================
def seed_from_dotgg(rows, names, base):
    """Fill set totals, legend lists and ovr counts from DotGG data."""
    from collections import defaultdict
    set_data = defaultdict(lambda: {"total": 0, "legends": set(), "ovr": 0, "abbr": None, "ids": set()})
    for row in rows:
        card = dict(zip(names, row))
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
        for s_name, s_val in base.get("sets", {}).items():
            if s_val.get("id") == sid:
                uid_count = len(d["ids"])
                if uid_count > 0:
                    s_val["total"] = uid_count
                    s_val["total_base"] = uid_count - d["ovr"]
                    s_val["total_ovr"] = d["ovr"]
                    s_val["legend_count"] = len(d["legends"])
                    s_val["leyendas"] = [{"name": n, "img": None} for n in sorted(d["legends"])]
                break

if api_rows:
    seed_from_dotgg(api_rows, api_names, datos_actuales)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(datos_actuales, f, indent=4, ensure_ascii=False)
    total_seeded = sum(s.get("total",0) for s in datos_actuales.get("sets",{}).values())
    print(f"✅ 'cartas.json' seedeado desde DotGG ({total_seeded} cartas totales).")

# ==========================================
# Build prices from DotGG data
# ==========================================
def make_price_key(api_id, set_id):
    k = api_id.lower()
    if k.endswith("-star"):
        k = k[:-5] + "*"
    suffix = EPIC_SUFFIX.get(set_id)
    if suffix:
        k = f"{k}-{suffix}"
    return k

def build_prices(rows, names):
    prices = {}
    legend_min = {}
    for row in rows:
        card = dict(zip(names, row))
        set_name = card.get("set_name")
        set_id = SET_NAME_MAP.get(set_name)
        if not set_id: continue
        cm_price = card.get("cmPrice")
        if not cm_price or cm_price == 0 or cm_price == "0" or cm_price == "0.000000": continue
        cm_f = float(cm_price)
        ps = f"€{cm_f:.2f}"
        if set_id not in prices: prices[set_id] = {}
        prices[set_id][make_price_key(card.get("id",""), set_id)] = ps
        if card.get("type") == "Legend":
            tags = card.get("tags") or []
            for cn in legends_per_set.get(set_id, []):
                if cn in tags:
                    if set_id not in legend_min: legend_min[set_id] = {}
                    e = legend_min[set_id].get(cn)
                    if e is None or cm_f < e: legend_min[set_id][cn] = cm_f
    for sid, champs in legend_min.items():
        if sid not in prices: prices[sid] = {}
        for cn, mp in champs.items():
            prices[sid][cn] = f"€{mp:.2f}"
    return prices

# Save preliminary prices (in case Gemini fails later)
cardmarket_prices_file = "cardmarket_prices.json"
current_prices = {}
if os.path.exists(cardmarket_prices_file):
    with open(cardmarket_prices_file, "r", encoding="utf-8-sig") as f:
        current_prices = json.load(f)
prelim_prices = build_prices(api_rows, api_names) if api_rows else {}
for sid, sp in prelim_prices.items():
    if sid not in current_prices: current_prices[sid] = {}
    for k, v in sp.items():
        current_prices[sid][k] = v
with open(cardmarket_prices_file, "w", encoding="utf-8") as f:
    json.dump(current_prices, f, indent=4, ensure_ascii=False)
total_prelim = sum(len(v) for v in prelim_prices.values())
print(f"✅ 'cardmarket_prices.json' guardado ({total_prelim} precios).")

# Ensure auxiliary files exist (git add safety)
for fname in ("id_to_name.json", "legend_data.json"):
    if not os.path.exists(fname):
        with open(fname, "w", encoding="utf-8") as f:
            json.dump({}, f)
if not os.path.exists("epic-cards.js"):
    with open("epic-cards.js", "w", encoding="utf-8") as f:
        f.write("window.EPIC_CARD_DATA = {};")

# Listar cartas épicas+ para el prompt (desde DotGG)
epic_list_lines = []
REVERSE_CODE_MAP = {v: k for k, v in SET_CODE_MAP.items()}
dotgg_premium = {"Epic", "Showcase"}
for row in api_rows:
    card = dict(zip(api_names, row))
    if card.get("rarity") not in dotgg_premium:
        continue
    set_name = card.get("set_name", "")
    set_code = REVERSE_CODE_MAP.get(SET_NAME_MAP.get(set_name))
    if not set_code: continue
    epic_list_lines.append(f'  {SET_NAME_MAP.get(set_name,"?")}/{card["id"]}: {card["name"]} [{card["rarity"]}]')
epic_list_str = "\n".join(epic_list_lines)

abbrs = ", ".join(s_data.get("abbr","") for s_name, s_data in datos_actuales.get("sets",{}).items())
set_nums = f"1-{len(datos_actuales.get('sets',{}))}"
per_box_example = {
    "Epic": {sn: "~6 por caja" for sn in EXPANSIONES},
    "Showcase": {sn: "~2 por caja" for sn in EXPANSIONES},
    "Overnumbered": {sn: "~1 en 3 cajas" for sn in EXPANSIONES},
    "Signature": {sn: "~1 en 30 cajas" for sn in EXPANSIONES},
    "Ultimate_Rare": {sn: "~1 en 1000 sobres" for sn in EXPANSIONES}
}
per_box_str = json.dumps(per_box_example, separators=(",", ":")).replace("{","{{").replace("}","}}")

mensaje = f"""
Eres el mantenedor automático de la base de datos de Riftbound TCG.
Tu trabajo es actualizar el JSON completo de las expansiones con TODOS los campos.

FUENTES PRIORITARIAS:
- riftbound.leagueoflegends.com
- Riot Games

ESTRUCTURA JSON REQUERIDA (debes devolver EXACTAMENTE este formato):
{{
    "sets": {{
        "NOMBRE_EXPANSION": {{
            "id": "nombre en minúsculas",
            "abbr": "siglas ({abbrs})",
            "set_number": {set_nums},
            "color": "código hex",
            "date": "Mes Año del lanzamiento",
            "cartas_reveladas": número,
            "total": número total de cartas del set,
            "total_base": número de cartas base,
            "total_ovr": número de cartas OVR/Showcase/Alt-Art,
            "imgBase": "URL base de imágenes (o null si no hay)",
            "legend_count": número de leyendas,
            "leyendas": [
                {{"name": "Nombre del campeón", "img": "URL directa de la imagen (o null si no encuentras)"}}
            ],
            "productos": ["Lista", "de", "productos"],
            "champion_decks": ["Campeones", "con", "Champion Deck"],
            "ovr_breakdown": [
                {{"tipo":"Alt-Art","cantidad":20,"numeracion":"rangos","notas":"descripción"}},
                {{"tipo":"OVR base","cantidad":40,"numeracion":"rangos","notas":"descripción"}},
                {{"tipo":"OVR con firma","cantidad":10,"numeracion":"rangos","notas":"descripción"}}
            ],
            "mecanicas": [
                {{"kicker":"tipo","name":"nombre","desc":"descripción"}}
            ]
        }}
    }},
    "pull_rates": {{
        "general_booster_pack_contents": {{...}},
        "rarity_odds": {{...}},
        "set_specific": {{...}},
        "per_box": {per_box_str}
    }}
}}

NOTA IMPORTANTE sobre "per_box": usa SOLO estas claves de rareza: "Epic", "Showcase", "Overnumbered", "Signature", "Ultimate_Rare".
Para cada rareza, pon un objeto con los IDs de set como claves y un texto descriptivo como valor.
Ejemplos de texto: "~6 por caja", "~2 por caja", "~1 en 3 cajas", "~1 en 30 cajas", "~1 en 42 cajas".
NO uses "rareza" como clave. NO uses texto largo narrativo.
IMPORTANTE: TODOS los valores deben expresarse POR CAJA (24 sobres). Usa SIEMPRE "cajas" como unidad, NUNCA "sobres".

TAREAS:
1. Detectar nuevas expansiones (si aparece una nueva, AÑÁDELA al JSON).
2. Mantener productos, ovr_breakdown, mecanicas por cada expansión.
3. Actualizar pull_rates si hay cambios oficiales.
4. Para expansiones NUEVAS, rellena todos los campos con la información disponible.

IMPORTANTE: Los campos total, total_base, total_ovr, legend_count y leyendas
vienen de la API de DotGG y son EXACTOS. NO los modifiques bajo ninguna circunstancia.
Solo añade lo que falte: date, imgBase, productos, ovr_breakdown, mecanicas, pull_rates.

IMPORTANTE sobre ovr_breakdown: el campo "cantidad" debe ser un NÚMERO entero,
nunca la letra "N" ni texto. Si no sabes la cantidad exacta, pon 0.

IMPORTANTE sobre mecanicas: DEBES incluir mecanicas para TODAS las expansiones,
tanto las ya lanzadas como las nuevas. No dejes el array vacío para ninguna.
DATA ACTUAL DE SETS:
{json.dumps(datos_actuales, indent=2, ensure_ascii=False)}

CARTAS ÉPICAS EXISTENTES (referencia para datos del set):
{epic_list_str}

REGLAS CRÍTICAS:
1. Devuelve EXCLUSIVAMENTE el objeto JSON actualizado exactamente con la estructura de arriba.
2. No incluyas explicaciones, markdown, ni texto extra.
3. Si no hay cambios, devuelve el mismo JSON exacto que te di.
4. Para expansiones existentes, mantén los campos que no cambien.
5. NO INVENTES URLs. Si no encuentras una URL oficial de imágenes (de riotgames.com, riftbound.leagueoflegends.com, riftbound.gg o cardgamer.com), pon "imgBase": null.
6. NO CAMBIES champion_decks ni mecánicas de expansiones existentes a menos que tengas confirmación en fuente oficial publicada por Riot Games.
7. Todo debe estar contrastado con fuentes oficiales de Riot Games, riftbound.leagueoflegends.com, riftbound.gg o cardgamer.com. No uses otras webs.
8. Los campos total, total_base, total_ovr, legend_count y leyendas vienen de la API de DotGG. NO los modifiques.
9. Para el campo "img" de cada leyenda, usa SOLO URLs de cardgamer.com, riftbound.leagueoflegends.com o riftbound.gg. Si no encuentras la URL exacta de la imagen, pon null.
"""

# Ejecución con control de cuota
intentos_maximos = 3
espera_inicial = 10
response = None

if gemini_available:
    for intento in range(intentos_maximos):
        try:
            print(f"🚀 Consultando novedades a Gemini (Intento {intento + 1})...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=mensaje,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    tools=[{"google_search": {}}]
                )
            )
            break
        except ClientError as e:
            if e.code in (429, 503):
                print(f"⚠️ Error {e.code}, reintentando en {espera_inicial}s...")
                time.sleep(espera_inicial)
                espera_inicial *= 2
            else:
                print(f"❌ Error de API: {e}")
                break
        except Exception as e:
            err_str = str(e)
            if '503' in err_str or 'UNAVAILABLE' in err_str:
                print(f"⚠️ Error 503 inesperado, reintentando en {espera_inicial}s...")
                time.sleep(espera_inicial)
                espera_inicial *= 2
            else:
                print(f"❌ Error inesperado: {e}")
                break

gemini_ok = False

if response and response.text:
    # ==========================================
    # Validación y extracción del JSON generado
    # ==========================================
    texto_respuesta = response.text.strip()

    # Limpieza de bloques markdown
    if "```json" in texto_respuesta:
        texto_respuesta = texto_respuesta.split("```json")[1].split("```")[0].strip()
    elif "```" in texto_respuesta:
        texto_respuesta = texto_respuesta.split("```")[1].split("```")[0].strip()

    try:
        gemini_ok = True
        datos_nuevos = json.loads(texto_respuesta)

        # Verificación de que no eliminó las expansiones clave
        for exp in EXPANSIONES:
            if "sets" not in datos_nuevos or exp not in datos_nuevos["sets"]:
                raise ValueError(f"Falta la expansión obligatoria: {exp}")

        # Verificar campos esenciales por expansión
        for exp in EXPANSIONES:
            s = datos_nuevos["sets"][exp]
            for campo in ["id", "abbr", "total", "total_base", "total_ovr", "legend_count",
                          "leyendas", "productos", "ovr_breakdown", "mecanicas"]:
                if campo not in s:
                    raise ValueError(f"Falta campo '{campo}' en {exp}")

        # Overwrite DotGG-sourced fields with seeded values (they are exact from API)
        for exp in EXPANSIONES:
            seed = datos_actuales.get("sets", {}).get(exp, {})
            if exp in datos_nuevos["sets"]:
                for campo in ["total", "total_base", "total_ovr", "legend_count", "leyendas"]:
                    if campo in seed:
                        datos_nuevos["sets"][exp][campo] = seed[campo]

        # Normalize per_box: ensure correct rarity keys, not "rareza"
        VALID_RARITIES = {"Epic", "Showcase", "Overnumbered", "Signature", "Ultimate_Rare"}
        pr = datos_nuevos.get("pull_rates", {})
        if "per_box" in pr:
            pb = pr["per_box"]
            if isinstance(pb, dict):
                # If it has "rareza" but not the valid keys, try to convert
                if "rareza" in pb and not any(k in pb for k in VALID_RARITIES):
                    rareza_data = pb.pop("rareza")
                    if isinstance(rareza_data, dict):
                        pb["Epic"] = rareza_data
                        pb["Showcase"] = rareza_data
                        pb["Overnumbered"] = rareza_data
                        pb["Signature"] = rareza_data
                        pb["Ultimate_Rare"] = rareza_data

    except (json.JSONDecodeError, ValueError) as e:
        print(f"❌ Validación fallida: {e}")
        print("Respuesta cruda:", texto_respuesta if 'texto_respuesta' in dir() else "(no hay respuesta)")
        gemini_ok = False

    if gemini_ok:
        # ==========================================
        # Guardar cartas.json solo si hay cambios
        # ==========================================
        # Limpiar campo interno _source_url de todos los sets antes de guardar
        source_urls_used = []
        for nombre_set, data_set in datos_nuevos["sets"].items():
            if "_source_url" in data_set:
                source_urls_used.append(f"  {nombre_set}: {data_set.pop('_source_url')}")
        if source_urls_used:
            print("URLs fuente reportadas por el AI:")
            for line in source_urls_used:
                print(line)

        if datos_nuevos == datos_actuales:
            print("ℹ️ No se detectaron novedades en las fuentes oficiales para cartas.json.")
        else:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(datos_nuevos, f, indent=4, ensure_ascii=False)
            print("✅ 'cartas.json' actualizado con éxito.")
            datos_actuales = datos_nuevos  # use updated data for suffix rebuilding

            # Rebuild legends_per_set from updated data
            legends_per_set.clear()
            for s_name, s_data in datos_actuales.get("sets", {}).items():
                sid = s_data.get("id")
                names = []
                for leg in s_data.get("leyendas", []):
                    n = leg.get("name") if isinstance(leg, dict) else (leg if isinstance(leg, str) else None)
                    if n:
                        names.append(n)
                legends_per_set[sid] = names
else:
    print("⚠️ Gemini no disponible — continuando con datos seedeados.")

# ==========================================
# Reconstruir sufijos y regenerar archivos finales
# ==========================================
if not api_rows:
    print("⚠️ Sin datos DotGG — se mantienen archivos anteriores.")
    # Ensure files exist for git add
    for fname in ("id_to_name.json", "legend_data.json"):
        if not os.path.exists(fname):
            with open(fname, "w", encoding="utf-8") as f:
                json.dump({}, f)
            print(f"ℹ️ '{fname}' vacío generado.")
    if not os.path.exists("epic-cards.js"):
        with open("epic-cards.js", "w", encoding="utf-8") as f:
            f.write("window.EPIC_CARD_DATA = {};")
        print("ℹ️ 'epic-cards.js' vacío generado.")
else:
    # Normalize any per-pack ("sobres") values to per-box ("cajas") in current data
    pb = datos_actuales.get("pull_rates", {}).get("per_box", {})
    if isinstance(pb, dict):
        for rarity_key in pb:
            for set_key in list(pb[rarity_key] or {}):
                v = pb[rarity_key][set_key]
                if v and isinstance(v, str):
                    m = re.match(r'~?([\d.]+)\s*en\s*([\d.]+)\s*sobres?', v)
                    if m:
                        den = float(m.group(2))
                        new_den = max(1, round(den / 24))
                        pb[rarity_key][set_key] = f'~1 en {new_den} cajas'

    # Rebuild ovr_breakdown from DotGG data (always, discarding stale Gemini values)
    if api_rows:
        ovr_counts = {}
        for row in api_rows:
            card = dict(zip(api_names, row))
            if card.get("rarity") != "Showcase": continue
            sn = card.get("set_name", "")
            sid = SET_NAME_MAP.get(sn)
            if not sid: continue
            if sid not in ovr_counts: ovr_counts[sid] = {"alt":0,"sig":0,"ovr":0}
            nm = card.get("name","").lower()
            aid = card.get("id","").lower()
            if aid.endswith("-star"):
                ovr_counts[sid]["sig"] += 1
            elif "alternate art" in nm or (aid.endswith("a") and card.get("rarity") == "Showcase"):
                ovr_counts[sid]["alt"] += 1
            else:
                ovr_counts[sid]["ovr"] += 1
        for s_name, s_data in datos_actuales.get("sets", {}).items():
            sid = s_data.get("id")
            total_ovr = int(s_data.get("total_ovr", 0))
            if total_ovr == 0: continue
            ob = []
            dc = ovr_counts.get(sid)
            alt = dc["alt"] if dc else 0
            sig = dc["sig"] if dc else 0
            ovr = dc["ovr"] if dc else 0
            dotgg_sum = alt + sig + ovr
            if dotgg_sum > 0:
                ob.append({"tipo":"Alt-Art","cantidad":alt,"numeracion":"","notas":""})
                ob.append({"tipo":"OVR base","cantidad":ovr,"numeracion":"","notas":""})
                ob.append({"tipo":"OVR con firma","cantidad":sig,"numeracion":"","notas":""})
                leftover = total_ovr - dotgg_sum
                if leftover > 0:
                    ob[0]["cantidad"] += leftover
            else:
                ob.append({"tipo":"Alt-Art","cantidad":total_ovr,"numeracion":"","notas":""})
            s_data["ovr_breakdown"] = ob

    # Ensure released flag: sets that have DotGG cards get released: True
    dotgg_sids = set()
    for row in api_rows:
        card = dict(zip(api_names, row))
        sn = card.get("set_name", "")
        sid = SET_NAME_MAP.get(sn)
        if sid: dotgg_sids.add(sid)
    for s_name, s_data in datos_actuales.get("sets", {}).items():
        s_data["released"] = s_data.get("id") in dotgg_sids

    # Re-read total_base from (potentially updated) cartas.json for EPIC_SUFFIX
    EPIC_SUFFIX_FINAL = {}
    for s_name, s_data in datos_actuales.get("sets", {}).items():
        sid = s_data.get("id")
        tb = s_data.get("total_base", 0)
        if tb:
            EPIC_SUFFIX_FINAL[sid] = str(tb)

    # Rebuild SET_NAME_MAP from final data
    SET_NAME_MAP_FINAL = {}
    for s_name, s_data in datos_actuales.get("sets", {}).items():
        SET_NAME_MAP_FINAL[s_name] = s_data.get("id")
    for dotgg_name in DOTGG_SET_NAMES:
        sid = dotgg_name.lower().replace(" ", "_")
        if sid in DOTGG_SET_MERGE:
            SET_NAME_MAP_FINAL[dotgg_name] = DOTGG_SET_MERGE[sid]
        else:
            SET_NAME_MAP_FINAL[dotgg_name] = sid

    def make_key(api_id, set_id):
        k = api_id.lower()
        if k.endswith("-star"):
            k = k[:-5] + "*"
        suffix = EPIC_SUFFIX_FINAL.get(set_id)
        if suffix:
            k = f"{k}-{suffix}"
        return k

    # Regenerate cardmarket_prices.json with final suffix
    final_prices = {}
    legend_min = {}
    for row in api_rows:
        card = dict(zip(api_names, row))
        sn = card.get("set_name")
        sid = SET_NAME_MAP_FINAL.get(sn)
        if not sid: continue
        cm = card.get("cmPrice")
        if not cm or cm == 0 or cm == "0" or cm == "0.000000": continue
        cm_f = float(cm)
        if sid not in final_prices: final_prices[sid] = {}
        final_prices[sid][make_key(card.get("id",""), sid)] = f"€{cm_f:.2f}"
        if card.get("type") == "Legend":
            for cn in legends_per_set.get(sid, []):
                if cn in (card.get("tags") or []):
                    if sid not in legend_min: legend_min[sid] = {}
                    e = legend_min[sid].get(cn)
                    if e is None or cm_f < e: legend_min[sid][cn] = cm_f
    for sid, champs in legend_min.items():
        if sid not in final_prices: final_prices[sid] = {}
        for cn, mp in champs.items():
            final_prices[sid][cn] = f"€{mp:.2f}"

    with open(cardmarket_prices_file, "w", encoding="utf-8") as f:
        json.dump(final_prices, f, indent=4, ensure_ascii=False)
    total_final = sum(len(v) for v in final_prices.values())
    print(f"✅ 'cardmarket_prices.json' re-escrito ({total_final} precios).")

    # Save ID-to-name map for Telegram notifications
    id_name_map_save = {}
    for row in api_rows:
        card = dict(zip(api_names, row))
        sn = card.get("set_name", "")
        sid = SET_NAME_MAP_FINAL.get(sn)
        if not sid: continue
        cm = card.get("cmPrice")
        if not cm or cm == 0 or cm == "0" or cm == "0.000000": continue
        k = make_key(card.get("id",""), sid)
        if sid not in id_name_map_save: id_name_map_save[sid] = {}
        id_name_map_save[sid][k] = card.get("name", k)
    # Add legend champion-name keys (self-mapping)
    for sid, champs in legend_min.items():
        if sid not in id_name_map_save: id_name_map_save[sid] = {}
        for cn in champs:
            id_name_map_save[sid][cn] = cn
    with open("id_to_name.json", "w", encoding="utf-8") as f:
        json.dump(id_name_map_save, f, indent=4, ensure_ascii=False)

    # Save legend data (images, titles, numbers) for each set's champions
    legend_data_save = {}
    legend_data_min = {}
    for row in api_rows:
        card = dict(zip(api_names, row))
        if card.get("type") != "Legend": continue
        sn = card.get("set_name", "")
        sid = SET_NAME_MAP_FINAL.get(sn)
        if not sid: continue
        full_name = card.get("name", "")
        champ = re.split(r' - |, ', full_name, maxsplit=1)[0].strip()
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
        title = full_name.split(" - ", 1)[1] if " - " in full_name else (full_name.split(", ", 1)[1] if ", " in full_name else "")
        legend_data_save[sid][champ] = {
            "img": card.get("image") or "",
            "title": title,
            "number": number
        }
    with open("legend_data.json", "w", encoding="utf-8") as f:
        json.dump(legend_data_save, f, indent=4, ensure_ascii=False)
    print(f"✅ 'legend_data.json' guardado ({sum(len(v) for v in legend_data_save.values())} leyendas).")

    # Generate epic-cards.js from DotGG data
    def build_epic_cards():
        """Build window.EPIC_CARD_DATA from DotGG API data."""
        id_to_abbr = {}
        for s_name, s_data in datos_actuales.get("sets", {}).items():
            abbr = s_data.get("abbr")
            sid = s_data.get("id")
            if abbr and sid:
                id_to_abbr[sid] = abbr

        premium_rarities = {"Epic", "Showcase"}
        result = {}
        for row in api_rows:
            card = dict(zip(api_names, row))
            rarity = card.get("rarity", "")
            if rarity not in premium_rarities:
                continue
            sn = card.get("set_name", "")
            sid = SET_NAME_MAP_FINAL.get(sn)
            sc = id_to_abbr.get(sid)
            if not sc: continue
            if sc not in result: result[sc] = []

            nm = card.get("name", "")
            aid = card.get("id", "")
            our_id = make_key(aid, SET_NAME_MAP_FINAL.get(sn, ""))
            nm_lower = nm.lower()
            aid_lower = aid.lower()
            num_m = re.search(r"-(\d+)", aid)
            number = int(num_m.group(1)) if num_m else 0

            alt   = "alternate art" in nm_lower or (aid_lower.endswith("a") and rarity == "Showcase")
            ovr   = "overnumbered" in nm_lower or ("ovr" in nm_lower and not "alternate" in nm_lower)
            sig   = "signature" in nm_lower or "signed" in nm_lower
            if rarity == "Showcase" and not alt and not sig:
                ovr = True

            color_raw = card.get("color") or []
            if isinstance(color_raw, list):
                domain = " / ".join(c.title() for c in color_raw if c)
            else:
                domain = str(color_raw).title() if color_raw else ""

            result[sc].append({
                "name": nm,
                "number": number,
                "id": our_id,
                "rarity": rarity,
                "type": card.get("type", ""),
                "domain": domain,
                "image": card.get("image", ""),
                "alt": alt,
                "ovr": ovr,
                "signature": sig
            })

        for sc in result:
            result[sc].sort(key=lambda c: c["id"])
        return result

    epic_data = build_epic_cards()
    with open("epic-cards.js", "w", encoding="utf-8") as f:
        f.write("window.EPIC_CARD_DATA = " + json.dumps(epic_data, ensure_ascii=False) + ";")
    total_epic = sum(len(v) for v in epic_data.values())
    print(f"✅ 'epic-cards.js' generado ({total_epic} cartas premium).")

    # Save final datos_actuales (ovr_breakdown fill, released flag, etc.)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(datos_actuales, f, indent=4, ensure_ascii=False)
    print("✅ 'cartas.json' guardado con datos finales.")
