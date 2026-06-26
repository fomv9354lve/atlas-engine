#!/usr/bin/env python3
"""atlas_local — arranca Atlas en TU máquina, a full power.

Diferencias vs el web hosted (krenniq.com):
  * corre 100% local (127.0.0.1) — tus circuitos NUNCA salen de tu red.
  * SIN throttle de servidor: ATLAS_TIMEOUT_S alto (1h por defecto) -> los circuitos pesados
    corren hasta terminar en tu hardware, en vez de degradar a los 30s del demo público.
  * sin límites de uso, sin cuenta.

Uso:
    pip install -r requirements.txt
    python atlas_local.py            # abre http://127.0.0.1:<puerto> en tu navegador

Licencia: Apache 2.0 (ver LICENSE/NOTICE). Motor: Stim / quimb / cotengra + adjudicación de ruta.
"""
from __future__ import annotations
import os
import socket
import sys
import threading
import time
import webbrowser


def _free_port(preferred: int = 8791) -> int:
    """Usa el puerto preferido si está libre; si no, pide uno libre al SO."""
    for port in (preferred, 0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            p = s.getsockname()[1]
            s.close()
            return p
        except OSError:
            s.close()
    return preferred


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "engine"))

    # --- full power local ---
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")          # arranque rápido y reproducible
    os.environ["ATLAS_HOST"] = "127.0.0.1"                   # solo local: nada sale de tu máquina
    os.environ.setdefault("ATLAS_TIMEOUT_S", "3600")         # 1h: corre hasta terminar (vs 30s del demo)
    port = _free_port(int(os.environ.get("ATLAS_PORT", "8791")))
    os.environ["ATLAS_PORT"] = str(port)

    url = "http://127.0.0.1:%d/" % port
    print("=" * 64)
    print("  Atlas — Quantum Compute Triage  ·  LOCAL / FULL POWER")
    print("  © 2026 Fco. Osvaldo Morales Vilchis · Apache 2.0")
    print("=" * 64)
    print("  Motor: Stim / quimb / cotengra  ·  timeout: %ss  ·  100%% local" %
          os.environ["ATLAS_TIMEOUT_S"])
    print("  Abriendo:  %s" % url)
    print("  (Ctrl-C para salir)")
    print("=" * 64)

    def _open():
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()

    # webui.py arranca su propio ThreadingHTTPServer (+ warmup) bajo __main__, leyendo ATLAS_HOST/PORT
    # del entorno (que ya fijamos). runpy lo ejecuta como __main__ con nuestra config full-power.
    import runpy
    try:
        runpy.run_path(os.path.join(here, "engine", "webui.py"), run_name="__main__")
    except Exception as e:
        print("\n[error] no pude arrancar el motor: %r" % e)
        print("¿Instalaste las dependencias?  ->  pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n¡Listo! Atlas local detenido.")
