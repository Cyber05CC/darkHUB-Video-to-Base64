# Changelog

## 2.0.0 - 2026-04-22

- refactored the main node into a PNG/MP4-focused Base64 encoder with a copy-only UI
- removed in-node image/video preview rendering and download artifact generation from the main workflow
- preserved optional MP4 audio muxing so video Base64 exports keep their audio track
- normalized older GIF, WEBP, and WEBM requests into the new PNG/MP4-only export flow
- simplified node metadata so RunningHub and ComfyUI show a cleaner Base64 storage panel
- updated documentation, package metadata, and release versioning for the new behavior
- made the publish workflow skip cleanly when the registry token is missing

## 1.1.0 - 2026-04-16

- added RunningHub-friendly output artifacts, preview images, and saved media/text paths
- added Base64 preview and download metadata to both encoder and decoder nodes
- improved Base64 extraction and error handling for pasted or wrapped input strings
- added passthrough/media path outputs for easier workflow integration
- improved animated image and video preview behavior

## 1.0.0 - 2026-04-14

- finalized the custom node as a GitHub- and ComfyUI-ready package
- translated backend/frontend user-facing text to English
- added semantic versioning via `_version.py`
- improved Base64 encode/decode status messaging
- added ComfyUI Registry metadata in `pyproject.toml`
- added `requirements.txt` and `requirements-dev.txt`
- added GitHub workflows for validation and registry publishing
- added product documentation and MIT license