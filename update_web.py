import os
import google.generativeai as genai

with open("index.html", "r", encoding="utf-8") as f:
    html_actual = f.read()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config={"max_output_tokens": 16000}
    tools=[{"google_search": {}}]
)

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

response = model.generate_content(mensaje)
html_nuevo = response.text

# Limpia posibles bloques de código que Gemini a veces añade
if html_nuevo.startswith("```"):
    html_nuevo = html_nuevo.split("\n", 1)[1]
if html_nuevo.endswith("```"):
    html_nuevo = html_nuevo.rsplit("```", 1)[0]
html_nuevo = html_nuevo.strip()

if not html_nuevo or len(html_nuevo) < 1000:
    print("⚠️ Respuesta demasiado corta, manteniendo el original")
    exit(0)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_nuevo)

print("✅ HTML actualizado correctamente")
