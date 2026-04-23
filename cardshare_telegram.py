import os
import re
import unicodedata
import requests
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# --- CONFIGURACIÓN DINÁMICA ---
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_STR = os.getenv('TELEGRAM_SESSION')
CHANNEL_ID = 'NewcamdCccamIptv'

SERVER_FILE = 'server.txt'
PLAYLIST_FILE = 'lista.m3u'

# --- TUS REQUISITOS ESTRICTOS ---
REQUISITOS_SERIES = ['fantastico', 'magnificos', 'pantera rosa', 'conde patula']
REQUISITOS_VOD = ['rocky', 'volver al futuro', 'shrek para siempre']

# ¡VARIABLE CORREGIDA!
REQUISITOS_REGION = ['colombia', 'chile', 'mexic']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

def leer_url_actual():
    if os.path.exists(SERVER_FILE):
        with open(SERVER_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return 'http://redworld.pro:8880/get.php?username=jhon670&password=eMwQGD7QrzBk&type=m3u_plus&output=ts'

def guardar_todo(url):
    try:
        print("Descargando la lista completa de canales. Esto puede tardar unos segundos...")
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 200 and len(response.text) > 1000:
            with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            with open(SERVER_FILE, 'w', encoding='utf-8') as f:
                f.write(url)
                
            print(f"✅ Archivos {SERVER_FILE} y {PLAYLIST_FILE} guardados exitosamente.")
            return True
        else:
            print(f"⚠️ El servidor bloqueó la descarga de la lista. Error HTTP: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error crítico al descargar o guardar archivos: {e}")
        return False

def extraer_todas_credenciales(texto):
    """Extrae credenciales tanto de URLs completas como de textos sueltos (User/Pass)."""
    credenciales = []
    if not texto: return credenciales
    
    # 1. Buscar URLs completas clásicas
    patron_url = r'(http[s]?://[^/\s]+).*?username=([^&\s]+).*?pas?sword=([^&\s]+)'
    urls = re.findall(patron_url, texto, re.IGNORECASE)
    for host, user, pwd in urls:
        credenciales.append((host, user, pwd))
        
    # 2. Buscar formato de texto suelto
    if not urls:
        hosts = re.findall(r'(http[s]?://[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+(?::\d+)?)', texto)
        users = re.findall(r'(?:user|username|usuario|usr)[\s]*[:=]?[\s]*([^\s]+)', texto, re.IGNORECASE)
        pwds = re.findall(r'(?:pass|password|pwd|clave|contraseña)[\s]*[:=]?[\s]*([^\s]+)', texto, re.IGNORECASE)
        
        for h, u, p in zip(hosts, users, pwds):
            credenciales.append((h.rstrip('/'), u.strip(), p.strip()))
            
    return credenciales

def quitar_tildes(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def validar_calidad_servidor(host, user, pwd):
    try:
        # FASE 1: DESCARGA ULTRARRÁPIDA DE CATEGORÍAS (El ADN)
        r_cat_live = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_categories", headers=HEADERS, timeout=10)
        r_cat_series = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_series_categories", headers=HEADERS, timeout=10)
        
        if r_cat_live.status_code == 200 and r_cat_series.status_code == 200:
            categorias_texto = quitar_tildes(str(r_cat_live.json()).lower() + str(r_cat_series.json()).lower())
            
            # 1.1 Verificamos el Candado Regional en las carpetas
            tiene_region_real = any(req in categorias_texto for req in REQUISITOS_REGION)
            
            # 1.2 Verificamos la Lista Negra (Filtro anti-basura europea)
            servidor_europeo = any(basura in categorias_texto for basura in ['de ✨', 'tr ✨', 'alb ✨', 'uk/us ✨'])
            
            # Si no es de la región o es europeo, lo descartamos en 1 segundo sin descargar nada más
            if not tiene_region_real or servidor_europeo:
                return False

            # FASE 2: VALIDACIÓN PROFUNDA DE CONTENIDO (Solo llega aquí si es VIP y Latino)
            r_live = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_streams", headers=HEADERS, timeout=15)
            r_series = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_series", headers=HEADERS, timeout=15)
            r_vod = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_vod_streams", headers=HEADERS, timeout=15)

            if all(r.status_code == 200 for r in [r_live, r_series, r_vod]):
                vod_data = r_vod.json()
                
                # 2.1 Precisión de URLs (Streams Caídos)
                if isinstance(vod_data, list) and len(vod_data) > 0:
                    fallos_seguidos = 0
                    for item in vod_data[:6]:
                        s_id = item.get('stream_id')
                        ext = item.get('container_extension', 'mp4')
                        if s_id:
                            test_url = f"{host}/movie/{user}/{pwd}/{s_id}.{ext}"
                            try:
                                res = requests.get(test_url, headers=HEADERS, timeout=5, stream=True)
                                status = res.status_code
                                res.close()
                                if status in [200, 206, 302]: break
                                else: fallos_seguidos += 1
                            except: fallos_seguidos += 1
                    
                    if fallos_seguidos >= 5: return False

                # 2.2 Validación de tus gustos estrictos
                c_live = quitar_tildes(str(r_live.json()).lower())
                c_series = quitar_tildes(str(r_series.json()).lower())
                c_vod = quitar_tildes(str(vod_data).lower())
                
                tiene_247 = bool(re.search(r'(?<!not\s)24/7', c_live))
                tiene_clasicos = any(req in c_series for req in REQUISITOS_SERIES)
                tiene_peliculas = any(req in c_vod for req in REQUISITOS_VOD)
                tiene_etiqueta_latina = any(e in (c_live + c_series + c_vod) for e in ['latino', 'espanol'])
                
                if tiene_247 and tiene_clasicos and tiene_peliculas and tiene_etiqueta_latina:
                    return True
    except:
        pass
    return False
async def main():
    current_url = leer_url_actual()
    creds_actuales = extraer_todas_credenciales(current_url)
    
    if creds_actuales:
        host, user, pwd = creds_actuales[0]
        clean_url = f"{host}/get.php?username={user}&password={pwd}&type=m3u_plus&output=ts"
        print(f"Verificando servidor actual: {host}...")
        
        if validar_calidad_servidor(host, user, pwd):
            print("✅ El servidor actual sigue siendo válido a nivel de API.")
            if not os.path.exists(PLAYLIST_FILE) or os.path.getsize(PLAYLIST_FILE) < 100:
                print("⚠️ El archivo lista.m3u está vacío. Intentando descargar...")
                if guardar_todo(clean_url): return
                else: print("❌ El servidor actual no permite descarga directa. Se descarta.")
            else:
                return

    print("\n📡 Extrayendo servidores recientes de Telegram...")
    candidatos_unicos = []
    vistos = set() 
    
    # FASE 1: Extracción ultrarrápida (Evita que Telegram se desconecte)
    async with TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH) as client:
        async for msg in client.iter_messages(CHANNEL_ID, limit=100):
            if not msg.text: continue
            
            candidatos = extraer_todas_credenciales(msg.text)
            for c_host, c_user, c_pwd in candidatos:
                huella = f"{c_host}-{c_user}-{c_pwd}"
                if huella not in vistos:
                    vistos.add(huella)
                    candidatos_unicos.append((c_host, c_user, c_pwd))
                    
    print(f"✅ Se encontraron {len(candidatos_unicos)} candidatos únicos. Cerrando conexión de Telegram...\n")
    
    # FASE 2: Validación tranquila sin depender de Telethon
    for c_host, c_user, c_pwd in candidatos_unicos:
        print(f"Probando candidato: {c_host}...", end=" ")
        
        if validar_calidad_servidor(c_host, c_user, c_pwd):
            final_url = f"{c_host}/get.php?username={c_user}&password={c_pwd}&type=m3u_plus&output=ts"
            if guardar_todo(final_url):
                print("¡ÉXITO TOTAL! Servidor válido y lista descargada.")
                return
            else:
                print("Rechazado: El servidor no permite descargar el archivo m3u.")
        else:
            print("Rechazado: No cumple con el contenido o los streams están caídos.")
            
    print("❌ Ningún servidor nuevo cumplió los requisitos estrictos en esta ronda.")

if __name__ == '__main__':
    asyncio.run(main())
