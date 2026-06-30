import asyncio
import aiohttp
import os
import random
import smtplib
from email.mime.text import MIMEText

ARCHIVO_LISTA = "24/7.m3u"
UMBRAL_SUPERVIVENCIA = 0.60
MUESTRA_CANALES = 20

def enviar_alerta(asunto, cuerpo):
    user = os.environ.get('EMAIL_USER')
    password = os.environ.get('EMAIL_PASS')
    
    if not user or not password:
        return
        
    msg = MIMEText(cuerpo)
    msg['Subject'] = asunto
    msg['From'] = user
    msg['To'] = user
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(user, password)
            server.sendmail(user, user, msg.as_string())
    except Exception:
        pass

async def probar_canal(session, url):
    try:
        async with session.get(url, timeout=5) as response:
            return response.status in [200, 206, 302]
    except:
        return False

async def main():
    if not os.path.exists(ARCHIVO_LISTA):
        enviar_alerta("⚠️ Archivo no encontrado", "No se encontró el M3U base. Se iniciará la extracción completa.")
        print("update_required=true")
        return

    enlaces = [line.strip() for line in open(ARCHIVO_LISTA, 'r', encoding='utf-8') if line.startswith('http')]
    
    if len(enlaces) < 10:
        enviar_alerta("⚠️ Lista casi vacía", "Muy pocos canales detectados. Se iniciará la extracción completa.")
        print("update_required=true")
        return

    muestra = random.sample(enlaces, min(MUESTRA_CANALES, len(enlaces)))
    
    async with aiohttp.ClientSession() as session:
        tareas = [probar_canal(session, url) for url in muestra]
        resultados = await asyncio.gather(*tareas)
        
    tasa = sum(resultados) / len(muestra)
    porcentaje = tasa * 100
    
    if tasa < UMBRAL_SUPERVIVENCIA:
        enviar_alerta("⚠️ Alerta: Canales Caídos", f"La estabilidad cayó al {porcentaje:.1f}%. Se ejecutará la extracción automática en GitHub Actions.")
        print("update_required=true")
    else:
        enviar_alerta("✅ IPTV Estable", f"Los canales están estables con un {porcentaje:.1f}% de funcionalidad. No se requiere extracción.")
        print("update_required=false")

if __name__ == "__main__":
    asyncio.run(main())
