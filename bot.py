import os
import logging
import re
import fitz  # PyMuPDF для извлечения изображений
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from PyPDF2 import PdfReader
from docx import Document

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Пришли мне PDF — я верну тебе текст и картинки, если они есть.")

# --- Обработка PDF ---
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc_file = update.message.document
    if doc_file.mime_type != "application/pdf":
        return await update.message.reply_text("Это не PDF.")

    # скачиваем PDF
    file_path = f"/tmp/{doc_file.file_name}"
    new_file = await context.bot.get_file(doc_file.file_id)
    await new_file.download_to_drive(file_path)

    # извлекаем текст
    raw = ""
    try:
        reader = PdfReader(file_path)
        for p in reader.pages:
            raw += p.extract_text() or ''
            raw += '\n'
    except Exception as e:
        return await update.message.reply_text(f"Ошибка при чтении PDF: {e}")

    # чистим неоправданные переносы и пробелы между предложениями
    # убираем переносы строк после дефиса
    text = re.sub(r"-\s*\n", "", raw)
    # заменяем все переносы и множественные пробелы на один пробел
    text = re.sub(r"\s*\n+\s*", " ", text)
    text = re.sub(r"[ ]{2,}", " ", text).strip()

    if not text:
        return await update.message.reply_text("Не удалось извлечь текст.")
    context.user_data['last_pdf_text'] = text

    # извлекаем картинки
    images = []
    try:
        pdf = fitz.open(file_path)
        for page in pdf:
            for img in page.get_images(full=True):
                xref = img[0]
                base = pdf.extract_image(xref)
                images.append((base['image'], base['ext']))
    except Exception:
        images = []

    # отправляем текст порциями
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i+4096])

    # кнопки
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Скачать в Word", callback_data="download_word")],
        [InlineKeyboardButton("🔄 Загрузить ещё PDF-файл", callback_data="start_over")],
    ])
    await update.message.reply_text(
        "Ваш текст готов! Выберите действие ниже:",
        reply_markup=keyboard,
    )

    # отправляем картинки, если они есть
    for img_bytes, ext in images:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_bytes
        )

# --- Скачать в Word ---
async def download_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = context.user_data.get('last_pdf_text')
    if not text:
        return await query.edit_message_text("Нет текста для генерации Word.")

    # создаём .docx
    doc = Document()
    for line in text.split('. '):
        doc.add_paragraph(line.strip() + '.')
    out = "/tmp/output.docx"
    doc.save(out)

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(out, 'rb'),
        filename='converted.docx'
    )

    # обновляем кнопки
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Загрузить ещё PDF-файл", callback_data="start_over")],
    ])
    await query.edit_message_reply_markup(reply_markup=keyboard)

# --- Загрузить ещё PDF ---
async def start_over_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop('last_pdf_text', None)
    await query.edit_message_reply_markup(None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔄 Пришлите новый PDF-файл сюда."
    )

# --- main ---
def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error('TELEGRAM_BOT_TOKEN не задан')
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))
    app.add_handler(CallbackQueryHandler(download_word_callback, pattern='download_word'))
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern='start_over'))

    # webhook для Render
    host = os.getenv('RENDER_EXTERNAL_URL')
    if not host:
        logger.error('RENDER_EXTERNAL_URL не задан')
        return
    port = int(os.getenv('PORT', 5000))
    webhook_url = f"{host}/{token}"
    app.run_webhook(
        listen='0.0.0.0',
        port=port,
        url_path=token,
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()
