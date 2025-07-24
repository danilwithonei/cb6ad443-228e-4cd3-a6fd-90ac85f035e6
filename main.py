import os
import uuid
import cv2
import insightface
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, Body
from typing import Dict
from utils import (
    create_temp,
    extract_frames,
    get_temp_frame_paths,
    create_video,
    detect_fps,
    restore_audio,
    clean_temp,
    is_video,
    has_image_extension,
    get_temp_output_path,
    get_temp_directory_path,
)
from queue import Queue
import threading
import time
from tqdm import tqdm
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("video_processing.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Глобальные переменные
tasks: Dict[str, dict] = {}
task_queue = Queue()
queue_lock = threading.Lock()
processing_lock = threading.Lock()
in_process: bool = False

# Инициализация моделей
face_detector = None
face_swapper = None


@app.on_event("startup")
async def startup_event():
    """Инициализация приложения"""
    global face_detector, face_swapper

    logger.info("Starting application initialization")

    try:
        models_dir = "models"
        model_path = os.path.join(models_dir, "inswapper_128.onnx")

        if not os.path.exists(model_path):
            raise RuntimeError(f"Model not found at {model_path}")

        available_providers = ort.get_available_providers()
        print(available_providers)
        providers = [available_providers[1]]

        logger.info("Initializing face detector...")
        face_detector = insightface.app.FaceAnalysis(name="buffalo_l", providers=providers)
        face_detector.prepare(ctx_id=0, det_size=(640, 640))

        logger.info("Initializing face swapper...")
        face_swapper = insightface.model_zoo.get_model(model_path, providers=providers)

        # Запуск обработчика очереди
        threading.Thread(target=process_queue, daemon=True).start()
        logger.info("Queue processor started")

    except Exception as e:
        logger.error(f"Initialization failed: {str(e)}")
        raise


def process_queue():
    """Обработчик очереди задач"""
    logger.info("Queue processor is running")
    global in_process
    while True:
        try:
            time.sleep(1)
            with queue_lock:

                if not task_queue.empty() and not in_process:
                    task_data = task_queue.get()
                    task_id = task_data["task_id"]

                    logger.info(f"Starting processing task {task_id}")

                    tasks[task_id]["status"] = "processing"
                    tasks[task_id]["start_time"] = datetime.now().isoformat()

                    # Запуск обработки в отдельном потоке
                    processing_thread = threading.Thread(
                        target=process_video_task,
                        args=(
                            task_id,
                            task_data["source_path"],
                            task_data["output_path"],
                            task_data["target_face_path"],
                        ),
                        daemon=True,
                    )
                    processing_thread.start()

        except Exception as e:
            logger.error(f"Queue processor error: {str(e)}")


def process_video_task(task_id: str, source_path: str, output_path: str, target_face_path: str):
    """Обработка видео"""
    try:
        global in_process
        in_process = True
        task_info = tasks[task_id]
        task_info["message"] = "Initializing processing"
        logger.info(f"Task {task_id}: Initializing processing")

        # Загрузка целевого лица
        logger.debug(f"Task {task_id}: Loading target face")
        target_img = cv2.imread(target_face_path)
        if target_img is None:
            raise ValueError(f"Failed to read target image: {target_face_path}")

        target_faces = face_detector.get(target_img)
        if not target_faces:
            raise ValueError("No faces detected in target image")
        target_face = target_faces[0]

        # Создание временных файлов
        logger.debug(f"Task {task_id}: Creating temp files")
        create_temp(source_path)
        temp_dir = get_temp_directory_path(source_path)

        # Извлечение кадров
        task_info["message"] = "Extracting frames"
        logger.info(f"Task {task_id}: Extracting frames")
        extract_frames(source_path)
        frame_paths = get_temp_frame_paths(source_path)
        total_frames = len(frame_paths)

        if total_frames == 0:
            raise ValueError("No frames extracted from video")

        # Обработка кадров с прогресс-баром
        task_info["message"] = "Processing frames"
        logger.info(f"Task {task_id}: Processing {total_frames} frames")

        progress_bar = tqdm(
            enumerate(frame_paths), total=total_frames, desc=f"Processing {os.path.basename(source_path)}", unit="frame"
        )

        for i, frame_path in progress_bar:
            frame = cv2.imread(frame_path)
            if frame is None:
                continue

            # Детекция и замена лиц
            source_faces = face_detector.get(frame)
            if source_faces:
                source_face = source_faces[0]
                frame = face_swapper.get(frame, source_face, target_face, paste_back=True)

            cv2.imwrite(frame_path, frame)

            # Обновление прогресса
            progress = (i + 1) / total_frames * 100
            task_info["progress"] = round(progress, 1)
            progress_bar.set_postfix(progress=f"{progress:.1f}%")
            progress_bar.set_description(
                f"Processing {os.path.basename(source_path)}, queue size: {task_queue.qsize()}"
            )

        progress_bar.close()

        # Сборка видео
        task_info["message"] = "Creating video"
        logger.info(f"Task {task_id}: Creating video")
        fps = detect_fps(source_path)
        create_video(source_path, fps)

        # Восстановление аудио
        task_info["message"] = "Restoring audio"
        logger.info(f"Task {task_id}: Restoring audio")
        temp_output = get_temp_output_path(source_path)
        restore_audio(source_path, output_path)

        # Финализация
        clean_temp(source_path)
        task_info.update(
            {
                "status": "completed",
                "progress": 100,
                "message": "Video processing completed",
                "output_path": output_path,
                "end_time": datetime.now().isoformat(),
                "duration": (datetime.now() - datetime.fromisoformat(task_info["start_time"])).total_seconds(),
            }
        )
        logger.info(f"Task {task_id}: Completed successfully")
        in_process = False

    except Exception as e:
        task_info.update({"status": "failed", "message": f"Error: {str(e)}", "end_time": datetime.now().isoformat()})
        if "start_time" in task_info:
            task_info["duration"] = (datetime.now() - datetime.fromisoformat(task_info["start_time"])).total_seconds()
        logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
        clean_temp(source_path)
        in_process = False


@app.post("/process")
async def process_video(source_path: str = Body(...), output_path: str = Body(...), target_face_path: str = Body(...)):
    """Добавление задачи на обработку видео"""
    logger.info(f"New processing request: {source_path} -> {output_path}")

    # Валидация
    if not os.path.exists(source_path):
        logger.error(f"Source not found: {source_path}")
        raise HTTPException(400, "Source video not found")
    if not is_video(source_path):
        logger.error(f"Not a video file: {source_path}")
        raise HTTPException(400, "Source path is not a video file")
    if not os.path.exists(target_face_path):
        logger.error(f"Target face not found: {target_face_path}")
        raise HTTPException(400, "Target face image not found")
    if not has_image_extension(target_face_path):
        logger.error(f"Invalid image format: {target_face_path}")
        raise HTTPException(400, "Target face path is not a valid image")

    # Создание задачи
    task_id = str(uuid.uuid4())

    with queue_lock:
        tasks[task_id] = {
            "status": "queued",
            "progress": 0,
            "source_path": source_path,
            "output_path": output_path,
            "target_face_path": target_face_path,
            "created_at": datetime.now().isoformat(),
        }

        task_queue.put(
            {
                "task_id": task_id,
                "source_path": source_path,
                "output_path": output_path,
                "target_face_path": target_face_path,
            }
        )

        queue_size = task_queue.qsize()

    logger.info(f"Task {task_id} created, queue position: {queue_size}")
    return {
        "task_id": task_id,
        "status": "queued",
        "queue_position": queue_size,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """Получение статуса задачи"""
    with queue_lock:
        task = tasks.get(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            raise HTTPException(404, "Task not found")

        response = {
            "status": task["status"],
            "progress": task.get("progress", 0),
            "message": task.get("message", ""),
            "output_path": task.get("output_path", ""),
            "created_at": task.get("created_at"),
            "start_time": task.get("start_time"),
            "duration": task.get("duration"),
        }

        if task["status"] == "queued":
            queue_list = list(task_queue.queue)
            for i, item in enumerate(queue_list):
                if item["task_id"] == task_id:
                    response["queue_position"] = i + 1
                    break

        logger.debug(f"Status request for task {task_id}: {response}")
        return response


@app.get("/queue")
async def get_queue():
    """Получение информации об очереди"""
    with queue_lock:
        queue_list = list(task_queue.queue)
        active_tasks = {k: v for k, v in tasks.items() if v["status"] == "processing"}

        response = {
            "queue_size": task_queue.qsize(),
            "active_tasks": len(active_tasks),
            "queued_tasks": [
                {
                    "task_id": task["task_id"],
                    "source": os.path.basename(task["source_path"]),
                    "created_at": tasks[task["task_id"]].get("created_at"),
                }
                for task in queue_list
            ],
            "active_task_details": [
                {
                    "task_id": task_id,
                    "progress": task["progress"],
                    "message": task["message"],
                    "start_time": task["start_time"],
                }
                for task_id, task in active_tasks.items()
            ],
        }

        logger.debug("Queue status request")
        return response


@app.get("/system/status")
async def system_status():
    """Системная информация"""
    with queue_lock:
        return {
            "timestamp": datetime.now().isoformat(),
            "total_tasks": len(tasks),
            "queued_tasks": task_queue.qsize(),
            "active_tasks": sum(1 for t in tasks.values() if t["status"] == "processing"),
            "completed_tasks": sum(1 for t in tasks.values() if t["status"] == "completed"),
            "failed_tasks": sum(1 for t in tasks.values() if t["status"] == "failed"),
            "system_load": os.getloadavg() if hasattr(os, "getloadavg") else None,
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
