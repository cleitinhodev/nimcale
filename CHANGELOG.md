# Changelog

All notable changes to Nimcale are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/),
versions follow [Semantic Versioning](https://semver.org/).

## [1.1.0-beta.1] - 2026-11-11 (test pre-release, branch `dev/surface`)

**Experimental test build** published as a GitHub *pre-release* from the `dev/surface` branch. The stable
version is still **1.0.3** (`main`). The app shows a "TEST VERSION" badge in the status bar and window title.

### Added
- **Surface (3D model) layer** - new *Surface* tab: put the current texture **and** relief onto a 3D object
  (cup, bottle, box...). Nothing was removed: without a surface the app is exactly the normal plate / coin.
  - Import **OBJ (+MTL), STL, PLY, GLB / glTF, 3MF, OFF and DAE (Collada)** (menu *File - Import surface*,
    `Ctrl+Shift+U`, toolbar or drag & drop). Several parts are merged, metres are converted to mm, missing
    normals are computed, large meshes (> 2 M triangles) are simplified. FBX is **not** supported.
  - **12 sample models** (cup, mug with handle, bottle, vase, ball, box, can, plate, keychain tag, phone-case
    slab, pen holder, lamp shade) generated procedurally (`scripts/make_samples.py`), all closed solids.
  - Projections: automatic (detects cylinder / sphere / flat / box), model UVs, cylindrical, spherical,
    planar, box (triplanar) and decal (one side only), with projection axis / direction.
  - Image fit (cover the whole side, go around once, object height), move U/V, scale, separate X/Y
    proportion, rotation, seam position, repeat (tile) or single image, mirror, use the plate outline as a
    mask, outer wall only / also top and bottom (cylinders).
  - Relief displaces the surface along its normals with conforming adaptive subdivision (detail slider);
    uses the existing depth, invert and smoothing settings. Live preview with the texture colours.
  - Model: up axis, size (mm), rotation X/Y/Z, base colour.
  - **Export everything merged** in the existing formats (STL, OBJ+MTL+texture, GLB/glTF, PLY, 3MF, OFF),
    including **HD** export (up to 4 M triangles). Closed input models stay closed (watertight).
  - **Remove surface / back to the default plate** (button + File menu, undoable): only the 3D model goes
    away, every plate / coin setting is kept. Surfaces are saved in `.nimcale` projects.
- New help/guide entries, shortcuts, translations for all 12 languages.

### Dependencies
- trimesh, networkx, lxml, pycollada (and python-dateutil / tzdata) are now runtime dependencies.

## [1.0.3] - 2026-11-11

Stable. Includes everything from 1.0.2 (title bar follows the OS theme) plus:

### Fixed
- **Imported images were always cut as a circle.** The default coin preset's circular outline stayed active
  after importing another height map (or texture + height map). Now a new height map switches the outline
  to the object's own contour, analysing the new image, and the coin-only settings (rim, bevel) are reset -
  unless you picked a shape, preset or edge setting yourself, which is then kept. The circle only applies
  to the default coin or when chosen explicitly. Opening a project keeps its saved shape.

### Added
- Automatic background detection for the contour: **dark**, **white** or **transparent** backgrounds
  (the height map's alpha channel is now kept, also inside `.nimcale` projects) or a **picked colour**
  with tolerance.
- Fine tuning in *Shape → Outline*: outline source (automatic / height map threshold / texture alpha /
  texture colour key / circle / ellipse / rounded rectangle / hexagon / octagon), background mode,
  threshold or tolerance, expand / shrink (px), edge smoothing, edge softness, fill holes, remove small
  islands (minimum area), keep only the largest object, and a **live outline preview** (magenta contour,
  cut-away area dimmed) plus the detected background and coverage.
- The same contour is used for the HD export (pixel sizes refer to the original image, so preview and
  export match). Translations in all 12 languages; tests for non-circular imports (star on black, white,
  transparent and coloured backgrounds), texture alpha / colour key, grow/shrink, islands, largest object,
  user choice kept, project alpha round trip and a watertight HD export.

### Note
- v1.0.2 had already been published when this fix was ready; releases are never replaced, so the fix
  ships as **1.0.3**, the new stable release.

## [1.0.2] - 2026-11-11

First **stable** release of Nimcale 1.0.

### Added
- The native window title bar (title and icon) follows the operating system theme instead of always
  being white. New setting *Settings → Appearance → Title bar*: **follow system** (default) / dark / light /
  theme colour.
  - Windows 10 (1809+) and 11: dark/light title bar through `DwmSetWindowAttribute`
    (`DWMWA_USE_IMMERSIVE_DARK_MODE` 20, falling back to 19 on older Windows 10). The system choice is read
    from `AppsUseLightTheme` and checked every 2 seconds, so switching Windows between light and dark
    updates the open window live. On Windows 11 "theme colour" paints the caption, border and title text in
    Nimcale's purple. Unsupported Windows versions keep the default bar silently.
  - macOS: GLFW windows already follow the system appearance.
  - Linux: best effort, depends on the window manager (`_GTK_THEME_VARIANT` hint via `xprop`, honoured by
    GNOME/Mutter and other GTK-based window managers; the system preference is read from GNOME `gsettings`).
- Translations of the new setting in all 12 languages; tests for the title bar logic; the CI smoke test
  logs the title bar mode applied by the frozen exe (default and "theme" mode).

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
- On a PC without usable GPU OpenGL the **second** start failed: a start with the software renderer recorded
  "OpenGL ok", so the next start skipped the probe and tried the GPU. Only GPU starts are recorded as ok now
  (found by the new CI smoke test).
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
