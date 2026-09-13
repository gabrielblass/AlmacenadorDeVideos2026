import os
# 🔥 ESTO OBLIGA A RENDER A ESCUPIR LOS TEXTOS EN VIVO 🔥
os.environ["PYTHONUNBUFFERED"] = "1"

import asyncio
import nest_asyncio
nest_asyncio.apply()

import sys
import aiosqlite
import logging
from pyrogram import Client, filters
from pyrogram.enums import MessagesFilter
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
from aiohttp import web

# Ocultar advertencias molestas
logging.getLogger("pyrogram").setLevel(logging.ERROR)

# ==========================================
# 1. CONFIGURACIÓN INICIAL
# ==========================================
load_dotenv()

try:
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "").strip()
    
    # 🔥 DESTINO FORZADO 🔥
    TARGET_CHAT_ID = 5200605685 
    
    RAW_BACKUP = os.environ.get("BACKUP_CHAT_ID", "").strip().replace('"', '').replace("'", "")
    SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()
    
    if not API_ID or not API_HASH:
        raise ValueError("Faltan API_ID o API_HASH.")
    if not RAW_BACKUP:
        raise ValueError("Falta BACKUP_CHAT_ID en Render.")
        
    BACKUP_CHAT_ID = int(RAW_BACKUP)
except Exception as e:
    print(f"❌ [ERROR DE CONFIGURACIÓN]: {e}")
    sys.exit(1)

# 🔥 ======================================== 🔥
# 🔥 MODO RANGOS (FRANCOTIRADOR)              🔥
# 🔥 ======================================== 🔥
GRUPO_OBJETIVO = "doeujj"
ID_INICIO = 13420
ID_FIN = 22707
# 🔥 ======================================== 🔥

DB_NAME = "memoria_eterna.db"

if SESSION_STRING:
    app = Client("mi_radar_2026", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, sleep_threshold=120)
    print("🛡️ Iniciando con Session String Inmortal.")
else:
    app = Client("mi_radar_2026", api_id=API_ID, api_hash=API_HASH, sleep_threshold=120)
    print("⚠️ Iniciando con sesión local.")

albumes_procesados = set()

# ==========================================
# 2. VERIFICACIÓN DIRECTA (SIN ESCANEAR OTROS GRUPOS)
# ==========================================
async def despertar_ojos():
    print("🧠 Verificando conexiones objetivo (Ignorando grupos fantasma)...")
    try:
        await app.get_chat(TARGET_CHAT_ID)
        print(f"👁️ Destino verificado.")
    except Exception as e: pass
        
    try:
        await app.get_chat(BACKUP_CHAT_ID)
        print(f"👁️ Respaldo verificado.")
    except Exception as e: pass

    try:
        await app.get_chat(GRUPO_OBJETIVO)
        print(f"👁️ Origen verificado.")
    except Exception as e: pass
                
    print("👁️ Ojos operativos al 100%. Procediendo a extraer videos...")

# ==========================================
# 3. BASE DE DATOS Y RESPALDOS 
# ==========================================
async def iniciar_db():
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS archivos_enviados 
                            (huella TEXT PRIMARY KEY)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS progreso_grupos 
                            (chat_id TEXT PRIMARY KEY, ultimo_mensaje_id INTEGER)''')
        await db.commit()

async def enviar_respaldo():
    if not BACKUP_CHAT_ID: return
    try:
        await asyncio.sleep(2)
        await app.send_document(chat_id=BACKUP_CHAT_ID, document=DB_NAME, caption=f"🛡️ Respaldo Rango {ID_INICIO}-{ID_FIN}")
        print("☁️ [BACKUP] Memoria guardada con éxito en tu chat.")
    except Exception as e:
        pass

async def descargar_respaldo():
    print("🔄 Buscando tu archivo .db en el chat de respaldo...")
    try:
        async for mensaje in app.get_chat_history(BACKUP_CHAT_ID, limit=50):
            if mensaje.document and mensaje.document.file_name.endswith(".db"):
                print(f"📥 ¡TE ENCONTRÉ, MEMORIA!: {mensaje.document.file_name}")
                await app.download_media(mensaje.document, file_name=DB_NAME)
                print("✅ Memoria inyectada. Retomando donde se quedó sin duplicar.")
                return
        print("⚠️ No hay archivo .db reciente. Arrancando el rango desde cero.")
    except Exception as e:
        print(f"⚠️ Aviso al leer respaldo: {e}")

def generar_huella(mensaje):
    media = mensaje.photo or mensaje.video
    if not media: return None
    return getattr(media, "file_unique_id", None)

async def es_duplicado(huella):
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        cursor = await db.execute("SELECT 1 FROM archivos_enviados WHERE huella = ?", (huella,))
        resultado = await cursor.fetchone()
        return bool(resultado)

async def registrar_huella(huella):
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        await db.execute("INSERT OR IGNORE INTO archivos_enviados (huella) VALUES (?)", (huella,))
        await db.commit()

# ==========================================
# 4. MOTOR DE ENVÍO
# ==========================================
async def procesar_y_enviar(mensaje):
    huella = generar_huella(mensaje)
    if not huella: return 0  
    
    if await es_duplicado(huella):
        if getattr(mensaje, "media_group_id", None):
            albumes_procesados.add(mensaje.media_group_id) 
        return 0

    if getattr(mensaje, "media_group_id", None):
        if mensaje.media_group_id in albumes_procesados:
            return 0
        albumes_procesados.add(mensaje.media_group_id)
        
        try:
            grupo_completo = await app.get_media_group(mensaje.chat.id, mensaje.id)
            media_limpia = []
            huellas_grupo = []
            for msg in grupo_completo:
                h = generar_huella(msg)
                if h: huellas_grupo.append(h)
                if msg.photo: media_limpia.append(InputMediaPhoto(msg.photo.file_id, caption=""))
                elif msg.video: media_limpia.append(InputMediaVideo(msg.video.file_id, caption=""))
            
            if media_limpia:
                await app.send_media_group(TARGET_CHAT_ID, media=media_limpia)
                for h in huellas_grupo: await registrar_huella(h)
                print(f"📦 [ENVIADO] ÁLBUM copiado (ID: {mensaje.id}).")
                await asyncio.sleep(4) 
                return len(media_limpia)
                
        except FloodWait as e:
            print(f"🚨 Telegram pide descansar {e.value}s... Esperando.")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            if "Peer id invalid" in str(e) or "CHAT_ID_INVALID" in str(e):
                try:
                    msg_ids = [m.id for m in grupo_completo]
                    await app.forward_messages(TARGET_CHAT_ID, mensaje.chat.id, msg_ids)
                    for h in huellas_grupo: await registrar_huella(h)
                    print(f"📦 [REENVIADO FORZOSO] ÁLBUM superó el bloqueo (ID: {mensaje.id}).")
                    await asyncio.sleep(4)
                    return len(msg_ids)
                except Exception as e2: pass
        return 0

    while True:
        try:
            await mensaje.copy(chat_id=TARGET_CHAT_ID, caption="")
            await registrar_huella(huella)
            print(f"🚀 [ENVIADO] INDIVIDUAL copiado | ID: {mensaje.id}")
            await asyncio.sleep(2) 
            return 1 
        except FloodWait as e:
            print(f"🚨 Telegram pide descansar {e.value}s... Esperando.")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            if "Peer id invalid" in str(e) or "CHAT_ID_INVALID" in str(e):
                try:
                    await app.forward_messages(TARGET_CHAT_ID, mensaje.chat.id, mensaje.id)
                    await registrar_huella(huella)
                    print(f"🚀 [REENVIADO FORZOSO] INDIVIDUAL superó el bloqueo | ID: {mensaje.id}")
                    await asyncio.sleep(2)
                    return 1
                except Exception as e2: return 0
            return 0

# ==========================================
# 5. EL FRANCOTIRADOR (POR RANGOS)
# ==========================================
async def aspiradora_rangos():
    print(f"\n🎯 FRANCOTIRADOR ACTIVADO EN: {GRUPO_OBJETIVO}")
    print(f"🔍 Extrayendo EXCLUSIVAMENTE del mensaje {ID_INICIO} al {ID_FIN}...")

    contador_rafaga = 0
    
    for inicio_bloque in range(ID_INICIO, ID_FIN + 1, 200):
        fin_bloque = min(inicio_bloque + 199, ID_FIN)
        ids_a_buscar = list(range(inicio_bloque, fin_bloque + 1))
        
        try:
            bloque_mensajes = await app.get_messages(GRUPO_OBJETIVO, ids_a_buscar)
        except FloodWait as e:
            print(f"🚨 Freno de lectura. Pausa de {e.value}s...")
            await asyncio.sleep(e.value + 1)
            bloque_mensajes = await app.get_messages(GRUPO_OBJETIVO, ids_a_buscar)
        except Exception as e:
            continue

        for mensaje in bloque_mensajes:
            if mensaje is None or mensaje.empty:
                continue
                
            if mensaje.photo or mensaje.video:
                archivos_enviados = await procesar_y_enviar(mensaje)
                
                if archivos_enviados > 0:
                    contador_rafaga += archivos_enviados
                    
                    if contador_rafaga >= 25:
                        print(f"⏸️ 25 archivos alcanzados. Guardando el .db por seguridad...")
                        await enviar_respaldo()
                        await asyncio.sleep(60) 
                        contador_rafaga = 0
        
        await asyncio.sleep(2) 
    
    await enviar_respaldo()
    print(f"🏁 Rango de {ID_INICIO} a {ID_FIN} completado al 100%. Misión cumplida.")

# ==========================================
# 6. MÓDULO WEB & ARRANQUE
# ==========================================
async def handle(request): return web.Response(text="Francotirador vivo.")

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
        msg = str(context.get("message", ""))
        if "Peer id invalid" in msg or "Task exception" in msg: return 
        loop.default_exception_handler(context)
    loop.set_exception_handler(silenciar_errores)

    await iniciar_web() 
    await app.start()

    await despertar_ojos()
    await descargar_respaldo()
    await iniciar_db()
    
    asyncio.create_task(aspiradora_rangos())
    
    print("✅ Sistema Operativo. Misión en proceso.")
    from pyrogram import idle
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())