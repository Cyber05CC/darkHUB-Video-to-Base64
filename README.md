# darkHUB Video to Base64

`darkHUB Video to Base64` is a production-ready ComfyUI custom node pack for converting image batches into Base64 strings and decoding Base64 payloads back into ComfyUI `IMAGE` tensors.

It supports:

- PNG, GIF, WEBP, MP4, and WEBM Base64 export
- Optional audio muxing for MP4 and WEBM output
- Base64 to image/video decoding
- Built-in ComfyUI frontend controls for download and copy actions
- Automatic save to the ComfyUI output directory, plus optional Downloads copies
- Semantically versioned node metadata for GitHub and ComfyUI Registry workflows

## Included Nodes

### 1. Video/Image -> Base64 (darkHUB)

Encodes an `IMAGE` batch into Base64.

Inputs:

- `images`: ComfyUI `IMAGE`
- `format`: `auto`, `png`, `gif`, `webp`, `mp4`, `webm`
- `fps`: frame rate for animated/video formats
- `quality`: encoding quality
- `audio` (optional): ComfyUI `AUDIO`, supported for `mp4` and `webm`
- `loop` (optional): loop animated GIF/WEBP output
- `add_data_uri` (optional): prepend `data:<mime>;base64,`
- `auto_download` (optional): save an extra copy to the system Downloads folder
- `filename_prefix` (optional): filename prefix for saved files

Outputs:

- `base64_string`
- `mime_type`
- `frame_count`

### 2. Base64 -> Image (darkHUB)

Decodes Base64 back into ComfyUI `IMAGE` tensors. Static images, animated images, MP4, and WEBM are supported.

Inputs:

- `base64_string`
- `auto_download` (optional)
- `filename_prefix` (optional)

Outputs:

- `images`

### 3. Base64 Info (darkHUB)

Displays file size, format, frame count, Base64 length, and node version.

## Installation

### ComfyUI custom_nodes

1. Place this repository inside `ComfyUI/custom_nodes/`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Restart ComfyUI.

### Notes about ffmpeg

- If `ffmpeg` is already available in your system path, the node will use it directly.
- If it is not installed globally, the bundled fallback from `imageio-ffmpeg` will be used when available.
- MP4 and WEBM decoding back into `IMAGE` tensors requires `ffmpeg`.

## Repository Layout

```text
.
|-- .github/workflows/
|   |-- publish_action.yml
|   `-- validate.yml
|-- web/
|   `-- darkhub_base64_preview.js
|-- __init__.py
|-- _version.py
|-- nodes.py
|-- pyproject.toml
|-- requirements.txt
|-- requirements-dev.txt
|-- CHANGELOG.md
`-- LICENSE
```

## GitHub and ComfyUI Registry Readiness

This package already includes:

- `pyproject.toml` with ComfyUI Registry metadata
- `requirements.txt` for ComfyUI Manager installs
- a publish GitHub Action for the ComfyUI Registry
- a validation GitHub Action for Python and frontend syntax
- versioning via `_version.py`
- documentation and release notes

Before publishing to the ComfyUI Registry, update these two fields in [pyproject.toml](./pyproject.toml):

- `project.urls.Repository`
- `tool.comfy.PublisherId`

Those values must match your final GitHub repository URL and your real Comfy Registry publisher ID.

## Versioning

Current release: `1.0.0`

Semantic versioning is used:

- `MAJOR`: breaking changes
- `MINOR`: backwards-compatible features
- `PATCH`: fixes and polish

## License

MIT License. See [LICENSE](./LICENSE).
