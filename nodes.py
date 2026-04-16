from __future__ import annotations

import base64
import io
import os
import re
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
    PACKAGE_VERSION = "1.1.0"


PACKAGE_NAME = "darkHUB Video to Base64"
NODE_CATEGORY = "darkHUB/Media"
OUTPUT_SUBFOLDER = "darkHUB-Video-to-Base64"
DEFAULT_DOWNLOADS_DIR = Path.home() / "Downloads"
DEFAULT_ENCODE_PREFIX = "darkhub_media"
DEFAULT_DECODE_PREFIX = "darkhub_decoded"
BASE64_PREVIEW_CHARS = 160
MIN_BASE64_CANDIDATE_LENGTH = 96
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
STATIC_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ANIMATED_IMAGE_EXTENSIONS = {".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm"}
BASE64_TEXT_CANDIDATE_PATTERN = re.compile(r"[A-Za-z0-9+/=\s]{96,}")
DATA_URI_PATTERN = re.compile(r"data:(?P<mime>[-\w.+]+/[-\w.+]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)", re.IGNORECASE)


def _log(message: str) -> None:
    print(f"[darkHUB Video to Base64 v{PACKAGE_VERSION}] {message}")


def _normalize_prefix(value: str | None, default: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    return cleaned or default


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _get_output_dir() -> Path:
    return Path(folder_paths.get_output_directory())


def _get_package_output_dir() -> Path:
    output_dir = _get_output_dir() / OUTPUT_SUBFOLDER
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _ensure_downloads_dir() -> Path:
    DEFAULT_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DOWNLOADS_DIR


def _save_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _save_optional_download_copy(path: Path, data: bytes | str) -> str:
    try:
        downloads_dir = _ensure_downloads_dir()
        target = downloads_dir / path.name
        if isinstance(data, bytes):
            _save_binary(target, data)
        else:
            _save_text(target, data)
        return str(target)
    except OSError as exc:
        _log(f"Downloads copy skipped for '{path.name}': {exc}")
        return ""


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

    candidates = []
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


def _relative_output_subfolder(path: Path) -> str:
    try:
        relative = path.parent.relative_to(_get_output_dir())
    except ValueError:
        return ""
    relative_str = relative.as_posix()
    return "" if relative_str == "." else relative_str


def _build_output_entry(path: Path, entry_type: str = "output", format_name: str | None = None) -> dict:
    entry = {
        "filename": path.name,
        "subfolder": _relative_output_subfolder(path),
        "type": entry_type,
    }
    if format_name:
        entry["format"] = format_name
    return entry


def _save_preview_image(frame: Image.Image, filename_stem: str) -> Path:
    preview_path = _get_package_output_dir() / f"{filename_stem}_preview.png"
    frame.save(preview_path, format="PNG")
    return preview_path


def _append_artifacts_to_ui(
    ui_payload: dict,
    media_path: Path,
    mime_type: str,
    text_path: Path | None = None,
    preview_path: Path | None = None,
) -> None:
    ui_payload.setdefault("files", []).append(_build_output_entry(media_path))
    if text_path is not None:
        ui_payload.setdefault("files", []).append(_build_output_entry(text_path))

    suffix = media_path.suffix.lower()
    if suffix in STATIC_IMAGE_EXTENSIONS:
        ui_payload.setdefault("images", []).append(_build_output_entry(media_path))
    elif suffix in ANIMATED_IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        ui_payload.setdefault("gifs", []).append(_build_output_entry(media_path, format_name=suffix[1:]))

    if preview_path is not None:
        ui_payload.setdefault("images", []).append(_build_output_entry(preview_path))


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
    save_kwargs = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames[1:],
        "duration": duration,
    }
    if loop:
        save_kwargs["loop"] = 0
    frames[0].save(buffer, **save_kwargs)
    return buffer.getvalue()


def encode_webp_bytes(frames: list[Image.Image], fps: float, loop: bool, quality: int) -> bytes:
    buffer = io.BytesIO()
    duration = max(int(1000 / fps), 1)
    save_kwargs = {
        "format": "WEBP",
        "save_all": True,
        "append_images": frames[1:],
        "duration": duration,
        "quality": quality,
    }
    if loop:
        save_kwargs["loop"] = 0
    frames[0].save(buffer, **save_kwargs)
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

    RETURN_TYPES = ("STRING", "STRING", "INT", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("base64_string", "mime_type", "frame_count", "preview_images", "media_path", "base64_text_path")
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
        base64_output = _build_data_uri(mime_type, base64_payload) if add_data_uri else base64_payload

        timestamp = int(time.time())
        filename_stem = f"{filename_prefix}_{timestamp}"
        media_path = _get_package_output_dir() / f"{filename_stem}{extension}"
        text_path = _get_package_output_dir() / f"{filename_stem}_base64.txt"
        preview_path = None

        _save_binary(media_path, raw_data)
        _save_text(text_path, base64_output)

        if extension in ANIMATED_IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            preview_path = _save_preview_image(frames[0], filename_stem)

        downloads_media_path = ""
        downloads_text_path = ""
        if auto_download:
            downloads_media_path = _save_optional_download_copy(media_path, raw_data)
            downloads_text_path = _save_optional_download_copy(text_path, base64_output)

        file_size = _format_size(len(raw_data))
        audio_label = " + audio" if audio_attached else ""
        base64_preview = _preview_base64(base64_output)
        status = (
            f"Base64 ready | {mime_type}{audio_label} | Frames: {batch_size} | "
            f"Size: {file_size} | Length: {len(base64_output):,} chars | Version: {PACKAGE_VERSION}"
        )
        if auto_download and downloads_media_path:
            status += " | Downloads: saved"

        _log(status)

        ui_payload = {
            "text": [f"{status}\nBase64 preview: {base64_preview}"],
            "base64_data": [base64_output],
            "base64_preview": [base64_preview],
            "mime_type": [mime_type],
            "media_filename": [media_path.name],
            "media_path": [str(media_path)],
            "txt_filename": [text_path.name],
            "txt_path": [str(text_path)],
            "file_size": [file_size],
            "version": [PACKAGE_VERSION],
            "downloads_media_path": [downloads_media_path],
            "downloads_text_path": [downloads_text_path],
        }
        _append_artifacts_to_ui(ui_payload, media_path, mime_type, text_path=text_path, preview_path=preview_path)

        return {
            "ui": ui_payload,
            "result": (base64_output, mime_type, batch_size, images, str(media_path), str(text_path)),
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

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "mime_type", "media_path", "base64_text_path")
    FUNCTION = "decode"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def decode(self, base64_string, auto_download=True, filename_prefix=DEFAULT_DECODE_PREFIX):
        import torch

        filename_prefix = _normalize_prefix(filename_prefix, DEFAULT_DECODE_PREFIX)
        detected_mime, cleaned = _extract_best_base64_payload(base64_string)

        if not cleaned:
            raise ValueError("[darkHUB] Empty base64 string received.")

        _log(f"Decoding Base64 input with {len(cleaned):,} characters.")

        try:
            raw_data = base64.b64decode(cleaned, validate=False)
        except Exception as exc:
            raise ValueError(
                f"[darkHUB] Base64 decode failed: {exc}. "
                "Expected a real Base64 string or data URI. If you connected Base64 Info, use the encoder's base64_string output instead."
            ) from exc

        extension, mime_type = _detect_binary_format(raw_data, fallback_mime=detected_mime)
        normalized_base64 = _build_data_uri(mime_type, cleaned)
        file_size = _format_size(len(raw_data))

        timestamp = int(time.time())
        filename_stem = f"{filename_prefix}_{timestamp}"
        output_path = _get_package_output_dir() / f"{filename_stem}{extension}"
        text_path = _get_package_output_dir() / f"{filename_stem}_base64.txt"
        preview_path = None

        _save_binary(output_path, raw_data)
        _save_text(text_path, normalized_base64)

        downloads_path = ""
        downloads_text_path = ""
        if auto_download:
            downloads_path = _save_optional_download_copy(output_path, raw_data)
            downloads_text_path = _save_optional_download_copy(text_path, normalized_base64)

        if extension in VIDEO_EXTENSIONS:
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

        if extension in ANIMATED_IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            preview_path = _save_preview_image(Image.fromarray((frames[0] * 255).clip(0, 255).astype(np.uint8)), filename_stem)

        tensor = torch.from_numpy(np.stack(frames, axis=0))

        base64_preview = _preview_base64(normalized_base64)
        status = (
            f"Decode complete | {mime_type} | Frames: {tensor.shape[0]} | "
            f"Size: {file_size} | Version: {PACKAGE_VERSION}"
        )
        if auto_download and downloads_path:
            status += " | Downloads: saved"
        _log(status)

        ui_payload = {
            "text": [f"{status}\nBase64 preview: {base64_preview}"],
            "base64_data": [normalized_base64],
            "base64_preview": [base64_preview],
            "mime_type": [mime_type],
            "media_filename": [output_path.name],
            "media_path": [str(output_path)],
            "txt_filename": [text_path.name],
            "txt_path": [str(text_path)],
            "filename": [output_path.name],
            "downloads_path": [downloads_path],
            "downloads_text_path": [downloads_text_path],
            "file_size": [file_size],
            "version": [PACKAGE_VERSION],
        }
        _append_artifacts_to_ui(ui_payload, output_path, mime_type, text_path=text_path, preview_path=preview_path)

        return {
            "ui": ui_payload,
            "result": (tensor, mime_type, str(output_path), str(text_path)),
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

        base64_preview = _preview_base64(base64_string)
        info_text = (
            f"Format: {mime_type}\n"
            f"Frames: {frame_count}\n"
            f"File size: {_format_size(raw_size)}\n"
            f"Base64 length: {len(base64_string):,} chars\n"
            f"Base64 preview: {base64_preview}\n"
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
