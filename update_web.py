import os
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# ==========================================
# Leer HTML actual
# ==========================================

if not os.path.exists("index.html"):
    print("❌ Error: No se encuentra el archivo index.html")
    exit(1)

with open("index.html", "r", encoding="utf-8") as f:
    html_actual = f.read()

# ==========================================
# Gemini Configuration
# ==========================================

client = genai.Client()

mensaje = f"""
Eres el mantenedor automático de una base de datos de Riftbound TCG.

OBJETIVO
Mantener la web actualizada usando únicamente información oficial y verificable.

FUENTES PRIORITARIAS

- riftbound.leagueoflegends.com
- Riot Games
- Card galleries oficiales
- Artículos oficiales de Riftbound

TAREAS

1. Detectar nuevas expansiones.
2. Detectar nuevas cartas reveladas.
3. Detectar nuevos productos.
4. Detectar cambios en rarezas.
5. Detectar cambios en pull rates.
6. Completar información que actualmente aparezca como preliminar o pendiente.
7. Corregir errores factuales demostrables.

REGLAS

- NO inventes información.
- NO hagas estimaciones.
- NO cambies estilos CSS.
- NO modifiques JavaScript.
- NO reorganices secciones.
- NO hagas mejoras cosméticas.
- NO reescribas textos por preferencias de estilo.
- Conserva toda la estructura existente.
- NO resumas el código bajo ninguna circunstancia.
- NO uses comentarios como "".
- Debes transcribir CADA UNA de las líneas del HTML original si no sufren cambios.

SOLO modifica contenido cuando:

- exista información nueva oficial
- exista una corrección verificable

Si no encuentras novedades ni correcciones:

DEVUELVE EXACTAMENTE EL MISMO HTML SIN CAMBIOS.

VALIDACIÓN

Antes de responder verifica que siguen existiendo:

- Origins
- Spiritforged
- Unleashed
- Vendetta
- Pull Rates
- const SETS

RESPUESTA

Devuelve exclusivamente HTML válido.
Sin markdown.
Sin explicaciones.
Sin bloques de código.

HTML ACTUAL:

{html_actual}
"""

# ==========================================
# Ejecución con control de cuota (Manejo de Error 429)
# ==========================================

intentos_maximos = 3
espera_inicial = 10  # segundos a esperar si da error 429
response = None

for intento in range(intentos_maximos):
    try:
        print(f"🚀 Enviando solicitud a Gemini (Intento {intento + 1}/{intentos_maximos})...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=mensaje,
            config=types.GenerateContentConfig(
                max_output_tokens=30000,
                temperature=0.1,
                tools=[{"google_search": {}}] 
            )
        )
        # Si la llamada es exitosa, rompemos el bucle de reintentos
        break
    except ClientError as e:
        if e.code == 429:
            print(f"⚠️ Error 429: Límite de cuota alcanzado. Esperando {espera_inicial} segundos antes de reintentar...")
            time.sleep(espera_inicial)
            espera_inicial *= 2  # Aumenta el tiempo de espera para el siguiente intento
        else:
            # Si es otro tipo de error de cliente (400, 403, 404, etc.), fallamos inmediatamente
            print(f"❌ Error de API: {e}")
            exit(1)
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        exit(1)

if not response:
    print("❌ Se agotaron los intentos debido a límites de cuota (429).")
    exit(1)

html_nuevo = response.text.strip()

# ==========================================
# Limpieza markdown
# ==========================================

if html_nuevo.startswith("```html"):
    html_nuevo = html_nuevo.split("```html", 1)[1]

if html_nuevo.startswith("```"):
    html_nuevo = html_nuevo.split("```", 1)[1]

if html_nuevo.endswith("```"):
    html_nuevo = html_nuevo.rsplit("```", 1)[0]

html_nuevo = html_nuevo.strip()

# ==========================================
# Validaciones fuertes
# ==========================================

required_strings = [
    "<html",
    "Origins",
    "Spiritforged",
    "Unleashed",
    "Vendetta",
    "Pull Rates",
    "const SETS"
]

for item in required_strings:
    if item not in html_nuevo:
        print(f"❌ Validación fallida: falta '{item}'")
        exit(0)

if len(html_nuevo) < len(html_actual) * 0.7:
    print("❌ HTML sospechosamente pequeño")
    exit(0)

# ==========================================
# Guardar únicamente si hay cambios
# ==========================================

if html_nuevo == html_actual:
    print("ℹ️ No hay cambios")
    exit(0)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_nuevo)

print("✅ HTML actualizado con éxito")
