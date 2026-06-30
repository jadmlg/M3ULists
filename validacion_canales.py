import asyncio
import aiohttp
import os

# --- CONFIGURACIÓN DE PRODUCCIÓN OPTIMIZADA ---
CONCURRENCIA_MAXIMA = 8  
TIMEOUT_SEGUNDOS = 5
ARCHIVO_ENTRADA = "24_7.m3u"
ARCHIVO_SALIDA = "24_7.m3u" # Sobrescribimos sobre el mismo archivo

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Range': 'bytes=0-1048576',
    'Connection': 'keep-alive'
}

canales_procesados = 0
canales_vivos = []

def cargar_candidatos_desde_m3u(ruta_archivo):
    candidatos = {}
    if not os.path.exists(ruta_archivo):
        print(f"⚠️ No se encontró el archivo de entrada: {ruta_archivo}")
        return candidatos
    
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        lineas = f.readlines()
        
    for i in range(len(lineas)):
        if lineas[i].startswith('#EXTINF'):
            metadata = lineas[i].strip()
            url = lineas[i+1].strip() if i+1 < len(lineas) else ""
            if url.startswith('http'):
                candidatos[url] = metadata
    return candidatos

async def validar_trabajador(session, url, metadata, sem, total_objetivo):
    global canales_procesados, canales_vivos
    
    async with sem:
        estado_valido = False
        try:
            nombre_canal = metadata.lower()
            etiquetas_extranjeras = ['[en]', '(en)', 'usa', 'english', '[fr]', '[it]', '[pt]', 'brazil', 'portugues', 'film','serie']
            
            if not any(extranjero in nombre_canal for extranjero in etiquetas_extranjeras):
                timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEGUNDOS)
                async with session.get(url, headers=HEADERS, timeout=timeout) as response:
                    
                    if response.status in [200, 206, 302]:
                        content_type = response.headers.get('Content-Type', '').lower()
                        filtros_basura = ['text/html', 'application/json', 'text/plain']
                        
                        if not any(basura in content_type for basura in filtros_basura):
                            chunk = await response.content.read(1024)
                            
                            if len(chunk) > 0:
                                content_length = int(response.headers.get('Content-Length', 999999))
                                
                                if content_length >= 1000:
                                    es_video_real = False
                                    for i in range(min(len(chunk), 188)):
                                        if chunk[i] == 71: # Protocolo MPEG-TS (0x47)
                                            if i + 188 < len(chunk) and chunk[i + 188] == 71:
                                                es_video_real = True
                                                break
                                            elif i == 0:
                                                es_video_real = True
                                                break
                                    
                                    if es_video_real:
                                        estado_valido = True
        except:
            pass  

        canales_procesados += 1
        if estado_valido:
            canales_vivos.append((metadata, url))
            
        if canales_procesados % 50 == 0 or canales_procesados == total_objetivo:
            porcentaje = (canales_procesados / total_objetivo) * 100
            print(f"🔄 Progreso: {canales_procesados}/{total_objetivo} ({porcentaje:.1f}%) | Vivos: {len(canales_vivos)}")

async def ejecutar_depuracion_total():
    global canales_procesados, canales_vivos
    canales_procesados = 0
    canales_vivos = []

    candidatos_totales = cargar_candidatos_desde_m3u(ARCHIVO_ENTRADA)
    if not candidatos_totales:
        print("⚠️ No hay canales para validar.")
        return

    total_objetivo = len(candidatos_totales)
    print(f"⚡ Iniciando depuración de {total_objetivo} canales...")
    
    sem = asyncio.Semaphore(CONCURRENCIA_MAXIMA)
    
    async with aiohttp.ClientSession() as session:
        tareas = [validar_trabajador(session, url, metadata, sem, total_objetivo) for url, metadata in candidatos_totales.items()]
        await asyncio.gather(*tareas)
    try:
        with open(ARCHIVO_SALIDA, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for metadata, url in canales_vivos:
                # Quitamos el posible salto de línea, agregamos buffer y reescribimos
                base_meta = metadata.strip().replace('tvg-shift="0"', '').replace('cache="1000"', '').replace('buffer-size="5000"', '')
                meta_estabilidad = base_meta + ' cache="1000" buffer-size="5000"'
                f.write(f"{meta_estabilidad}\n{url}\n")
                
        print(f"\n🏆 Depuración terminada. Archivo '{ARCHIVO_SALIDA}' reescrito con {len(canales_vivos)} canales estables.")                    
    except Exception as e:
        print(f"❌ Error al escribir el archivo: {e}")

if __name__ == "__main__":
    asyncio.run(ejecutar_depuracion_total())
