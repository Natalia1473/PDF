import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Пришли мне PDF — я верну тебе текст.")

# обработка PDF
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.mime_type != "application/pdf":
        return await update.message.reply_text("Это не PDF.")
    # скачиваем
    file_path = f"/tmp/{doc.file_name}"
    new_file = await context.bot.get_file(doc.file_id)
    await new_file.download_to_drive(file_path)
    # вытаскиваем текст
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
    # шлём порциями по 4096
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i : i + 4096])

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан")
        return

    # создаём приложение
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))

        # берём полный HTTPS-URL Render’а
    host = os.environ.get("RENDER_EXTERNAL_URL")
    if not host:
        logger.error("RENDER_EXTERNAL_URL не задан")
        return
    webhook_url = f"{host}/{token}"

    port = int(os.environ.get("PORT", 5000))
    # run_webhook сам установит webhook и сразу запустит сервер
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
