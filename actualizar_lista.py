# -*- coding: utf-8 -*-
import requests
from thefuzz import process, fuzz
import re
from unidecode import unidecode
import time

# --- CONFIGURACIÓN (Tus servidores) ---
SERVIDORES_M3U = [
    "http://181.78.79.63:1010/playlist.m3u",
    "http://181.78.74.68:8000/playlist.m3u"
]

DICCIONARIO_CATEGORIAS = {
    "CINE": ["GOLDEN","HBO", "TNT", "AMC", "CINEMAX", "STAR", "GOLDEN", "CINECANAL", "PARAMOUNT", "STUDIO", "CINE", "A E",
             "DHE", "DE PELICULA", "AXN", "WARNER", "SONY", "UNIVERSAL","FX","FREE","FILM","MULTIPREMIER","SPACE"],
    "DEPORTES": ["ESPN", "WIN", "FOX SPORTS", "TYC", "GOL", "SPORT", "DIRECTV", "NBA", "F1", "AMERICA SPORTS", "VIA X ESPORTS"],
    "MUSICA": ["MTV", "HTV", "MUSICA", "SALSA", "REGGAETON", "ROMANTICA", "POPULAR", "RUMBA", "LA KALLE", "LATIN POP", "TROPICAL", "MERENGUE", "ZONA LATINA", "CAPITAL"],
    "NACIONALES": ["CARACOL", "RCN", "CITY TV", "CANAL 1", "CANAL UNO", "ESTRELLAS", "AZTECA", "AZ ", "AMERICA TV"],
    "INFANTIL": ["DISNEY", "NICK", "CARTOON", "KIDS", "BABY", "TOON", "BOOMERANG", "INFANTIL", "DISCOVERY KIDS"],
    "NOTICIAS": ["CNN", "BBC", "NTN24", "NOTICIAS", "NEWS", "TELESUR", "DW", "CABLE", "TIEMPO"],
    "CULTURA": ["DISCOVERY", "NAT GEO", "HISTORY", "ANIMAL", "PLANET", "ID", "AGRO", "CULTURA"],
    "RELIGION": ["3ABN", "CRISTOVISION", "ENLACE", "BETHEL", "EWTN", "AVIVAMIENTO"]
}

def obtener_nombres_maestros():
    urls = ["https://epgshare01.online/epgshare01/epg_ripper_CO1.txt", "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.txt"]
    maestro = []
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            nombres = [linea.strip() for linea in r.text.split('\n') if linea.strip()]
            maestro.extend(nombres)
        except: pass
    return list(set(maestro))

def limpieza_estilo_metadata(nombre):
    if not nombre: return ""
    nombre = unidecode(nombre).upper()
    nombre = nombre.replace("&AMP;", " ").replace("&", " ")
    ruido = [r'\.CO', r'\.UY', r'\.AR', r'\.FI', r'\.PH', r'\.HK', r'\.DE', r'\.PL', r'BANDA C', r'TRASN', r'BARRANCA', r'TRANS', r'HD', r'SD', r'4K', r'LATIN']
    for r_word in ruido: nombre = re.sub(r_word, '', nombre)
    return " ".join(re.sub(r'[^A-Z0-9 ]', ' ', nombre).split())

def clasificar_con_logica_mejorada(canal_nombre):
    limpio = limpieza_estilo_metadata(canal_nombre)
    for cat, palabras in DICCIONARIO_CATEGORIAS.items():
        if any(p in limpio for p in palabras): return cat
    return "VARIADOS"

def ejecutar():
    nombres_maestros = obtener_nombres_maestros()
    lista_candidatos = []
    for url in SERVIDORES_M3U:
        try:
            respuesta = requests.get(url, timeout=15)
            lineas = respuesta.text.split('\n')
            for i in range(len(lineas)):
                if lineas[i].strip().upper().startswith("#EXTINF"):
                    nombre = lineas[i].split(',')[-1].strip()
                    if i + 1 < len(lineas) and lineas[i+1].strip().startswith("http"):
                        lista_candidatos.append({"nombre_original": nombre, "url": lineas[i+1].strip()})
        except: pass

    validos, invalidos = [], []
    headers = {'User-Agent': 'VLC/3.0.18'}
    for c in lista_candidatos:
        try:
            with requests.get(c['url'], headers=headers, timeout=5, stream=True) as r:
                if r.status_code == 200:
                    mejor_c, puntaje = process.extractOne(c['nombre_original'], nombres_maestros, scorer=fuzz.token_sort_ratio)
                    nombre_f = mejor_c if puntaje > 80 else c['nombre_original']
                    validos.append({"nombre": nombre_f, "url": c['url']})
                else: invalidos.append(c)
        except: invalidos.append(c)
        time.sleep(0.5)

    with open("lista_final_perfecta.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for v in validos:
            cat = clasificar_con_logica_mejorada(v['nombre'])
            f.write(f'#EXTINF:-1 group-title="{cat}",{v["nombre"]}\n{v["url"]}\n')

    with open("canales_invalidos.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n# REPORTE DE FALLOS\n")
        for inv in invalidos:
            f.write(f"#EXTINF:-1,{inv['nombre_original']}\n{inv['url']}\n")

if __name__ == "__main__":
    ejecutar()
