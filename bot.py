import os
import logging
import re
import fitz  # PyMuPDF для извлечения изображений
import tempfile
import docx
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
    await update.message.reply_text(
        "Привет! Пришли мне PDF — я верну тебе текст и картинки, если они есть."
    )

# --- Обработка PDF ---
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # САМЫЙ БЫСТРЫЙ ОТВЕТ Telegram — до скачивания и обработки файла!
    await update.message.reply_text("⏳ Обрабатываю файл, это может занять несколько секунд...")

    doc_file = update.message.document
    if doc_file.mime_type != "application/pdf":
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Это не PDF."
        )
        return

    # Скачиваем PDF
    file_path = f"/tmp/{doc_file.file_name}"
    new_file = await context.bot.get_file(doc_file.file_id)
    await new_file.download_to_drive(file_path)

    # Извлекаем текст
    raw_text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text() or ""
            raw_text += page_text + "\n"
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Ошибка при чтении PDF: {e}"
        )
        return

    # Чистим текст: дефисы на концах строк, все переносы на пробел, множественные пробелы к одному
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", raw_text)
    text = text.replace("\n", " ")
    text = re.sub(r" {2,}", " ", text).strip()

    if not text:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Не удалось извлечь текст."
        )
        return

    # --- Извлекаем картинки и убираем дубликаты ---
    images = []
    try:
        pdf_doc = fitz.open(file_path)
        for page in pdf_doc:
            for img in page.get_images(full=True):
                xref = img[0]
                img_dict = pdf_doc.extract_image(xref)
                images.append((img_dict['image'], img_dict['ext']))
    except Exception as e:
        logger.warning(f"Ошибка при извлечении изображений: {e}")

    # Только уникальные картинки (макс. 10)
    sent_images = set()
    unique_images = []
    for img_bytes, ext in images:
        img_hash = hash(img_bytes)
        if img_hash not in sent_images:
            unique_images.append((img_bytes, ext))
            sent_images.add(img_hash)
    unique_images = unique_images[:10]  # Ограничение по количеству

    # Сохраняем для Word
    context.user_data['last_pdf_text'] = text
    context.user_data['last_pdf_images'] = unique_images

    # Отправляем текст порциями
    for i in range(0, len(text), 4096):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text[i:i+4096])

    # Отправляем только уникальные картинки
    for img_bytes, ext in unique_images:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_bytes
        )

    # Теперь кнопки после текста и картинок
    try:
        logger.info("Отправлены все картинки, сейчас будут отправлены кнопки.")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Скачать в Word", callback_data="download_word")],
            [InlineKeyboardButton("🔄 Загрузить ещё PDF-файл", callback_data="start_over")],
        ])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ваш текст готов! Выберите действие ниже:",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке кнопок: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка при отправке кнопок. Попробуйте ещё раз."
        )

# --- Скачать в Word ---
async def download_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = context.user_data.get('last_pdf_text')
    images = context.user_data.get('last_pdf_images', [])

    if not text:
        return await query.edit_message_text("Нет текста для генерации Word.")

    doc = Document()
    # Добавляем текст (разбиваем по предложениям)
    for sentence in re.split(r'(?<=[.!?]) +', text):
        doc.add_paragraph(sentence)

    # Добавляем картинки (максимум 10)
    from docx.shared import Inches
    max_images = 10
    for img_bytes, ext in images[:max_images]:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.' + ext) as tmp_img:
            tmp_img.write(img_bytes)
            tmp_img.flush()
            try:
                doc.add_picture(tmp_img.name, width=Inches(5))
            except Exception as e:
                logger.warning(f'Не удалось вставить картинку: {e}')

    out_path = "/tmp/output.docx"
    doc.save(out_path)

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(out_path, 'rb'),
        filename='converted.docx'
    )

    # Обновляем кнопки
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Загрузить ещё PDF-файл", callback_data="start_over")],
    ])
    await query.edit_message_reply_markup(reply_markup=keyboard)

# --- Загрузить ещё PDF ---
async def start_over_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop('last_pdf_text', None)
    context.user_data.pop('last_pdf_images', None)
    await query.edit_message_reply_markup(None)
    # Новое сообщение внизу чата
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔄 Пришлите новый PDF-файл сюда."
    )

# --- Основная функция ---
def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error('TELEGRAM_BOT_TOKEN не задан')
        return

    app = (
        ApplicationBuilder()
        .token(token)
        .build()
    )
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))
    app.add_handler(CallbackQueryHandler(download_word_callback, pattern='download_word'))
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern='start_over'))

    # Webhook-настройки для Render
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
