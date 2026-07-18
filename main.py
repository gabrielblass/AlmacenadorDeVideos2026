import asyncio
import nest_asyncio
nest_asyncio.apply()

import os
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
# 1. CONFIGURACIÓN INICIAL
# ==========================================
load_dotenv()
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

RAW_TARGET = os.environ.get("TARGET_CHAT_ID", "").strip().replace('"', '').replace("'", "")
if RAW_TARGET.lstrip('-').isdigit():
    TARGET_CHAT_ID = int(RAW_TARGET)
else:
    TARGET_CHAT_ID = RAW_TARGET

BACKUP_CHAT_ID = int(os.environ.get("BACKUP_CHAT_ID", 0))

DB_NAME = "memoria_sistema.db"

# ANCLA DE MIGRACIÓN:
FORZAR_IDS = {-1002632813544: 3454} 

app = Client(
    "mi_radar_2026",
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60 
)

albumes_procesados = set()
CHATS_MONITOREADOS = set()
GRUPOS_EN_HISTORICO = set()

# ==========================================
# 2. BASE DE DATOS Y RESPALDOS (NUBE TELEGRAM)
# ==========================================
async def iniciar_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS archivos_enviados 
                            (huella TEXT PRIMARY KEY)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS progreso_grupos 
                            (chat_id TEXT PRIMARY KEY, ultimo_mensaje_id INTEGER)''')
        await db.commit()

async def enviar_respaldo():
    if not BACKUP_CHAT_ID:
        return
    try:
        await app.send_document(
            chat_id=BACKUP_CHAT_ID,
            document=DB_NAME,
            caption="🛡️ Respaldo Automático de la Memoria (SQLite)"
        )
        print("☁️ [BACKUP] Memoria guardada en Telegram con éxito.")
    except Exception as e:
        print(f"⚠️ Error al guardar respaldo: {e}")

async def descargar_respaldo():
    if not BACKUP_CHAT_ID:
        print("⚠️ No hay BACKUP_CHAT_ID configurado. Saltando restauración.")
        return
    
    print("🔄 Buscando respaldo de memoria en la nube de Telegram...")
    try:
        # Buscamos en los últimos 20 mensajes del canal de respaldo
        async for mensaje in app.get_chat_history(BACKUP_CHAT_ID, limit=20):
            if mensaje.document and mensaje.document.file_name == DB_NAME:
                print("📥 Respaldo encontrado. Descargando e inyectando memoria...")
                await app.download_media(mensaje.document, file_name=DB_NAME)
                print("✅ Memoria restaurada con éxito. ¡Amnesia curada!")
                return
        print("⚠️ No se encontró ningún respaldo anterior. Iniciando memoria desde cero.")
    except Exception as e:
        print(f"❌ Error al intentar descargar el respaldo: {e}")

async def obtener_progreso(chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT ultimo_mensaje_id FROM progreso_grupos WHERE chat_id = ?", (str(chat_id),))
        resultado = await cursor.fetchone()
        return resultado[0] if resultado else 0

async def guardar_progreso(chat_id, mensaje_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO progreso_grupos (chat_id, ultimo_mensaje_id) VALUES (?, ?)", (str(chat_id), mensaje_id))
        await db.commit()

# ==========================================
# 3. EL FILTRO DE HUELLA DIGITAL
# ==========================================
def generar_huella(mensaje):
    media = mensaje.photo or mensaje.video
    if not media: return None
    file_size = getattr(media, "file_size", 0)
    width = getattr(media, "width", 0)
    height = getattr(media, "height", 0)
    duration = getattr(media, "duration", 0) 
    return f"{file_size}_{width}_{height}_{duration}"

async def es_duplicado(huella):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT 1 FROM archivos_enviados WHERE huella = ?", (huella,))
        resultado = await cursor.fetchone()
        return bool(resultado)

async def registrar_huella(huella):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO archivos_enviados (huella) VALUES (?)", (huella,))
        await db.commit()

# ==========================================
# 4. EL MOTOR DE REENVÍO
# ==========================================
async def procesar_y_enviar(mensaje):
    huella = generar_huella(mensaje)
    if not huella: return False
    
    if await es_duplicado(huella):
        if getattr(mensaje, "media_group_id", None):
            albumes_procesados.add(mensaje.media_group_id) 
        print(f"⚠️ [FILTRO] Duplicado local ignorado (ID: {mensaje.id}).")
        return False

    if getattr(mensaje, "media_group_id", None):
        if mensaje.media_group_id in albumes_procesados:
            return False
        albumes_procesados.add(mensaje.media_group_id)
        
        while True:
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
                    print(f"📦 [ENVIADO] ÁLBUM copiado (Último ID: {mensaje.id}).")
                    await asyncio.sleep(4) 
                    return True
                return False
            except FloodWait as e:
                print(f"🚨 [ALERTA] Telegram pide descansar {e.value}s (Álbum ID: {mensaje.id}). Reintentando...")
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                print(f"❌ [ERROR FATAL ÁLBUM] No se pudo enviar el ID {mensaje.id}. Causa: {e}")
                return False

    while True:
        try:
            await mensaje.copy(chat_id=TARGET_CHAT_ID, caption="")
            await registrar_huella(huella)
            print(f"🚀 [ENVIADO] INDIVIDUAL copiado | ID: {mensaje.id}")
            await asyncio.sleep(2) 
            return True
        except FloodWait as e:
            print(f"🚨 [ALERTA] Telegram pide descansar {e.value}s (Individual ID: {mensaje.id}). Reintentando...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            print(f"❌ [ERROR FATAL INDIVIDUAL] No se pudo enviar el ID {mensaje.id}. Causa: {e}")
            return False

# ==========================================
# 5. EL RADAR EN VIVO 
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
# 6. EL MOTOR HISTÓRICO 
# ==========================================
def leer_grupos_txt():
    if not os.path.exists("grupos.txt"): return []
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
            
            if chat.id in FORZAR_IDS:
                ultimo_id = FORZAR_IDS[chat.id]
                print(f"⚙️ [MODO MANUAL] Forzando inicio desde el ID: {ultimo_id}")
            else:
                ultimo_id = await obtener_progreso(chat.id)
            
            mensajes_pendientes = []
            offset_mensaje_id = 0
            
            if ultimo_id > 0:
                print(f"🔍 Buscando todo lo nuevo por encima del mensaje #{ultimo_id}...")
            else:
                print(f"🔍 Escaneando historial completo por primera vez...")

            while True:
                bloque = []
                try:
                    async for m in app.get_chat_history(chat.id, offset_id=offset_mensaje_id, limit=100):
                        bloque.append(m)
                except FloodWait as e:
                    print(f"🚨 [ALERTA DE LECTURA] Telegram pide pausa de {e.value}s...")
                    await asyncio.sleep(e.value + 1)
                    continue

                if not bloque:
                    break

                alcanzo_limite = False
                for m in bloque:
                    if m.id <= ultimo_id:
                        alcanzo_limite = True
                        break
                    if m.photo or m.video:
                        mensajes_pendientes.append(m)
                    offset_mensaje_id = m.id

                if alcanzo_limite:
                    break
                
                await asyncio.sleep(2)

            if not mensajes_pendientes:
                print(f"✅ El grupo {nombre_txt} ya está 100% al día. No hay nada nuevo.")
                GRUPOS_EN_HISTORICO.discard(chat.id)
                continue
                
            print(f"📥 Se encontraron {len(mensajes_pendientes)} archivos nuevos.")
            
            if len(mensajes_pendientes) > 500:
                print("⏳ [ENFRIAMIENTO] Se leyó un historial masivo. Pausando 15 segundos...")
                await asyncio.sleep(15)

            mensajes_pendientes.reverse()
            
            contador_rafaga = 0
            for mensaje in mensajes_pendientes:
                fue_enviado = await procesar_y_enviar(mensaje)
                
                if fue_enviado or await es_duplicado(generar_huella(mensaje)):
                    await guardar_progreso(chat.id, mensaje.id)
                
                if fue_enviado:
                    contador_rafaga += 1
                    if contador_rafaga >= 50:
                        print("⏸️ [DESCANSO] Ráfaga de 50 completada. Respirando 120s (2 minutos) para proteger la cuenta...")
                        await asyncio.sleep(120)
                        
                        # 🔥 AQUÍ SE DISPARA EL RESPALDO AUTOMÁTICO A TELEGRAM 🔥
                        asyncio.create_task(enviar_respaldo())
                        
                        contador_rafaga = 0
                        print("▶️ [REANUDANDO] Conexión renovada...")
            
            print(f"🏁 Todos los archivos pendientes de {nombre_txt} han sido procesados.")
            GRUPOS_EN_HISTORICO.discard(chat.id)

        except Exception as e:
            if "Peer id invalid" not in str(e):
                print(f"❌ [ERROR] Falló al procesar el grupo {nombre_txt}: {e}")
            if enlace in GRUPOS_EN_HISTORICO:
                GRUPOS_EN_HISTORICO.discard(enlace)
            continue

    # Respaldo final al terminar toda la revisión histórica
    await enviar_respaldo()
    print("🏁 [MOTOR HISTÓRICO] Revisión antigua finalizada. El Radar asume el control total 24/7.")

# ==========================================
# MÓDULO WEB MÍNIMO (Para que Render no apague)
# ==========================================
async def handle(request):
    return web.Response(text="Bot vivo")

async def iniciar_web():
    app_web = web.Application()
    app_web.router.add_get('/', handle)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

# ==========================================
# 7. ARRANQUE DEL SISTEMA
# ==========================================
async def main():
    # 🔥 Silenciador de consola para errores fantasmas 🔥
    loop = asyncio.get_event_loop()
    def silenciar_errores_molestos(loop, context):
        msg = context.get("exception", context.get("message", ""))
        if "Peer id invalid" in str(msg):
            return 
        loop.default_exception_handler(context)
    loop.set_exception_handler(silenciar_errores_molestos)

    await iniciar_db()
    await iniciar_web() 
    print("🚀 Encendiendo el Sistema Dual Obrero...")
    
    await app.start()
    
    # 🔥 AHORA SÍ: EL BOT RECUPERA SU CEREBRO DE LA NUBE APENAS DESPIERTA 🔥
    await descargar_respaldo()
    
    print(f"✅ Destino configurado en el `.env`: {TARGET_CHAT_ID}")
    
    print("🔄 Sincronizando chats con Telegram para evitar errores de ID...")
    try:
        async for dialog in app.get_dialogs(limit=200):
            if dialog.chat.id == TARGET_CHAT_ID:
                break
    except Exception:
        pass
    
    try:
        chat_destino = await app.get_chat(TARGET_CHAT_ID)
        print(f"✅ ¡AHORA SÍ! Conectado exitosamente al grupo de destino: {chat_destino.title}")
    except Exception as e:
        print(f"❌ ¡CUIDADO! Sigue sin reconocer el ID. Error: {e}")
    
    asyncio.create_task(aspiradora_historica())
    
    print("✅ Sistema 100% Operativo. El Radar en Vivo está escuchando en el fondo.")
    from pyrogram import idle
    await idle()
    await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Sistema detenido manualmente.")