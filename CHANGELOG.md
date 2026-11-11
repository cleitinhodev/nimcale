# Changelog

All notable changes to Nimcale are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/),
versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0-beta] - 2026-11-11

First public release. Nimcale is the complete rewrite of the old "placa3d" relief viewer.

### Added
- New name, logo and icons (multi-size `.ico` for the executable and the window).
- New interface (Dear ImGui with docking): menu bar, toolbar, tabbed property panels, status bar,
  resizable/dockable windows whose layout is remembered.
- Purple/pink theme with animated neon/gradient effects (can be turned off in Settings).
- 12 interface languages with automatic detection: Português (Brasil), English, Español, Français, Deutsch,
  Italiano, Русский, Polski, Türkçe, 简体中文, 日本語, 한국어. Falls back to pt-BR when the system language
  cannot be detected and to English for missing strings.
- Default project: the Nimcale coin (texture + relief, "mix" view, object cutout).
- Shape presets (coin, medal, plate, outline, tile), cutout shapes (image outline, circle, ellipse,
  rounded rectangle, hexagon, octagon), rim and bevel, height curve (gamma, levels), noise / micro detail.
- Modeling tools: sculpt brushes (raise, lower, smooth, flatten, erase), undo / redo, mirror / flip,
  rotate 90°, crop, measurements in millimetres, dimension overlay, turntable, materials, grid.
- Export: STL (binary/ASCII), OBJ + MTL + texture, GLB / glTF, PLY with vertex colours, 3MF, OFF,
  16-bit height map PNG, normal map PNG, baked texture PNG, turntable GIF, HD screenshots.
- HD export: dense mesh independent of the preview (up to 6144 samples on the longest side, bicubic
  upsampling), background job with progress and cancel, watertight check, optional adaptive decimation.
- Projects (`.nimcale`), recent files, drag & drop of images, alignment save/load and auto-align.
- Maximum compatibility: OpenGL 3.3 core; automatic fallback to the bundled Mesa llvmpipe software
  renderer when the GPU driver is missing or broken (or by choice in Settings / `--software`).
- Settings persisted in `%APPDATA%\Nimcale` (Windows) / `~/.config/Nimcale` (Linux).
- Help / About window with links (site, project, donate), shortcut list and license information.
- Automated tests (pytest) and a GitHub Actions Windows build.

### Changed
- **Esc no longer quits the program.** It closes the open window or leaves sculpt mode.
  Use **Ctrl+Q** (or File → Quit) to quit.
- STL export is now watertight and much sharper (HD export instead of the preview mesh).

### Kept from placa3d
- Import texture / height map, depth, thickness, smoothing, threshold, brightness, contrast, invert,
  mesh resolution, texture fit / scale / offset / rotation, lighting, background colour, wireframe, axes,
  texture / height / mix views, plate vs. object cutout, screenshots, OBJ / GLB / STL export,
  alignment save/load and all mouse / keyboard controls.
