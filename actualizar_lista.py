# -*- coding: utf-8 -*-
import requests
import re
import time
import os
import smtplib
from email.mime.text import MIMEText
from unidecode import unidecode
from thefuzz import process, fuzz
from datetime import datetime

# --- CONFIGURACIÓN DE ARCHIVOS Y ALERTAS ---
ARCHIVO_SERVIDORES = "servidores.txt"
ARCHIVO_OUT = "servidores_out.txt"
ARCHIVO_LISTA = "lista_final_perfecta.m3u"
ARCHIVO_FALLOS = "canales_invalidos.m3u"
UMBRAL_FALLO_GENERAL = 0.35  # Te avisa si falla más del 35% de la lista

# --- FUNCIÓN DE ENVÍO DE CORREO ---
def enviar_alerta(asunto, cuerpo):
    user = os.environ.get('EMAIL_USER')
    password = os.environ.get('EMAIL_PASS')
    if not user or not password:
        print("⚠️ No se enviará correo: Faltan credenciales en Secrets.")
        return
    
    msg = MIMEText(cuerpo)
    msg['Subject'] = asunto
    msg['From'] = user
    msg['To'] = user # Te lo envías a ti mismo
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, password)
            server.sendmail(user, user, msg.as_string())
        print(f"📧 Alerta enviada: {asunto}")
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")

# --- DICCIONARIO DE CATEGORÍAS ---
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

def obtener_nombres_maestros():
    urls = ["https://epgshare01.online/epgshare01/epg_ripper_CO1.txt", "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.txt"]
    maestro = []
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            maestro.extend([l.strip() for l in r.text.split('\n') if l.strip()])
        except: pass
    return list(set(maestro))

def limpieza_estilo_metadata(nombre):
    if not nombre: return ""
    nombre = unidecode(nombre).upper()
    nombre = nombre.replace("&AMP;", " ").replace("&", " ")
    ruido = [r'\.CO', r'\.UY', r'\.AR', r'\.FI', r'\.PH', r'\.HK', r'\.DE', r'\.PL', r'BANDA C', r'TRASN', r'BARRANCA', r'TRANS', r'HD', r'SD', r'4K', r'LATIN']
    for r_word in ruido: nombre = re.sub(r_word, '', nombre)
    return " ".join(re.sub(r'[^A-Z0-9 ]', ' ', nombre).split())

def clasificar_canal(nombre_canal):
    limpio = limpieza_estilo_metadata(nombre_canal)
    for cat, palabras in DICCIONARIO_CATEGORIAS.items():
        if any(p in limpio for p in palabras): return cat
    return "VARIADOS"

def ejecutar():
    nombres_maestros = obtener_nombres_maestros()
    validos, invalidos, servidores_mantener, servidores_caidos_hoy = [], [], [], []
    headers = {'User-Agent': 'VLC/3.0.18'}
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Estadísticas para Alertas
    win_plus_total = 0
    win_plus_ok = 0

    if not os.path.exists(ARCHIVO_SERVIDORES): return

    with open(ARCHIVO_SERVIDORES, "r", encoding="utf-8") as f:
        urls_servidores = [line.strip() for line in f if line.strip()]

    for url_srv in urls_servidores:
        servidor_funciona = False
        try:
            r = requests.get(url_srv, timeout=15)
            if r.status_code == 200:
                lineas = r.text.split('\n')
                for i in range(len(lineas)):
                    if lineas[i].strip().upper().startswith("#EXTINF"):
                        nombre_org = lineas[i].split(',')[-1].strip()
                        if i + 1 < len(lineas) and lineas[i+1].strip().startswith("http"):
                            link = lineas[i+1].strip()
                            # Monitoreo específico de WIN SPORTS +
                            es_win_plus = "WIN SPORTS +" in nombre_org.upper() or "WIN SPORTS PLUS" in nombre_org.upper()
                            if es_win_plus: win_plus_total += 1

                            try:
                                with requests.get(link, headers=headers, timeout=5, stream=True) as resp:
                                    if resp.status_code == 200:
                                        m, p = process.extractOne(nombre_org, nombres_maestros, scorer=fuzz.token_sort_ratio)
                                        nombre_f = m if p > 80 else nombre_org
                                        validos.append({"nombre": nombre_f, "url": link})
                                        servidor_funciona = True
                                        if es_win_plus: win_plus_ok += 1
                                    else: invalidos.append({"nombre": nombre_org, "url": link})
                            except: invalidos.append({"nombre": nombre_org, "url": link})
                            time.sleep(0.1)
            
            if servidor_funciona: servidores_mantener.append(url_srv)
            else: servidores_caidos_hoy.append(f"{url_srv} - OUT: {fecha_hoy}")
        except: servidores_caidos_hoy.append(f"{url_srv} - OUT: {fecha_hoy}")

    # --- GUARDAR ARCHIVOS ---
    with open(ARCHIVO_SERVIDORES, "w", encoding="utf-8") as f:
        for s in servidores_mantener: f.write(s + "\n")
    if servidores_caidos_hoy:
        with open(ARCHIVO_OUT, "a", encoding="utf-8") as f:
            for s in servidores_caidos_hoy: f.write(s + "\n")
    with open(ARCHIVO_LISTA, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        v_ord = sorted(validos, key=lambda x: (clasificar_canal(x['nombre']), x['nombre']))
        for c in v_ord: f.write(f'#EXTINF:-1 group-title="{clasificar_canal(c["nombre"])}",{c["nombre"]}\n{c["url"]}\n')
    with open(ARCHIVO_FALLOS, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n# FALLOS\n")
        for inv in invalidos: f.write(f"#EXTINF:-1,{inv['nombre']}\n{inv['url']}\n")

    # --- LÓGICA DE ALERTAS POR CORREO ---
    # 1. Alerta Win Sports + estable
    if win_plus_total > 0:
        porc_win = win_plus_ok / win_plus_total
        if porc_win > 0.50:
            enviar_alerta("🔥 ¡Win Sports + Estable!", f"Buenas noticias. El {porc_win*100:.1f}% de tus fuentes de Win Sports + están funcionando ({win_plus_ok}/{win_plus_total}).")

    # 2. Alerta de desastre general (Necesitas nuevos servidores)
    total_total = len(validos) + len(invalidos)
    if total_total > 0:
        tasa_fallo = len(invalidos) / total_total
        if tasa_fallo > UMBRAL_FALLO_GENERAL:
            enviar_alerta("⚠️ Urgente: Tasa de fallo crítica", f"Tu lista está muriendo. El {tasa_fallo*100:.1f}% de los canales han fallado. Es hora de buscar servidores nuevos.")

if __name__ == "__main__":
    ejecutar()
