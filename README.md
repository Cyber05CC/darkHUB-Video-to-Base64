# darkHUB Base64

`darkHUB Base64` is a single-purpose ComfyUI custom node.

It accepts an `IMAGE` output directly from nodes such as `VAE Decode`, stores the result as Base64 inside the node, and exposes a single `Copy Base64` button in the node UI.

## Included Node

### darkHUB Base64

Inputs:

- `images`: ComfyUI `IMAGE`
- `format`: `auto`, `png`, or `mp4`
- `fps`: frame rate for MP4 output
- `quality`: MP4 quality control
- `audio` (optional): ComfyUI `AUDIO`, embedded when the output format is MP4

Outputs:

- `base64_string`
- `mime_type`
- `frame_count`

## Behavior

- `auto` chooses `png` for a single image with no audio.
- `auto` chooses `mp4` for multi-frame batches or when audio is connected.
- The node UI only renders one button: `Copy Base64`.
- PNG output does not accept audio.
- MP4 output keeps the audio track when audio is connected.

## Installation

1. Place this repository inside `ComfyUI/custom_nodes/`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Restart ComfyUI.

## ffmpeg Notes

- If `ffmpeg` is available in your system path, the node uses it directly.
- Otherwise the fallback binary from `imageio-ffmpeg` is used when available.
- MP4 output requires working `ffmpeg` support.

## Version

Current release: `3.0.1`

## License

MIT License. See [LICENSE](./LICENSE).