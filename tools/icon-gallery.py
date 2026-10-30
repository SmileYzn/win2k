#!/usr/bin/env python3
"""Gera Icon/icones.html: galeria dos principais ícones do tema Win2k.

Uso: python3 tools/icon-gallery.py

Cada ícone aparece em 48 e 16 px. Os caminhos apontam para o arquivo real (links
simbólicos resolvidos), para a página funcionar também no GitHub Pages.
"""

import html
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "Icon"
THEME = ICON_DIR / "Win2k"
OUT = ICON_DIR / "icones.html"
SIZES = (48, 16)

SECTIONS = [
    ("Lugares", [
        "user-home", "user-desktop", "folder", "folder-open", "folder-documents",
        "folder-download", "folder-music", "folder-pictures", "folder-videos",
        "folder-templates", "folder-publicshare", "folder-remote", "user-trash",
        "user-trash-full", "network-workgroup", "network-server", "start-here",
    ]),
    ("Dispositivos", [
        "computer", "drive-harddisk", "drive-removable-media", "drive-optical", "media-floppy",
        "media-optical", "printer", "scanner", "input-keyboard", "input-mouse", "audio-card",
        "camera-photo", "video-display", "network-wired", "multimedia-player", "phone",
    ]),
    ("Aplicativos e configurações", [
        "system-file-manager", "utilities-terminal", "accessories-text-editor",
        "accessories-calculator", "accessories-character-map", "internet-web-browser",
        "internet-mail", "help-browser", "system-search", "system-run",
        "system-software-install", "utilities-system-monitor", "multimedia-volume-control",
        "preferences-desktop", "preferences-desktop-theme", "preferences-desktop-wallpaper",
        "preferences-desktop-display", "preferences-system", "system-users",
        "system-log-out", "system-shutdown",
    ]),
    ("Tipos de arquivo", [
        "text-x-generic", "text-html", "text-x-script", "image-x-generic", "audio-x-generic",
        "video-x-generic", "x-office-document", "x-office-spreadsheet",
        "x-office-presentation", "application-pdf", "font-x-generic",
        "application-x-executable", "package-x-generic", "application-x-cd-image",
    ]),
    ("Ações", [
        "document-new", "document-open", "document-save", "document-print",
        "document-properties", "edit-undo", "edit-redo", "edit-cut", "edit-copy", "edit-paste",
        "edit-delete", "edit-find", "go-previous", "go-next", "go-up", "go-home",
        "view-refresh", "list-add", "list-remove",
    ]),
    ("Estado e diálogos", [
        "dialog-information", "dialog-warning", "dialog-error", "dialog-question",
        "dialog-password", "security-high", "audio-volume-high", "audio-volume-muted",
        "battery-full", "network-idle", "network-offline", "software-update-available",
    ]),
]


def find_icon(name, size):
    """Primeiro arquivo do ícone no tamanho pedido, em qualquer contexto do tema."""
    for context in sorted(p for p in THEME.iterdir() if p.is_dir()):
        path = context / str(size) / f"{name}.png"
        if path.exists():
            return Path(os.path.relpath(path.resolve(), ICON_DIR)).as_posix()
    return None


def card(name):
    images = []
    for size in SIZES:
        src = find_icon(name, size)
        if src:
            images.append(f'<img src="{html.escape(src)}" width="{size}" height="{size}" '
                          f'alt="">')
    if not images:
        return ""
    return (f'<figure title="{html.escape(name)}"><div class="icons">{"".join(images)}</div>'
            f'<figcaption>{html.escape(name).replace("-", "-<wbr>")}</figcaption></figure>')


def main():
    sections, total = [], 0
    for title, names in SECTIONS:
        cards = [c for c in (card(n) for n in names) if c]
        total += len(cards)
        sections.append(f'<fieldset><legend>{html.escape(title)}</legend>'
                        f'<div class="grid">{"".join(cards)}</div></fieldset>')

    count = sum(1 for p in THEME.rglob("*.png"))
    page = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ícones Win2k</title>
<style>
  :root {{
    --face: #d4d0c8; --light: #ffffff; --shadow: #808080; --dark: #404040;
    --title-a: #0a246a; --title-b: #a6caf0; --text: #000000; --select: #0a246a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px 16px; background: #3a6ea5; color: var(--text);
    font: 13px Tahoma, "MS Sans Serif", "Segoe UI", Verdana, sans-serif;
  }}
  .window {{
    max-width: 1100px; margin: 0 auto; background: var(--face);
    border: 1px solid; border-color: var(--face) var(--dark) var(--dark) var(--face);
    box-shadow: inset 1px 1px var(--light), inset -1px -1px var(--shadow); padding: 3px;
  }}
  .caption {{
    display: flex; align-items: center; gap: 6px; padding: 3px 4px; color: #fff;
    font-weight: bold; background: linear-gradient(to right, var(--title-a), var(--title-b));
  }}
  .caption img {{ width: 16px; height: 16px; }}
  .body {{ padding: 12px 14px 16px; }}
  .body p {{ margin: 0 0 12px; }}
  fieldset {{
    margin: 0 0 14px; padding: 10px 8px 6px;
    border: 1px solid var(--shadow); box-shadow: 1px 1px var(--light), inset 1px 1px var(--light);
  }}
  legend {{ padding: 0 4px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 4px; }}
  figure {{ margin: 0; padding: 6px 4px; text-align: center; border: 1px dotted transparent; }}
  figure:hover {{ border-color: var(--text); }}
  figure:hover figcaption {{ background: var(--select); color: #fff; }}
  .icons {{ display: flex; align-items: flex-end; justify-content: center; gap: 8px; height: 50px; }}
  img {{ image-rendering: pixelated; }}
  figcaption {{ display: inline-block; margin-top: 6px; padding: 0 2px; font-size: 11px; }}
  .footer {{ color: #444; font-size: 11px; }}
</style>
</head>
<body>
<div class="window">
  <div class="caption"><img src="{html.escape(find_icon("preferences-desktop-theme", 16) or "")}" alt="">Ícones Win2k</div>
  <div class="body">
    <p>Principais ícones do tema <b>Win2k</b>, em 48 e 16 px. São {total} ícones aqui, de
    {count} arquivos PNG no pacote. Passe o mouse sobre um ícone para ver o nome usado
    pelos aplicativos.</p>
    {"".join(sections)}
    <p class="footer">Gerado por <code>tools/icon-gallery.py</code>.</p>
  </div>
</div>
</body>
</html>
"""
    OUT.write_text(page)
    print(f"{OUT.relative_to(ROOT)}: {total} ícones")


if __name__ == "__main__":
    main()
