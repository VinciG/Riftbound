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

# Estructura por defecto si no existe
ESQUEMA_BASE = {
    "sets": {
        "Origins": {
            "id": "origins", "abbr": "OGN", "set_number": 1, "color": "#4a9eff",
            "date": "", "cartas_reveladas": 0, "total": 0, "total_base": 0, "total_ovr": 0,
            "imgBase": "", "legend_count": 0, "leyendas": [],
            "productos": [], "champion_decks": [], "ovr_breakdown": [], "mecanicas": []
        },
        "Spiritforged": {
            "id": "spiritforged", "abbr": "SFD", "set_number": 2, "color": "#3ecf8e",
            "date": "", "cartas_reveladas": 0, "total": 0, "total_base": 0, "total_ovr": 0,
            "imgBase": "", "legend_count": 0, "leyendas": [],
            "productos": [], "champion_decks": [], "ovr_breakdown": [], "mecanicas": []
        },
        "Unleashed": {
            "id": "unleashed", "abbr": "UNL", "set_number": 3, "color": "#f4a535",
            "date": "", "cartas_reveladas": 0, "total": 0, "total_base": 0, "total_ovr": 0,
            "imgBase": "", "legend_count": 0, "leyendas": [],
            "productos": [], "champion_decks": [], "ovr_breakdown": [], "mecanicas": []
        },
        "Vendetta": {
            "id": "vendetta", "abbr": "VEN", "set_number": 4, "color": "#e879a0",
            "date": "", "cartas_reveladas": 0, "total": 0, "total_base": 0, "total_ovr": 0,
            "imgBase": "", "legend_count": 0, "leyendas": [],
            "productos": [], "champion_decks": [], "ovr_breakdown": [], "mecanicas": []
        }
    },
    "pull_rates": {}
}

if not os.path.exists(json_file):
    datos_actuales = json.loads(json.dumps(ESQUEMA_BASE))
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(datos_actuales, f, indent=4, ensure_ascii=False)
else:
    with open(json_file, "r", encoding="utf-8") as f:
        datos_actuales = json.load(f)

# ==========================================
# Configuración de Gemini
# ==========================================
client = genai.Client()

EXPANSIONES = ["Origins", "Spiritforged", "Unleashed", "Vendetta"]

# Mapa de códigos de set a IDs internos
SET_CODE_MAP = {"OGN": "origins", "SFD": "spiritforged", "UNL": "unleashed", "VEN": "vendetta"}

# Leer precios actuales de cardmarket_prices.json (si existe)
cardmarket_prices_file = "cardmarket_prices.json"
cardmarket_prices_actual = {}
if os.path.exists(cardmarket_prices_file):
    with open(cardmarket_prices_file, "r", encoding="utf-8-sig") as f:
        cardmarket_prices_actual = json.load(f)

# ==========================================
# Obtener precios reales desde DotGG API
# ==========================================
DOTGG_API_URL = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"

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

# Build set_name → set_id map AND EPIC_SUFFIX from cartas.json total_base
SET_NAME_MAP = {}
EPIC_SUFFIX = {}
for s_name, s_data in datos_actuales.get("sets", {}).items():
    sid = s_data.get("id")
    SET_NAME_MAP[s_name] = sid
    tb = s_data.get("total_base", 0)
    if tb:
        EPIC_SUFFIX[sid] = str(tb)

def fetch_dotgg_prices():
    """Fetch all Riftbound cards with prices from DotGG public API (no key needed)."""
    req = urllib.request.Request(DOTGG_API_URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    names = raw["names"]
    rows = raw["data"]

    prices = {}
    legend_min_prices = {}

    for row in rows:
        card = dict(zip(names, row))
        set_name = card.get("set_name")
        set_id = SET_NAME_MAP.get(set_name)
        if not set_id:
            continue

        cm_price = card.get("cmPrice")
        if cm_price is None or cm_price == 0 or cm_price == "0" or cm_price == "0.000000":
            continue

        cm_price_f = float(cm_price)
        price_str = f"€{cm_price_f:.2f}"

        if set_id not in prices:
            prices[set_id] = {}

        # Key from API card id + suffix from epic-cards.js
        # Convert API suffix -STAR → * (epic-cards.js format), -P promo suffix kept
        api_id = card.get("id", "")
        our_key = api_id.lower()
        if our_key.endswith("-star"):
            our_key = our_key[:-5] + "*"
        suffix = EPIC_SUFFIX.get(set_id)
        if suffix:
            our_key = f"{our_key}-{suffix}"
        prices[set_id][our_key] = price_str

        # Legend-type cards: track minimum price per champion
        if card.get("type") == "Legend":
            tags = card.get("tags") or []
            for champ_name in legends_per_set.get(set_id, []):
                if champ_name in tags:
                    if set_id not in legend_min_prices:
                        legend_min_prices[set_id] = {}
                    existing = legend_min_prices[set_id].get(champ_name)
                    if existing is None or cm_price_f < existing:
                        legend_min_prices[set_id][champ_name] = cm_price_f

    # Add legend champion-name keys (cheapest Legend-type card for each champ)
    for set_id, champs in legend_min_prices.items():
        if set_id not in prices:
            prices[set_id] = {}
        for champ_name, min_price in champs.items():
            prices[set_id][champ_name] = f"€{min_price:.2f}"

    return prices

# Fetch DotGG prices and merge into cardmarket_prices_actual
try:
    dotgg_prices = fetch_dotgg_prices()
    for set_id, set_prices in dotgg_prices.items():
        for key, val in set_prices.items():
            cardmarket_prices_actual[set_id][key] = val
    total = sum(len(v) for v in dotgg_prices.values())
    print(f"  → {total} precios obtenidos desde DotGG API")
except Exception as e:
    print(f"  ⚠️ Error al obtener precios de DotGG API: {e}")
    print("  Manteniendo precios anteriores.")

# ==========================================
# Obtener todos los datos desde DotGG API
# ==========================================
DOTGG_API_URL = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"

def fetch_dotgg_all():
    """Fetch ALL cards with prices from DotGG public API (no key needed)."""
    req = urllib.request.Request(DOTGG_API_URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return raw["names"], raw["data"]

api_names, api_rows = [], []
try:
    api_names, api_rows = fetch_dotgg_all()
    print(f"  → {len(api_rows)} cartas obtenidas desde DotGG API")
except Exception as e:
    print(f"  ⚠️ Error al obtener datos de DotGG API: {e}")

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
            "abbr": "siglas (OGN, SFD, UNL, VEN)",
            "set_number": 1-4,
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
                {{"tipo":"Alt-Art","cantidad":N,"numeracion":"rangos","notas":"descripción"}},
                {{"tipo":"OVR base","cantidad":N,"numeracion":"rangos","notas":"descripción"}},
                {{"tipo":"OVR con firma","cantidad":N,"numeracion":"rangos","notas":"descripción"}}
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
        "per_box": {{
            "rareza": {{"Origins":"texto","Spiritforged":"texto","Unleashed":"texto","Vendetta":"texto"}}
        }}
    }}
}}

TAREAS:
1. Detectar nuevas expansiones (si aparece una nueva, AÑÁDELA al JSON).
2. Detectar nuevas cartas o leyendas reveladas y actualizar leyendas, total_base, total_ovr.
3. Mantener productos, ovr_breakdown, mecanicas por cada expansión.
4. Actualizar pull_rates si hay cambios oficiales.
5. Para expansiones NUEVAS, rellena todos los campos con la información disponible.
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
8. Si cambias total, total_base o total_ovr de un set ya lanzado, DEBES incluir el campo "_source_url": "URL_DE_LA_FUENTE" dentro de ese set. La URL debe ser de riftbound.leagueoflegends.com, riftbound.gg o cardgamer.com. Sin ese campo o con URL no válida, el cambio será RECHAZADO automáticamente.
9. Para el campo "img" de cada leyenda, usa SOLO URLs de cardgamer.com, riftbound.leagueoflegends.com o riftbound.gg. Si no encuentras la URL exacta de la imagen, pon null.
"""

# Ejecución con control de cuota
intentos_maximos = 3
espera_inicial = 10
response = None

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
        if e.code == 429:
            print(f"⚠️ Cuota agotada, esperando {espera_inicial}s...")
            time.sleep(espera_inicial)
            espera_inicial *= 2
        else:
            print(f"❌ Error de API: {e}")
            exit(1)
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        exit(1)

if not response:
    print("❌ No se pudo conectar con la API.")
    exit(1)

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

    FUENTES_VALIDAS = ["riftbound.leagueoflegends.com", "riftbound.gg", "cardgamer.com", "tcggo.com"]

    # Validar Regla 8: cambios en totals requieren _source_url de fuente válida
    for exp in EXPANSIONES:
        old = datos_actuales.get("sets", {}).get(exp, {})
        new = datos_nuevos["sets"][exp]
        for campo in ["total", "total_base", "total_ovr"]:
            if old.get(campo) != new.get(campo):
                if not old.get(campo):
                    continue  # fresh population (was 0/null), no source URL needed
                url = new.get("_source_url", "")
                if not url:
                    raise ValueError(
                        f"Regla 8 violada: {exp}.{campo} cambió de {old.get(campo)} a {new.get(campo)} "
                        f"sin incluir '_source_url'. Cambio rechazado."
                    )
                if not any(dom in url for dom in FUENTES_VALIDAS):
                    raise ValueError(
                        f"Regla 8 violada: {exp}.{campo} cambió de {old.get(campo)} a {new.get(campo)} "
                        f"con _source_url '{url}' que no es de fuente válida ({', '.join(FUENTES_VALIDAS)}). Cambio rechazado."
                    )

except (json.JSONDecodeError, ValueError) as e:
    print(f"❌ Validación fallida: {e}")
    print("Respuesta cruda:", texto_respuesta)
    exit(0)

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
        title = full_name.split(", ", 1)[1] if ", " in full_name else ""
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
        sn_to_code = {}
        for s_name, s_data in datos_actuales.get("sets", {}).items():
            abbr = s_data.get("abbr")
            if abbr:
                sn_to_code[s_name] = abbr

        premium_rarities = {"Epic", "Showcase"}
        result = {}
        for row in api_rows:
            card = dict(zip(api_names, row))
            rarity = card.get("rarity", "")
            if rarity not in premium_rarities:
                continue
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
