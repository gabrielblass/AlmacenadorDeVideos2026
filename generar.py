import asyncio

# 🔥 PARCHE OBLIGATORIO PARA PYTHON 3.14+ 🔥
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client

print("\n" + "="*50)
print("🧠 GENERADOR DE SESSION STRING INMORTAL 🧠")
print("="*50 + "\n")

api_id = input("👉 Ingresa tu API_ID (el número): ")
api_hash = input("👉 Ingresa tu API_HASH (letras y números): ")

async def main():
    print("\n⏳ Conectando con los servidores de Telegram...")
    # Usamos in_memory=True para no dejar archivos basura
    async with Client("sesion_temporal", api_id=int(api_id), api_hash=api_hash, in_memory=True) as app:
        string = await app.export_session_string()
        print("\n✅ ¡ÉXITO! AQUÍ ESTÁ TU NUEVA LLAVE:")
        print("Copia ABSOLUTAMENTE TODO este texto largo y pégalo en el SESSION_STRING de Render:")
        print("\n" + "👇" * 15 + "\n")
        print(string)
        print("\n" + "👆" * 15 + "\n")

loop.run_until_complete(main())