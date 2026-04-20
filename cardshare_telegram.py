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

# Archivos que actúan como base de datos en tu repositorio
SERVER_FILE = 'server.txt'
PLAYLIST_FILE = 'lista.m3u'

REQUISITOS_SERIES = ['fantastico', 'magnificos', 'pantera rosa']
REQUISITOS_VOD = ['rocky', 'volver al futuro', 'shrek']
REQUISITOS_LIVE = ['24/7']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

def leer_url_actual():
    if os.path.exists(SERVER_FILE):
        with open(SERVER_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def guardar_todo(url):
    """Guarda la URL en server.txt y descarga la lista completa en lista.m3u"""
    try:
        # 1. Guardar la URL de referencia
        with open(SERVER_FILE, 'w', encoding='utf-8') as f:
            f.write(url)
        
        # 2. Descargar y guardar la lista completa para Kodi
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
                f.write(response.text)
            print(f"✅ Archivos {SERVER_FILE} y {PLAYLIST_FILE} actualizados.")
    except Exception as e:
        print(f"❌ Error al guardar archivos: {e}")

def extraer_credenciales(url):
    if not url: return None, None, None
    host = re.search(r'(http[s]?://[^/]+)', url)
    user = re.search(r'username=([^&]+)', url)
    pwd = re.search(r'pas?sword=([^&]+)', url)
    if host and user and pwd:
        return host.group(1), user.group(1), pwd.group(1)
    return None, None, None

def quitar_tildes(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def validar_calidad_servidor(host, user, pwd):
    try:
        r_live = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_streams", headers=HEADERS, timeout=15)
        r_series = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_series", headers=HEADERS, timeout=15)
        r_vod = requests.get(f"{host}/player_api.php?username={user}&password={pwd}&action=get_vod_streams", headers=HEADERS, timeout=15)

        if all(r.status_code == 200 for r in [r_live, r_series, r_vod]):
            c_live = quitar_tildes(str(r_live.json()).lower())
            c_series = quitar_tildes(str(r_series.json()).lower())
            c_vod = quitar_tildes(str(r_vod.json()).lower())
            
            check = [
                any(req in c_live for req in REQUISITOS_LIVE),
                any(req in c_series for req in REQUISITOS_SERIES),
                any(req in c_vod for req in REQUISITOS_VOD),
                any(e in (c_live + c_series + c_vod) for e in ['latino', 'espanol'])
            ]
            return all(check)
    except:
        pass
    return False

async def main():
    current_url = leer_url_actual()
    host, user, pwd = extraer_credenciales(current_url)
    
    if host:
        print(f"Verificando servidor actual: {host}...")
        if validar_calidad_servidor(host, user, pwd):
            print("✅ El servidor actual sigue siendo válido.")
            # Aseguramos que lista.m3u exista aunque el servidor no haya cambiado
            if not os.path.exists(PLAYLIST_FILE):
                guardar_todo(current_url)
            return

    print("❌ Buscando nuevo servidor en Telegram...")
    async with TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH) as client:
        async for msg in client.iter_messages(CHANNEL_ID, limit=100):
            if not msg.text: continue
            urls = re.findall(r'(http[s]?://\S+get\.php\?username=\S+)', msg.text)
            for url_cand in urls:
                c_host, c_user, c_pwd = extraer_credenciales(url_cand)
                if c_host:
                    print(f"Probando: {c_host}...", end=" ")
                    if validar_calidad_servidor(c_host, c_user, c_pwd):
                        final_url = f"{c_host}/get.php?username={c_user}&password={c_pwd}&type=m3u_plus&output=ts"
                        print("¡EXITO!")
                        guardar_todo(final_url)
                        return
                    print("No sirve.")

if __name__ == '__main__':
    asyncio.run(main())
