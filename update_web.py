import os
from google import genai
from google.genai import types

# 1. Leer el HTML actual
with open("index.html", "r", encoding="utf-8") as f:
    html_actual = f.read()

# 2. Inicializar el cliente oficial moderno
# El cliente busca automáticamente la variable "GEMINI_API_KEY" en el entorno
client = genai.Client()

mensaje = f"""Eres un experto en el TCG Riftbound (el juego de cartas de League of Legends).
Tienes esta página web en HTML que es una base de datos del juego.

## TAREA PRINCIPAL — Buscar novedades antes de editar

Busca en la web información actualizada sobre Riftbound:
- "Riftbound TCG new set"
- "Riftbound Vendetta card gallery"
- "riftbound.leagueoflegends.com"
- Cualquier set o expansión que NO aparezca ya en el HTML

## REGLAS según lo que encuentres

### Si encuentras una colección NUEVA que no está en el HTML:
- Añade una sección completa con el mismo formato que las existentes
- Incluye: nombre, fecha, número de cartas, leyendas, mecánicas nuevas, tabla OVR/Showcase
- Si los datos son parciales, márcalos como "preliminares"
- Actualiza la sección "Visión General" con los nuevos totales
- Actualiza la tabla de Pull Rates con la nueva columna

### Si Vendetta ya ha salido (fecha >= 31 julio 2026) y encuentras su card list completa:
- Rellena todos los datos que faltan en la sección Vendetta
- Quita el aviso de "datos preliminares" si los datos son definitivos
- Añade la tabla completa de OVR/Showcase

### Si no encuentras nada nuevo:
- Haz una mejora pequeña al HTML existente (redacción, claridad, corrección de datos)
- No inventes datos de cartas

## FORMATO DE RESPUESTA
Devuelve SOLO el HTML completo, sin explicaciones, sin markdown, sin bloques de código.

## HTML ACTUAL:
{html_actual}"""

# 3. Ejecutar la llamada con Gemini 3.5 Flash y Google Search activado de forma nativa
response = client.models.generate_content(
    model='gemini-3.5-flash',
    contents=mensaje,
    config=types.GenerateContentConfig(
        max_output_tokens=16000,
        tools=[types.Tool(google_search=types.GoogleSearch())] # Sintaxis correcta del nuevo SDK
    )
)

html_nuevo = response.text

# 4. Limpieza de bloques markdown molestos
if html_nuevo.startswith("```html"):
    html_nuevo = html_nuevo.split("```html", 1)[1]
elif html_nuevo.startswith("```"):
    html_nuevo = html_nuevo.split("```", 1)[1]

if html_nuevo.endswith("```"):
    html_nuevo = html_nuevo.rsplit("```", 1)[0]

html_nuevo = html_nuevo.strip()

# 5. Validación elemental de seguridad
if not html_nuevo or len(html_nuevo) < 1000 or "<html" not in html_nuevo:
    print("⚠️ Respuesta inválida o vacía. Manteniendo el archivo original.")
    exit(0)

# 6. Guardar los cambios
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_nuevo)

print("✅ HTML actualizado correctamente con el nuevo SDK")
