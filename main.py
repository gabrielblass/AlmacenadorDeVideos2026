import asyncio
import os
import aiosqlite
from pyrogram import Client, filters
from pyrogram.enums import MessagesFilter
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

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

SESSION_STRING = "AQJCFbQAD1sY-yOTliNYkeknOmhL1lR44a5Ox2rRch9gPeJ_KFxb1dnm6zoK1MnQW3uhYYDxdT0D3NWkxhLrJQKFwrGeJlfHblgMN92GGkC8OJKNuxb4yQIqrahxYLUagQg1rZvMWq8xRVTAZ1BurPnYuw3diNKicy9Y9QG96Ozw4zZeXsEymM1ctewXZEm4utlBweVZSAC7JOBxYezJ4817HWsL6QJ4WXcyKTFAQd-wXBybhf7mqKgW8BUvh-icGxOuKKOeivG9oo-lJsR_S1LUyF1zakNW-CQkc6euF_Vw90HYXuWE4PBl3S1xopXVF_PwA2GyBAyyDKHzEW4MVN7bl3cNzAAAAABKHUk3AA"

DB_NAME = "memoria_sistema.db"

# ANCLA DE MIGRACIÓN:
FORZAR_IDS = {-1002632813544: 3454} 

# 🔥 APAGAMOS EL PILOTO AUTOMÁTICO DE PYROGRAM 🔥
app = Client(
    "obrero_maestro",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    sleep_threshold=0 
)

albumes_procesados = set()
CHATS_MONITOREADOS = set()
GRUPOS_EN_HISTORICO = set()

# ==========================================
# 2. BASE DE DATOS Y RESPALDOS
# ==========================================
async def iniciar_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS archivos_enviados 
                            (huella TEXT PRIMARY KEY)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS progreso_grupos 
                            (chat_id TEXT PRIMARY KEY, ultimo_mensaje_id INTEGER)''')
        await db.commit()

async def enviar_respaldo():
    try:
        await app.send_document(
            chat_id=BACKUP_CHAT_ID,
            document=DB_NAME,
            caption="🛡️ Respaldo Automático de la Memoria (SQLite)"
        )
    except Exception:
        pass

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
        except FloodWait as e:
            print(f"🚨 [ALERTA] Telegram pide descansar {e.value}s (Álbum ID: {mensaje.id})")
            await asyncio.sleep(e.value)
            return False
        except Exception:
            return False

    try:
        await mensaje.copy(chat_id=TARGET_CHAT_ID, caption="")
        await registrar_huella(huella)
        print(f"🚀 [ENVIADO] INDIVIDUAL copiado | ID: {mensaje.id}")
        await asyncio.sleep(2) 
        return True
    except FloodWait as e:
        print(f"🚨 [ALERTA] Telegram pide descansar {e.value}s (Individual ID: {mensaje.id})")
        await asyncio.sleep(e.value)
        return False
    except Exception:
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
                    await asyncio.sleep(e.value)
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
            
            # 🔥 ENFRIADOR AUTOMÁTICO 🔥
            if len(mensajes_pendientes) > 500:
                print("⏳ [ENFRIAMIENTO] Se leyó un historial masivo. Pausando 15 segundos...")
                await asyncio.sleep(15)

            mensajes_pendientes.reverse()
            
            contador_rafaga = 0
            for mensaje in mensajes_pendientes:
                fue_enviado = await procesar_y_enviar(mensaje)
                await guardar_progreso(chat.id, mensaje.id)
                
                if fue_enviado:
                    contador_rafaga += 1
                    if contador_rafaga >= 50:
                        print("⏸️ [DESCANSO] Ráfaga de 50 completada. Respirando 60s...")
                        await asyncio.sleep(60)
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

    print("🏁 [MOTOR HISTÓRICO] Revisión antigua finalizada. El Radar asume el control total 24/7.")

# ==========================================
# 7. ARRANQUE DEL SISTEMA
# ==========================================
async def main():
    await iniciar_db()
    print("🚀 Encendiendo el Sistema Dual Obrero...")
    await app.start()
    
    print(f"✅ Destino configurado correctamente en el ID: {TARGET_CHAT_ID}")
    
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