import os
from telethon import TelegramClient
from telethon.sessions import StringSession

# Esto es lo que GitHub Actions inyectará desde los Secrets que configuramos
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_STR = os.getenv('TELEGRAM_SESSION')

# --- PRUEBA DE CONEXIÓN RÁPIDA ---
async def test_conexion():
    try:
        async with TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH) as client:
            me = await client.get_me()
            print(f"✅ Conexión exitosa como: {me.first_name}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

import asyncio
asyncio.run(test_conexion())
