from __future__ import annotations

import base64
import io
import os
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image

try:
    from ._version import VERSION as PACKAGE_VERSION
except ImportError:
    PACKAGE_VERSION = "1.0.0"


PACKAGE_NAME = "darkHUB Video to Base64"
NODE_CATEGORY = "darkHUB/Media"
BASE64_PREVIEW_CHARS = 96
MIN_BASE64_CANDIDATE_LENGTH = 96
MIME_MAP = {
    "png": "image/png",
    "mp4": "video/mp4",
}
VIDEO_EXTENSIONS = {".mp4", ".webm"}
DATA_URI_PATTERN = re.compile(r"data:(?P<mime>[-\w.+]+/[-\w.+]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)", re.IGNORECASE)
BASE64_TEXT_CANDIDATE_PATTERN = re.compile(r"[A-Za-z0-9+/=\s]{96,}")


def _log(message: str) -> None:
    print(f"[{PACKAGE_NAME} v{PACKAGE_VERSION}] {message}")


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _clean_base64(text: str) -> str:
    cleaned = (text or "").strip().strip("'\"")
    if cleaned.startswith("data:"):
        _, _, cleaned = cleaned.partition(",")
    cleaned = cleaned.replace("\n", "").replace("\r", "").replace(" ", "").replace("\t", "")
    remainder = len(cleaned) % 4
    if remainder:
        cleaned += "=" * (4 - remainder)
    return cleaned


def _can_decode_base64(text: str) -> bool:
    if len(text) < 16:
        return False
    try:
        base64.b64decode(text, validate=True)
        return True
    except Exception:
        return False


def _preview_base64(text: str, limit: int = BASE64_PREVIEW_CHARS) -> str:
    payload = _clean_base64(text)
    if len(payload) <= limit:
        return payload
    return f"{payload[:limit]}..."


def _extract_data_uri(base64_string: str) -> tuple[str | None, str]:
    text = (base64_string or "").strip()
    match = DATA_URI_PATTERN.search(text)
    if match:
        return match.group("mime").lower(), _clean_base64(match.group("data"))
    if text.startswith("data:"):
        header, _, payload = text.partition(",")
        mime_type = header[5:].split(";", 1)[0].strip().lower() if header else None
        return mime_type or None, _clean_base64(payload)
    return None, _clean_base64(text)


def _extract_best_base64_payload(text: str) -> tuple[str | None, str]:
    detected_mime, cleaned = _extract_data_uri(text)
    if detected_mime or _can_decode_base64(cleaned):
        return detected_mime, cleaned

    candidates: list[str] = []
    for match in BASE64_TEXT_CANDIDATE_PATTERN.finditer(text or ""):
        candidate = _clean_base64(match.group(0))
        if len(candidate) >= MIN_BASE64_CANDIDATE_LENGTH and _can_decode_base64(candidate):
            candidates.append(candidate)

    if candidates:
        candidates.sort(key=len, reverse=True)
        return detected_mime, candidates[0]

    return detected_mime, cleaned


def _build_data_uri(mime_type: str, base64_payload: str) -> str:
    return f"data:{mime_type};base64,{_clean_base64(base64_payload)}"


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

    fallback_map = {
        "image/png": (".png", "image/png"),
        "image/gif": (".gif", "image/gif"),
        "image/webp": (".webp", "image/webp"),
        "video/mp4": (".mp4", "video/mp4"),
        "video/webm": (".webm", "video/webm"),
        "image/jpeg": (".jpg", "image/jpeg"),
    }
    if fallback_mime in fallback_map:
        return fallback_map[fallback_mime]

    return ".bin", fallback_mime or "application/octet-stream"


def _normalize_export_format(format_name: str, batch_size: int, audio) -> tuple[str, str | None]:
    requested = (format_name or "auto").lower()

    if requested == "auto":
        normalized = "png" if batch_size == 1 and audio is None else "mp4"
        return normalized, None

    if requested in {"png", "mp4"}:
        return requested, None

    if requested in {"gif", "webp"}:
        normalized = "png" if batch_size == 1 and audio is None else "mp4"
        return normalized, f"{requested.upper()} output is no longer generated directly in v{PACKAGE_VERSION}; using {normalized.upper()} instead."

    if requested == "webm":
        return "mp4", f"WEBM output is no longer generated directly in v{PACKAGE_VERSION}; using MP4 instead."

    raise ValueError(f"Unsupported output format: {format_name}")


def tensor_to_pil(tensor) -> Image.Image:
    array = (tensor.detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    if array.shape[-1] == 1:
        array = array.squeeze(-1)
    return Image.fromarray(array)


def encode_png_bytes(frames: list[Image.Image]) -> bytes:
    buffer = io.BytesIO()
    frames[0].save(buffer, format="PNG")
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


def encode_mp4_bytes(frames: list[Image.Image], fps: float, quality: int, audio_wav: bytes | None = None) -> bytes:
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("ffmpeg was not found. Install ffmpeg or run: pip install imageio-ffmpeg")

    width, height = frames[0].size
    padded_width = width if width % 2 == 0 else width + 1
    padded_height = height if height % 2 == 0 else height + 1
    crf = max(0, min(51, int(51 - quality * 0.51)))

    video_only_file = tempfile.NamedTemporaryFile(suffix="_video.mp4", delete=False)
    video_only_path = video_only_file.name
    video_only_file.close()

    temp_audio_path = None
    muxed_output_path = None

    try:
        encode_command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
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
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            str(crf),
            "-preset",
            "medium",
            "-movflags",
            "+faststart",
            video_only_path,
        ]
        process = subprocess.Popen(encode_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for frame in frames:
                process.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
        finally:
            if process.stdin:
                process.stdin.close()

        process.wait(timeout=300)
        if process.returncode != 0:
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg video encode failed: {stderr[-500:]}")

        if audio_wav is None:
            with open(video_only_path, "rb") as video_file:
                return video_file.read()

        temp_audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_audio_path = temp_audio_file.name
        temp_audio_file.write(audio_wav)
        temp_audio_file.close()

        muxed_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        muxed_output_path = muxed_file.name
        muxed_file.close()

        mux_command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
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
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            muxed_output_path,
        ]
        process = subprocess.Popen(mux_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = process.communicate(timeout=300)
        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg audio mux failed: {stderr_text[-500:]}")

        with open(muxed_output_path, "rb") as muxed_file_handle:
            return muxed_file_handle.read()
    finally:
        for temp_path in [video_only_path, temp_audio_path, muxed_output_path]:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


class DarkHubVideoToBase64:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "format": (["auto", "png", "mp4"],),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5}),
                "quality": ("INT", {"default": 100, "min": 1, "max": 100, "step": 1}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "add_data_uri": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("base64_string", "mime_type", "frame_count", "preview_images", "media_path", "base64_text_path")
    FUNCTION = "convert"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def convert(self, images, format="auto", fps=24.0, quality=100, audio=None, add_data_uri=False):
        batch_size = int(images.shape[0])
        if batch_size <= 0:
            raise ValueError("[darkHUB] The node received an empty IMAGE batch.")

        frames = [tensor_to_pil(images[index]) for index in range(batch_size)]
        normalized_format, format_note = _normalize_export_format(format, batch_size, audio)

        audio_wav = None
        audio_attached = False
        audio_note = None
        if audio is not None:
            if normalized_format == "mp4":
                try:
                    audio_wav = _audio_to_wav_bytes(audio)
                    audio_attached = True
                except Exception as exc:
                    raise ValueError(f"[darkHUB] Audio could not be prepared for MP4 export: {exc}") from exc
            else:
                audio_note = "Audio input was ignored because PNG output cannot embed audio."

        if normalized_format == "png":
            raw_data = encode_png_bytes(frames)
        elif normalized_format == "mp4":
            raw_data = encode_mp4_bytes(frames, fps, quality, audio_wav)
        else:
            raise ValueError(f"Unsupported output format: {normalized_format}")

        mime_type = MIME_MAP[normalized_format]
        base64_payload = base64.b64encode(raw_data).decode("utf-8")
        base64_output = _build_data_uri(mime_type, base64_payload) if add_data_uri else base64_payload
        file_size = _format_size(len(raw_data))

        status_parts = [
            f"Base64 ready | {mime_type}",
            f"Frames: {batch_size}",
            f"Size: {file_size}",
            f"Length: {len(base64_output):,} chars",
            f"Version: {PACKAGE_VERSION}",
        ]
        if audio_attached:
            status_parts.append("Audio: embedded")
        if format_note:
            status_parts.append(format_note)
        if audio_note:
            status_parts.append(audio_note)

        status = " | ".join(status_parts)
        _log(status)

        ui_payload = {
            "text": [status],
            "base64_data": [base64_output],
            "mime_type": [mime_type],
            "frame_count": [batch_size],
            "base64_length": [len(base64_output)],
            "file_size": [file_size],
            "has_audio": [audio_attached],
            "version": [PACKAGE_VERSION],
        }

        return {
            "ui": ui_payload,
            "result": (base64_output, mime_type, batch_size, images, "", ""),
        }


class DarkHubBase64ToImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base64_string": ("STRING", {"multiline": True, "forceInput": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "mime_type", "media_path", "base64_text_path")
    FUNCTION = "decode"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def decode(self, base64_string):
        import torch

        detected_mime, cleaned = _extract_best_base64_payload(base64_string)
        if not cleaned:
            raise ValueError("[darkHUB] Empty Base64 string received.")

        try:
            raw_data = base64.b64decode(cleaned, validate=False)
        except Exception as exc:
            raise ValueError(f"[darkHUB] Base64 decode failed: {exc}") from exc

        extension, mime_type = _detect_binary_format(raw_data, fallback_mime=detected_mime)
        if extension in VIDEO_EXTENSIONS:
            frames = self._decode_video_frames(raw_data, extension)
        else:
            frames = self._decode_image_frames(raw_data)

        if not frames:
            raise ValueError("[darkHUB] No frames were decoded from the provided Base64 data.")

        tensor = torch.from_numpy(np.stack(frames, axis=0))
        status = (
            f"Decode complete | {mime_type} | Frames: {tensor.shape[0]} | "
            f"Size: {_format_size(len(raw_data))} | Version: {PACKAGE_VERSION}"
        )
        _log(status)

        return {
            "ui": {"text": [status]},
            "result": (tensor, mime_type, "", ""),
        }

    def _decode_image_frames(self, raw_data: bytes) -> list[np.ndarray]:
        image = Image.open(io.BytesIO(raw_data))
        frame_count = getattr(image, "n_frames", 1)
        frames: list[np.ndarray] = []
        for index in range(frame_count):
            image.seek(index)
            frame = image.convert("RGB")
            frames.append(np.asarray(frame).astype(np.float32) / 255.0)
        return frames

    def _decode_video_frames(self, raw_data: bytes, extension: str) -> list[np.ndarray]:
        try:
            import imageio_ffmpeg
        except Exception as exc:
            raise RuntimeError("imageio-ffmpeg is required to decode MP4 Base64 payloads.") from exc

        temp_file = tempfile.NamedTemporaryFile(suffix=extension, delete=False)
        temp_file.write(raw_data)
        temp_file_path = temp_file.name
        temp_file.close()

        reader = None
        try:
            reader = imageio_ffmpeg.read_frames(temp_file_path, pix_fmt="rgb24")
            metadata = next(reader)
            width, height = metadata["size"]
            expected_size = width * height * 3
            frames: list[np.ndarray] = []
            for frame_bytes in reader:
                if len(frame_bytes) != expected_size:
                    continue
                frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(height, width, 3)
                frames.append(frame.astype(np.float32) / 255.0)
            return frames
        finally:
            close = getattr(reader, "close", None)
            if callable(close):
                close()
            if os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass


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
            f"Base64 preview: {_preview_base64(base64_string)}\n"
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