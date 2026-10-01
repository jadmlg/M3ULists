import os
import re
import random
import asyncio
import aiohttp
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

# --- 1. CONFIGURACIÓN DE ENTORNO (VÍA SECRETS DE GITHUB) ---
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
SESSION_STR = os.getenv('TELEGRAM_SESSION', '')

CANALES_TELEGRAM = ['iptv_m3', 'ListIptvWorld', 'connecttechnology', 'StbEmucodesStalkerPortal', 'king_network7', 'appinnfeed']
ARCHIVO_M3U = "24_7.m3u"
ARCHIVO_BOVEDA = "boveda_servidores.json"
HEADERS_TEST = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) VLC/3.0.18'}

# --- 2. MÓDULO DE SALUD (EL GUARDIÁN) ---
async def verificar_salud_actual():
    """Verifica si la lista actual tiene al menos un 50% de canales vivos."""
    if not os.path.exists(ARCHIVO_M3U):
        print("📁 No existe archivo M3U previo. Se requiere actualización completa.")
        return False

    with open(ARCHIVO_M3U, 'r', encoding='utf-8') as f:
        lineas = f.readlines()
    
    urls = [lineas[i+1].strip() for i in range(len(lineas)) if lineas[i].startswith('#EXTINF') and i+1 < len(lineas)]
    
    if not urls:
        return False

    muestra = random.sample(urls, min(10, len(urls)))
    vivos = 0

    print(f"🩺 Evaluando salud de {len(muestra)} canales de la lista actual...")
    async with aiohttp.ClientSession() as session:
        for url in muestra:
            try:
                async with session.get(url, headers=HEADERS_TEST, timeout=6) as res:
                    if res.status in [200, 206] and 'text/html' not in res.headers.get('Content-Type', '').lower():
                        vivos += 1
            except:
                pass

    tasa_salud = vivos / len(muestra)
    print(f"📊 Tasa de supervivencia: {tasa_salud*100}% ({vivos}/{len(muestra)})")
    
    return tasa_salud >= 0.5

# --- 3. GESTIÓN DE LA BÓVEDA ---
def cargar_boveda():
    if os.path.exists(ARCHIVO_BOVEDA):
        with open(ARCHIVO_BOVEDA, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def guardar_boveda(boveda):
    with open(ARCHIVO_BOVEDA, 'w', encoding='utf-8') as f:
        json.dump(boveda, f, indent=4)

def extraer_credenciales(texto):
    credenciales = []
    enlaces = re.findall(r'(http[s]?://\S+)', texto)
    for url in enlaces:
        if 'username=' in url.lower() and 'password=' in url.lower():
            host = re.search(r'(http[s]?://[^/]+)', url)
            user = re.search(r'username=([^&]+)', url, re.IGNORECASE)
            pwd = re.search(r'pas?sword=([^&]+)', url, re.IGNORECASE)
            if host and user and pwd:
                credenciales.append((host.group(1), user.group(1), pwd.group(1)))
    return credenciales

# --- 4. MÓDULO FRANCOTIRADOR ---
async def probar_y_extraer_vip(session, huella, datos_servidor, boveda, diccionario_resultados, sem):
    host, user, pwd = datos_servidor['Host'], datos_servidor['Usuario'], datos_servidor['Password']
    url_cats = f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_categories"
    url_streams = f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_streams"
    
    async with sem:
        try:
            categorias_objetivo = {}
            async with session.get(url_cats, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10) as r_cats:
                if r_cats.status != 200:
                    raise Exception("Status HTTP no válido")
                
                json_cats = await r_cats.json()
                for c in json_cats:
                    nombre_cat = str(c.get('category_name', '')).strip()
                    nombre_cat_lower = nombre_cat.lower()
                    
                    if ('✅' in nombre_cat and '24/7' in nombre_cat_lower) or nombre_cat_lower == '24/7 vip':
                        categorias_objetivo[str(c['category_id'])] = nombre_cat

            if not categorias_objetivo:
                boveda[huella]['fallos'] = boveda[huella].get('fallos', 0) + 1
                return 

            print(f"🎯 ¡Blanco encontrado en {host}! Categorías VIP: {list(categorias_objetivo.values())}")
            boveda[huella]['estado'] = 'VIP'
            boveda[huella]['fallos'] = 0 

            async with session.get(url_streams, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15) as r_streams:
                if r_streams.status == 200:
                    json_streams = await r_streams.json()
                    for canal in json_streams:
                        cat_id = str(canal.get('category_id', ''))
                        if cat_id in categorias_objetivo:
                            n_real = canal.get('name', 'Desconocido')
                            logo = canal.get('stream_icon', '')
                            grupo = categorias_objetivo[cat_id]
                            s_id = canal.get('stream_id')
                            
                            url_stream = f"{host}/live/{user}/{pwd}/{s_id}.ts"
                            metadata = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{grupo}",{n_real}\n'
                            
                            diccionario_resultados[url_stream] = metadata
                            
        except Exception:
            boveda[huella]['fallos'] = boveda[huella].get('fallos', 0) + 1
            if boveda[huella]['fallos'] >= 3:
                boveda[huella]['estado'] = 'DESCARTADO'

# --- 5. VALIDACIÓN FINAL DE VIDEO (MPEG-TS 0x47) ---
async def test_conexion_final(session, url, metadata, sem):
    async with sem:
        try:
            async with session.get(url, headers=HEADERS_TEST, timeout=10) as res:
                if res.status in [200, 206, 302]:
                    content_type = res.headers.get('Content-Type', '').lower()
                    
                    if any(b in content_type for b in ['text', 'html', 'json']):
                        return None
                    
                    chunk = await res.content.read(1024)
                    
                    es_video_real = False
                    if len(chunk) > 188:
                        for i in range(min(len(chunk), 188)):
                            if chunk[i] == 71:
                                if i + 188 < len(chunk) and chunk[i + 188] == 71:
                                    es_video_real = True
                                    break
                                elif i == 0:
                                    es_video_real = True
                                    break
                    
                    if es_video_real:
                        res.close()
                        return metadata, url
        except:
            pass
        return None

# --- 6. FLUJO PRINCIPAL ---
async def main():
    print("🚀 Iniciando Motor de Bóveda y Extracción 24/7...")
    
    lista_saludable = await verificar_salud_actual()
    if lista_saludable:
        print("✅ La lista actual está en buenas condiciones. Se omite la búsqueda y actualización.")
        return

    print("⚠️ La lista actual está degradada o no existe. Iniciando Bóveda de servidores...")
    boveda = cargar_boveda()
    
    print("📡 Cazando cuentas en Telegram...")
    nuevas_cuentas = 0
    async with TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH) as client:
        for canal in CANALES_TELEGRAM:
            try:
                async for msg in client.iter_messages(canal, limit=150):
                    texto = msg.text or ""
                    if '24/7' in texto.lower() or 'redworld' in texto.lower() or 'http' in texto.lower():
                        for h, u, p in extraer_credenciales(texto):
                            h_clean = re.sub(r'(http[s]?://)[^@/]+@', r'\1', h).rstrip('/')
                            huella = f"{h_clean}-{u}-{p}"
                            
                            if huella not in boveda:
                                boveda[huella] = {
                                    'Host': h_clean, 'Usuario': u, 'Password': p, 
                                    'estado': 'PENDIENTE', 'fallos': 0
                                }
                                nuevas_cuentas += 1
            except Exception:
                pass
            await asyncio.sleep(1)

    print(f"📦 Cacería terminada. Se añadieron {nuevas_cuentas} cuentas nuevas a la Bóveda.")
    guardar_boveda(boveda)

    servidores_activos = {k: v for k, v in boveda.items() if v['estado'] != 'DESCARTADO' and v.get('fallos', 0) < 3}
    print(f"🔍 Auditando {len(servidores_activos)} servidores (Ignorando los descartados)...")

    if not servidores_activos:
        print("❌ No hay servidores viables en la bóveda.")
        return

    canales_candidatos = {}
    async with aiohttp.ClientSession() as session:
        sem_servers = asyncio.Semaphore(15)
        tareas_servers = [probar_y_extraer_vip(session, huella, datos, boveda, canales_candidatos, sem_servers) 
                          for huella, datos in servidores_activos.items()]
        await asyncio.gather(*tareas_servers)

        guardar_boveda(boveda)

        if not canales_candidatos:
            print("💀 Ningún servidor auditado sobrevivió al filtro estricto.")
            return

        print(f"⚡ Validando video real de {len(canales_candidatos)} canales extraídos...")
        sem_streams = asyncio.Semaphore(1)
        
        tareas_streams = [test_conexion_final(session, url, meta, sem_streams) for url, meta in canales_candidatos.items()]
        resultados = await asyncio.gather(*tareas_streams)
        
        canales_funcionales = [r for r in resultados if r is not None]

    if canales_funcionales:
        with open(ARCHIVO_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for meta, url in canales_funcionales:
                f.write(meta)
                f.write(f"{url}\n")
        print(f"🏆 ¡Éxito total! Se guardaron {len(canales_funcionales)} canales premium en {ARCHIVO_M3U}.")
    else:
        print("❌ Ningún canal reproducía imagen real. Las cuentas fueron penalizadas en la Bóveda.")

if __name__ == "__main__":
    asyncio.run(main())
