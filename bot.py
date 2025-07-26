import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, html
from aiogram import types
from aiogram import F
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode, ContentType
from aiogram.types import Message
from sqlalchemy.future import select

from database import init_db, async_session_maker, User

from not_a_token import NOT_A_TOKEN

import httpx
import uuid

# Конфигурация API
TOKEN = NOT_A_TOKEN
API_URL = "http://localhost:8000"

# Create directories for saving files
circle_videos_path = Path("circle_videos")
face_images_path = Path("face_images")
circle_videos_path.mkdir(exist_ok=True, parents=True)
face_images_path.mkdir(exist_ok=True, parents=True)


def progress_bar(current, total, bar_length=10):
    percent = current / total
    filled_length = int(bar_length * percent)
    bar = "▮" * filled_length + "▯" * (bar_length - filled_length)
    return bar


async def check_status(user_id: int, message: types.Message, message_id: int):
    async with async_session_maker() as session:
        result = await session.execute(select(User).filter_by(user_id=user_id))
        user = result.scalars().first()
        if not user:
            return

        output_path = circle_videos_path / str(user_id)/user._video / "result.mp4"

        while True:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"{API_URL}/status/{user.task_id}")

                if response.status_code == 200:
                    task_data = response.json()
                    progress = task_data["progress"]
                

                    # Обновляем сообщение с прогрессом
                    await bot.edit_message_text(
                        f"Progress:{str(uuid.uuid4())[:4]} [{progress}%]{progress_bar(progress, 100)}",
                        chat_id=message.chat.id,
                        message_id=message_id,
                        parse_mode="html",
                    )

                    if progress >= 100:
                        await asyncio.sleep(5)
                        # Отправляем готовое видео
                        if output_path.exists():
                            with open(output_path, "rb") as video_file:
                                await bot.send_video_note(
                                    chat_id=message.chat.id,
                                    video_note=types.BufferedInputFile(video_file.read(), filename="result.mp4"),
                                )
                        keyboard = await get_main_keyboard(user_id)
                        await message.answer("What would you like to do next?", reply_markup=keyboard)
                        return
                else:
                    error = f"API error: {response.status_code} - {response.text}"
                    await bot.edit_message_text(f"❌ Error: {error}", chat_id=message.chat.id, message_id=message_id)
                    return

            except Exception as e:
                error = f"Connection error: {str(e)}"
                await bot.edit_message_text(f"❌ Error: {error}", chat_id=message.chat.id, message_id=message_id)
                return

            # Пауза между проверками
            await asyncio.sleep(1)


async def start_processing(user_id: int):
    async with async_session_maker() as session:
        result = await session.execute(select(User).filter_by(user_id=user_id))
        user = result.scalars().first()

        if not user or not user.circle_video_path or not user.face_image_path:
            return None, "Missing required files"

        source_path = user.circle_video_path
        target_face_path = user.face_image_path

        output_dir = circle_videos_path / str(user_id)/user._video
        output_path = str(output_dir / "result.mp4")

        payload = {"source_path": source_path, "output_path": output_path, "target_face_path": target_face_path}

        try:
            # Отправляем запрос к API
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{API_URL}/process", json=payload)

            if response.status_code == 200:
                # Обновляем информацию о пользователе
                task_data = response.json()
                user.task_id = task_data["task_id"]
                await session.commit()

                return task_data, "Processing started"
            else:
                error = f"API error: {response.status_code} - {response.text}"
                logging.error(error)
                return None, error

        except Exception as e:
            error = f"Connection error: {str(e)}"
            logging.error(error)
            return None, error


class Form(StatesGroup):
    add_circle = State()
    add_face_img = State()
    in_process = State()
    ready = State()


dp = Dispatcher()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def get_main_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    """Generate dynamic keyboard based on user's progress"""
    async with async_session_maker() as session:
        result = await session.execute(select(User).filter_by(user_id=user_id))
        user = result.scalars().first()

    circle_done = user and user.circle_video_path is not None
    face_done = user and user.face_image_path is not None

    kb = [
        [
            types.InlineKeyboardButton(
                text=f"{'✅ ' if circle_done else ''}Send circle video", callback_data="add_circle"
            )
        ],
        [types.InlineKeyboardButton(text=f"{'✅ ' if face_done else ''}Send face image", callback_data="add_face_img")],
    ]

    if circle_done and face_done:
        kb.append([types.InlineKeyboardButton(text="Start processing", callback_data="start_processing")])

    return types.InlineKeyboardMarkup(inline_keyboard=kb)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    last_msg_time = datetime.now()

    async with async_session_maker() as session:
        async with session.begin():
            result = await session.execute(select(User).filter_by(user_id=user_id))
            user = result.scalars().first()
            if user is None:
                new_user = User(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    last_msg_time=last_msg_time,
                )
                session.add(new_user)
                await message.reply("Welcome! Let's get started.")
            else:
                user.last_msg_time = last_msg_time
                await message.reply("Welcome back!")

    await message.answer(
        f"Hello, {html.bold(message.from_user.full_name)}!",
        reply_markup=types.ReplyKeyboardRemove(),
    )

    # Send dynamic keyboard based on user progress
    keyboard = await get_main_keyboard(user_id)
    await message.answer("What would you like to do next?", reply_markup=keyboard)


@dp.callback_query(F.data == "add_circle")
async def add_circle_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.add_circle)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer("Please send me a circle video message")


@dp.callback_query(F.data == "add_face_img")
async def add_face_img_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.add_face_img)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer("Please send me a photo of your face")


@dp.callback_query(F.data == "start_processing")
async def start_processing_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.set_state(Form.in_process)
    await callback.message.edit_reply_markup(reply_markup=None)

    # Отправляем начальное сообщение о процессе
    bot_msg = await callback.message.answer("Starting processing...")

    # Запускаем обработку
    await start_processing(user_id)

    # Запускаем отслеживание статуса как асинхронную задачу
    asyncio.create_task(check_status(user_id, callback.message, bot_msg.message_id))


# Handler for circle videos
@dp.message(Form.add_circle, F.content_type == ContentType.VIDEO_NOTE)
async def handle_circle_video(message: types.Message, state: FSMContext):
    video_note = message.video_note
    file_id = video_note.file_id
    user_id = message.from_user.id

    async with async_session_maker() as session:
        async with session.begin():
            result = await session.execute(select(User).filter_by(user_id=user_id))
            user = result.scalars().first()

            if user is not None:
                # Create user-specific directory
                _video = str(uuid.uuid4())
                user_dir = circle_videos_path / str(user_id) / _video
                user_dir.mkdir(exist_ok=True, parents=True)
                user._video = _video
                # Save video
                filename = "circle_video.mp4"
                file_path = user_dir / filename

                try:
                    file = await bot.get_file(file_id)
                    await bot.download_file(file.file_path, file_path)

                    # Update user record
                    user.circle_video_path = str(file_path)
                    await session.commit()

                    await message.answer("✅ Circle video saved successfully!")
                    await state.clear()

                    # Show updated menu
                    keyboard = await get_main_keyboard(user_id)
                    await message.answer("What would you like to do next?", reply_markup=keyboard)

                except Exception as e:
                    logging.error(f"Error saving video: {e}")
                    await message.answer("❌ Failed to save video. Please try again.")


# Handler for face photos
@dp.message(Form.add_face_img, F.content_type == ContentType.PHOTO)
async def handle_face_photo(message: types.Message, state: FSMContext):
    # Get highest quality photo
    photo = message.photo[-1]
    file_id = photo.file_id
    user_id = message.from_user.id

    async with async_session_maker() as session:
        async with session.begin():
            result = await session.execute(select(User).filter_by(user_id=user_id))
            user = result.scalars().first()

            if user is not None:
                # Create user-specific directory
                _photo = str(uuid.uuid4())
                user_dir = face_images_path / str(user_id) / _photo
                user_dir.mkdir(exist_ok=True, parents=True)
                user._photo = _photo

                # Save photo
                filename = "face_image.jpg"
                file_path = user_dir / filename

                try:
                    file = await bot.get_file(file_id)
                    await bot.download_file(file.file_path, file_path)

                    # Update user record
                    user.face_image_path = str(file_path)
                    await session.commit()

                    await message.answer("✅ Face photo saved successfully!")
                    await state.clear()

                    # Show updated menu
                    keyboard = await get_main_keyboard(user_id)
                    await message.answer("What would you like to do next?", reply_markup=keyboard)

                except Exception as e:
                    logging.error(f"Error saving photo: {e}")
                    await message.answer("❌ Failed to save photo. Please try again.")


# Handler for incorrect content types
@dp.message(Form.add_circle)
async def handle_wrong_content_circle(message: types.Message):
    await message.answer("Please send a circle video message (video note) or use /cancel")


@dp.message(Form.add_face_img)
async def handle_wrong_content_face(message: types.Message):
    await message.answer("Please send a photo or use /cancel")


# Cancel command handler
@dp.message(Command("cancel"))
@dp.message(F.text.casefold() == "cancel")
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("Operation cancelled")

    # Show main menu
    keyboard = await get_main_keyboard(message.from_user.id)
    await message.answer("What would you like to do next?", reply_markup=keyboard)


# Status command to show progress
@dp.message(Command("status"))
async def status_handler(message: types.Message):
    user_id = message.from_user.id
    async with async_session_maker() as session:
        result = await session.execute(select(User).filter_by(user_id=user_id))
        user = result.scalars().first()

    if user is None:
        await message.answer("You haven't started yet. Use /start to begin.")
        return

    status_message = [
        "Your current progress:",
        f"- Circle video: {'✅ Uploaded' if user.circle_video_path else '❌ Missing'}",
        f"- Face photo: {'✅ Uploaded' if user.face_image_path else '❌ Missing'}",
    ]

    if user.circle_video_path and user.face_image_path:
        status_message.append("\n✅ Both files uploaded! You can start processing.")

    await message.answer("\n".join(status_message))

    # Show appropriate keyboard
    keyboard = await get_main_keyboard(user_id)
    await message.answer("What would you like to do next?", reply_markup=keyboard)


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(init_db())
    asyncio.run(main())
