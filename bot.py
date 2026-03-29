import os
import yt_dlp
import tempfile
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from fastapi import FastAPI, Request
import uvicorn

# ---------- 1. Конфигурация ----------
# Токен будет взят из переменной окружения на Railway
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN set")

# Клавиатура с кнопками
keyboard = [
    ["🔍 Найти песню"],
    ["📂 Скачанные", "📀 Плейлисты"],
    ["🌊 Моя волна"]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Хранилище данных (пока в памяти, при перезапуске бота данные теряются)
user_data_store = {}

# ---------- 2. Функция скачивания и отправки аудио ----------
async def download_and_send_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, title: str):
    """
    Скачивает аудио с YouTube и отправляет пользователю как MP3.
    """
    try:
        # Создаём временный файл с именем вида music_XXXXXX.mp3
        with tempfile.NamedTemporaryFile(prefix="music_", suffix=".mp3", delete=False) as tmp:
            tmp_name = tmp.name

        # Настройки yt-dlp: скачать лучшее аудио, конвертировать в mp3 (битрейт 192 кбит/с)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': tmp_name.replace('.mp3', ''),  # yt-dlp добавит расширение сам
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Скачиваем по ссылке
            ydl.download([url])
            # После скачивания и конвертации файл будет иметь расширение .mp3
            # Ищем его: либо tmp_name.mp3, либо tmp_name + '.mp3'
            actual_filename = tmp_name + '.mp3'
            if not os.path.exists(actual_filename):
                actual_filename = tmp_name.replace('.mp3', '.mp3')  # запасной вариант
            # Отправляем пользователю
            with open(actual_filename, 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=title,
                    performer="YouTube",
                    caption="🎵 Скачано!"
                )
            # Удаляем временный файл
            os.remove(actual_filename)

    except Exception as e:
        await update.message.reply_text(f"Ошибка при скачивании: {e}")

# ---------- 3. Обработчики команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Инициализируем данные пользователя
    user_data_store[user_id] = {
        "downloads": [],
        "playlist": [],
        "history": []
    }
    await update.message.reply_text("🎧 Бот работает! Выбирай 👇", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Если пользователя нет в хранилище, создаём пустую запись
    if user_id not in user_data_store:
        user_data_store[user_id] = {"downloads": [], "playlist": [], "history": []}

    data = user_data_store[user_id]

    # Обрабатываем кнопки
    if text == "🔍 Найти песню":
        await update.message.reply_text("Напиши название песни 🎶")

    elif text == "📂 Скачанные":
        if data["downloads"]:
            await update.message.reply_text("\n".join(data["downloads"]))
        else:
            await update.message.reply_text("Пока нет скачанных 😢")

    elif text == "📀 Плейлисты":
        if data["playlist"]:
            await update.message.reply_text("\n".join(data["playlist"]))
        else:
            await update.message.reply_text("Плейлист пуст 😢")

    elif text == "🌊 Моя волна":
        if data["history"]:
            await update.message.reply_text("Тебе может понравиться:\n" + "\n".join(data["history"][-3:]))
        else:
            await update.message.reply_text("Сначала поищи музыку 🎧")

    else:
        # Это поисковый запрос (пользователь ввёл название)
        query = text
        ydl_opts = {
            'format': 'bestaudio',
            'quiet': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                video = info['entries'][0]
                title = video['title']
                url = video['webpage_url']

                # Сохраняем в историю
                data["history"].append(title)

                # Создаём кнопки под сообщением
                keyboard_inline = [
                    [InlineKeyboardButton("📥 Скачать", callback_data="download")],
                    [InlineKeyboardButton("➕ В плейлист", callback_data="add_to_playlist")]
                ]
                reply_markup_inline = InlineKeyboardMarkup(keyboard_inline)

                # Сохраняем ссылку и название в контекст (чтобы потом знать, что скачивать)
                context.user_data['last_url'] = url
                context.user_data['last_title'] = title

                await update.message.reply_text(
                    f"🎵 {title}\n\nСсылка: {url}",
                    reply_markup=reply_markup_inline
                )
        except Exception as e:
            await update.message.reply_text("Ошибка поиска 😢")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = user_data_store.get(user_id, {"downloads": [], "playlist": [], "history": []})
    last_url = context.user_data.get('last_url')
    last_title = context.user_data.get('last_title')

    if query.data == "download":
        if last_url and last_title:
            # Добавляем название в список скачанных для отображения в меню
            if last_title not in data["downloads"]:
                data["downloads"].append(last_title)
            # Меняем текст кнопки на «Скачиваю...»
            await query.edit_message_text(f"Скачиваю: {last_title} ⏳")
            # Скачиваем и отправляем MP3
            await download_and_send_audio(update, context, last_url, last_title)
        else:
            await query.edit_message_text("Нечего скачивать 😉")

    elif query.data == "add_to_playlist":
        if last_title and last_title not in data["playlist"]:
            data["playlist"].append(last_title)
            await query.edit_message_text(f"Добавлено в плейлист: {last_title} 🎧")
        else:
            await query.edit_message_text("Нечего добавлять или уже есть 😉")

# ---------- 4. Настройка вебхука ----------
def create_application():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    return app

# ---------- 5. FastAPI для приёма вебхуков ----------
fastapi_app = FastAPI()
telegram_app = create_application()

@fastapi_app.on_event("startup")
async def set_webhook():
    webhook_url = f"{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://fallback')}/webhook"
    if webhook_url != "https://fallback/webhook":
        await telegram_app.bot.set_webhook(webhook_url)
        print(f"Webhook set to {webhook_url}")
    else:
        print("RAILWAY_PUBLIC_DOMAIN not set")

@fastapi_app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@fastapi_app.get("/")
async def root():
    return {"status": "Bot is running"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)