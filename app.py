"""Point d'entrée de l'application graphique (interface web via pywebview).

Usage::

    python app.py

L'interface (``ui/web``) s'affiche dans une fenêtre native utilisant le moteur
WebView2 de Windows (déjà présent sur Windows 10/11). Toute la logique reste en
Python (``ui/web_api.py`` -> ``ui/controller.py`` -> ``core``).

La variable d'environnement ``STANDARDISATION_RMN_DEBUG=1`` ouvre les outils de
développement du navigateur intégré.
"""

from __future__ import annotations

import json
import os


def main() -> int:
    import webview
    from webview.dom import DOMEventHandler

    from ui.web_api import Api, WebviewDialogs, dropped_path, web_root

    dialogs = WebviewDialogs()
    window = webview.create_window(
        "Standardisation RMN",
        url=os.path.join(web_root(), "index.html"),
        js_api=Api(dialogs),
        width=1080,
        height=740,
        min_size=(720, 560),
    )
    dialogs.attach(window)

    def on_drop(event) -> None:
        # Le chemin complet n'est connu que côté Python : on le renvoie au JS.
        path = dropped_path(event)
        if path:
            window.evaluate_js(f"window.onDroppedPath({json.dumps(path)})")

    def on_loaded() -> None:
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    window.events.loaded += on_loaded
    webview.start(debug=bool(os.environ.get("STANDARDISATION_RMN_DEBUG")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
