import os
import logging
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
    await update.message.reply_text("Привет! Пришли мне PDF — я верну тебе текст.")

# --- Обработка PDF ---
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.mime_type != "application/pdf":
        return await update.message.reply_text("Это не PDF.")

    # Скачиваем во временный файл
    file_path = f"/tmp/{doc.file_name}"
    new_file = await context.bot.get_file(doc.file_id)
    await new_file.download_to_drive(file_path)

    # Извлекаем текст
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return await update.message.reply_text(f"Ошибка при чтении PDF: {e}")

    if not text.strip():
        return await update.message.reply_text("Не удалось извлечь текст.")

    # Сохраняем текст для последующих действий
    context.user_data["last_pdf_text"] = text

    # Отправляем текст порциями
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i : i + 4096])

    # Кнопки: Скопировать текст, Скачать в Word и Загрузить ещё PDF-файл
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Скопировать текст", callback_data="copy_text"),
            InlineKeyboardButton("📥 Скачать в Word", callback_data="download_word"),
        ],
        [InlineKeyboardButton("🔄 Загрузить ещё PDF-файл", callback_data="start_over")],
    ])
    await update.message.reply_text(
        "Ваш текст готов! Выберите действие ниже:",
        reply_markup=keyboard,
    )

# --- Обработка нажатия Скопировать текст ---
async def copy_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = context.user_data.get("last_pdf_text")
    if not text:
        return await query.edit_message_text("Нет текста для копирования.")

    # Отправляем текст порциями
    for i in range(0, len(text), 4096):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text[i : i + 4096]
        )

# --- Обработка нажатия Скачать в Word ---
async def download_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = context.user_data.get("last_pdf_text")
    if not text:
        return await query.edit_message_text("Нет текста для генерации Word.")

    # Генерируем .docx
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    out_path = "/tmp/output.docx"
    doc.save(out_path)

    # Отправляем файл Word
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(out_path, "rb"),
        filename="converted.docx",
    )

    # Кнопка Загрузить ещё PDF-файл
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Загрузить ещё PDF-файл", callback_data="start_over")],
    ])
    await query.edit_message_text(
        "Файл Word готов! Если хотите загрузить ещё PDF-файл — нажмите кнопку ниже.",
        reply_markup=keyboard,
    )

# --- Обработка нажатия Загрузить ещё PDF-файл ---
async def start_over_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("last_pdf_text", None)
    await query.edit_message_text("Отправьте прямо в этот чат PDF-файл.")

# --- Основная функция ---
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))
    app.add_handler(CallbackQueryHandler(copy_text_callback, pattern="copy_text"))
    app.add_handler(CallbackQueryHandler(download_word_callback, pattern="download_word"))
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern="start_over"))

    # Webhook-настройки для Render
    host = os.environ.get("RENDER_EXTERNAL_URL")
    if not host:
        logger.error("RENDER_EXTERNAL_URL не задан")
        return
    port = int(os.environ.get("PORT", 5000))
    webhook_url = f"{host}/{token}"

    # Запуск встроенного webhook-сервера
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
