import os
import json
import time
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

# Leer cardmarket_urls actual (si existe)
cardmarket_urls_actual = {}
cardmarket_urls_file = "cardmarket_urls.json"
if os.path.exists(cardmarket_urls_file):
    with open(cardmarket_urls_file, "r", encoding="utf-8") as f:
        cardmarket_urls_actual = json.load(f)

# Cargar datos de cartas épicas para pasarlos al prompt
epic_data_raw = {}
try:
    import re
    with open("epic-cards.js", "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"window\.EPIC_CARD_DATA\s*=\s*(\{.+?\});", content, re.DOTALL)
    if match:
        epic_data_raw = json.loads(match.group(1))
except Exception:
    epic_data_raw = {}

# Listar las épicas para el prompt
epic_list_lines = []
for set_code, cards in epic_data_raw.items():
    set_id = SET_CODE_MAP.get(set_code, set_code.lower())
    for card in cards:
        epic_list_lines.append(f'  {set_id}/{card["id"]}: {card["name"]} [{card["rarity"]}]')
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
                {{"name": "Nombre del campeón", "img": "URL directa de la imagen (o null si no encuentras)", "cardmarket": "URL directa a la carta en Cardmarket (o null si no la encuentras)"}}
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
    }},
    "cardmarket_urls": {{
        "origins": {{
            "Kai'Sa": "URL o null",
            "ogn-039-298": "URL o null"
        }},
        "spiritforged": {{
            "Rumble": "URL o null",
            "sfd-027-221": "URL o null"
        }},
        "unleashed": {{
            "Jhin": "URL o null",
            "unl-022a-219": "URL o null"
        }},
        "vendetta": {{
            "Nasus": "URL o null"
        }}
    }}
}}

TAREAS:
1. Detectar nuevas expansiones (si aparece una nueva, AÑÁDELA al JSON).
2. Detectar nuevas cartas o leyendas reveladas y actualizar leyendas, total_base, total_ovr.
3. Mantener productos, ovr_breakdown, mecanicas por cada expansión.
4. Actualizar pull_rates si hay cambios oficiales.
5. Para expansiones NUEVAS, rellena todos los campos con la información disponible.
6. Generar o actualizar las URLs de Cardmarket para TODAS las cartas en cardmarket_urls.
   Las claves son: nombre de leyenda (ej. "Kai'Sa") o ID de carta épica (ej. "ogn-039-298").
   El valor es la URL exacta y REAL de Cardmarket, obtenida mediante búsqueda, o null si no la encuentras.

DATA ACTUAL DE SETS:
{json.dumps(datos_actuales, indent=2, ensure_ascii=False)}

CARTAS ÉPICAS EXISTENTES (inclúyelas todas en cardmarket_urls):
{epic_list_str}

URLS DE CARDMARKET ACTUALES (actualiza o añade según corresponda):
{json.dumps(cardmarket_urls_actual, indent=2, ensure_ascii=False)}

CÓMO OBTENER LA URL REAL DE CARDMARKET (IMPORTANTE):

NO CONSTRUYAS URLs con formato. DEBES BUSCAR CADA CARTA en Cardmarket usando Google Search y extraer la URL real.

Para cada carta:
1. Busca en Google: "Riftbound [nombre carta] cardmarket"
2. Si no aparece, busca: "cardmarket Riftbound [nombre carta]"
3. Si no aparece, busca: "cardmarket Riftbound [set] [número de carta]"
4. Extrae la URL exacta del resultado de búsqueda — DEBE ser cardmarket.com/en/Riftbound/Products/Singles/...
5. Si no encuentras la URL exacta tras varios intentos, pon null.

Ejemplos de búsqueda:
- Para "Kai'Sa": busca "Riftbound Kai'Sa cardmarket"
- Para "ogn-039-298" (Kai'Sa Survivor): busca "Riftbound Kai'Sa Survivor cardmarket" o "Riftbound ogn-039 cardmarket"

REGLAS:
- La URL debe ser REAL, obtenida de los resultados de búsqueda
- NO uses formatos, plantillas ni construyas la URL manualmente
- Si Google no encuentra la carta, pon null
- Si la URL que encuentras no es de cardmarket.com, pon null

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
10. cardmarket_urls debe contener TODAS las cartas (leyendas + épicas). Las URLs deben ser URLs REALES obtenidas de búsqueda en Google, no construidas con formato. Si la búsqueda no encuentra la URL exacta, pon null.
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

    # Extraer cardmarket_urls antes de comparar con datos actuales
    cardmarket_urls = datos_nuevos.pop("cardmarket_urls", {})

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

    FUENTES_VALIDAS = ["riftbound.leagueoflegends.com", "riftbound.gg", "cardgamer.com"]

    # Validar campo cardmarket en leyendas (redundante con cardmarket_urls, pero por compatibilidad)
    for exp in EXPANSIONES:
        for leyenda in datos_nuevos["sets"][exp].get("leyendas", []):
            url = leyenda.get("cardmarket")
            if url and "cardmarket.com" not in url:
                raise ValueError(
                    f"Leyenda {exp}/{leyenda['name']} tiene cardmarket '{url}' "
                    f"que no es de cardmarket.com. Cambio rechazado."
                )

    # Validar cardmarket_urls: todos los valores deben ser null o cardmarket.com
    for set_id, entries in cardmarket_urls.items():
        for card_key, url in entries.items():
            if url and "cardmarket.com" not in url:
                raise ValueError(
                    f"cardmarket_urls[{set_id}]['{card_key}'] = '{url}' "
                    f"no es de cardmarket.com. Cambio rechazado."
                )

    # Validar Regla 8: cambios en totals requieren _source_url de fuente válida
    for exp in EXPANSIONES:
        old = datos_actuales.get("sets", {}).get(exp, {})
        new = datos_nuevos["sets"][exp]
        for campo in ["total", "total_base", "total_ovr"]:
            if old.get(campo) != new.get(campo):
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
# Guardar cardmarket_urls.json
# ==========================================
if cardmarket_urls:
    with open("cardmarket_urls.json", "w", encoding="utf-8") as f:
        json.dump(cardmarket_urls, f, indent=4, ensure_ascii=False)
    print("✅ 'cardmarket_urls.json' actualizado con URLs de Cardmarket.")

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
