---
name: headless-chromium-rootless-libs
description: 'Use when a headless Chromium/Playwright/Chrome launch fails on a rootless Linux box with "libgbm.so.1: cannot open shared object file" (or missing libwayland-server) and there is no root to apt-get install'
---

# Headless Chromium without root: missing libgbm

Chromium dlopens Mesa's `libgbm.so.1` at launch; without it the process dies
before any page opens. On a rootless box, download the .debs and extract them
into the home directory instead of installing.

`libgbm1` needs its companion `libwayland-server0` - fetch both, or the
extracted lib fails on its own dependency.

## Recipe

1. Confirm the lib is really absent: `ldconfig -p | grep libgbm`.
2. Try the one-command path first (works when apt lists exist):
   ```bash
   mkdir -p ~/chromedeps && cd "$(mktemp -d)"
   apt-get download libgbm1 libwayland-server0   # unprivileged: downloads only
   dpkg-deb -x libgbm1_*.deb ~/chromedeps
   dpkg-deb -x libwayland-server0_*.deb ~/chromedeps
   ```
3. If apt has no lists ("Unable to locate package"), fetch from the Ubuntu
   pool directly. Browse the directory listing to find the current filename -
   libgbm lives under `pool/main/m/mesa/`, wayland under `pool/main/w/wayland/`
   (the pool holds many versions; pick the build matching your distro, jammy
   in the examples - a wrong-distro build extracts fine then fails at
   runtime):
   ```bash
   curl -s http://archive.ubuntu.com/ubuntu/pool/main/m/mesa/ | grep -o 'libgbm1[^"]*amd64.deb'
   # jammy examples: libgbm1_22.0.1-1ubuntu2_amd64.deb (or the 23.2.1 jammy update),
   #                 libwayland-server0_1.20.0-1_amd64.deb
   curl -sO "http://archive.ubuntu.com/ubuntu/pool/main/m/mesa/libgbm1_<picked>_amd64.deb"
   curl -sO "http://archive.ubuntu.com/ubuntu/pool/main/w/wayland/libwayland-server0_<picked>_amd64.deb"
   dpkg-deb -x libgbm1_*.deb ~/chromedeps && dpkg-deb -x libwayland-server0_*.deb ~/chromedeps
   ```
   If `ldd` then reports further missing deps (libdrm, libexpat, libglapi), they
   come from their own pool directories - same download-and-extract pattern.
4. Wire it at launch - either export
   `LD_LIBRARY_PATH=~/chromedeps/usr/lib/x86_64-linux-gnu`, or pass it
   self-contained: `chromium.launch(env={"LD_LIBRARY_PATH": "<path>"})`
   (Playwright Python; the `env` kwarg reaches the browser process).

## Verification

`LD_LIBRARY_PATH=... ldd ~/chromedeps/usr/lib/x86_64-linux-gnu/libgbm.so.1`
must show no "not found". Do not diagnose with `ldd` on the Chrome binary -
libgbm is dlopen'd, not DT_NEEDED, so it never appears there; the launch error
message names it.

## Gotchas

- This skill assumes the Playwright package itself imports; browser binaries
  under `~/.cache/ms-playwright` are not the Python package - install it
  (`uv pip install playwright`) and let it manage matching browser builds.
- Any wrapper that launches the browser (CI step, service, subprocess) must
  inherit or set the `LD_LIBRARY_PATH` itself.
- Headless WebGL is a separate failure: Chrome 139 removed the automatic
  SwiftShader fallback, so WebGL needs `--enable-unsafe-swiftshader` in the
  launch args.
