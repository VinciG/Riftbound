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
            "leyendas": ["Lista", "de", "nombres", "de", "campeones"],
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

DATA ACTUAL:
{json.dumps(datos_actuales, indent=2, ensure_ascii=False)}

REGLAS CRÍTICAS:
1. Devuelve EXCLUSIVAMENTE el objeto JSON actualizado exactamente con la estructura de arriba.
2. No incluyas explicaciones, markdown, ni texto extra.
3. Si no hay cambios, devuelve el mismo JSON exacto que te di.
4. Para expansiones existentes, mantén los campos que no cambien.
5. NO INVENTES URLs. Si no encuentras una URL oficial de imágenes (de riotgames.com, riftbound.leagueoflegends.com, riftbound.gg o cardgamer.com), pon "imgBase": null.
6. NO CAMBIES champion_decks ni mecánicas de expansiones existentes a menos que tengas confirmación en fuente oficial publicada por Riot Games.
7. Todo debe estar contrastado con fuentes oficiales de Riot Games, riftbound.leagueoflegends.com, riftbound.gg o cardgamer.com. No uses otras webs.
8. Si el total, total_base o total_ovr de un set ya lanzado cambia respecto al JSON actual, DEBES incluir la URL exacta de la fuente que respalda ese cambio.
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

except (json.JSONDecodeError, ValueError) as e:
    print(f"❌ Validación fallida: {e}")
    print("Respuesta cruda:", texto_respuesta)
    exit(0)

# ==========================================
# Guardar únicamente si hay cambios reales
# ==========================================
if datos_nuevos == datos_actuales:
    print("ℹ️ No se detectaron novedades en las fuentes oficiales.")
    exit(0)

with open(json_file, "w", encoding="utf-8") as f:
    json.dump(datos_nuevos, f, indent=4, ensure_ascii=False)

print("✅ Base de datos 'cartas.json' actualizada con éxito.")
