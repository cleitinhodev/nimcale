# Changelog

All notable changes to Nimcale are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/),
versions follow [Semantic Versioning](https://semver.org/).

## [1.0.1-beta] - 2026-11-11

### Fixed
- **Windows: crash at start-up** of 1.0.0-beta (`AttributeError: DockingLayoutCondition ...
  first_use_since_app_start`). The docking layout used an enum name that does not exist in hello_imgui;
  the screenshot-based tests used a different branch and never ran that line. Enum names and optional
  RunnerParams fields are now resolved with version-tolerant fallbacks (`nimcale/compat.py`).
- **Windows: GPU probe always failed** ("Failed to load GLFW3 shared library"), so every PC was sent to the
  slow software renderer. The probe now uses the same GLFW DLL as the window (imgui-bundle's, found
  through `PYGLFW_LIBRARY`), pyGLFW's own DLLs are bundled too, and a probe that cannot run is treated as
  inconclusive: the graphics card is still tried. Only a real OpenGL failure (no 3.3 context, or the
  driver crashing the probe) selects the Mesa software renderer.
- A program error during start-up is no longer mistaken for an OpenGL problem (no wrong "use the software
  renderer?" question, and the GPU is not marked as failed).

### Changed
- Dependencies are pinned to the exact versions tested (`requirements*.txt`, `pyproject.toml`).
- CI smoke tests now run the frozen exe through the real start-up path (as a double click: automatic
  renderer choice with the GPU probe, first and second start with saved settings/layout), plus the GL probe
  with and without Mesa, the forced software renderer with a screenshot, and the self test. Each run fails
  on a non-zero exit code, a traceback or an error line in `nimcale.log` (`scripts/ci_smoke.ps1`).
- New tests: start-up/renderer selection, building the real RunnerParams for every start mode, and a static
  audit of every imgui-bundle / hello_imgui / GLFW name used in the code.
- New option `--quit-after N` (quit after N frames) and `NIMCALE_NO_DIALOGS=1` for automated runs.

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
