# Changelog

## 3.0.2 - 2026-04-24

- aligned the published registry display name with the single-node product name: `darkHUB Base64`
- prepared a fresh version to force a new Comfy Registry publish after the workflow fix
## 3.0.1 - 2026-04-24

- fixed the GitHub Actions publish workflow so registry publishing no longer fails on secret parsing
- prepared a fresh semantic version for the next Comfy Registry publish
## 3.0.0 - 2026-04-24

- reduced the package to a single registered node: `darkHUB Base64`
- removed `Base64 -> Image` and `Base64 Info` from node registration so searching `darkHUB` only returns the main node
- simplified the node UI to a single `Copy Base64` button
- removed extra preview, metadata, and compatibility outputs from the main node
- kept direct `IMAGE` to Base64 conversion with `png` and `mp4` support only
- preserved MP4 audio muxing so video Base64 exports include audio when connected
- aligned package metadata and documentation with the final single-node release

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