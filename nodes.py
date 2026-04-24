from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image

try:
    from ._version import VERSION as PACKAGE_VERSION
except ImportError:
    PACKAGE_VERSION = "3.0.0"


PACKAGE_NAME = "darkHUB Base64"
NODE_CATEGORY = "darkHUB"
MIME_MAP = {
    "png": "image/png",
    "mp4": "video/mp4",
}


def _log(message: str) -> None:
    print(f"[{PACKAGE_NAME} v{PACKAGE_VERSION}] {message}")


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _resolve_output_format(format_name: str, batch_size: int, audio) -> str:
    requested = (format_name or "auto").lower()
    if requested == "auto":
        return "png" if batch_size == 1 and audio is None else "mp4"
    if requested not in MIME_MAP:
        raise ValueError("[darkHUB] Supported formats are only auto, png, and mp4.")
    return requested


def tensor_to_pil(tensor) -> Image.Image:
    array = (tensor.detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    if array.shape[-1] == 1:
        array = array.squeeze(-1)
    return Image.fromarray(array)


def encode_png_bytes(frame: Image.Image) -> bytes:
    buffer = io.BytesIO()
    frame.save(buffer, format="PNG")
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
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("base64_string", "mime_type", "frame_count")
    FUNCTION = "convert"
    CATEGORY = NODE_CATEGORY
    OUTPUT_NODE = True

    def convert(self, images, format="auto", fps=24.0, quality=100, audio=None):
        batch_size = int(images.shape[0])
        if batch_size <= 0:
            raise ValueError("[darkHUB] The node received an empty IMAGE batch.")

        output_format = _resolve_output_format(format, batch_size, audio)
        frames = [tensor_to_pil(images[index]) for index in range(batch_size)]

        if output_format == "png":
            if audio is not None:
                raise ValueError("[darkHUB] PNG output cannot contain audio. Use auto or mp4 when audio is connected.")
            raw_data = encode_png_bytes(frames[0])
        else:
            audio_wav = _audio_to_wav_bytes(audio) if audio is not None else None
            raw_data = encode_mp4_bytes(frames, fps, quality, audio_wav)

        base64_string = base64.b64encode(raw_data).decode("utf-8")
        mime_type = MIME_MAP[output_format]

        _log(
            f"Stored Base64 | {mime_type} | Frames: {batch_size} | "
            f"Size: {_format_size(len(raw_data))} | Length: {len(base64_string):,} chars"
        )

        return {
            "ui": {
                "base64_data": [base64_string],
            },
            "result": (base64_string, mime_type, batch_size),
        }


NODE_CLASS_MAPPINGS = {
    "DarkHubVideoToBase64": DarkHubVideoToBase64,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DarkHubVideoToBase64": "darkHUB Base64",
}