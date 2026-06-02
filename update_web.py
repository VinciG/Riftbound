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

# Si no existe el archivo de datos, creamos uno base inicial
if not os.path.exists(json_file):
    datos_actuales = {
        "sets": {
            "Origins": {"cartas_reveladas": 0, "total": 0, "productos": []},
            "Spiritforged": {"cartas_reveladas": 0, "total": 0, "productos": []},
            "Unleashed": {"cartas_reveladas": 0, "total": 0, "productos": []},
            "Vendetta": {"cartas_reveladas": 0, "total": 0, "productos": []}
        },
        "pull_rates": {}
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(datos_actuales, f, indent=4, ensure_ascii=False)
else:
    with open(json_file, "r", encoding="utf-8") as f:
        datos_actuales = json.load(f)

# ==========================================
# Configuración de Gemini
# ==========================================
client = genai.Client()

mensaje = f"""
Eres el mantenedor automático de la base de datos de Riftbound TCG.
Tu único trabajo es actualizar la información de las expansiones, cartas y productos en formato JSON.

FUENTES PRIORITARIAS:
- riftbound.leagueoflegends.com
- Riot Games

TAREAS:
1. Detectar nuevas expansiones o cartas reveladas.
2. Actualizar el número de cartas y productos de: Origins, Spiritforged, Unleashed, Vendetta.
3. Detectar cambios en Pull Rates.

DATA ACTUAL:
{json.dumps(datos_actuales, indent=2, ensure_ascii=False)}

REGLA CRÍTICA:
Devuelve EXCLUSIVAMENTE el objeto JSON actualizado. No incluyas explicaciones, ni bloques de código markdown, ni texto extra. Si no hay cambios, devuelve el mismo JSON exacto que te di.
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
                # 💡 Corregido: Se quitó response_mime_type porque la API no permite usarlo junto a Google Search
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

# 💡 Corregido: Limpieza inteligente por si Gemini devuelve bloques de markdown como ```json ... ```
if "```json" in texto_respuesta:
    texto_respuesta = texto_respuesta.split("```json")[1].split("```")[0].strip()
elif "```" in texto_respuesta:
    texto_respuesta = texto_respuesta.split("```")[1].split("```")[0].strip()

try:
    datos_nuevos = json.loads(texto_respuesta)
    
    # Verificación de que no eliminó las expansiones clave dentro del JSON
    for exp in ["Origins", "Spiritforged", "Unleashed", "Vendetta"]:
        if "sets" not in datos_nuevos or exp not in datos_nuevos["sets"]:
            raise ValueError(f"Falta la expansión obligatoria dentro del JSON: {exp}")
            
except (json.JSONDecodeError, ValueError) as e:
    print(f"❌ Validación fallida (La IA no devolvió un JSON limpio o compatible): {e}")
    print("Respuesta cruda de la IA para revisar errores:", texto_respuesta)
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
