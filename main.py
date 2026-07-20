import asyncio
import nest_asyncio
nest_asyncio.apply()

import os
import sys
import aiosqlite
import logging
from pyrogram import Client, filters
from pyrogram.enums import MessagesFilter
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
from aiohttp import web

# Ocultar advertencias molestas internas de Pyrogram
logging.getLogger("pyrogram").setLevel(logging.ERROR)

# ==========================================
# 1. CONFIGURACIÓN INICIAL & PREVENCIÓN DE ERRORES
# ==========================================
load_dotenv()

# VALIDACIÓN ESTRICTA
try:
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "").strip()
    RAW_TARGET = os.environ.get("TARGET_CHAT_ID", "").strip().replace('"', '').replace("'", "")
    RAW_BACKUP = os.environ.get("BACKUP_CHAT_ID", "").strip().replace('"', '').replace("'", "")
        
    SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()
    
    if not API_ID or not API_HASH:
        raise ValueError("Faltan API_ID o API_HASH.")
    if not RAW_TARGET:
        raise ValueError("Falta TARGET_CHAT_ID.")
    if not RAW_BACKUP:
        raise ValueError("Falta BACKUP_CHAT_ID. Sin esto el bot perderá la memoria en Render.")
        
    TARGET_CHAT_ID = int(RAW_TARGET)
    BACKUP_CHAT_ID = int(RAW_BACKUP)
except Exception as e:
    print(f"❌ [ERROR FATAL DE CONFIGURACIÓN] Revisa tu panel de Render o .env: {e}")
    sys.exit(1)

# 🔥 CEREBRO TOTALMENTE NUEVO 🔥
DB_NAME = "memoria_definitiva_27.db"

# 🔥 BLINDAJE DE SESIÓN CONTRA RENDER 🔥
if SESSION_STRING:
    app = Client("mi_radar_2026", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, sleep_threshold=120)
    print("🛡️ Iniciando con Session String Inmortal.")
else:
    app = Client("mi_radar_2026", api_id=API_ID, api_hash=API_HASH, sleep_threshold=120)
    print("⚠️ Iniciando con sesión local (Sin Session String).")

albumes_procesados = set()
CHATS_MONITOREADOS = set()
GRUPOS_EN_HISTORICO = set()

# ==========================================
# 2. BASE DE DATOS Y RESPALDOS (NUBE TELEGRAM)
# ==========================================
async def iniciar_db():
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS archivos_enviados 
                            (huella TEXT PRIMARY KEY)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS progreso_grupos 
                            (chat_id TEXT PRIMARY KEY, ultimo_mensaje_id INTEGER)''')
        await db.commit()

async def enviar_respaldo():
    if not BACKUP_CHAT_ID:
        return
    try:
        await asyncio.sleep(2)
        await app.send_document(
            chat_id=BACKUP_CHAT_ID,
            document=DB_NAME,
            caption="🛡️ Respaldo Automático de la Memoria"
        )
        print("☁️ [BACKUP] Memoria .db guardada en Telegram con éxito.")
    except Exception as e:
        if "Peer id invalid" in str(e):
            alt_id = str(BACKUP_CHAT_ID)
            alt_id = int(alt_id.replace("-100", "-")) if alt_id.startswith("-100") else int(alt_id.replace("-", "-100"))
            try:
                await app.send_document(chat_id=alt_id, document=DB_NAME, caption="🛡️ Respaldo Automático (ID Corregido)")
                print("☁️ [BACKUP] Memoria guardada exitosamente (con ID auto-corregido).")
            except Exception as e2:
                print(f"⚠️ [ALERTA] Falló el ID alternativo también: {e2}")
        else:
            print(f"⚠️ [ALERTA] Error al guardar respaldo en el canal: {e}")

async def descargar_respaldo():
    print("🔄 Buscando respaldo de memoria en la nube de Telegram...")
    try:
        async for mensaje in app.get_chat_history(BACKUP_CHAT_ID, limit=20):
            if mensaje.document and mensaje.document.file_name == DB_NAME:
                print("📥 Respaldo encontrado. Descargando e inyectando memoria...")
                await app.download_media(mensaje.document, file_name=DB_NAME)
                print("✅ Memoria restaurada con éxito.")
                return
        print("⚠️ No se encontró respaldo anterior. Iniciando memoria limpia desde cero.")
    except Exception:
        pass

async def obtener_progreso(chat_id):
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        cursor = await db.execute("SELECT ultimo_mensaje_id FROM progreso_grupos WHERE chat_id = ?", (str(chat_id),))
        resultado = await cursor.fetchone()
        return resultado[0] if resultado else 0

async def guardar_progreso(chat_id, mensaje_id):
    async with aiosqlite.connect(DB_NAME, timeout=15) as db:
        await db.execute("INSERT OR REPLACE INTO progreso_grupos (chat_id, ultimo_mensaje_id) VALUES (?, ?)", (str(chat_id), mensaje_id))
        await db.commit()

# ==========================================
# 3. EL FILTRO DE HUELLA DIGITAL
# ==========================================
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
# 4. EL MOTOR DE REENVÍO
# ==========================================
async def procesar_y_enviar(mensaje):
    huella = generar_huella(mensaje)
    if not huella: return 0  
    
    if await es_duplicado(huella):
        if getattr(mensaje, "media_group_id", None):
            albumes_procesados.add(mensaje.media_group_id) 
        print(f"⚠️ [FILTRO] Duplicado ignorado (ID: {mensaje.id}).")
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
                if msg.photo:
                    media_limpia.append(InputMediaPhoto(msg.photo.file_id, caption=""))
                elif msg.video:
                    media_limpia.append(InputMediaVideo(msg.video.file_id, caption=""))
            
            if media_limpia:
                await app.send_media_group(TARGET_CHAT_ID, media=media_limpia)
                for h in huellas_grupo: await registrar_huella(h)
                cantidad_archivos = len(media_limpia)
                print(f"📦 [ENVIADO] ÁLBUM de {cantidad_archivos} archivos copiado (Último ID: {mensaje.id}).")
                await asyncio.sleep(4) 
                return cantidad_archivos
                
        except FloodWait as e:
            print(f"🚨 Telegram pide descansar {e.value}s (Álbum). Reintentando...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            print(f"❌ [ERROR ÁLBUM] No se pudo enviar el ID {mensaje.id}. Causa: {e}")
        return 0

    while True:
        try:
            await mensaje.copy(chat_id=TARGET_CHAT_ID, caption="")
            await registrar_huella(huella)
            print(f"🚀 [ENVIADO] INDIVIDUAL copiado | ID: {mensaje.id}")
            await asyncio.sleep(2) 
            return 1 
        except FloodWait as e:
            print(f"🚨 Telegram pide descansar {e.value}s (Individual). Reintentando...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            print(f"❌ [ERROR INDIVIDUAL] No se pudo enviar el ID {mensaje.id}. Causa: {e}")
            return 0

# ==========================================
# 5. EL RADAR EN VIVO (24/7)
# ==========================================
@app.on_message(filters.photo | filters.video)
async def radar_en_vivo(client, mensaje):
    if mensaje.chat.id not in CHATS_MONITOREADOS:
        return
    if mensaje.chat.id in GRUPOS_EN_HISTORICO:
        return

    await guardar_progreso(mensaje.chat.id, mensaje.id)
    await procesar_y_enviar(mensaje)

# ==========================================
# 6. EL MOTOR HISTÓRICO (EL MÉTODO CLÁSICO QUE SÍ FUNCIONA)
# ==========================================
def leer_grupos_txt():
    if not os.path.exists("grupos.txt"): 
        print("⚠️ [AVISO] No se encontró el archivo grupos.txt. Creando uno vacío...")
        open("grupos.txt", "w").close()
        return []
    grupos_limpios = []
    with open("grupos.txt", "r") as f:
        for linea in f:
            texto_original = linea.strip()
            if not texto_original: continue
            enlace = texto_original
            if enlace.lstrip('-').isdigit():
                enlace = int(enlace)
            grupos_limpios.append({"enlace": enlace, "nombre_txt": texto_original})
    return grupos_limpios

async def aspiradora_historica():
    grupos = leer_grupos_txt()
    
    for item in grupos:
        enlace = item["enlace"]
        nombre_txt = item["nombre_txt"]
        
        try:
            chat = await app.get_chat(enlace)
            CHATS_MONITOREADOS.add(chat.id)
            GRUPOS_EN_HISTORICO.add(chat.id) 
            
            print(f"\n" + "="*50)
            print(f"📊 PRE-ESCANEO DE GRUPO: {nombre_txt}")
            print("="*50 + "\n")
            
            ultimo_id = await obtener_progreso(chat.id)
            mensajes_pendientes = []
            
            if ultimo_id > 0:
                print(f"🔍 Retomando desde el último ID guardado: #{ultimo_id}")
            else:
                print(f"🔍 Grupo nuevo. Extrayendo el historial completo...")

            # EL MÉTODO ANTIGUO Y CONFIABLE: Lee todo hacia atrás sin marearse
            try:
                async for m in app.get_chat_history(chat.id):
                    # Si llegamos al punto que ya procesamos en el pasado, nos detenemos
                    if m.id <= ultimo_id:
                        break
                    
                    if m.photo or m.video:
                        mensajes_pendientes.append(m)
            except Exception as e:
                print(f"⚠️ Error al leer el historial: {e}")
                continue

            if not mensajes_pendientes:
                print(f"✅ El grupo {nombre_txt} ya está 100% al día.")
                GRUPOS_EN_HISTORICO.discard(chat.id) 
                continue
                
            print(f"📥 Se extrajeron {len(mensajes_pendientes)} archivos multimedia.")
            
            if len(mensajes_pendientes) > 500:
                print("⏳ Historial masivo detectado. Pausando 10 segundos por seguridad...")
                await asyncio.sleep(10)

            # Volteamos la lista para enviar desde el 3182 hacia el presente
            mensajes_pendientes.reverse()

            # Rastreador visual
            primer_msg = mensajes_pendientes[0]
            link = f"https://t.me/c/{str(chat.id).replace('-100', '')}/{primer_msg.id}"
            print("\n" + "🔥"*25)
            print(f"👁️ RASTREADOR: EL BOT COMENZARÁ A ENVIAR DESDE ESTE VIDEO (ID: {primer_msg.id}):")
            print(f"👉 Link exacto: {link}")
            print("🔥"*25 + "\n")

            contador_rafaga = 0
            
            for mensaje in mensajes_pendientes:
                archivos_enviados = await procesar_y_enviar(mensaje)
                
                # Actualizamos la memoria con cada archivo que pasa
                if archivos_enviados > 0 or await es_duplicado(generar_huella(mensaje)):
                    await guardar_progreso(chat.id, mensaje.id)
                
                if archivos_enviados > 0:
                    contador_rafaga += archivos_enviados
                    
                    # EL DESCANSO Y RESPALDO QUE PEDISTE
                    if contador_rafaga >= 50:
                        print(f"⏸️ Límite de {contador_rafaga} archivos. Tirando el .db al grupo...")
                        await enviar_respaldo()
                        print("💤 Archivo enviado. Durmiendo 120 segundos sin joder a Telegram...")
                        await asyncio.sleep(120) 
                        contador_rafaga = 0
                        print("▶️ [REANUDANDO] Continuando con los siguientes videos...")
            
            print(f"🏁 Todos los archivos de {nombre_txt} han sido copiados.")
            GRUPOS_EN_HISTORICO.discard(chat.id) 

        except Exception as e:
            if "Peer id invalid" not in str(e):
                print(f"❌ [ERROR] No se pudo procesar el grupo {nombre_txt}. Causa: {e}")
            if enlace in GRUPOS_EN_HISTORICO:
                GRUPOS_EN_HISTORICO.discard(enlace)
            continue

    await enviar_respaldo()
    print("🏁 [MOTOR HISTÓRICO] Revisión terminada. Bot en modo Radar 24/7.")

# ==========================================
# MÓDULO WEB MÍNIMO (Para que Render no apague el bot)
# ==========================================
async def handle(request):
    return web.Response(text="El Almacenador de Videos está vivo.")

async def iniciar_web():
    try:
        app_web = web.Application()
        app_web.router.add_get('/', handle)
        runner = web.AppRunner(app_web)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"🌐 Servidor web fantasma iniciado en el puerto {port}")
    except Exception as e:
        print(f"⚠️ Aviso: Error al iniciar servidor web: {e}")

# ==========================================
# 7. ARRANQUE DEL SISTEMA
# ==========================================
async def main():
    loop = asyncio.get_event_loop()
    def silenciar_errores_molestos(loop, context):
        msg = context.get("exception", context.get("message", ""))
        if "Peer id invalid" in str(msg): return 
        loop.default_exception_handler(context)
    loop.set_exception_handler(silenciar_errores_molestos)

    await iniciar_web() 
    print("🚀 Encendiendo el Sistema Clásico Obrero...")
    
    await app.start()
    
    await descargar_respaldo()
    await iniciar_db()
    
    print(f"✅ Destino configurado: {TARGET_CHAT_ID}")
    
    try:
        chat_destino = await app.get_chat(TARGET_CHAT_ID)
        print(f"✅ Conectado exitosamente al grupo de destino: {chat_destino.title}")
    except Exception as e:
        print(f"❌ ¡CUIDADO! Telegram no reconoce el destino. Error: {e}")
    
    asyncio.create_task(aspiradora_historica())
    
    print("✅ Sistema 100% Operativo. Radar en guardia.")
    from pyrogram import idle
    await idle()
    await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Sistema detenido manualmente.")
