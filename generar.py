import asyncio
from pyrogram import Client

API_ID = 37885364
API_HASH = "f4a0bb2800576bbf30aace4282eff648"

async def main():
    app = Client("sesion_temporal", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await app.start()
    print("\n" + "="*50)
    print("🔥 TU SESSION STRING ES (COPIA LO QUE ESTÁ ABAJO): 🔥\n")
    print(await app.export_session_string())
    print("\n" + "="*50)
    await app.stop()

asyncio.run(main())