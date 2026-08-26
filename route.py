from aiohttp import web
from config import PORT
import logging

async def handle(request):
    return web.Response(text="Bot is running and healthy!")

async def web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Health-check web server started on port {PORT}")