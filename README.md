# darkHUB Video to Base64

`darkHUB Video to Base64` is a focused ComfyUI custom node pack for converting generated `IMAGE` batches into copyable Base64 strings.

Version `2.0.0` is a RunningHub-friendly refactor with a simpler workflow:

- PNG and MP4 Base64 export only
- optional audio muxing into MP4 output
- a responsive copy-only node UI with no image/video preview inside the node
- robust Base64 extraction from raw strings or data URIs
- compatibility helper nodes for decoding Base64 back into ComfyUI `IMAGE` tensors

## Included Nodes

### 1. Video/Image -> Base64 (darkHUB)

This is the main node.

It accepts ComfyUI `IMAGE` output directly from nodes such as `VAE Decode`, image loaders, video frame generators, or any other node that outputs `IMAGE`.

Inputs:

- `images`: ComfyUI `IMAGE`
- `format`: `auto`, `png`, or `mp4`
- `fps`: frame rate for MP4 export
- `quality`: MP4 quality control
- `audio` (optional): ComfyUI `AUDIO`, embedded when the output format is MP4
- `add_data_uri` (optional): prepend `data:<mime>;base64,`

Outputs:

- `base64_string`
- `mime_type`
- `frame_count`

Legacy passthrough outputs are still returned for workflow compatibility, but the node no longer writes preview files or download artifacts.

### 2. Base64 -> Image (darkHUB)

Decodes Base64 strings or data URIs back into ComfyUI `IMAGE` tensors.

### 3. Base64 Info (darkHUB)

Displays file size, format, frame count, Base64 length, preview text, and the node version.

## Behavior Notes

- `auto` chooses `png` for a single image with no audio.
- `auto` chooses `mp4` for multi-frame image batches or when audio is connected.
- If an older workflow still sends `gif`, `webp`, or `webm`, the node normalizes those requests to `png` or `mp4` and reports that in the node status.
- The frontend panel only shows metadata plus a `Copy Base64` button.
- For MP4 exports with audio, the audio track is muxed into the MP4 before Base64 encoding.

## Installation

1. Place this repository inside `ComfyUI/custom_nodes/`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Restart ComfyUI.

## ffmpeg Notes

- If `ffmpeg` is already available in your system path, the node uses it directly.
- Otherwise the fallback binary from `imageio-ffmpeg` is used when available.
- MP4 export and MP4 Base64 decode both require working `ffmpeg` support.

## GitHub Actions

This repository includes:

- Python syntax validation
- frontend syntax validation
- Comfy Registry publishing metadata
- a publish workflow that now skips safely when `REGISTRY_ACCESS_TOKEN` is not configured

## Versioning

Current release: `2.0.0`

Semantic versioning is used:

- `MAJOR`: breaking changes
- `MINOR`: backwards-compatible features
- `PATCH`: fixes and polish

## License

MIT License. See [LICENSE](./LICENSE).