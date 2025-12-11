import os
import cv2
import insightface
import onnxruntime as ort
import logging
from datetime import datetime
from tqdm import tqdm
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
    is_image,
)


class FaceSwapper:
    def __init__(self, model_path="models/inswapper_128.onnx", providers=None):
        """
        Инициализация моделей для замены лиц

        Args:
            model_path (str): Путь к модели inswapper
            providers (list): ONNX providers (GPU/CPU)
        """
        # Настройка логирования
        self.logger = logging.getLogger("FaceSwapper")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(handler)

        self.total_frames = 0
        self.current_frame = 0

        # Определение доступных провайдеров
        if providers is None:
            available_providers = ort.get_available_providers()
            providers = (
                ["CUDAExecutionProvider"]
                if "CUDAExecutionProvider" in available_providers
                else ["CPUExecutionProvider"]
            )

        self.logger.info(f"Using providers: {providers}")

        # Инициализация моделей
        try:
            self.logger.info("Initializing face detector...")
            self.face_detector = insightface.app.FaceAnalysis(name="buffalo_l", providers=providers)
            self.face_detector.prepare(ctx_id=0, det_size=(640, 640))

            self.logger.info("Initializing face swapper...")
            self.face_swapper = insightface.model_zoo.get_model(model_path, providers=providers)
            self.logger.info("Initialization successful")
        except Exception as e:
            self.logger.error(f"Initialization failed: {str(e)}")
            raise

    def swap_faces(self, source_video: str, target_face_img: str, output_video: str, update_status_func=None):
        """
        Основной метод для замены лица в видео

        Args:
            source_video (str): Путь к исходному видео
            target_face_img (str): Путь к изображению с целевым лицом
            output_video (str): Путь для сохранения результата

        Returns:
            dict: Информация о результате обработки
        """
        start_time = datetime.now()
        self.logger.info(f"Starting processing: {source_video} -> {output_video}")

        update_status_func("start_processing")

        try:
            # Валидация входных данных
            self._validate_video_inputs(source_video, target_face_img)

            # Загрузка целевого лица
            target_face = self._load_target_face(target_face_img)

            # Создание временных файлов
            temp_dir = create_temp(source_video)
            self.logger.debug(f"Created temp directory: {temp_dir}")

            try:
                # Извлечение кадров
                self.logger.info("Extracting frames...")
                extract_frames(source_video)
                frame_paths = get_temp_frame_paths(source_video)
                total_frames = len(frame_paths)

                if total_frames == 0:
                    raise ValueError("No frames extracted from video")

                self.logger.info(f"Processing {total_frames} frames")

                self.total_frames = total_frames
                # Обработка кадров
                for i, frame_path in enumerate(tqdm(frame_paths, desc="Processing frames")):
                    frame = cv2.imread(frame_path)
                    if frame is None:
                        continue

                    # Замена лица в кадре
                    processed_frame = self._process_frame(frame, target_face)
                    cv2.imwrite(frame_path, processed_frame)
                    self.current_frame = i
                    if i % 10 == 0:
                        update_status_func("processing", {"total_frames": total_frames, "current_frame": i + 1})

                # Сборка видео
                self.logger.info("Creating output video...")
                fps = detect_fps(source_video)
                create_video(source_video, fps)

                # Восстановление аудио
                self.logger.info("Restoring audio...")
                get_temp_output_path(source_video)
                restore_audio(source_video, output_video)

                # Формирование результата
                duration = (datetime.now() - start_time).total_seconds()
                result = {
                    "status": "completed",
                    "output_path": output_video,
                    "frames_processed": total_frames,
                    "processing_time_sec": round(duration, 2),
                    "message": f"Successfully processed {total_frames} frames",
                }
                self.logger.info(f"Processing completed in {duration:.2f} seconds")
                return result

            finally:
                # Очистка временных файлов
                clean_temp(source_video)
                self.logger.debug("Temporary files cleaned up")

        except Exception as e:
            clean_temp(source_video)
            self.logger.error(f"Processing failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Face swap failed: {str(e)}") from e

    def swap_face_in_image(self, source_image: str, target_face_img: str, output_image: str):
        """
        Замена лица в статическом изображении

        Args:
            source_image (str): Путь к исходному изображению
            target_face_img (str): Путь к изображению с целевым лицом
            output_image (str): Путь для сохранения результата

        Returns:
            dict: Информация о результате обработки
        """
        start_time = datetime.now()
        self.logger.info(f"Starting image processing: {source_image} -> {output_image}")

        try:
            # Валидация входных данных
            self._validate_image_inputs(source_image, target_face_img)

            # Загрузка целевого лица
            target_face = self._load_target_face(target_face_img)

            # Загрузка исходного изображения
            self.logger.info("Loading source image...")
            source_img = cv2.imread(source_image)
            if source_img is None:
                raise ValueError(f"Failed to read source image: {source_image}")

            # Обработка изображения
            self.logger.info("Processing image...")
            processed_img = self._process_frame(source_img, target_face)

            # Сохранение результата
            self.logger.info("Saving result...")
            success = cv2.imwrite(output_image, processed_img)
            if not success:
                raise IOError(f"Failed to save result to {output_image}")

            # Формирование результата
            duration = (datetime.now() - start_time).total_seconds()
            result = {
                "status": "completed",
                "output_path": output_image,
                "processing_time_sec": round(duration, 2),
                "message": "Face swap in image completed successfully",
            }
            self.logger.info(f"Image processing completed in {duration:.2f} seconds")
            return result

        except Exception as e:
            self.logger.error(f"Image processing failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Image face swap failed: {str(e)}") from e

    def _validate_video_inputs(self, source_video: str, target_face_img: str):
        """Проверка корректности входных данных для видео"""
        if not os.path.exists(source_video):
            raise FileNotFoundError(f"Source video not found: {source_video}")

        if not is_video(source_video):
            raise ValueError(f"Invalid video format: {source_video}")

        self._validate_common_inputs(target_face_img)

    def _validate_image_inputs(self, source_image: str, target_face_img: str):
        """Проверка корректности входных данных для изображений"""
        if not os.path.exists(source_image):
            raise FileNotFoundError(f"Source image not found: {source_image}")

        if not is_image(source_image):
            raise ValueError(f"Invalid image format: {source_image}")

        self._validate_common_inputs(target_face_img)

    def _validate_common_inputs(self, target_face_img: str):
        """Общая валидация для целевого изображения лица"""
        if not os.path.exists(target_face_img):
            raise FileNotFoundError(f"Target face image not found: {target_face_img}")

        if not has_image_extension(target_face_img):
            raise ValueError(f"Invalid image format: {target_face_img}")

    def _load_target_face(self, image_path: str):
        """Загрузка и детекция целевого лица"""
        target_img = cv2.imread(image_path)
        if target_img is None:
            raise ValueError(f"Failed to read target image: {image_path}")

        faces = self.face_detector.get(target_img)
        if not faces:
            raise ValueError("No faces detected in target image")

        self.logger.info(f"Found {len(faces)} faces in target image, using first")
        return faces[0]

    def _process_frame(self, frame, target_face):
        """
        Обработка одного кадра или изображения с заменой лица

        Args:
            frame (numpy.ndarray): Исходное изображение/кадр
            target_face: Лицо для замены

        Returns:
            numpy.ndarray: Обработанное изображение
        """
        faces = self.face_detector.get(frame)

        if not faces:
            self.logger.warning("No faces detected in frame/image")
            return frame  # Возвращаем исходное изображение если лиц нет

        self.logger.debug(f"Detected {len(faces)} faces in frame")

        # Заменяем первое обнаруженное лицо
        source_face = faces[0]
        return self.face_swapper.get(frame, source_face, target_face, paste_back=True)


# Пример использования
if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    try:
        # Инициализация обработчика
        swapper = FaceSwapper(providers=["CUDAExecutionProvider"])

        # Пример обработки видео
        video_result = swapper.swap_faces(
            source_video="input.mp4", target_face_img="face.jpg", output_video="output_video.mp4"
        )
        print("Video processing result:", video_result)

        # Пример обработки изображения
        image_result = swapper.swap_face_in_image(
            source_image="input.jpg", target_face_img="face.jpg", output_image="output_image.jpg"
        )
        print("Image processing result:", image_result)

    except Exception as e:
        logging.error(f"Application failed: {str(e)}")
