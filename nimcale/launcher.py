# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line entry point: picks the OpenGL path (GPU or Mesa software), handles start-up errors."""
import argparse
import os
import subprocess
import sys
import time
import traceback

from nimcale import APP_NAME, __version__, paths

LOCK_NAME = "starting.lock"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="Nimcale", description="Nimcale - 3D relief / coin / plate maker")
    ap.add_argument("texture", nargs="?", help="texture image (or a .nimcale project)")
    ap.add_argument("heightmap", nargs="?", help="height map image")
    ap.add_argument("--project", help="open a .nimcale project")
    ap.add_argument("--surface", help="3D model file (or sample name: cup, mug, bottle...) for the surface layer")
    ap.add_argument("--software", action="store_true", help="force the Mesa software OpenGL renderer")
    ap.add_argument("--gpu", action="store_true", help="force the GPU (system) OpenGL driver")
    ap.add_argument("--probe-gl", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--probe-out", help=argparse.SUPPRESS)
    ap.add_argument("--lang", help="UI language code (pt-BR, en, es, ...)")
    ap.add_argument("--size", default="1440x900", help="initial window size WxH")
    ap.add_argument("--shot", help="save a screenshot of the whole window after --frames frames, then quit")
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument("--open", help="open windows at start: about,settings,export")
    ap.add_argument("--tab", type=int, default=None, help="about window tab (1..4) or properties tab")
    ap.add_argument("--props-tab", default=None, help="properties tab to select (model, shape, texture, sculpt, scene)")
    ap.add_argument("--do", default="", help=argparse.SUPPRESS)   # comma separated actions (tests)
    ap.add_argument("--set", default="", help=argparse.SUPPRESS)  # k=v,... model parameters (tests / screenshots)
    ap.add_argument("--do-at", type=int, default=3, help=argparse.SUPPRESS)
    ap.add_argument("--quit-after", type=int, default=0, help="quit after N frames (smoke test)")
    ap.add_argument("--demo-sculpt", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--reset-layout", action="store_true", help="forget the saved window layout")
    ap.add_argument("--selftest", action="store_true", help="run a quick non-GUI self test and exit")
    ap.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    a = ap.parse_args(argv)
    if a.texture and a.texture.lower().endswith(".nimcale") and not a.project:
        a.project, a.texture = a.texture, None
    try:
        w, h = a.size.lower().split("x")
        a.size = (max(640, int(w)), max(480, int(h)))
    except ValueError:
        a.size = (1440, 900)
    return a


# ---------------------------------------------------------------------------- logging
def setup_logging():
    """In the windowed (no console) exe stdout/stderr are None: send them to a log file."""
    log = os.path.join(paths.config_dir(), "nimcale.log")
    if sys.stdout is None or sys.stderr is None or getattr(sys, "frozen", False):
        try:
            f = open(log, "w", encoding="utf-8", buffering=1)
            if sys.stdout is None or getattr(sys, "frozen", False):
                sys.stdout = f
            if sys.stderr is None or getattr(sys, "frozen", False):
                sys.stderr = f
        except OSError:
            pass
    return log


def message_box(title, text, yes_no=False):
    print("%s: %s" % (title, text), file=sys.stderr, flush=True)
    if os.environ.get("NIMCALE_NO_DIALOGS"):      # automated runs (CI smoke tests) must never block
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            flags = 0x10 | (0x04 if yes_no else 0)     # MB_ICONERROR | MB_YESNO
            r = ctypes.windll.user32.MessageBoxW(None, text, title, flags)
            return r == 6
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------- OpenGL selection
def mesa_dir():
    cands = []
    if os.environ.get("NIMCALE_MESA_DIR"):
        cands.append(os.environ["NIMCALE_MESA_DIR"])
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "mesa"))
        cands.append(os.path.join(os.path.dirname(sys.executable), "mesa"))
    root = os.path.dirname(paths.package_dir())
    cands.append(os.path.join(root, "third_party", "mesa"))
    for c in cands:
        if os.path.isfile(os.path.join(c, "opengl32.dll")):
            return c
    return None


def glfw_library():
    """Path of the GLFW shared library to use with pyGLFW.

    imgui-bundle ships its own GLFW (the one the real window uses); pyGLFW must load that same file.
    In the frozen exe pyGLFW cannot find its bundled DLL by itself, which made the GPU probe fail."""
    names = {"win32": ["glfw3.dll"], "darwin": ["libglfw.3.dylib"]}.get(sys.platform, ["libglfw.so.3", "libglfw.so"])
    dirs = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs += [os.path.join(meipass, "imgui_bundle"), os.path.join(meipass, "glfw"), meipass]
    try:
        import importlib.util
        for mod in ("imgui_bundle", "glfw"):
            spec = importlib.util.find_spec(mod)
            if spec and spec.origin:
                dirs.append(os.path.dirname(spec.origin))
    except Exception:
        pass
    dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


def setup_glfw_library():
    if os.environ.get("PYGLFW_LIBRARY") and os.path.isfile(os.environ["PYGLFW_LIBRARY"]):
        return os.environ["PYGLFW_LIBRARY"]
    p = glfw_library()
    if p:
        os.environ["PYGLFW_LIBRARY"] = p
    return p


def enable_software_gl():
    """Make the Mesa llvmpipe OpenGL the one used by this process. Must run before imgui_bundle is imported."""
    os.environ.setdefault("GALLIUM_DRIVER", "llvmpipe")
    os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "4.5")
    os.environ.setdefault("MESA_GLSL_VERSION_OVERRIDE", "450")
    if sys.platform != "win32":
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
        return True
    d = mesa_dir()
    if not d:
        return False
    import ctypes
    try:
        os.add_dll_directory(d)
    except (AttributeError, OSError):
        pass
    try:
        # libgallium_wgl.dll first, then opengl32.dll by full path: once loaded, every later
        # "opengl32.dll" import in the process (imgui_bundle, glfw) resolves to Mesa's copy.
        if os.path.isfile(os.path.join(d, "libgallium_wgl.dll")):
            ctypes.WinDLL(os.path.join(d, "libgallium_wgl.dll"))
        ctypes.WinDLL(os.path.join(d, "opengl32.dll"))
        return True
    except OSError as e:
        print("Mesa load failed:", e, flush=True)
        return False


def probe_gl(out_path=None):
    """Child-process check: can we get an OpenGL 3.3 core context? Prints one result line:

    * ``PROBE OK <renderer> <version>``  - hardware/driver OpenGL works
    * ``PROBE FAIL <reason>``            - the driver cannot give a usable OpenGL 3.3 context
    * ``PROBE ERROR <reason>``           - the probe itself could not run (missing DLL, import error...);
                                           says nothing about the GPU, so it must not force software mode

    The windowed exe has no stdout, so the result is written to ``out_path``."""
    if out_path:
        try:
            sys.stdout = open(out_path, "w", encoding="utf-8", buffering=1)
        except OSError:
            pass
    elif sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    lib = setup_glfw_library()
    try:
        import glfw
        if getattr(glfw, "_glfw", True) is None:
            raise OSError("GLFW library not found (%s)" % lib)
        import moderngl
    except Exception as e:
        print("PROBE ERROR", e, flush=True)
        return 6
    try:
        if not glfw.init():
            print("PROBE ERROR glfw.init", flush=True)
            return 2
    except Exception as e:
        print("PROBE ERROR glfw.init", e, flush=True)
        return 2
    try:
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)
        win = glfw.create_window(64, 64, "probe", None, None)
        if not win:
            print("PROBE FAIL no OpenGL 3.3 core context", flush=True)
            return 3
        glfw.make_context_current(win)
        ctx = moderngl.create_context(require=330)
        fbo = ctx.simple_framebuffer((8, 8))
        fbo.use()
        ctx.clear(1, 0, 1, 1)
        px = fbo.read(components=3)
        ok = px[:3] == b"\xff\x00\xff"
        print("PROBE OK" if ok else "PROBE FAIL read-back", ctx.info["GL_RENDERER"], ctx.info["GL_VERSION"],
              flush=True)
        glfw.terminate()
        return 0 if ok else 4
    except Exception as e:
        print("PROBE FAIL", e, flush=True)
        return 5


def self_cmd(*extra):
    if getattr(sys, "frozen", False):
        return [sys.executable] + list(extra)
    return [sys.executable, "-m", "nimcale"] + list(extra)


def run_probe(software=False, timeout=25):
    import tempfile
    fd, out_path = tempfile.mkstemp(prefix="nimcale_probe_", suffix=".txt")
    os.close(fd)
    args = ["--probe-gl", "--probe-out", out_path] + (["--software"] if software else [])
    try:
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
        r = subprocess.run(self_cmd(*args), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout, **kw)
        try:
            with open(out_path, encoding="utf-8", errors="replace") as f:
                out = f.read()
        except OSError:
            out = ""
        out = out.strip()
        if r.returncode == 0 and "PROBE OK" in out:
            return "ok", out[-400:]
        if "PROBE ERROR" in out:
            return "error", out[-400:]
        if "PROBE FAIL" in out:
            return "fail", out[-400:]
        # no result line at all: the driver crashed the probe process (typical of broken drivers)
        return "crash", ("exit code %s %s" % (r.returncode, out))[-400:]
    except subprocess.TimeoutExpired:
        return "error", "timeout"
    except Exception as e:
        return "error", str(e)
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def choose_renderer(a, cfg):
    """Returns True when the software renderer must be used."""
    if a.software:
        return True
    if a.gpu:
        return False
    if cfg.renderer == "software":
        return True
    if cfg.renderer == "gpu":
        return False
    lock = os.path.join(paths.config_dir(), LOCK_NAME)
    crashed = os.path.exists(lock)
    if crashed or cfg.gl_status not in ("ok",):
        if sys.platform == "win32" or os.environ.get("NIMCALE_FORCE_PROBE"):
            res, out = run_probe(False)
            print("GPU probe:", res, out, flush=True)
            if res in ("fail", "crash"):
                cfg.gl_status = "gpu-failed"
                cfg.save()
                return True
            if res == "error":
                # the probe could not run: try the GPU anyway (the start-up crash marker and the
                # OpenGL error dialog still offer the software renderer if it really fails)
                print("GPU probe inconclusive: trying the graphics driver", flush=True)
        if crashed and cfg.gl_status == "ok":
            # GPU probe is fine but last start crashed anyway: be safe this time
            print("previous start crashed: using software renderer", flush=True)
            cfg.gl_status = "crashed"
            cfg.save()
            return True
    return False


# ---------------------------------------------------------------------------- self test
def selftest():
    import tempfile
    from nimcale.core import images
    from nimcale.core.params import ModelParams
    from nimcale.core.pipeline import Pipeline
    from nimcale.core import mesh as meshmod
    from nimcale.app import DEFAULT_HM, coin_defaults
    from nimcale.export import formats
    t0 = time.time()
    hm = images.load_heightmap(DEFAULT_HM)
    p = coin_defaults(ModelParams())
    from nimcale.core.pipeline import fit_shape_params
    p.shape_cx, p.shape_cy, p.shape_rx, p.shape_ry = fit_shape_params(hm, p, "circle")
    res = Pipeline().compute(hm, p)
    m = meshmod.build_solid(res.hf, res.sdf, res.size, p.depth, p.thickness, res=400)
    closed = meshmod.check_closed(m.F)
    path = os.path.join(tempfile.gettempdir(), "nimcale_selftest.stl")
    formats.write_stl(path, m.scaled(p.size_mm))
    print("selftest: %d triangles, watertight=%s, %.1fs -> %s" % (len(m.F), closed, time.time() - t0, path))
    ok = closed["watertight"]
    # surface layer (test build): bundled samples + every import format through the frozen trimesh/collada
    try:
        import trimesh
        from nimcale.app import sample_path
        from nimcale.core import surface as S
        t1 = time.time()
        sm = S.load_surface(sample_path("mug"))
        tm = trimesh.Trimesh(sm.V, sm.F, process=False)
        fmts, bad = [], []
        for ext in (".obj", ".stl", ".ply", ".glb", ".gltf", ".3mf", ".off", ".dae"):
            fp = os.path.join(tempfile.gettempdir(), "nimcale_selftest_srf" + ext)
            try:
                tm.export(fp)
                fmts.append("%s:%d" % (ext[1:], S.load_surface(fp).n_faces))
            except Exception as e:  # noqa: BLE001
                import traceback
                where = traceback.extract_tb(e.__traceback__)[-3:]
                bad.append("%s -> %r at %s" % (ext, e, " / ".join("%s:%d" % (os.path.basename(f.filename), f.lineno)
                                                                  for f in where)))
        for b in bad:
            print("selftest surface format FAILED:", b)
        if bad:
            ok = False
        sr = S.SurfaceBuilder().build(sm, p, res, max_faces=60_000)
        from PIL import Image
        welded, _split, _atlas = S.export_meshes(sr, Image.new("RGB", (8, 8)), (0.8, 0.8, 0.8))
        sc = meshmod.check_closed(welded.F)
        ok = ok and sc["watertight"]
        print("selftest surface: %s | %d triangles, watertight=%s, %.1fs"
              % (" ".join(fmts), len(welded.F), sc["watertight"], time.time() - t1))
    except Exception as e:  # noqa: BLE001
        print("selftest surface FAILED:", repr(e))
        ok = False
    return 0 if ok else 1


# ---------------------------------------------------------------------------- main
def main(argv=None):
    a = parse_args(argv)
    if a.probe_gl:
        if a.software:
            enable_software_gl()
        return probe_gl(a.probe_out)
    log = setup_logging()
    print("%s %s | Python %s | %s" % (APP_NAME, __version__, sys.version.split()[0], sys.platform), flush=True)
    print("GLFW library:", setup_glfw_library(), flush=True)
    if a.selftest:
        return selftest()
    from nimcale.config import AppConfig
    cfg = AppConfig.load()
    software = choose_renderer(a, cfg)
    if software:
        ok = enable_software_gl()
        print("renderer: software (Mesa)", "enabled" if ok else "NOT AVAILABLE", flush=True)
    else:
        print("renderer: graphics driver (GPU)", flush=True)
    from nimcale import i18n
    i18n.set_language(a.lang or cfg.language)
    lock = os.path.join(paths.config_dir(), LOCK_NAME)
    try:
        with open(lock, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass
    try:
        from nimcale.runner import Runner
        r = Runner(a, cfg)
        r.software = software
        r.run()
        if not r.started:
            raise RuntimeError("the window closed before OpenGL 3.3 started")
        try:
            os.remove(lock)
        except OSError:
            pass
        errors = getattr(r.app, "error_count", 0)
        if a.quit_after and errors:
            print("ERROR: %d error message(s) during the smoke run" % errors, flush=True)
            return 4
        return 0
    except Exception as e:
        traceback.print_exc()
        try:
            os.remove(lock)
        except OSError:
            pass
        from nimcale.i18n import tr
        started, stage = False, "setup"
        try:
            started, stage = r.started, getattr(r, "stage", "setup")
        except Exception:
            pass
        if not started and not software and stage == "run":
            cfg.gl_status = "gpu-failed"
            cfg.save()
            if message_box(APP_NAME, tr("err.gl_retry", err=str(e)), yes_no=True):
                subprocess.Popen(self_cmd("--software"))
            return 2
        message_box(APP_NAME, tr("err.fatal", err=str(e), log=log))
        return 1


if __name__ == "__main__":
    sys.exit(main())
