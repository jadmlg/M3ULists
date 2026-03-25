# -*- coding: utf-8 -*-
import requests
import re
import time
import os
from unidecode import unidecode
from thefuzz import process, fuzz
from datetime import datetime

# --- CONFIGURACIÓN DE ARCHIVOS ---
ARCHIVO_SERVIDORES = "servidores.txt"
ARCHIVO_OUT = "servidores_out.txt"
ARCHIVO_LISTA = "lista_final_perfecta.m3u"
ARCHIVO_FALLOS = "canales_invalidos.m3u"

# --- DICCIONARIO DE CATEGORÍAS (Tu versión optimizada) ---
DICCIONARIO_CATEGORIAS = {
    "CINE": ["GOLDEN","HBO", "TNT", "AMC", "CINEMAX", "STAR", "GOLDEN", "CINECANAL", "PARAMOUNT", "STUDIO", "CINE", "A E",
             "DHE", "DE PELICULA", "AXN", "WARNER", "SONY", "UNIVERSAL","FX","FREE","FILM","MULTIPREMIER","SPACE", "TCM"],
    "DEPORTES": ["ESPN", "WIN", "FOX SPORTS", "TYC", "GOL", "SPORT", "DIRECTV", "NBA", "F1", "AMERICA SPORTS", "VIA X ESPORTS"],
    "MUSICA": ["MTV", "HTV", "MUSICA", "SALSA", "REGGAETON", "ROMANTICA", "POPULAR", "RUMBA", "LA KALLE", "LATIN POP", "TROPICAL", "MERENGUE", "ZONA LATINA", "CAPITAL"],
    "NACIONALES": ["CARACOL", "RCN", "CITY TV", "CANAL 1", "CANAL UNO", "ESTRELLAS", "AZTECA", "AZ ", "AMERICA TV", "TELEANTIOQUIA", "TELECAFE", "TELECARIBE", "TELEPACIFICO", "SEÑAL COLOMBIA"], 
    "INFANTIL": ["DISNEY", "NICK", "CARTOON", "KIDS", "BABY", "TOON", "BOOMERANG", "INFANTIL", "DISCOVERY KIDS"],
    "NOTICIAS": ["CNN", "BBC", "NTN24", "NOTICIAS", "NEWS", "TELESUR", "DW", "CABLE", "TIEMPO", "24 HORAS"],
    "CULTURA": ["DISCOVERY", "NAT GEO", "HISTORY", "ANIMAL", "PLANET", "ID", "AGRO", "CULTURA", "GURMET", "GOURMET"],
    "RELIGION": ["3ABN", "CRISTOVISION", "ENLACE", "BETHEL", "EWTN", "AVIVAMIENTO"]
}

# --- FUNCIONES DE APOYO ---
def obtener_nombres_maestros():
    urls = [
        "https://epgshare01.online/epgshare01/epg_ripper_CO1.txt",
        "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.txt"
    ]
    maestro = []
    print("⏳ Descargando diccionarios de nombres maestros...")
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            nombres = [linea.strip() for linea in r.text.split('\n') if linea.strip()]
            maestro.extend(nombres)
        except:
            print(f"⚠️ No se pudo descargar de: {url}")
    return list(set(maestro))

def limpieza_estilo_metadata(nombre):
    if not nombre: return ""
    nombre = unidecode(nombre).upper()
    nombre = nombre.replace("&AMP;", " ").replace("&", " ")
    ruido = [
        r'\.CO', r'\.UY', r'\.AR', r'\.FI', r'\.PH', r'\.HK', r'\.DE', r'\.PL', 
        r'BANDA C', r'TRASN', r'BARRANCA', r'TRANS', r'HD', r'SD', r'4K', r'LATIN'
    ]
    for r_word in ruido:
        nombre = re.sub(r_word, '', nombre)
    return " ".join(re.sub(r'[^A-Z0-9 ]', ' ', nombre).split())

def clasificar_canal(nombre_canal):
    limpio = limpieza_estilo_metadata(nombre_canal)
    for cat, palabras in DICCIONARIO_CATEGORIAS.items():
        if any(p in limpio for p in palabras):
            return cat
    return "VARIADOS"

# --- PROCESO PRINCIPAL ---
def ejecutar():
    nombres_maestros = obtener_nombres_maestros()
    validos = []
    invalidos = []
    servidores_mantener = []
    servidores_caidos_hoy = []
    headers = {'User-Agent': 'VLC/3.0.18'}
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Leer servidores.txt
    if not os.path.exists(ARCHIVO_SERVIDORES):
        print(f"❌ Error: El archivo {ARCHIVO_SERVIDORES} no existe.")
        return

    with open(ARCHIVO_SERVIDORES, "r", encoding="utf-8") as f:
        urls_servidores = [line.strip() for line in f if line.strip()]

    print(f"🚀 Iniciando revisión de {len(urls_servidores)} servidores...")

    for url_srv in urls_servidores:
        print(f"\n🌐 Analizando: {url_srv}")
        servidor_funciona = False
        
        try:
            r = requests.get(url_srv, timeout=15)
            if r.status_code == 200:
                lineas = r.text.split('\n')
                candidatos_srv = []
                
                # Extraer estructura del M3U
                for i in range(len(lineas)):
                    linea = lineas[i].strip()
                    if linea.upper().startswith("#EXTINF"):
                        nombre_org = linea.split(',')[-1].strip()
                        if i + 1 < len(lineas):
                            url_canal = lineas[i+1].strip()
                            if url_canal.startswith("http"):
                                candidatos_srv.append({"nombre": nombre_org, "url": url_canal})

                # Probar canales del servidor
                for canal in candidatos_srv:
                    try:
                        with requests.get(canal['url'], headers=headers, timeout=5, stream=True) as resp:
                            if resp.status_code == 200:
                                # Estandarizar nombre con EPG
                                mejor_match, puntaje = process.extractOne(
                                    canal['nombre'], 
                                    nombres_maestros, 
                                    scorer=fuzz.token_sort_ratio
                                )
                                nombre_final = mejor_match if puntaje > 80 else canal['nombre']
                                
                                validos.append({"nombre": nombre_final, "url": canal['url']})
                                servidor_funciona = True
                            else:
                                invalidos.append(canal)
                    except:
                        invalidos.append(canal)
                    time.sleep(0.2) # Pausa para evitar bloqueos
            
            if servidor_funciona:
                servidores_mantener.append(url_srv)
            else:
                print(f"⚠️ Servidor sin canales activos: {url_srv}")
                servidores_caidos_hoy.append(f"{url_srv} - OUT: {fecha_hoy}")

        except Exception as e:
            print(f"❌ Error de conexión con el servidor: {url_srv}")
            servidores_caidos_hoy.append(f"{url_srv} - OUT: {fecha_hoy}")

    # --- 1. ACTUALIZAR SERVIDORES ---
    with open(ARCHIVO_SERVIDORES, "w", encoding="utf-8") as f:
        for s in servidores_mantener:
            f.write(s + "\n")

    # --- 2. REGISTRAR CAÍDOS (Rastro) ---
    if servidores_caidos_hoy:
        with open(ARCHIVO_OUT, "a", encoding="utf-8") as f:
            for s in servidores_caidos_hoy:
                f.write(s + "\n")

    # --- 3. ESCRIBIR M3U FINAL ---
    with open(ARCHIVO_LISTA, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        # Ordenar por categoría y luego por nombre
        validos_ordenados = sorted(validos, key=lambda x: (clasificar_canal(x['nombre']), x['nombre']))
        for c in validos_ordenados:
            cat = clasificar_canal(c['nombre'])
            f.write(f'#EXTINF:-1 group-title="{cat}",{c["nombre"]}\n')
            f.write(f"{c['url']}\n")

    # --- 4. ESCRIBIR REPORTE DE FALLOS ---
    with open(ARCHIVO_FALLOS, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n# REPORTE DE CANALES CAÍDOS\n")
        for inv in invalidos:
            f.write(f"#EXTINF:-1,{inv['nombre']}\n")
            f.write(f"{inv['url']}\n")

    print(f"\n✅ PROCESO FINALIZADO ✅")
    print(f"📈 Servidores Activos: {len(servidores_mantener)}")
    print(f"📉 Servidores Eliminados: {len(servidores_caidos_hoy)}")
    print(f"📺 Canales Válidos: {len(validos)}")

if __name__ == "__main__":
    ejecutar()
