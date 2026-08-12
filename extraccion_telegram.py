import os
import re
import asyncio
import unicodedata
import aiohttp
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from tqdm.asyncio import tqdm
from tqdm import tqdm as tqdm_sync

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ExtractorIPTV")

# --- CONFIGURACIÓN ---
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
SESSION_STR = os.getenv('TELEGRAM_SESSION', '')

CANALES = ['iptv_m3', 'connecttechnology', 'StbEmucodesStalkerPortal', 'king_network7', 'ListIptvWorld','tugaiptv2025','iptechworld3', 'zigasat','listiptvworld',
           'appinnfeed','satglobaltv']
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

# --- NUEVOS FILTROS ESTRICTOS DE IDIOMA ---
REQUISITOS_REGION = ['colombia', 'chile', 'mexic']
BASURA_EUROPEA = ['de ✨', 'tr ✨', 'alb ✨', 'uk/us ✨', 'ex-yu ✨','IT']

# 1. Blacklist Expandida (Lo que bloqueamos)
BLACKLIST_GLOBAL = r'\b(br|pt|brasil|portugues|legendado|dublado|en|uk|us|usa|english|france|germany|italy|ar|arab|ru|ro|de|tr|fr|nl|pl|in|pk|can|aus|nz|za|ph|movies|kids|news|sports|action|comedy|horror|thriller|entertainment|vip uk|vip us)\b'
BLACKLIST_PREFIJOS = r'^(?:\[|\()? *(en|uk|us|fr|de|it|ar|pt|br|ru|ro|nl|pl|tr|in|pk) *(?:\]|\))? *[:\|\- ]'

# 2. Whitelist Hispana (Lo que EXIGIMOS para aceptar un canal 24/7)
WHITELIST_HISPANA = r'\b(latino|lat|es|espanol|español|castellano|mx|co|cl|ar|pe|ec|ve|bo|uy|py|pr|do|cu|mexico|colombia|chile|argentina|peru|ecuador|venezuela|bolivia|uruguay|paraguay|cuba|puerto rico|infantil|infantiles|peliculas|pelis|series|deportes|documentales|comedia|accion|terror|animacion|novelas|telenovelas|noticias|musica|vivo|retro|clasicos)\b'

mis_busquedas = ['magnificos', 'pantera rosa', 'conde patula', 'volver al futuro', 'shrek para siempre']
regex_clasicos = r'(' + '|'.join(mis_busquedas) + r')'

ARCHIVO_M3U = "24_7.m3u"

# --- FUNCIONES BASE ---
def quitar_tildes(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def extraer_credenciales(texto):
    credenciales = []
    if not texto: return credenciales

    enlaces = re.findall(r'(http[s]?://\S+)', texto)
    for url in enlaces:
        if 'username=' in url.lower() and ('password=' in url.lower() or 'pasword=' in url.lower()):
            host = re.search(r'(http[s]?://[^/]+)', url)
            user = re.search(r'username=([^&]+)', url, re.IGNORECASE)
            pwd = re.search(r'pas?sword=([^&]+)', url, re.IGNORECASE)
            if host and user and pwd:
                credenciales.append((host.group(1), user.group(1), pwd.group(1)))

    if not credenciales:
        h_match = re.search(r'(?:dns|portal|server|host)[\s]*[:=]?[\s]*(http[s]?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?::\d+)?)', texto, re.IGNORECASE)
        u_match = re.search(r'(?:user|username|usuario|usr)[\s]*[:=]?[\s]*([^\s]+)', texto, re.IGNORECASE)
        p_match = re.search(r'(?:pass|password|pwd|clave|contraseña)[\s]*[:=]?[\s]*([^\s]+)', texto, re.IGNORECASE)
        if h_match and u_match and p_match:
            credenciales.append((h_match.group(1), u_match.group(1), p_match.group(1)))

    return credenciales

def leer_historial_m3u():
    candidatos_viejos = {}
    if not os.path.exists(ARCHIVO_M3U):
        logger.info("📁 No hay historial previo. Se creará desde cero.")
        return candidatos_viejos

    logger.info("♻️ Cargando candidatos del historial anterior...")
    try:
        with open(ARCHIVO_M3U, 'r', encoding='utf-8') as f:
            lineas = f.readlines()

        for i in range(len(lineas)):
            if lineas[i].startswith('#EXTINF'):
                metadata = lineas[i]
                url = lineas[i+1].strip() if i+1 < len(lineas) else ""
                if url.startswith('http'):
                    candidatos_viejos[url] = metadata
        logger.info(f"   └─ Se recuperaron {len(candidatos_viejos)} URLs del archivo anterior.")
    except Exception as e:
        logger.error(f"❌ Error leyendo historial M3U: {e}")

    return candidatos_viejos

# --- OPTIMIZACIÓN ASÍNCRONA PARA AUDITORÍA Y EXTRACCIÓN ---
async def auditar_un_servidor(session, row, sem):
    host, user, pwd = row['Host'], row['Usuario'], row['Password']
    url_live = f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_categories"
    url_series = f"{host}/player_api.php?username={user}&password={pwd}&action=get_series_categories"

    async with sem:
        try:
            timeout = aiohttp.ClientTimeout(total=15, sock_connect=5, sock_read=10)
            async with session.get(url_live, headers=HEADERS, timeout=timeout) as res_live, \
                       session.get(url_series, headers=HEADERS, timeout=timeout) as res_series:

                if res_live.status == 200 and res_series.status == 200:
                    json_live = await res_live.json()
                    json_series = await res_series.json()

                    cat_texto = quitar_tildes(str(json_live).lower() + str(json_series).lower())
                    if any(req in cat_texto for req in REQUISITOS_REGION) and not any(b in cat_texto for b in BASURA_EUROPEA):
                        return row
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        except Exception:
            pass
        return None

async def procesar_catalogo_vip(session, vip, candidatos_totales, sem):
    host, user, pwd = vip['Host'], vip['Usuario'], vip['Password']
    url_cats = f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_categories"
    url_streams = f"{host}/player_api.php?username={user}&password={pwd}&action=get_live_streams"

    async with sem:
        dic_cats = {}
        try:
            timeout = aiohttp.ClientTimeout(total=20, sock_connect=5, sock_read=15)
            # 1. Obtener categorías
            async with session.get(url_cats, headers=HEADERS, timeout=timeout) as r_cats:
                if r_cats.status == 200:
                    json_cats = await r_cats.json()
                    dic_cats = {str(c['category_id']): str(c['category_name']) for c in json_cats} # Guardamos nombre original con mayúsculas

            # 2. Obtener streams y procesar
            async with session.get(url_streams, headers=HEADERS, timeout=timeout) as r_live:
                if r_live.status == 200:
                    json_live = await r_live.json()
                    for canal in json_live:
                        nombre = str(canal.get('name', '')).lower()
                        categoria_original = dic_cats.get(str(canal.get('category_id', '')), "")
                        contexto_total = f"{categoria_original.lower()} {nombre}"

                        # === 1. FILTRO BASURA (Blacklist) ===
                        if re.search(BLACKLIST_GLOBAL, contexto_total) or re.search(BLACKLIST_PREFIJOS, nombre):
                            continue

                        # === 2. IDENTIFICACIÓN ===
                        tiene_24_7 = re.search(r'(?:^|\b|:)24/7(?:\b|$)', nombre)
                        es_falso = re.search(r'not\s*24/7', nombre, re.IGNORECASE)
                        es_clasico = re.search(regex_clasicos, nombre)
                        es_win = re.search(r'win sports\s*(?:\+|plus|mas)', nombre)
                        es_directv = re.search(r'directv sports|dsports', nombre)

                        # === 3. VALIDACIÓN ESTRICTA DE HISPANIDAD ===
                        es_hispano = re.search(WHITELIST_HISPANA, contexto_total)

                        guardar_canal = False
                        
                        if es_clasico or es_win or es_directv:
                            guardar_canal = True  # Son búsquedas directas tuyas, pasan directo
                        elif tiene_24_7 and not es_falso:
                            # Si es un canal 24/7 genérico, SOLO pasa si hay evidencia de que es en español
                            if es_hispano:
                                guardar_canal = True

                        # === 4. GUARDADO Y ORDENAMIENTO ===
                        if guardar_canal:
                            s_id = canal.get('stream_id')
                            url_stream = f"{host}/live/{user}/{pwd}/{s_id}.ts"

                            # Mejoramiento de Categorías para el M3U
                            if es_win or es_directv:
                                grupo = "Deportes Premium"
                            elif es_clasico and not tiene_24_7:
                                grupo = "Clásicos en Vivo"
                            else:
                                # Toma el nombre de la categoría del servidor original (Ej: "24/7 Películas Acción")
                                grupo = categoria_original.strip() if categoria_original else "24/7 Latino"

                            n_real = canal.get('name', 'Desconocido')
                            logo = canal.get('stream_icon', '')

                            metadata = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{grupo}",{n_real}\n'
                            candidatos_totales[url_stream] = metadata
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass 
        except Exception as e:
            pass

# --- MOTOR DE VALIDACIÓN ASÍNCRONO ---
async def verificar_canal(session, url, metadata, sem):
    async with sem:
        try:
            timeout = aiohttp.ClientTimeout(total=8, sock_connect=3, sock_read=5)
            async with session.get(url, headers=HEADERS, timeout=timeout) as response:
                if response.status in [200, 206, 302]:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' not in content_type:
                        return (metadata, url)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        except Exception:
            pass
        return None

async def validador_masivo(session, diccionario_canales):
    logger.info(f"⚡ Iniciando validación de señal de {len(diccionario_canales)} canales (Modo Seguro)...")
    sem = asyncio.Semaphore(15)  

    tareas = [verificar_canal(session, url, metadata, sem) for url, metadata in diccionario_canales.items()]
    
    resultados = await tqdm.gather(*tareas, desc="Validando Señales", colour='green')

    canales_vivos = [res for res in resultados if res is not None]
    logger.info(f"✅ Validación completada. Se salvaron {len(canales_vivos)} canales funcionales.")
    return canales_vivos

# --- FLUJO PRINCIPAL ---
async def main_colab():
    logger.info("🚀 Iniciando Arquitectura de Extracción Incremental Optimizada...")

    candidatos_totales = leer_historial_m3u()
    encontrados = []
    vistos = set()

    async with TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH) as client:
        pbar_telegram = tqdm_sync(CANALES, desc="Escaneando Telegram", colour='blue')
        
        for canal in pbar_telegram:
            pbar_telegram.set_postfix_str(f"Canal actual: {canal}")
            try:
                async for msg in client.iter_messages(canal, limit=500):
                    texto_completo = msg.text or ""

                    if msg.document and msg.file.name and msg.file.name.lower().endswith(('.m3u', '.txt')):
                        try:
                            archivo_bytes = await client.download_media(msg, file=bytes)
                            texto_completo += "\n" + archivo_bytes.decode('utf-8', errors='ignore')
                        except Exception as e:
                            pass

                    if not texto_completo.strip(): continue

                    for h, u, p in extraer_credenciales(texto_completo):
                        h_clean = re.sub(r'(http[s]?://)[^@/]+@', r'\1', h).rstrip('/')
                        huella = f"{h_clean}-{u}-{p}"
                        if huella not in vistos:
                            vistos.add(huella)
                            encontrados.append({'Host': h_clean, 'Usuario': u, 'Password': p})

                await asyncio.sleep(2.5)

            except FloodWaitError as fwe:
                logger.warning(f"🛑 Telegram exige espera de {fwe.seconds} segundos. Pausando...")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                pass

    lista_servidores = []
    if encontrados:
        servidores_unicos = {}
        for cred in encontrados:
            host = cred['Host']
            if host not in servidores_unicos:
                servidores_unicos[host] = cred
        lista_servidores = list(servidores_unicos.values())

    async with aiohttp.ClientSession() as session:
        if lista_servidores:
            logger.info(f"🔍 Auditando {len(lista_servidores)} servidores únicos...")
            sem_auditoria = asyncio.Semaphore(10)

            tareas_auditoria = [auditar_un_servidor(session, row, sem_auditoria) for row in lista_servidores]
            resultados_auditoria = await tqdm.gather(*tareas_auditoria, desc="Auditando Servidores", colour='yellow')
            servidores_vip = [res for res in resultados_auditoria if res is not None]
        else:
            servidores_vip = []

        logger.info(f"💎 Se encontraron {len(servidores_vip)} servidores VIP nuevos.")

        if servidores_vip:
            sem_catalogos = asyncio.Semaphore(5) 
            tareas_catalogos = [procesar_catalogo_vip(session, vip, candidatos_totales, sem_catalogos) for vip in servidores_vip]
            await tqdm.gather(*tareas_catalogos, desc="Extrayendo Catálogos", colour='magenta')

        canales_funcionales = await validador_masivo(session, candidatos_totales)

    try:
        with open(ARCHIVO_M3U, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for metadata, url in canales_funcionales:
                f.write(metadata)
                f.write(f"{url}\n")
        logger.info(f"🏆 Proceso finalizado. Archivo '{ARCHIVO_M3U}' actualizado con éxito.")
    except Exception as e:
        logger.error(f"❌ Error al escribir el archivo M3U de salida: {e}")

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_colab())
