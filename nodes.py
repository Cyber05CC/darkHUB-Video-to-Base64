from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image

import folder_paths

try:
    from ._version import VERSION as PACKAGE_VERSION
except ImportError:
    PACKAGE_VERSION = "1.0.0"


PACKAGE_NAME = "darkHUB Video to Base64"
NODE_CATEGORY = "darkHUB/Media"
DEFAULT_DOWNLOADS_DIR = Path.home() / "Downloads"
DEFAULT_ENCODE_PREFIX = "darkhub_media"
DEFAULT_DECODE_PREFIX = "darkhub_decoded"
MIME_MAP = {
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
}
EXTENSION_MAP = {
    "png": ".png",
    "gif": ".gif",
    "webp": ".webp",
    "mp4": ".mp4",
    "webm": ".webm",
}


def _log(message: str) -> None:
    print(f"[darkHUB Video to Base64 v{PACKAGE_VERSION}] {message}")


def _normalize_prefix(value: str | None, default: str) -> str:
    cleaned = (value or "").strip().replace(" ", "_")
    return cleaned or default


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _get_output_dir() -> Path:
    return Path(folder_paths.get_output_directory())


def _ensure_downloads_dir() -> Path:
    DEFAULT_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DOWNLOADS_DIR


def _save_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_base64(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("data:"):
        _, _, cleaned = cleaned.partition(",")
    cleaned = cleaned.replace("\n", "").replace("\r", "").replace(" ", "").replace("\t", "")
    remainder = len(cleaned) % 4
    if remainder:
        cleaned += "=" * (4 - remainder)
    return cleaned


def _extract_data_uri(base64_string: str) -> tuple[str | None, str]:
    text = (base64_string or "").strip()
    if text.startswith("data:"):
        header, _, payload = text.partition(",")
        mime_type = header[5:].split(";", 1)[0].strip().lower() if header else None
        return mime_type or None, _clean_base64(payload)
    return None, _clean_base64(text)


def _detect_binary_format(raw_data: bytes, fallback_mime: str | None = None) -> tuple[str, str]:
    if raw_data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    if raw_data[:3] == b"GIF":
        return ".gif", "image/gif"
    if len(raw_data) > 12 and raw_data[:4] == b"RIFF" and raw_data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if len(raw_data) > 8 and raw_data[4:8] == b"ftyp":
        return ".mp4", "video/mp4"
    if raw_data[:4] == b"\x1aE\xdf\xa3":
        return ".webm", "video/webm"
    if raw_data[:2] == b"\xff\xd8":
        return ".jpg", "image/jpeg"

    if fallback_mime == "image/png":
        return ".png", fallback_mime
    if fallback_mime == "image/gif":
        return ".gif", fallback_mime
    if fallback_mime == "image/webp":
        return ".webp", fallback_mime
    if fallback_mime == "video/mp4":
        return ".mp4", fallback_mime
    if fallback_mime == "video/webm":
        return ".webm", fallback_mime
    if fallback_mime == "image/jpeg":
        return ".jpg", fallback_mime

    return ".bin", fallback_mime or "application/octet-stream"


def tensor_to_pil(tensor) -> Image.Image:
    array = (tensor.detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    if array.shape[-1] == 1:
        array = array.squeeze(-1)
    return Image.fromarray(array)


def encode_png_bytes(frames: list[Image.Image]) -> bytes:
    buffer = io.BytesIO()
    frames[0].save(buffer, format="PNG")
    return buffer.getvalue()


def encode_gif_bytes(frames: list[Image.Image], fps: float, loop: bool) -> bytes:
    buffer = io.BytesIO()
    duration = max(int(1000 / fps), 10)
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0 if loop else 1,
    )
    return buffer.getvalue()


def encode_webp_bytes(frames: list[Image.Image], fps: float, loop: bool, quality: int) -> bytes:
    buffer = io.BytesIO()
    duration = max(int(1000 / fps), 1)
    frames[0].save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0 if loop else 1,
        quality=quality,
    )
    return buffer.getvalue()


def _find_ffmpeg() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _find_ffprobe(ffmpeg_path: str | None) -> str | None:
    executable = shutil.which("ffprobe")
    if executable:
        return executable

    if ffmpeg_path:
        ffmpeg_file = Path(ffmpeg_path)
        probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        candidate = ffmpeg_file.with_name(probe_name)
        if candidate.exists():
            return str(candidate)

    return None


def _audio_to_wav_bytes(audio) -> bytes:
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])

    if waveform.dim() == 3:
        waveform = waveform[0]

    numpy_audio = waveform.detach().cpu().numpy()
    channels = int(numpy_audio.shape[0])
    samples = int(numpy_audio.shape[1])
    if channels <= 0 or samples <= 0:
        raise ValueError("Audio input does not contain any samples.")

    wav_int16 = (numpy_audio.T * 32767).clip(-32768, 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(wav_int16.tobytes())

    return buffer.getvalue()


def _encode_video_with_audio(
    frames: list[Image.Image],
    fps: float,
    suffix: str,
    codec: str,
    extra_args: list[str],
    audio_wav_bytes: bytes | None = None,
) -> bytes:
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("ffmpeg was not found. Install ffmpeg or run: pip install imageio-ffmpeg")

    width, height = frames[0].size
    padded_width = width if width % 2 == 0 else width + 1
    padded_height = height if height % 2 == 0 else height + 1

    final_video_path = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    final_video_path.close()

    temp_audio_path = None
    muxed_output_path = None
    video_only_path = None

    try:
        command = [
            ffmpeg,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{width}x{height}",
            "-pix_fmt",
            "rgb24",
            "-r",
            str(fps),
            "-i",
            "-",
            "-vf",
            f"pad={padded_width}:{padded_height}:0:0",
            "-c:v",
            codec,
            "-pix_fmt",
            "yuv420p",
        ]
        command.extend(extra_args)

        if audio_wav_bytes is None:
            command.append(final_video_path.name)
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for frame in frames:
                process.stdin.write(np.asarray(frame).tobytes())
            process.stdin.close()
            process.wait(timeout=300)
            if process.returncode != 0:
                stderr = process.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"ffmpeg video encode failed: {stderr[-500:]}")

            return Path(final_video_path.name).read_bytes()

        temp_video_file = tempfile.NamedTemporaryFile(suffix=f"_video{suffix}", delete=False)
        video_only_path = temp_video_file.name
        temp_video_file.close()

        command.append(video_only_path)
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for frame in frames:
            process.stdin.write(np.asarray(frame).tobytes())
        process.stdin.close()
        process.wait(timeout=300)
        if process.returncode != 0:
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg video encode failed: {stderr[-500:]}")

        temp_audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_audio_path = temp_audio_file.name
        temp_audio_file.write(audio_wav_bytes)
        temp_audio_file.close()

        muxed_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        muxed_output_path = muxed_file.name
        muxed_file.close()

        audio_args = ["-c:a", "libopus"] if suffix == ".webm" else ["-c:a", "aac", "-b:a", "192k"]
        mux_command = [
            ffmpeg,
            "-y",
            "-i",
            video_only_path,
            "-i",
            temp_audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            *audio_args,
            "-shortest",
        ]
        if suffix == ".mp4":
            mux_command.extend(["-movflags", "+faststart"])
        mux_command.append(muxed_output_path)

        process = subprocess.Popen(mux_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = process.communicate(timeout=300)
        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg audio mux failed: {stderr_text[-500:]}")

        return Path(muxed_output_path).read_bytes()
    finally:
        for temp_path in [final_video_path.name, temp_audio_path, muxed_output_path, video_only_path]:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


def encode_mp4_bytes(frames: list[Image.Image], fps: float, quality: int, audio_wav: bytes | None = None) -> bytes:
    crf = max(0, min(51, int(51 - quality * 0.51)))
    return _encode_video_with_audio(
        frames=frames,
        fps=fps,
        suffix=".mp4",
        codec="libx264",
        extra_args=["-crf", str(crf), "-preset", "medium", "-movflags", "+faststart"],
        audio_wav_bytes=audio_wav,
    )


def encode_webm_bytes(frames: list[Image.Image], fps: float, quality: int, audio_wav: bytes | None = None) -> bytes:
    crf = max(0, min(63, int(63 - quality * 0.63)))
    return _encode_video_with_audio(
        frames=frames,
        fps=fps,
        suffix=".webm",
        codec="libvpx-vp9",
        extra_args=["-crf", str(crf), "-b:v", "0"],
        audio_wav_bytes=audio_wav,
    )


class DarkHubVideoToBase64:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "format": (["auto", "png", "gif", "webp", "mp4", "webm"],),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5}),
                "quality": ("INT", {"default": 85, "min": 1, "max": 100, "step": 1}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "loop": ("BOOLEAN", {"default": True}),
                "add_data_uri": ("BOOLEAN", {"default": False}),
                "auto_download": ("BOOLEAN", {"default": True}),
                "filename_prefix": ("STRING", {"default": DEFAULT_ENCODE_PREFIX}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("base64_string", "mime_type", "frame_count")
    FUNCTION = "convert"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def convert(
        self,
        images,
        format="auto",
        fps=24.0,
        quality=85,
        audio=None,
        loop=True,
        add_data_uri=False,
        auto_download=True,
        filename_prefix=DEFAULT_ENCODE_PREFIX,
    ):
        batch_size = int(images.shape[0])
        frames = [tensor_to_pil(images[index]) for index in range(batch_size)]
        filename_prefix = _normalize_prefix(filename_prefix, DEFAULT_ENCODE_PREFIX)

        if format == "auto":
            format = "png" if batch_size == 1 and audio is None else "mp4"

        audio_wav = None
        audio_attached = False
        if audio is not None and format in ("mp4", "webm"):
            try:
                audio_wav = _audio_to_wav_bytes(audio)
                audio_attached = True
                _log(f"Audio track detected: {len(audio_wav):,} bytes (WAV temp payload)")
            except Exception as exc:
                _log(f"Audio conversion failed and will be skipped: {exc}")
        elif audio is not None:
            _log(f"Audio input ignored because '{format}' does not support audio output.")

        if format == "png":
            raw_data = encode_png_bytes(frames)
        elif format == "gif":
            raw_data = encode_gif_bytes(frames, fps, loop)
        elif format == "webp":
            raw_data = encode_webp_bytes(frames, fps, loop, quality)
        elif format == "mp4":
            raw_data = encode_mp4_bytes(frames, fps, quality, audio_wav)
        elif format == "webm":
            raw_data = encode_webm_bytes(frames, fps, quality, audio_wav)
        else:
            raise ValueError(f"Unsupported output format: {format}")

        base64_payload = base64.b64encode(raw_data).decode("utf-8")
        mime_type = MIME_MAP[format]
        extension = EXTENSION_MAP[format]
        base64_output = f"data:{mime_type};base64,{base64_payload}" if add_data_uri else base64_payload

        timestamp = int(time.time())
        media_filename = f"{filename_prefix}_{timestamp}{extension}"
        text_filename = f"{filename_prefix}_{timestamp}_base64.txt"

        output_dir = _get_output_dir()
        _save_binary(output_dir / media_filename, raw_data)
        _save_text(output_dir / text_filename, base64_output)

        downloads_media_path = ""
        downloads_text_path = ""
        if auto_download:
            downloads_dir = _ensure_downloads_dir()
            downloads_media_path = str(downloads_dir / media_filename)
            downloads_text_path = str(downloads_dir / text_filename)
            _save_binary(downloads_dir / media_filename, raw_data)
            _save_text(downloads_dir / text_filename, base64_output)

        file_size = _format_size(len(raw_data))
        audio_label = " + audio" if audio_attached else ""
        status = (
            f"Base64 ready | {mime_type}{audio_label} | Frames: {batch_size} | "
            f"Size: {file_size} | Length: {len(base64_output):,} chars | Version: {PACKAGE_VERSION}"
        )
        if auto_download:
            status += " | Downloads: saved"

        _log(status)

        return {
            "ui": {
                "text": [status],
                "base64_data": [base64_output],
                "mime_type": [mime_type],
                "media_filename": [media_filename],
                "txt_filename": [text_filename],
                "file_size": [file_size],
                "version": [PACKAGE_VERSION],
                "downloads_media_path": [downloads_media_path],
                "downloads_text_path": [downloads_text_path],
            },
            "result": (base64_output, mime_type, batch_size),
        }


class DarkHubBase64ToImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base64_string": ("STRING", {"multiline": True, "forceInput": True}),
            },
            "optional": {
                "auto_download": ("BOOLEAN", {"default": True}),
                "filename_prefix": ("STRING", {"default": DEFAULT_DECODE_PREFIX}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "decode"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def decode(self, base64_string, auto_download=True, filename_prefix=DEFAULT_DECODE_PREFIX):
        import torch

        filename_prefix = _normalize_prefix(filename_prefix, DEFAULT_DECODE_PREFIX)
        detected_mime, cleaned = _extract_data_uri(base64_string)

        if not cleaned:
            raise ValueError("[darkHUB] Empty base64 string received.")

        _log(f"Decoding Base64 input with {len(cleaned):,} characters.")

        try:
            raw_data = base64.b64decode(cleaned)
        except Exception as exc:
            raise ValueError(f"[darkHUB] Base64 decode failed: {exc}") from exc

        extension, mime_type = _detect_binary_format(raw_data, fallback_mime=detected_mime)
        file_size = _format_size(len(raw_data))

        timestamp = int(time.time())
        output_filename = f"{filename_prefix}_{timestamp}{extension}"
        output_dir = _get_output_dir()
        output_path = output_dir / output_filename
        _save_binary(output_path, raw_data)

        downloads_path = ""
        if auto_download:
            downloads_dir = _ensure_downloads_dir()
            downloads_path = str(downloads_dir / output_filename)
            _save_binary(downloads_dir / output_filename, raw_data)

        if extension in (".mp4", ".webm"):
            frames = self._decode_video_frames(raw_data, extension)
            if not frames:
                raise RuntimeError(
                    f"[darkHUB] Video data was saved to '{output_path}', but no frames could be decoded. "
                    "Install ffmpeg to convert MP4/WEBM Base64 data back into IMAGE tensors."
                )
        else:
            frames = self._decode_image_frames(raw_data, output_path)

        if not frames:
            raise ValueError("[darkHUB] No frames were decoded from the provided Base64 data.")

        tensor = torch.from_numpy(np.stack(frames, axis=0))

        status = f"Decode complete | {mime_type} | Frames: {tensor.shape[0]} | Size: {file_size} | Version: {PACKAGE_VERSION}"
        if auto_download:
            status += " | Downloads: saved"
        _log(status)

        return {
            "ui": {
                "text": [status],
                "filename": [output_filename],
                "downloads_path": [downloads_path],
                "version": [PACKAGE_VERSION],
            },
            "result": (tensor,),
        }

    def _decode_image_frames(self, raw_data: bytes, fallback_path: Path) -> list[np.ndarray]:
        frames = []
        try:
            image = Image.open(io.BytesIO(raw_data))
        except Exception:
            image = Image.open(fallback_path)

        frame_count = getattr(image, "n_frames", 1)
        for index in range(frame_count):
            image.seek(index)
            frame = image.convert("RGB")
            frames.append(np.asarray(frame).astype(np.float32) / 255.0)

        return frames

    def _decode_video_frames(self, raw_data: bytes, extension: str) -> list[np.ndarray]:
        ffmpeg = _find_ffmpeg()
        if ffmpeg is None:
            raise RuntimeError("ffmpeg was not found. Install ffmpeg or run: pip install imageio-ffmpeg")

        temp_file = tempfile.NamedTemporaryFile(suffix=extension, delete=False)
        temp_file.write(raw_data)
        temp_file_path = temp_file.name
        temp_file.close()

        try:
            width, height = self._probe_video_dimensions(ffmpeg, temp_file_path)
            if not width or not height:
                return self._decode_video_frames_with_imageio(temp_file_path)

            command = [
                ffmpeg,
                "-i",
                temp_file_path,
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-v",
                "error",
                "-",
            ]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, _ = process.communicate(timeout=120)
            if process.returncode != 0 or not stdout:
                return self._decode_video_frames_with_imageio(temp_file_path)

            frame_size = width * height * 3
            frames = []
            for offset in range(0, len(stdout), frame_size):
                chunk = stdout[offset : offset + frame_size]
                if len(chunk) < frame_size:
                    break
                frame = np.frombuffer(chunk, dtype=np.uint8).reshape(height, width, 3)
                frames.append(frame.astype(np.float32) / 255.0)
            return frames
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def _decode_video_frames_with_imageio(self, video_path: str) -> list[np.ndarray]:
        try:
            import imageio_ffmpeg
        except Exception:
            return []

        try:
            reader = imageio_ffmpeg.read_frames(video_path, pix_fmt="rgb24")
            metadata = next(reader)
            width, height = metadata["size"]
        except Exception:
            return []

        frames = []
        expected_size = width * height * 3
        try:
            for frame_bytes in reader:
                if len(frame_bytes) != expected_size:
                    continue
                frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(height, width, 3)
                frames.append(frame.astype(np.float32) / 255.0)
        except Exception:
            return frames
        finally:
            close = getattr(reader, "close", None)
            if callable(close):
                close()

        return frames

    def _probe_video_dimensions(self, ffmpeg_path: str, video_path: str) -> tuple[int | None, int | None]:
        ffprobe = _find_ffprobe(ffmpeg_path)
        if ffprobe is None:
            return None, None

        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except Exception:
            return None, None

        dimensions = result.stdout.strip().split(",")
        if len(dimensions) != 2:
            return None, None

        try:
            return int(dimensions[0]), int(dimensions[1])
        except ValueError:
            return None, None


class DarkHubBase64Info:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base64_string": ("STRING", {"multiline": False, "forceInput": True}),
                "mime_type": ("STRING", {"multiline": False, "forceInput": True}),
                "frame_count": ("INT", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info_text",)
    FUNCTION = "info"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def info(self, base64_string, mime_type, frame_count):
        cleaned = _clean_base64(base64_string)
        try:
            raw_size = len(base64.b64decode(cleaned))
        except Exception:
            raw_size = 0

        info_text = (
            f"Format: {mime_type}\n"
            f"Frames: {frame_count}\n"
            f"File size: {_format_size(raw_size)}\n"
            f"Base64 length: {len(base64_string):,} chars\n"
            f"Node version: {PACKAGE_VERSION}"
        )
        _log(f"Info requested\n{info_text}")
        return {"ui": {"text": [info_text]}, "result": (info_text,)}


NODE_CLASS_MAPPINGS = {
    "DarkHubVideoToBase64": DarkHubVideoToBase64,
    "DarkHubBase64ToImage": DarkHubBase64ToImage,
    "DarkHubBase64Info": DarkHubBase64Info,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DarkHubVideoToBase64": "Video/Image -> Base64 (darkHUB)",
    "DarkHubBase64ToImage": "Base64 -> Image (darkHUB)",
    "DarkHubBase64Info": "Base64 Info (darkHUB)",
}
