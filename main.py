import os
os.environ["PYTHONUNBUFFERED"] = "1"

import asyncio
import nest_asyncio
nest_asyncio.apply()

import sys
import aiosqlite
import logging
from pyrogram import Client, filters
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

# ==========================================
# MODO RANGOS (ESPEJO TOTAL)
# ==========================================
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
# 2. ESCÁNER DE CACHÉ
# ==========================================
async def despertar_ojos():
    print("🧠 Escaneando chats recientes para registrar IDs en la sesión...")
    try:
        async for dialog in app.get_dialogs(limit=300):
            pass
    except Exception:
        pass

    print("✅ Memoria restaurada. Verificando objetivos...")
    
    try:
        await app.get_chat(TARGET_CHAT_ID)
        print(f"👁️ Destino verificado (Videos Virales).")
    except Exception as e: 
        print(f"⚠️ Falló el destino: {e}")
        
    try:
        await app.get_chat(BACKUP_CHAT_ID)
        print(f"👁️ Respaldo verificado (Canal Gran).")
    except Exception as e: 
        print(f"⚠️ Falló el respaldo: {e}")

    try:
        await app.get_chat(GRUPO_OBJETIVO)
        print(f"👁️ Origen verificado ({GRUPO_OBJETIVO}).")
    except Exception as e: 
        print(f"⚠️ Falló el origen: {e}")
                
    print("👁️ Todo listo. Procediendo a extraer contenido exacto...")

# ==========================================
# 3. BASE DE DATOS Y RESPALDOS (LIMPIA)
# ==========================================
async def iniciar_db():
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        await db.execute("DROP TABLE IF EXISTS archivos_enviados")
        await db.execute('''CREATE TABLE archivos_enviados (huella TEXT PRIMARY KEY)''')
        await db.commit()
    print("🧹 Base de datos blanqueada. Iniciando espejo estricto sin saltos.")

async def enviar_respaldo():
    try:
        await asyncio.sleep(2)
        await app.send_document(chat_id=BACKUP_CHAT_ID, document=DB_NAME, caption=f"🛡️ Respaldo Rango {ID_INICIO}-{ID_FIN}")
        print("☁️ [BACKUP] Memoria guardada con éxito en el canal Gran.")
    except Exception as e:
        print(f"⚠️ Error al guardar backup: {e}")

def generar_huella(mensaje):
    # Atrapa TODO para que la base de datos sepa qué copió, sea video o texto puro
    if mensaje.photo: return getattr(mensaje.photo, "file_unique_id", None)
    if mensaje.video: return getattr(mensaje.video, "file_unique_id", None)
    if mensaje.animation: return getattr(mensaje.animation, "file_unique_id", None)
    if mensaje.document: return getattr(mensaje.document, "file_unique_id", None)
    # Si es un texto puro o promo sin archivo:
    return f"msg_texto_{mensaje.id}"

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
# 4. MOTOR DE ENVÍO MODO ESPEJO
# ==========================================
async def procesar_y_enviar(mensaje):
    huella = generar_huella(mensaje)
    if not huella: return 0  
    
    if await es_duplicado(huella):
        if getattr(mensaje, "media_group_id", None):
            albumes_procesados.add(mensaje.media_group_id) 
        return 0

    # Lógica para grupos/álbumes: Mantiene textos originales
    if getattr(mensaje, "media_group_id", None):
        if mensaje.media_group_id in albumes_procesados:
            return 0
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
                    
                    # Se copia TAL CUAL, con su caption (texto) original
                    txt_original = msg.caption or ""
                    
                    if msg.photo: 
                        media_limpia.append(InputMediaPhoto(msg.photo.file_id, caption=txt_original))
                    elif msg.video: 
                        media_limpia.append(InputMediaVideo(msg.video.file_id, caption=txt_original))
                    elif msg.animation: 
                        media_limpia.append(InputMediaVideo(msg.animation.file_id, caption=txt_original))
                    elif msg.document: 
                        media_limpia.append(InputMediaDocument(msg.document.file_id, caption=txt_original))
                        
                    ids_del_album.append(str(msg.id))
            
            if media_limpia:
                await app.send_media_group(TARGET_CHAT_ID, media=media_limpia)
                for h in huellas_grupo: await registrar_huella(h)
                
                print(f"📦 [ÁLBUM ESPEJO] IDs agrupados: {', '.join(ids_del_album)}")
                await asyncio.sleep(4) 
                return len(media_limpia)
                
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception:
            pass
        return 0

    # Lógica para individuales o promos puras: Mantiene todo tal cual
    while True:
        try:
            await mensaje.copy(chat_id=TARGET_CHAT_ID) # Ya no le borra el caption a nada
            await registrar_huella(huella)
            print(f"🚀 [ESPEJO EXACTO] ID real: {mensaje.id}")
            await asyncio.sleep(2.5) 
            return 1 
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            if "Peer id invalid" in str(e) or "CHAT_ID_INVALID" in str(e):
                try:
                    await app.forward_messages(TARGET_CHAT_ID, mensaje.chat.id, mensaje.id)
                    await registrar_huella(huella)
                    print(f"🚀 [REENVIADO] ID real: {mensaje.id}")
                    await asyncio.sleep(2.5)
                    return 1
                except Exception: return 0
            return 0

# ==========================================
# 5. BARRIDO CRONOLÓGICO TOTAL
# ==========================================
async def aspiradora_rangos():
    print(f"\n🎯 MODO ESPEJO ACTIVO EN: {GRUPO_OBJETIVO}")
    print(f"🔍 Copiando absolutamente todo del {ID_INICIO} al {ID_FIN}...")

    contador_rafaga = 0
    
    for inicio_bloque in range(ID_INICIO, ID_FIN + 1, 100):
        fin_bloque = min(ID_FIN, inicio_bloque + 99)
        ids_a_buscar = list(range(inicio_bloque, fin_bloque + 1))
        
        try:
            bloque_mensajes = await app.get_messages(GRUPO_OBJETIVO, ids_a_buscar)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            bloque_mensajes = await app.get_messages(GRUPO_OBJETIVO, ids_a_buscar)
        except Exception:
            continue

        for mensaje in bloque_mensajes:
            if mensaje is None or mensaje.empty:
                continue
                
            # 🔥 YA NO FILTRA MULTIMEDIA. ENVÍA CUALQUIER MENSAJE QUE EXISTA EN ESE RANGO 🔥
            if ID_INICIO <= mensaje.id <= ID_FIN:
                archivos_enviados = await procesar_y_enviar(mensaje)
                
                if archivos_enviados > 0:
                    contador_rafaga += archivos_enviados
                    
                    if contador_rafaga >= 25:
                        print(f"⏸️ 25 mensajes alcanzados. Guardando el .db por seguridad...")
                        await enviar_respaldo()
                        await asyncio.sleep(15) 
                        contador_rafaga = 0
        
        await asyncio.sleep(0.5) 
    
    await enviar_respaldo()
    print(f"🏁 Rango completado al 100%. Misión cumplida.")

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
    await iniciar_db()
    
    asyncio.create_task(aspiradora_rangos())
    
    print("✅ Sistema Operativo. Misión en proceso.")
    from pyrogram import idle
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())