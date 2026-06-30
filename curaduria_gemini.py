import os
import re
import json
import time
import google.generativeai as genai

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("⚠️ No se encontró GEMINI_API_KEY en las variables de entorno.")

genai.configure(api_key=GEMINI_API_KEY)

modelo = genai.GenerativeModel(
    'gemini-2.5-flash', # Actualizado al modelo actual recomendado
    generation_config={"response_mime_type": "application/json"}
)

ARCHIVO_ENTRADA = "24_7.m3u"
ARCHIVO_SALIDA = "Latino_Premium_Curado.m3u"

# --- FUNCIONES DE LIMPIEZA PREVIA ---
def normalizar_nombre(nombre):
    n = nombre.lower()
    n = re.sub(r'\(nuevos vip\)', '', n)
    n = re.sub(r'24/7|24-7|24hrs|24 h', '', n)
    n = re.sub(r'\[.*?\]|\(.*?\)', '', n)
    n = re.sub(r'fhd|hd|sd|4k|tv', '', n)
    n = re.sub(r'exyu|tr|en|uk|us', '', n)
    return n.strip()

def leer_m3u_con_redundancia(ruta):
    print(f"📖 Leyendo archivo en bruto: {ruta}...")
    todos_los_enlaces = []
    nombres_para_ia = set()

    if not os.path.exists(ruta):
        print(f"⚠️ El archivo {ruta} no existe.")
        return todos_los_enlaces, list(nombres_para_ia)

    with open(ruta, 'r', encoding='utf-8') as f:
        lineas = f.readlines()

    for i in range(len(lineas)):
        if lineas[i].startswith('#EXTINF'):
            metadata = lineas[i].strip()
            url = lineas[i+1].strip() if i+1 < len(lineas) else ""

            nombre_crudo = metadata.split(',')[-1]
            nombre_limpio = normalizar_nombre(nombre_crudo)

            if nombre_limpio:
                nombres_para_ia.add(nombre_limpio)
                logo_match = re.search(r'tvg-logo="(.*?)"', metadata)
                logo = logo_match.group(1) if logo_match else ""

                todos_los_enlaces.append({
                    "nombre_limpio": nombre_limpio,
                    "nombre_original": nombre_crudo,
                    "url": url,
                    "logo": logo
                })
    return todos_los_enlaces, list(nombres_para_ia)

# --- EL CEREBRO DEL AGENTE ---
def clasificar_con_ia(lote_nombres):
    prompt_sistema = """
    Eres un curador experto en contenido de TV para Latinoamérica.
    Tu tarea es analizar esta lista de nombres de canales y asignarles una categoría estricta.

    Reglas de Categorización:
    - "Anime": Dragon ball, Naruto, Caballeros del Zodiaco, etc.
    - "Novelas": La Madrastra, Colorina, Pasión de Gavilanes, etc.
    - "Series": Breaking Bad, Chicago Fire, Friends, etc.
    - "Infantil": Peppa, Autos Locos, Cartoon, Disney, etc.
    - "Cine": Películas, Marvel, Acción, etc.
    - "Deportes": Win Sports, DSports, ESPN, etc.
    - "Otros Idiomas": ASIGNA ESTA CATEGORÍA si el nombre parece estar en otro idioma, contenido adulto o no tiene sentido en español.

    Devuelve ÚNICAMENTE un JSON válido donde las claves sean el nombre exacto que te di, y el valor sea la categoría.
    Ejemplo: {"dragon ball z": "Anime", "lud zbunjen normalan": "Otros Idiomas", "win sports +": "Deportes"}
    """

    for intento in range(2):
        try:
            respuesta = modelo.generate_content(f"{prompt_sistema}\n\nCanales a clasificar:\n{json.dumps(lote_nombres)}")
            return json.loads(respuesta.text), True
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Quota exceeded" in error_str:
                print(f"   ⚠️ Límite de cuota detectado (Error 429).")
                return {}, False

            print(f"   ⏳ Error de red ({type(e).__name__}). Reintentando...")
            time.sleep(3)

    return {}, False

# --- FLUJO PRINCIPAL ---
def ejecutar_agente():
    todos_los_enlaces, nombres_unicos = leer_m3u_con_redundancia(ARCHIVO_ENTRADA)
    if not nombres_unicos:
        print("No hay canales para procesar.")
        return

    diccionario_categorias = {}
    tamaño_lote = 50
    lotes_a_procesar = [nombres_unicos[i:i + tamaño_lote] for i in range(0, len(nombres_unicos), tamaño_lote)]
    lotes_fallidos = []

    print(f"\n🤖 Iniciando clasificación de {len(nombres_unicos)} canales únicos...")

    for idx, lote in enumerate(lotes_a_procesar):
        print(f"   Consultando lote {idx + 1} de {len(lotes_a_procesar)}...")
        resultados, exito = clasificar_con_ia(lote)

        if exito:
            diccionario_categorias.update(resultados)
        else:
            print(f"   📦 El lote {idx + 1} falló. A la cola de recuperación.")
            lotes_fallidos.append((idx + 1, lote))

        time.sleep(15)

    if lotes_fallidos:
        print(f"\n🔄 RECUPERACIÓN: {len(lotes_fallidos)} lotes pendientes. Pausando 60s...")
        time.sleep(60)
        ronda = 1
        while lotes_fallidos and ronda <= 2:
            print(f"\n   --- Ronda {ronda} ---")
            lotes_pendientes = lotes_fallidos.copy()
            lotes_fallidos = []

            for num_lote, lote in lotes_pendientes:
                print(f"   Reintentando lote {num_lote}...")
                resultados, exito = clasificar_con_ia(lote)

                if exito:
                    diccionario_categorias.update(resultados)
                    print(f"   ✅ Lote {num_lote} recuperado.")
                else:
                    print(f"   ❌ Lote {num_lote} falló de nuevo.")
                    lotes_fallidos.append((num_lote, lote))
                time.sleep(15)
            
            if lotes_fallidos and ronda < 2:
                time.sleep(60)
            ronda += 1

    print("\n📝 Ensamblando catálogo final...")
    catalogo_final = []

    for canal in todos_los_enlaces:
        nombre_l = canal["nombre_limpio"]
        categoria_asignada = diccionario_categorias.get(nombre_l, "Otros")
        n_orig = canal["nombre_original"]
        url = canal["url"]
        logo = canal["logo"]

        nuevo_metadata = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{categoria_asignada}",{n_orig.replace("(Nuevos VIP)", "").strip()}\n'
        catalogo_final.append(nuevo_metadata + url + "\n")

    with open(ARCHIVO_SALIDA, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        f.writelines(catalogo_final)

    print(f"✅ ¡Terminado! {len(catalogo_final)} enlaces guardados en {ARCHIVO_SALIDA}.")

if __name__ == "__main__":
    ejecutar_agente()
