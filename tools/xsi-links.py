#!/usr/bin/env python3
"""Ícones clássicos do Win2k para os nomes do xapp-symbolic-icons (XSI).

O Cinnamon, o Nemo, o Xed e os XApps pedem ícones "xsi-*-symbolic". O XSI instala esses
ícones (em traço, modernos) no hicolor, e eles aparecem sempre que o tema não tem o nome.
Este script cria em Icon/Win2k links "xsi-*" para os ícones clássicos equivalentes que o
pacote já tem, usando a tabela do XSI (icons/xsi-adwaita-symbolic.info, nome Adwaita de
cada ícone XSI), e gera tools/xsi-faltantes.md com os nomes que ficaram sem ícone.

Cada link fica na mesma pasta (contexto e tamanho) do ícone de destino e só é criado se o
destino existir: o suporte que o Win98SE recebeu (PR #51) foi revertido por criar links
quebrados. Rodar de novo apaga os links "xsi-*" anteriores e refaz todos, então basta
repetir depois de atualizar o XSI:

    python3 tools/xsi-links.py --xsi ~/Desktop/xapp-symbolic-icons
"""

import argparse
import configparser
import datetime
import glob
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "Icon/Win2k"
REPORT = ROOT / "tools/xsi-faltantes.md"
# Links "-symbolic" criados pelo script (fora os xsi-* e APP_ICONS), para apagá-los ao rodar
# de novo sem tocar nos "-symbolic" que vieram do SE98.
SYMBOLIC_MANIFEST = ROOT / "tools/symbolic-links.txt"
EXTS = (".png", ".svg", ".xpm")

# Nomes XSI usados pelo Cinnamon que não têm equivalente pela tabela do XSI: sufixo XSI
# (sem "xsi-" e "-symbolic") -> ícone Win2k.
MANUAL = {
    "cog": "preferences-system",
    "preferences": "preferences-system",
    "list-edit": "gtk-edit",
    "mount-archive": "package-x-generic",
    "night-light": "weather-clear-night",
    "night-light-disabled": "weather-clear-night",
    "user-favorites": "starred",
    "unfavorite": "non-starred",
    "focus-windows": "preferences-system-windows",
    "boot-menu": "system-reboot",
    "touch-disabled": "input-touchpad-symbolic",
    "touchpad-disabled": "input-touchpad-symbolic",
    "emblem-ok": "emblem-default",
    "hourglass": "appointment-soon",
    "media-mount": "drive-removable-media",
    "preview": "document-print-preview",
    "video-joined-displays": "video-display",
    "view-mirror": "video-display",
    "view-left-pane": "view-split-left-right",
    "view-bottom-pane": "view-split-top-bottom",
    "rotation-allowed": "object-rotate-right",
    # categorias do menu do Cinnamon com ícones simbólicos
    "applications-preferences": "preferences-desktop",
    "applications-administration": "applications-system",
}
# Ícones que precisam continuar como o XSI os desenha.
KEEP = {"xsi-empty-icon-symbolic"}

# Ícones próprios de programas, fora do XSI, que também vêm em traço do hicolor: nome
# completo -> ícone Win2k. As variantes "-rtl" usam o "-rtl" do destino, se houver.
APP_ICONS = {
    # Nemo: botão que alterna entre a barra de caminho e o campo de endereço
    "nemo-location-symbolic": "go-jump",
    # Nemo, rodapé: barra lateral (o mesmo ícone do botão da barra lateral do Xed),
    # locais, árvore e painel de visualização
    "nemo-sidebar-hide-symbolic": "view-dual",
    "nemo-sidebar-show-symbolic": "view-dual",
    "nemo-sidebar-places-symbolic": "user-bookmarks",
    "nemo-sidebar-tree-symbolic": "view-list-tree",
    "nemo-preview-show-symbolic": "view-preview",
    "nemo-preview-hide-symbolic": "view-preview",
    # Menus do Cinnamon (menu@cinnamon.org, Classic Menu, Configurable Menu, Cinnamenu):
    # categoria "Todos os aplicativos", como a pasta Programas do menu Iniciar
    "cinnamon-all-applications": "applications-all",
    "cinnamon-all-applications-symbolic": "applications-all",
    # Applet de notificações (notifications@cinnamon.org, ícones simbólicos próprios):
    # sino parado sem notificações, tocando com notificações e, nas críticas, o applet
    # pisca entre "critical" e "alt-critical"
    "empty-notif-symbolic": "notification",
    "normal-notif-symbolic": "notification-active",
    "low-notif-symbolic": "notification-active",
    "critical-notif-symbolic": "emblem-important",
    "alt-critical-notif-symbolic": "notification-active",
}

# Onde procurar os nomes "xsi-*" usados pelos programas instalados (para o relatório).
USED_PATHS = ["/usr/share/cinnamon", "/usr/lib/cinnamon-settings-daemon", "/usr/bin/nemo",
              "/usr/share/nemo", "/usr/bin/xed", "/usr/share/xed", "/usr/lib/xed",
              "/usr/share/cinnamon-screensaver"]
USED_GLOBS = ["/usr/lib/libnemo*", "/usr/lib/libxapp*", "/usr/lib/cinnamon*",
              "/usr/lib/python3*/site-packages/xapp"]
# Outro pacote clássico instalado, consultado pelo relatório.
OTHER_THEMES = {"Chicago95": "/usr/share/icons/Chicago95"}


def inherited_names(theme):
    """Nomes de ícone dos temas herdados (Inherits do index.theme) instalados no sistema."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.read(theme / "index.theme")
    names = set()
    for t in cp["Icon Theme"].get("Inherits", "").split(","):
        for f in glob.glob(f"/usr/share/icons/{t.strip()}/**/*.*", recursive=True):
            if f.endswith(EXTS) and os.path.exists(f):
                names.add(os.path.basename(f).rsplit(".", 1)[0])
    return names


def theme_dirs(theme):
    """Pastas listadas em Directories do index.theme (só elas são consultadas pelo GTK)."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.read(theme / "index.theme")
    return [d for d in cp["Icon Theme"]["Directories"].split(",") if (theme / d).is_dir()]


def index(theme, dirs):
    """nome -> {pasta: arquivo}, só arquivos que existem (links resolvidos)."""
    out = {}
    for d in dirs:
        for f in os.scandir(theme / d):
            name, ext = os.path.splitext(f.name)
            if ext in EXTS and not name.startswith("xsi-") and os.path.exists(f.path):
                out.setdefault(name, {})[d] = f.name
    return out


def read_table(xsi):
    """xsi-*-symbolic -> nomes Adwaita equivalentes (tabela do XSI)."""
    table = {}
    for line in open(xsi / "icons/xsi-adwaita-symbolic.info"):
        parts = [p.strip() for p in line.split(" # ")]
        if len(parts) == 3 and parts[2] != "null":
            table.setdefault(f"xsi-{parts[2]}-symbolic", []).append(parts[0])
    return table


def candidates(name, table):
    if name.endswith("-rtl"):
        name = name[:-len("-rtl")]
    base = name[len("xsi-"):-len("-symbolic")]
    out = [MANUAL[base]] if base in MANUAL else []
    olds = table.get(name, [])
    out += [o + "-symbolic" for o in olds] + olds + [base + "-symbolic", base]
    return out


def resolve(name, table, idx):
    if name in KEEP:
        return None
    if name.endswith("-rtl"):
        target = resolve(name[:-len("-rtl")], table, idx)
        if target and target + "-rtl" in idx:
            return target + "-rtl"
        return target
    return next((c for c in candidates(name, table) if c in idx), None)


def used_names():
    paths = USED_PATHS + [p for g in USED_GLOBS for p in glob.glob(g)]
    paths = [p for p in paths if os.path.exists(p)]
    r = subprocess.run(["grep", "-rhoaE", r"xsi-[a-z0-9-]+-symbolic(-rtl)?", *paths],
                       capture_output=True, text=True)
    return set(r.stdout.split())


def other_theme_has(path, names):
    hits = []
    for n in names:
        found = [f for f in glob.glob(f"{path}/*/*/{n}.*") if os.path.exists(f)]
        if found:
            sizes = sorted({f.split("/")[-2] for f in found}, key=lambda s: (len(s), s))
            hits.append(f"`{n}` ({', '.join(sizes)})")
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--xsi", type=Path, default=Path.home() / "Desktop/xapp-symbolic-icons",
                    help="clone do xapp-symbolic-icons")
    args = ap.parse_args()

    dirs = theme_dirs(THEME)
    ours = set(APP_ICONS) | {n + "-rtl" for n in APP_ICONS}
    removed = 0
    if SYMBOLIC_MANIFEST.exists():
        for rel in SYMBOLIC_MANIFEST.read_text().split():
            if os.path.islink(THEME / rel):
                os.unlink(THEME / rel)
                removed += 1
    for d in dirs:
        for f in os.scandir(THEME / d):
            stem = os.path.splitext(f.name)[0]
            if f.is_symlink() and (stem.startswith("xsi-") or stem in ours):
                os.unlink(f.path)
                removed += 1

    idx = index(THEME, dirs)
    table = read_table(args.xsi)
    xsi_names = sorted(p.stem for p in (args.xsi / "icons/symbolic").glob("xsi-*.svg"))

    made, mapped, missing = 0, {}, []
    for name in xsi_names:
        target = resolve(name, table, idx)
        if not target:
            missing.append(name)
            continue
        mapped[name] = target
        for d, fname in idx[target].items():
            os.symlink(fname, THEME / d / (name + os.path.splitext(fname)[1]))
            made += 1

    app_made = 0
    for name, target in APP_ICONS.items():
        for link, dest in ((name, target), (name + "-rtl", target + "-rtl")):
            if dest not in idx:
                dest = target
            for d, fname in idx.get(dest, {}).items():
                os.symlink(fname, THEME / d / (link + os.path.splitext(fname)[1]))
                app_made += 1
    print(f"{app_made} links para {len(APP_ICONS)} ícones de programas (Nemo, menus e notificações do Cinnamon)")

    # Cinnamon (notificações, applets) pede ícones como simbólicos: "battery" vira
    # "battery-symbolic" e, se o Win2k só tem a versão colorida, o GTK usa o desenho
    # moderno do Adwaita/breeze antes de aceitá-la. Para esses nomes, "-symbolic" aponta
    # para o ícone clássico, como os links "-symbolic" que o pacote já tem.
    inherited = inherited_names(THEME)
    sym_links = []
    for name, where in sorted(idx.items()):
        sym = name + "-symbolic"
        if name.endswith("-symbolic") or sym in idx or sym not in inherited:
            continue
        for d, fname in where.items():
            rel = f"{d}/{sym}{os.path.splitext(fname)[1]}"
            os.symlink(fname, THEME / rel)
            sym_links.append(rel)
    SYMBOLIC_MANIFEST.write_text("\n".join(sorted(sym_links)) + "\n")
    print(f"{len(sym_links)} links -symbolic para {len({r.rsplit('/', 1)[1] for r in sym_links})}"
          " ícones que só tinham versão colorida")

    broken = [f.path for d in dirs for f in os.scandir(THEME / d)
              if f.is_symlink() and not os.path.exists(f.path)
              and (f.name.startswith("xsi-") or os.path.splitext(f.name)[0] in ours
                   or f"{d}/{f.name}" in sym_links)]
    print(f"{removed} links antigos removidos, {made} criados para {len(mapped)} de "
          f"{len(xsi_names)} ícones XSI; {len(broken)} quebrados")

    used = used_names()
    missing = [n for n in missing if n not in KEEP]
    missing_used = [n for n in missing if n in used]
    missing_other = [n for n in missing if n not in used]
    lines = [
        "# Ícones XSI sem ícone clássico no Win2k",
        "",
        f"Gerado por `tools/xsi-links.py` em {datetime.date.today():%d/%m/%Y}, a partir do "
        f"xapp-symbolic-icons ({len(xsi_names)} ícones). {len(mapped)} têm ícone clássico no "
        f"Win2k; os {len(missing)} abaixo continuam com o desenho do XSI (hicolor).",
        "",
        "Para cobrir um deles: copiar para `Icon/Win2k` um ícone com um dos nomes da coluna "
        "\"Nomes equivalentes\" (ou acrescentar um mapeamento em `MANUAL` no script) e rodar "
        "o script de novo. Antes de copiar de outro projeto, conferir a licença: o pacote "
        "Win2k é GPL-2.0 (Icon/Win2k/LICENSE); o Chicago95 é GPL-3.0 (conferir no "
        "repositório dele).",
        "",
        "Mantidos de propósito com o desenho do XSI: "
        + ", ".join(f"`{n}`" for n in sorted(KEEP)) + ".",
        "",
    ]
    table_rows = lambda names: ["| Ícone XSI | Nomes equivalentes | Chicago95 instalado |",
                                "|---|---|---|"] + [
        f"| `{n}` | {', '.join(f'`{c}`' for c in dict.fromkeys(candidates(n, table))) } | "
        f"{', '.join(other_theme_has(OTHER_THEMES['Chicago95'], [n] + candidates(n, table))) or '—'} |"
        for n in names]
    lines += [f"## Usados pelos programas instalados ({len(missing_used)})", "",
              "Cinnamon, Nemo, Xed e XApps pedem estes nomes.", ""]
    lines += table_rows(missing_used) if missing_used else ["Nenhum."]
    lines += ["", f"## Demais ({len(missing_other)})", ""] + table_rows(missing_other) + [""]
    REPORT.write_text("\n".join(lines))
    print(f"relatório: {REPORT.relative_to(ROOT)} ({len(missing_used)} usados, "
          f"{len(missing_other)} demais)")


if __name__ == "__main__":
    main()
