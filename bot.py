import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import PyPDF2

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли мне PDF — я верну тебе текст."
    )

# Обработка документа
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.mime_type != "application/pdf":
        return await update.message.reply_text("Это не PDF.")
    # скачиваем во временный файл
    file_path = f"/tmp/{doc.file_name}"
    new_file = await context.bot.get_file(doc.file_id)
    await new_file.download_to_drive(file_path)
    # извлекаем текст
    text = ""
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
    except Exception as e:
        return await update.message.reply_text(f"Ошибка при чтении PDF: {e}")
    # Telegram ограничение 4096 символов
    if not text:
        return await update.message.reply_text("Не удалось извлечь текст.")
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i : i + 4096])

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан")
        return
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))
    app.run_polling()

if __name__ == "__main__":
    main()
