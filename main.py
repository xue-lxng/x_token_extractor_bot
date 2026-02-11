from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    Document,
    Message,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Константы
TEMP_DIR = Path("temp_files")
TEMP_DIR.mkdir(exist_ok=True)


# FSM для хранения настроек пользователя
class UserSettings(StatesGroup):
    field_index = State()
    delimiter = State()


# Роутер для обработчиков
router = Router()


def extract_field(
        in_path: Path,
        out_path: Path,
        field_index: int,
        delimiter: str = ":",
        encoding: str = "utf-8",
) -> int:
    """
    Reads `in_path` line-by-line, splits each line by `delimiter`,
    writes `parts[field_index]` to `out_path` (one per line).
    Returns number of written lines.
    """
    written = 0

    with in_path.open(
            "r", encoding=encoding, errors="replace", newline=""
    ) as fin, out_path.open("w", encoding=encoding, newline="\n") as fout:
        for line_no, raw in enumerate(fin, start=1):
            line = raw.strip()
            if not line:
                continue

            parts = line.split(delimiter)

            if field_index >= len(parts):
                continue

            value = parts[field_index].strip()
            if not value:
                continue

            fout.write(value + "\n")
            written += 1

    return written


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.set_data({"field_index": 5, "delimiter": ":"})

    await message.answer(
        "👋 Привет! Я бот для извлечения полей из текстовых файлов.\n\n"
        "📤 Отправь мне txt файл, и я извлеку нужное поле из каждой строки.\n\n"
        "<b>Текущие настройки:</b>\n"
        "• Индекс поля: 5 (6-е поле)\n"
        "• Разделитель: ':'\n\n"
        "<b>Команды:</b>\n"
        "/set_index число - установить индекс поля (0-based)\n"
        "/set_delimiter символ - установить разделитель\n"
        "/settings - показать текущие настройки\n"
        "/help - справка",
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "<b>📖 Справка по использованию</b>\n\n"
        "Бот извлекает определенное поле из каждой строки файла по разделителю.\n\n"
        "<b>Пример входного файла:</b>\n"
        "<code>user1:pass1:email1:data1:info1:token1</code>\n"
        "<code>user2:pass2:email2:data2:info2:token2</code>\n\n"
        "С индексом 5 и разделителем ':' получите:\n"
        "<code>token1</code>\n"
        "<code>token2</code>\n\n"
        "<b>Команды настройки:</b>\n"
        "/set_index 2 - извлекать 3-е поле (индексация с 0)\n"
        "/set_delimiter | - использовать | как разделитель\n"
        "/settings - текущие настройки",
        parse_mode="HTML"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    """Показать текущие настройки"""
    data = await state.get_data()
    field_index = data.get("field_index", 5)
    delimiter = data.get("delimiter", ":")

    await message.answer(
        f"⚙️ <b>Текущие настройки:</b>\n\n"
        f"• Индекс поля: <code>{field_index}</code> ({field_index + 1}-е поле)\n"
        f"• Разделитель: <code>{delimiter}</code>",
        parse_mode="HTML"
    )


@router.message(Command("set_index"))
async def cmd_set_index(message: Message, state: FSMContext):
    """Установить индекс поля"""
    try:
        # Извлекаем число из команды
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "❌ Укажите индекс поля.\n"
                "Пример: <code>/set_index 5</code>",
                parse_mode="HTML"
            )
            return

        field_index = int(parts[1])
        if field_index < 0:
            await message.answer("❌ Индекс должен быть неотрицательным числом.")
            return

        data = await state.get_data()
        data["field_index"] = field_index
        await state.set_data(data)

        await message.answer(
            f"✅ Индекс поля установлен: <code>{field_index}</code> ({field_index + 1}-е поле)",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Некорректное число. Используйте целое число >= 0.")


@router.message(Command("set_delimiter"))
async def cmd_set_delimiter(message: Message, state: FSMContext):
    """Установить разделитель"""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1]:
        await message.answer(
            "❌ Укажите разделитель.\n"
            "Пример: <code>/set_delimiter :</code> или <code>/set_delimiter |</code>",
            parse_mode="HTML"
        )
        return

    delimiter = parts[1]
    data = await state.get_data()
    data["delimiter"] = delimiter
    await state.set_data(data)

    await message.answer(
        f"✅ Разделитель установлен: <code>{delimiter}</code>",
        parse_mode="HTML"
    )


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot):
    """Обработчик загруженных файлов"""
    document: Document = message.document

    # Проверяем, что это текстовый файл
    if not document.file_name.endswith('.txt'):
        await message.answer(
            "❌ Пожалуйста, отправьте текстовый файл (.txt)"
        )
        return

    # Получаем настройки пользователя
    data = await state.get_data()
    field_index = data.get("field_index", 5)
    delimiter = data.get("delimiter", ":")

    processing_msg = await message.answer("⏳ Обрабатываю файл...")

    try:
        # Скачиваем файл
        file = await bot.get_file(document.file_id)
        file_path = TEMP_DIR / f"input_{message.from_user.id}_{message.message_id}.txt"
        output_path = TEMP_DIR / f"output_{message.from_user.id}_{message.message_id}.txt"

        await bot.download_file(file.file_path, file_path)

        # Обрабатываем файл
        count = extract_field(
            in_path=file_path,
            out_path=output_path,
            field_index=field_index,
            delimiter=delimiter,
            encoding="utf-8"
        )

        if count == 0:
            await processing_msg.edit_text(
                "⚠️ Не найдено строк с указанным полем.\n"
                "Проверьте настройки (индекс поля и разделитель)."
            )
            return

        # Читаем результат и отправляем
        with output_path.open("rb") as f:
            result_file = BufferedInputFile(
                f.read(),
                filename=f"extracted_{document.file_name}"
            )

        await message.answer_document(
            result_file,
            caption=(
                f"✅ Готово! Извлечено <b>{count}</b> строк.\n\n"
                f"Настройки:\n"
                f"• Индекс поля: {field_index}\n"
                f"• Разделитель: <code>{delimiter}</code>"
            ),
            parse_mode="HTML"
        )

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error processing file: {e}", exc_info=True)
        await processing_msg.edit_text(
            f"❌ Ошибка при обработке файла:\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )
    finally:
        # Удаляем временные файлы
        file_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


@router.message()
async def handle_other(message: Message):
    """Обработчик остальных сообщений"""
    await message.answer(
        "📄 Отправьте мне txt файл для обработки.\n"
        "Или используйте /help для справки."
    )


async def main():
    """Главная функция запуска бота"""
    # Замените на ваш токен

    dotenv.load_dotenv()

    BOT_TOKEN = os.getenv("BOT_TOKEN")

    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрируем роутер
    dp.include_router(router)

    # Удаляем вебхуки и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
