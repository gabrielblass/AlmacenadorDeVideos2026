import os
os.environ["PYTHONUNBUFFERED"] = "1"

import asyncio
import nest_asyncio
nest_asyncio.apply()

import sys
import aiosqlite
import logging
from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
from aiohttp import web

logging.getLogger("pyrogram").setLevel(logging.ERROR)

# ==========================================
# 1. CONFIGURACIÓN INICIAL
# ==========================================
load_dotenv()

try:
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "").strip()
    SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()
    
    TARGET_CHAT_ID = -1005200605685  # Grupo "Videos Virales"
    BACKUP_CHAT_ID = -1003179132816  # Canal "Gran"
    
    if not API_ID or not API_HASH:
        raise ValueError("Faltan API_ID o API_HASH.")
        
except Exception as e:
    print(f"❌ [ERROR DE CONFIGURACIÓN]: {e}")
    sys.exit(1)

GRUPO_OBJETIVO = "doeujj"
ID_INICIO = 13420
ID_FIN = 22707

DB_NAME = "memoria_eterna.db"

if SESSION_STRING:
    app = Client("mi_radar_2026", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, sleep_threshold=120)
    print("🛡️ Iniciando con Session String Inmortal.")
else:
    app = Client("mi_radar_2026", api_id=API_ID, api_hash=API_HASH, sleep_threshold=120)
    print("⚠️ Iniciando con sesión local.")

albumes_procesados = set()

# ==========================================
# 2. BASE DE DATOS LIMPIA
# ==========================================
async def iniciar_db():
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        await db.execute("DROP TABLE IF EXISTS archivos_enviados")
        await db.execute('''CREATE TABLE archivos_enviados (huella TEXT PRIMARY KEY)''')
        await db.commit()
    print("🧹 Base de datos blanqueada.")

def generar_huella(mensaje):
    if mensaje.photo: return getattr(mensaje.photo, "file_unique_id", None)
    if mensaje.video: return getattr(mensaje.video, "file_unique_id", None)
    if mensaje.animation: return getattr(mensaje.animation, "file_unique_id", None)
    if mensaje.document: return getattr(mensaje.document, "file_unique_id", None)
    return f"msg_texto_{mensaje.id}"

# ==========================================
# 3. MOTOR DE ENVÍO Y RASTREO EXTREMO
# ==========================================
async def procesar_y_enviar(mensaje):
    huella = generar_huella(mensaje)
    if not huella: 
        print(f"⚠️ [IGNORADO] ID {mensaje.id} no generó huella válida.")
        return 0  
    
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        cursor = await db.execute("SELECT 1 FROM archivos_enviados WHERE huella = ?", (huella,))
        if await cursor.fetchone(): 
            print(f"🔁 [DUPLICADO] ID {mensaje.id} saltado, ya estaba en BD.")
            return 0

    # Lógica de Álbumes
    if getattr(mensaje, "media_group_id", None):
        if mensaje.media_group_id in albumes_procesados: return 0
        albumes_procesados.add(mensaje.media_group_id)
        
        try:
            grupo_completo = await app.get_media_group(mensaje.chat.id, mensaje.id)
            media_limpia = []
            huellas_grupo = []
            ids_del_album = [] 
            
            for msg in grupo_completo:
                if ID_INICIO <= msg.id <= ID_FIN:
                    h = generar_huella(msg)
                    if h: huellas_grupo.append(h)
                    txt_original = msg.caption or ""
                    
                    if msg.photo: media_limpia.append(InputMediaPhoto(msg.photo.file_id, caption=txt_original))
                    elif msg.video: media_limpia.append(InputMediaVideo(msg.video.file_id, caption=txt_original))
                    elif msg.animation: media_limpia.append(InputMediaVideo(msg.animation.file_id, caption=txt_original))
                    elif msg.document: media_limpia.append(InputMediaDocument(msg.document.file_id, caption=txt_original))
                        
                    ids_del_album.append(str(msg.id))
            
            if media_limpia:
                await app.send_media_group(TARGET_CHAT_ID, media=media_limpia)
                async with aiosqlite.connect(DB_NAME, timeout=15) as db:
                    for h in huellas_grupo: 
                        await db.execute("INSERT OR IGNORE INTO archivos_enviados (huella) VALUES (?)", (h,))
                    await db.commit()
                print(f"📦 [ÁLBUM COPIADO] IDs exactos: {', '.join(ids_del_album)}")
                await asyncio.sleep(4) 
                return len(media_limpia)
        except Exception as e:
            print(f"❌ [ERROR ÁLBUM ID {mensaje.id}]: {e}")
        return 0

    # Lógica Individual
    while True:
        try:
            await mensaje.copy(chat_id=TARGET_CHAT_ID)
            async with aiosqlite.connect(DB_NAME, timeout=15) as db:
                await db.execute("INSERT OR IGNORE INTO archivos_enviados (huella) VALUES (?)", (huella,))
                await db.commit()
            print(f"🚀 [COPIADO ÉXITO] ID: {mensaje.id}")
            await asyncio.sleep(2.5) 
            return 1 
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            print(f"❌ [ERROR COPIANDO ID {mensaje.id}]: {e}")
            try:
                await app.forward_messages(TARGET_CHAT_ID, mensaje.chat.id, mensaje.id)
                async with aiosqlite.connect(DB_NAME, timeout=15) as db:
                    await db.execute("INSERT OR IGNORE INTO archivos_enviados (huella) VALUES (?)", (huella,))
                    await db.commit()
                print(f"🚀 [REENVIADO COMO RESPALDO] ID: {mensaje.id}")
                await asyncio.sleep(2.5)
                return 1
            except Exception as e2: 
                print(f"❌ [FALLO TOTAL ID {mensaje.id}]: No se pudo ni copiar ni reenviar. Error: {e2}")
                return 0

# ==========================================
# 4. FRANCOTIRADOR LUPA (GRITA TODO)
# ==========================================
async def aspiradora_rangos():
    print(f"\n🎯 MODO LUPA ACTIVO EN: {GRUPO_OBJETIVO}")
    print(f"🔍 Evaluando CADA MENSAJE del {ID_INICIO} al {ID_FIN}...\n")

    contador_rafaga = 0
    
    for inicio_bloque in range(ID_INICIO, ID_FIN + 1, 100):
        fin_bloque = min(ID_FIN, inicio_bloque + 99)
        ids_a_buscar = list(range(inicio_bloque, fin_bloque + 1))
        
        try:
            bloque_mensajes = await app.get_messages(GRUPO_OBJETIVO, ids_a_buscar)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            bloque_mensajes = await app.get_messages(GRUPO_OBJETIVO, ids_a_buscar)
        except Exception as e:
            print(f"⚠️ [FALLO DE CONEXIÓN AL GRUPO] Error en bloque {inicio_bloque}-{fin_bloque}: {e}")
            continue

        for mensaje in bloque_mensajes:
            # SI ESTÁ VACÍO O BORRADO, AHORA TE LO AVISA
            if mensaje is None or getattr(mensaje, "empty", False):
                _id = getattr(mensaje, 'id', 'Desconocido')
                print(f"👻 [FANTASMA/BORRADO] Telegram dice que el ID {_id} ya no existe o está oculto.")
                continue
                
            print(f"👀 [ENCONTRADO] Procesando ID exacto: {mensaje.id}")
            
            if ID_INICIO <= mensaje.id <= ID_FIN:
                archivos_enviados = await procesar_y_enviar(mensaje)
                if archivos_enviados > 0:
                    contador_rafaga += archivos_enviados
                    if contador_rafaga >= 25:
                        print(f"⏸️ 25 alcanzados. Respirando...")
                        await asyncio.sleep(10) 
                        contador_rafaga = 0
        
        await asyncio.sleep(0.5) 
    
    print(f"\n🏁 Rango completado al 100%.")

# ==========================================
# 5. MÓDULO WEB & ARRANQUE
# ==========================================
async def handle(request): return web.Response(text="Francotirador Lupa vivo.")

async def iniciar_web():
    try:
        app_web = web.Application()
        app_web.router.add_get('/', handle)
        runner = web.AppRunner(app_web)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
    except Exception: pass

async def main():
    loop = asyncio.get_event_loop()
    def silenciar_errores(loop, context):
        pass # AHORA DEJAMOS QUE TODOS LOS ERRORES HABLEN
    loop.set_exception_handler(silenciar_errores)

    await iniciar_web() 
    await app.start()
    await iniciar_db()
    
    asyncio.create_task(aspiradora_rangos())
    
    print("✅ Sistema Operativo. Misión en proceso.")
    from pyrogram import idle
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())