import asyncio
import aiohttp
import os
import random

ARCHIVO_LISTA = "27_7.m3u"
UMBRAL_SUPERVIVENCIA = 0.60
MUESTRA_CANALES = 20

async def probar_canal(session, url):
    try:
        async with session.get(url, timeout=5) as response:
            return response.status in [200, 206, 302]
    except:
        return False

async def main():
    if not os.path.exists(ARCHIVO_LISTA):
        print("update_required=true")
        return

    enlaces = [line.strip() for line in open(ARCHIVO_LISTA, 'r', encoding='utf-8') if line.startswith('http')]
    
    if len(enlaces) < 10:
        print("update_required=true")
        return

    muestra = random.sample(enlaces, min(MUESTRA_CANALES, len(enlaces)))
    
    async with aiohttp.ClientSession() as session:
        tareas = [probar_canal(session, url) for url in muestra]
        resultados = await asyncio.gather(*tareas)
        
    tasa = sum(resultados) / len(muestra)
    
    if tasa < UMBRAL_SUPERVIVENCIA:
        print("update_required=true")
    else:
        print("update_required=false")

if __name__ == "__main__":
    asyncio.run(main())
