import os
import logging
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не задан")
    exit(1)

bot = Bot(token=TOKEN)
app = Flask(__name__)
dp = Dispatcher(bot, None, workers=0, use_context=True)

# Хендлеры
async def start(update, context):
    await update.message.reply_text("Привет! Пришли мне PDF — я верну тебе текст.")

async def handle_pdf(update, context):
    doc = update.message.document
    if doc.mime_type != "application/pdf":
        return await update.message.reply_text("Это не PDF.")
    file_path = f"/tmp/{doc.file_name}"
    new_file = await bot.get_file(doc.file_id)
    await new_file.download_to_drive(file_path)
    text = ""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text
    except Exception as e:
        return await update.message.reply_text(f"Ошибка при чтении PDF: {e}")
    if not text:
        return await update.message.reply_text("Не удалось извлечь текст.")
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i+4096])

dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))

# Обработка входящих запросов от Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dp.process_update(update)
    return "OK"

if __name__ == "__main__":
    # Устанавливаем webhook на адрес Render
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not host:
        logger.error("RENDER_EXTERNAL_HOSTNAME не задан")
        exit(1)
    webhook_url = f"https://{host}/{TOKEN}"
    bot.set_webhook(webhook_url)
    # Запускаем Flask-сервер на порту из ENV PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
