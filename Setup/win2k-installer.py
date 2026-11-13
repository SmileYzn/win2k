#!/usr/bin/env python3
"""Instalador do tema Windows 2000 para XFCE, MATE e Cinnamon.

Sem argumentos abre a janela. No terminal:

    python3 Setup/win2k-installer.py --list
    python3 Setup/win2k-installer.py --install all
    python3 Setup/win2k-installer.py --install icons,sounds --system
    python3 Setup/win2k-installer.py --install all --with-panel
    python3 Setup/win2k-installer.py --uninstall all

Modos:
  - "Só para mim" (padrão): copia para a pasta pessoal (~/.themes, ~/.local/share...),
    sem senha de root.
  - "Sistema" (--system): copia para /usr/share e /etc/xdg. Só a cópia roda como root,
    com o próprio script chamado de novo pelo pkexec (--root); a janela nunca roda como root.

"Aplicar" ativa cada parte no XFCE (xfconf-query), no Cinnamon (gsettings) e, para os sons,
no MATE (gsettings), conforme o que estiver instalado. Os valores anteriores ficam guardados em ~/.local/share/win2k-installer e
voltam ao desinstalar. O componente "terminal" grava da
mesma forma as cores do MATE Terminal (dconf) e do Xfce Terminal (xfconf).
"""

import argparse
import ast
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent   # raiz do projeto (o script fica em Setup/)
HOME = Path.home()
STATE_DIR = HOME / ".local/share/win2k-installer"
STATE_FILE = STATE_DIR / "state.json"
PANEL_PROFILE = SRC / "Panel/win2k.tar.bz2"
MATE_PANEL_PROFILE = SRC / "Panel/mate-win2k.dconf"
MATE_PANEL_BACKUP = STATE_DIR / "mate-panel-backup.dconf"
MINTMENU_APPLET = Path("/usr/share/mate-panel/applets/org.mate.panel.MintMenuApplet.mate-panel-applet")
# Texto e ícone do botão do MintMenu (fora do dconf do painel), em GVariant.
MINTMENU_SETTINGS = [("/com/linuxmint/mintmenu/applet-text", "'Iniciar'"),
                     ("/com/linuxmint/mintmenu/applet-icon", "'start-here'")]
MENU_SYSTEM_PATH = "/usr/share/win2k-menu"
# Ambiente original para os comandos chamados: a janela muda GTK_THEME e XDG_DATA_DIRS
# só para si mesma (veja use_project_theme).
CHILD_ENV = dict(os.environ)

# Componentes na ordem de instalação. "files": (origem no projeto, destino).
COMPONENTS = {
    "theme": {
        "label": "Tema GTK, xfwm4 e notificações",
        "files": {
            "system": [("Theme/Win2k", "/usr/share/themes/Win2k")],
            "user": [("Theme/Win2k", "~/.themes/Win2k")],
        },
    },
    "icons": {
        "label": "Ícones",
        "files": {
            "system": [("Icon/Win2k", "/usr/share/icons/Win2k")],
            "user": [("Icon/Win2k", "~/.local/share/icons/Win2k")],
        },
    },
    "cursors": {
        "label": "Cursores",
        "files": {
            "system": [("Cursor/Win2k_Cursors", "/usr/share/icons/Win2k_Cursors")],
            "user": [("Cursor/Win2k_Cursors", "~/.icons/Win2k_Cursors")],
        },
    },
    # Os dois esquemas de sons do Windows 2000. Só um fica ativo (veja SOUND_THEMES); o
    # .desktop do som de logon é dos dois e só sai quando nenhum continua instalado.
    "sounds": {
        "label": "Sons: esquema Padrão do Windows (e som de logon)",
        "files": {
            "system": [("Sound/Win2k", "/usr/share/sounds/Win2k"),
                       ("Sound/win2k-logon-sound.desktop", "/etc/xdg/autostart/win2k-logon-sound.desktop")],
            "user": [("Sound/Win2k", "~/.local/share/sounds/Win2k"),
                     ("Sound/win2k-logon-sound.desktop", "~/.config/autostart/win2k-logon-sound.desktop")],
        },
    },
    "sounds-utopia": {
        "label": "Sons: esquema Utopia (e som de logon)",
        "files": {
            "system": [("Sound/Win2k-Utopia", "/usr/share/sounds/Win2k-Utopia"),
                       ("Sound/win2k-logon-sound.desktop", "/etc/xdg/autostart/win2k-logon-sound.desktop")],
            "user": [("Sound/Win2k-Utopia", "~/.local/share/sounds/Win2k-Utopia"),
                     ("Sound/win2k-logon-sound.desktop", "~/.config/autostart/win2k-logon-sound.desktop")],
        },
    },
    "wallpaper": {
        "label": "Papel de parede",
        "files": {
            "system": [("Wallpaper/Win2k", "/usr/share/backgrounds/Win2k")],
            "user": [("Wallpaper/Win2k", "~/.local/share/backgrounds/Win2k")],
        },
    },
    "menu": {
        "label": "Menu Iniciar",
        "files": {
            "system": [("Menu", MENU_SYSTEM_PATH)],
            "user": [("Menu", "~/.local/share/win2k-menu")],
        },
    },
    # O painel não copia arquivos: carrega o perfil do xfce4-panel-profiles.
    "panel": {
        "label": "Painel Windows 2000 para XFCE (substitui o painel atual)",
        "files": {"system": [], "user": []},
    },
    # Também sem arquivos: carrega Panel/mate-win2k.dconf em /org/mate/panel/.
    "mate-panel": {
        "label": "Painel Windows 2000 para MATE (substitui o painel atual)",
        "files": {"system": [], "user": []},
    },
    # Também sem arquivos: só troca as cores do MATE Terminal e do Xfce Terminal.
    "terminal": {
        "label": "Tema de cores do terminal MS-DOS",
        "files": {"system": [], "user": []},
    },
}
FILE_COMPONENTS = [c for c in COMPONENTS if COMPONENTS[c]["files"]["user"]]
SETTINGS_ONLY = [c for c in COMPONENTS if c not in FILE_COMPONENTS]   # sempre aplicados
DEFAULT_OFF = {"panel", "mate-panel", "terminal", "sounds-utopia"}
# Componente de sons -> nome do tema de sons freedesktop que ele instala.
SOUND_THEMES = {"sounds": "Win2k", "sounds-utopia": "Win2k-Utopia"}

# Tema de cores do prompt do MS-DOS no Windows 2000: cinza sobre preto, as 16 cores do console
# e cursor sublinhado piscando.
DOS_COLORS = ["#000000", "#800000", "#008000", "#808000", "#000080", "#800080", "#008080",
              "#C0C0C0", "#808080", "#FF0000", "#00FF00", "#FFFF00", "#0000FF", "#FF00FF",
              "#00FFFF", "#FFFFFF"]
# MATE Terminal: chaves do perfil no dconf, valores em GVariant.
MATE_TERMINAL_SETTINGS = [
    ("use-theme-colors", "false"),
    ("foreground-color", "'#C0C0C0'"),
    ("background-color", "'#000000'"),
    ("bold-color-same-as-fg", "true"),
    ("palette", "'" + ":".join(DOS_COLORS) + "'"),
    ("cursor-shape", "'underline'"),
    ("cursor-blink-mode", "'on'"),
]
# Xfce Terminal: propriedades do canal xfce4-terminal.
XFCE_TERMINAL_SETTINGS = [
    ("xfce4-terminal", "/color-use-theme", "bool", "false"),
    ("xfce4-terminal", "/color-foreground", "string", "#C0C0C0"),
    ("xfce4-terminal", "/color-background", "string", "#000000"),
    ("xfce4-terminal", "/color-bold-use-default", "bool", "true"),
    ("xfce4-terminal", "/color-cursor-use-default", "bool", "true"),
    ("xfce4-terminal", "/color-palette", "string", ";".join(DOS_COLORS)),
    ("xfce4-terminal", "/misc-cursor-shape", "string", "TERMINAL_CURSOR_SHAPE_UNDERLINE"),
    ("xfce4-terminal", "/misc-cursor-blinks", "bool", "true"),
]


def dest_path(dest):
    return Path(os.path.expanduser(dest))


def run(cmd, check=False):
    return subprocess.run(cmd, capture_output=True, text=True, check=check, env=CHILD_ENV)


# --------------------------------------------------------------------------
# Cópia de arquivos (usada nos dois modos; no modo sistema roda como root)
# --------------------------------------------------------------------------

def install_files(comp, mode, log):
    for src_rel, dest in COMPONENTS[comp]["files"][mode]:
        src, dest = SRC / src_rel, dest_path(dest)
        if not src.exists():
            raise RuntimeError(f"origem não encontrada: {src}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            # Copia para .new e troca com rename: o destino quase não fica ausente
            # (o painel monitora o arquivo do menu e reclamaria se ele sumisse).
            new, old = dest.with_name(dest.name + ".new"), dest.with_name(dest.name + ".old")
            for p in (new, old):
                if p.exists():
                    shutil.rmtree(p)
            shutil.copytree(src, new, symlinks=True)
            if comp == "menu":
                fix_menu_paths(new, dest)
            if dest.exists():
                dest.rename(old)
            new.rename(dest)
            if old.exists():
                shutil.rmtree(old)
        else:
            shutil.copy2(src, dest)
        log(f"  {src_rel} → {dest}")
    if comp == "icons":
        dest = dest_path(COMPONENTS["icons"]["files"][mode][0][1])
        if shutil.which("gtk-update-icon-cache"):
            run(["gtk-update-icon-cache", "-f", "-t", str(dest)])
            log("  cache de ícones atualizado")
        else:
            log("  gtk-update-icon-cache não encontrado; cache de ícones não atualizado")


def fix_menu_paths(new_dir, final_dir):
    """Os atalhos do menu citam /usr/share/win2k-menu; ajusta para o destino real."""
    if str(final_dir) == MENU_SYSTEM_PATH:
        return
    for f in (new_dir / "applications").glob("*.desktop"):
        text = f.read_text()
        if MENU_SYSTEM_PATH in text:
            f.write_text(text.replace(MENU_SYSTEM_PATH, str(final_dir)))


def shared_with(comp, dest, mode):
    """Outro componente instalado que também usa o arquivo dest (o .desktop do som de logon)."""
    for other, info in COMPONENTS.items():
        if other != comp and any(d == dest for _, d in info["files"][mode]) and installed_in(other, mode):
            return other
    return None


def remove_files(comp, mode, log):
    for src_rel, dest in COMPONENTS[comp]["files"][mode]:
        other = shared_with(comp, dest, mode)
        if other:
            log(f"  {dest_path(dest)} mantido (usado por {COMPONENTS[other]['label']})")
            continue
        dest = dest_path(dest)
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
            log(f"  removido {dest}")
        elif dest.exists() or dest.is_symlink():
            dest.unlink()
            log(f"  removido {dest}")


def installed_in(comp, mode):
    files = COMPONENTS[comp]["files"][mode]
    return bool(files) and dest_path(files[0][1]).exists()


def root_main(action, comps):
    """Executado pelo pkexec. Só aceita os componentes conhecidos e os destinos fixos acima."""
    if os.geteuid() != 0:
        sys.exit("--root só pode ser usado pelo pkexec")
    os.umask(0o022)
    bad = [c for c in comps if c not in FILE_COMPONENTS]
    if action not in ("install", "uninstall") or bad:
        sys.exit(f"pedido inválido: {action} {bad}")

    def log(msg):
        print(msg, flush=True)

    for comp in comps:
        log(f"{COMPONENTS[comp]['label']}:")
        (install_files if action == "install" else remove_files)(comp, "system", log)


# --------------------------------------------------------------------------
# Configurações do XFCE, do MATE e do Cinnamon (sempre como o usuário)
# --------------------------------------------------------------------------

# Cada área de trabalho só recebe configurações se estiver instalada: no Cinnamon, por
# exemplo, não há xfconf-query nem xfce4-panel-profiles.
def have_xfce():
    return shutil.which("xfconf-query") is not None


def have_xfce_panel():
    return shutil.which("xfce4-panel-profiles") is not None


def have_mate_panel():
    return shutil.which("mate-panel") is not None and shutil.which("dconf") is not None


def have_mate():
    return (shutil.which("mate-session") is not None and shutil.which("gsettings") is not None
            and run(["gsettings", "list-keys", "org.mate.sound"]).returncode == 0)


def have_cinnamon():
    return (shutil.which("cinnamon") is not None and shutil.which("gsettings") is not None
            and run(["gsettings", "list-keys", "org.cinnamon.theme"]).returncode == 0)


def gsettings_get(schema, key):
    r = run(["gsettings", "get", schema, key])
    return r.stdout.strip() if r.returncode == 0 else None


def gsettings_set(schema, key, value):
    run(["gsettings", "set", schema, key, value], check=True)


def gsettings_reset(schema, key):
    run(["gsettings", "reset", schema, key])


def gvariant_str(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def cinnamon_settings_for(comp, mode):
    """Lista de (esquema, chave, valor em GVariant) que "Aplicar" grava no Cinnamon."""
    if comp == "theme":
        return [("org.cinnamon.desktop.interface", "gtk-theme", "'Win2k'"),
                ("org.cinnamon.desktop.wm.preferences", "theme", "'Win2k'"),
                ("org.cinnamon.theme", "name", "'Win2k'")]
    if comp == "icons":
        return [("org.cinnamon.desktop.interface", "icon-theme", "'Win2k'")]
    if comp == "cursors":
        return [("org.cinnamon.desktop.interface", "cursor-theme", "'Win2k_Cursors'")]
    if comp in SOUND_THEMES:
        # O Cinnamon toca o logon e o logoff pelas próprias chaves; o .desktop de autostart
        # do som de logon é só para o XFCE e o MATE (OnlyShowIn).
        stereo = dest_path(COMPONENTS[comp]["files"][mode][0][1]) / "stereo"
        return [("org.cinnamon.desktop.sound", "theme-name", gvariant_str(SOUND_THEMES[comp])),
                ("org.cinnamon.desktop.sound", "event-sounds", "true"),
                ("org.cinnamon.sounds", "login-enabled", "true"),
                ("org.cinnamon.sounds", "login-file", gvariant_str(str(stereo / "desktop-login.wav"))),
                ("org.cinnamon.sounds", "logout-enabled", "true"),
                ("org.cinnamon.sounds", "logout-file", gvariant_str(str(stereo / "desktop-logout.wav")))]
    if comp == "wallpaper":
        folder = dest_path(COMPONENTS["wallpaper"]["files"][mode][0][1])
        images = sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg"))
        if not images:
            return []
        return [("org.cinnamon.desktop.background", "picture-uri", gvariant_str(images[0].as_uri()))]
    return []


def mate_settings_for(comp, mode):
    """Lista de (esquema, chave, valor em GVariant) que "Aplicar" grava no MATE. O
    mate-settings-daemon repassa o tema de sons ao GTK (XSETTINGS)."""
    if comp in SOUND_THEMES:
        return [("org.mate.sound", "theme-name", gvariant_str(SOUND_THEMES[comp])),
                ("org.mate.sound", "event-sounds", "true")]
    return []


def apply_gsettings(items, desktop, previous, log):
    for schema, key, value in items:
        state_key = f"gsettings|{schema} {key}"
        if state_key not in previous:        # só o valor de antes da 1ª aplicação
            previous[state_key] = ["gvariant", gsettings_get(schema, key)]
        gsettings_set(schema, key, value)
        log(f"  {desktop}: {schema} {key} = {value}")


def apply_cinnamon(comp, mode, previous, log):
    if comp == "menu":
        log("  Cinnamon: o botão Iniciar é o applet de menu do painel; nada a aplicar")
        return
    apply_gsettings(cinnamon_settings_for(comp, mode), "Cinnamon", previous, log)


def xfconf_get(channel, prop):
    r = run(["xfconf-query", "-c", channel, "-p", prop])
    return r.stdout.strip() if r.returncode == 0 else None


def xfconf_set(channel, prop, kind, value):
    run(["xfconf-query", "-c", channel, "-p", prop, "-n", "-t", kind, "-s", value], check=True)


def xfconf_reset(channel, prop):
    run(["xfconf-query", "-c", channel, "-p", prop, "-r"])


def xfconf_list(channel):
    r = run(["xfconf-query", "-c", channel, "-l", "-v"])
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if parts:
            out[parts[0]] = parts[1] if len(parts) > 1 else ""
    return out


def dconf_get(path):
    r = run(["dconf", "read", path])
    return r.stdout.strip() or None if r.returncode == 0 else None


def dconf_set(path, value):
    run(["dconf", "write", path, value], check=True)


def dconf_reset(path):
    run(["dconf", "reset", path])


def mate_panel_running():
    return run(["pgrep", "-u", str(os.getuid()), "-x", "mate-panel"]).returncode == 0


def restart_mate_panel(log):
    """Recarrega o painel do MATE (tema, ícones ou layout novos), se ele estiver rodando."""
    if mate_panel_running():
        subprocess.Popen(["mate-panel", "--replace"], env=CHILD_ENV, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Painel do MATE reiniciado")


def load_mate_panel(text):
    """Troca a configuração do painel do MATE pelo dconf em text.

    O "dconf load" grava tudo numa só mudança, que o painel em execução lê de uma vez. Um
    "dconf reset" antes faria o painel ver os objetos sumirem e apagar a configuração deles;
    por isso as pastas que sobram (objetos e painéis fora das listas novas, que o painel
    ignora) só são apagadas depois.
    """
    subprocess.run(["dconf", "load", "/org/mate/panel/"], input=text, text=True,
                   capture_output=True, env=CHILD_ENV, check=True)
    for kind, key in (("objects", "object-id-list"), ("toplevels", "toplevel-id-list")):
        m = re.search(rf"^{key}=(\[.*\])$", text, re.M)
        keep = set(ast.literal_eval(m.group(1))) if m else set()
        listing = run(["dconf", "list", f"/org/mate/panel/{kind}/"]).stdout.split()
        for entry in listing:
            if entry.endswith("/") and entry[:-1] not in keep:
                run(["dconf", "reset", "-f", f"/org/mate/panel/{kind}/{entry}"])


def terminal_profile():
    """Caminho dconf do perfil padrão do MATE Terminal, ou None se ele não estiver instalado."""
    if not shutil.which("mate-terminal") or not shutil.which("dconf"):
        return None
    name = (dconf_get("/org/mate/terminal/global/default-profile") or "'default'").strip("'")
    return f"/org/mate/terminal/profiles/{name}/"


def menu_plugins():
    return [p for p, v in xfconf_list("xfce4-panel").items()
            if re.fullmatch(r"/plugins/plugin-\d+", p) and v == "applicationsmenu"]


def settings_for(comp, mode):
    """Lista de (canal, propriedade, tipo, valor) que "Aplicar" grava."""
    if comp == "theme":
        return [("xsettings", "/Net/ThemeName", "string", "Win2k"),
                ("xfwm4", "/general/theme", "string", "Win2k"),
                ("xfce4-notifyd", "/theme", "string", "Win2k")]
    if comp == "icons":
        return [("xsettings", "/Net/IconThemeName", "string", "Win2k")]
    if comp == "cursors":
        return [("xsettings", "/Gtk/CursorThemeName", "string", "Win2k_Cursors")]
    if comp in SOUND_THEMES:
        return [("xsettings", "/Net/SoundThemeName", "string", SOUND_THEMES[comp]),
                ("xsettings", "/Net/EnableEventSounds", "bool", "true")]
    if comp == "wallpaper":
        folder = dest_path(COMPONENTS["wallpaper"]["files"][mode][0][1])
        images = sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg"))
        if not images:
            return []
        props = [p for p in xfconf_list("xfce4-desktop") if p.endswith("/last-image")]
        return [("xfce4-desktop", p, "string", str(images[0])) for p in props]
    if comp == "menu":
        menu_file = str(dest_path(COMPONENTS["menu"]["files"][mode][0][1]) / "win2k-start.menu")
        out = []
        for p in menu_plugins():
            out += [("xfce4-panel", f"{p}/custom-menu", "bool", "true"),
                    ("xfce4-panel", f"{p}/custom-menu-file", "string", menu_file)]
        return out
    if comp == "terminal":
        return XFCE_TERMINAL_SETTINGS if shutil.which("xfce4-terminal") and have_xfce() else []
    return []


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def apply_component(comp, mode, state, log):
    previous = state.setdefault("previous", {})
    if comp == "panel":
        if not have_xfce_panel():
            log("  XFCE (xfce4-panel-profiles) não encontrado; nada a aplicar")
            return
        backup = STATE_DIR / "panel-backup.tar.bz2"
        if not backup.exists():
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            run(["xfce4-panel-profiles", "save", str(backup)], check=True)
            log(f"  backup do painel atual: {backup}")
        run(["xfce4-panel-profiles", "load", str(PANEL_PROFILE)], check=True)
        log("  perfil do painel carregado")
        return
    if comp == "mate-panel":
        if not have_mate_panel():
            log("  MATE (mate-panel e dconf) não encontrado; nada a aplicar")
            return
        if not MATE_PANEL_BACKUP.exists():
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            MATE_PANEL_BACKUP.write_text(run(["dconf", "dump", "/org/mate/panel/"], check=True).stdout)
            log(f"  backup do painel atual: {MATE_PANEL_BACKUP}")
        for path, value in MINTMENU_SETTINGS:
            if f"dconf|{path}" not in previous:     # só o valor de antes da 1ª aplicação
                previous[f"dconf|{path}"] = ["gvariant", dconf_get(path)]
            dconf_set(path, value)
        load_mate_panel(MATE_PANEL_PROFILE.read_text())
        log("  painel Windows 2000 carregado (MintMenu com \"Iniciar\")")
        if not MINTMENU_APPLET.exists():
            log("  atenção: o MintMenu não está instalado; o botão Iniciar só aparece com ele"
                " (pacote mintmenu)")
        return
    if comp == "terminal":
        profile = terminal_profile()
        if profile:
            for key, value in MATE_TERMINAL_SETTINGS:
                path = profile + key
                if f"dconf|{path}" not in previous:     # só o valor de antes da 1ª aplicação
                    previous[f"dconf|{path}"] = ["gvariant", dconf_get(path)]
                dconf_set(path, value)
            log(f"  MATE Terminal: cores do MS-DOS no perfil {profile}")
        if not (shutil.which("xfce4-terminal") and have_xfce()):
            if not profile:
                log("  nem o MATE Terminal nem o Xfce Terminal estão instalados; nada a aplicar")
            return

    if comp in SOUND_THEMES:
        state["sounds_applied"] = comp        # o esquema ativo é o que a remoção desfaz
    xfce, cinnamon = have_xfce(), have_cinnamon()
    mate = comp in SOUND_THEMES and have_mate()
    items = []
    if xfce:
        items = settings_for(comp, mode)
        if comp == "wallpaper" and not items:
            log("  nenhuma área de trabalho encontrada no xfdesktop; aplique o papel de parede à mão")
        if comp == "menu" and not items:
            log("  o painel não tem o plugin \"Menu de aplicativos\"; nada a apontar")
    elif not cinnamon and not mate and comp != "terminal":
        log("  nem o XFCE (xfconf-query) nem o Cinnamon (gsettings) foram encontrados;"
            " ative o componente nas configurações da sua área de trabalho")
    for channel, prop, kind, value in items:
        key = f"{channel}|{prop}"
        if key not in previous:          # guarda só o valor de antes da 1ª aplicação
            previous[key] = [kind, xfconf_get(channel, prop)]
        xfconf_set(channel, prop, kind, value)
        log(f"  {channel} {prop} = {value}")
    if comp == "terminal":
        return
    if cinnamon:
        apply_cinnamon(comp, mode, previous, log)
    if mate:
        apply_gsettings(mate_settings_for(comp, mode), "MATE", previous, log)

    if comp == "theme":
        # Apps libadwaita (GTK4) só leem o tema em ~/.config/gtk-4.0
        gtk4 = HOME / ".config/gtk-4.0"
        backup = STATE_DIR / "gtk-4.0.backup"
        if "gtk4_existed" not in state:
            state["gtk4_existed"] = gtk4.exists()
            if gtk4.exists():
                if backup.exists():
                    shutil.rmtree(backup)
                shutil.copytree(gtk4, backup, symlinks=True)
        shutil.copytree(SRC / "Theme/Win2k/gtk-4.0", gtk4, symlinks=True, dirs_exist_ok=True)
        log(f"  tema GTK4/libadwaita copiado para {gtk4}")
    if comp == "cursors":
        env = os.environ.get("XCURSOR_THEME")
        if env and env != "Win2k_Cursors":
            log(f"  atenção: XCURSOR_THEME={env} na sessão (veja /etc/environment e ~/.profile);"
                " apps Java e outros continuarão com esse cursor")


SOUND_PREFIXES = ("xsettings|/Net/SoundThemeName", "xsettings|/Net/EnableEventSounds",
                  "gsettings|org.cinnamon.desktop.sound ", "gsettings|org.cinnamon.sounds ",
                  "gsettings|org.mate.sound ")


def restore_component(comp, state, log):
    previous = state.get("previous", {})
    if comp in SOUND_THEMES:
        # Os dois esquemas gravam as mesmas chaves: só a remoção do esquema ativo devolve os
        # valores de antes (estados antigos, sem "sounds_applied", eram do "sounds").
        active = state.get("sounds_applied", "sounds")
        if active != comp:
            log(f"  o esquema ativo é outro ({COMPONENTS[active]['label']}); nada a restaurar")
            return
        state.pop("sounds_applied", None)
    if comp == "panel":
        backup = STATE_DIR / "panel-backup.tar.bz2"
        if backup.exists() and not have_xfce_panel():
            log(f"  XFCE (xfce4-panel-profiles) não encontrado; o backup fica em {backup}")
        elif backup.exists():
            run(["xfce4-panel-profiles", "load", str(backup)], check=True)
            backup.unlink()
            log("  painel anterior restaurado")
        return
    if comp == "mate-panel" and MATE_PANEL_BACKUP.exists() and not shutil.which("dconf"):
        log(f"  dconf não encontrado; o backup do painel do MATE fica em {MATE_PANEL_BACKUP}")
    elif comp == "mate-panel" and MATE_PANEL_BACKUP.exists():
        load_mate_panel(MATE_PANEL_BACKUP.read_text())
        MATE_PANEL_BACKUP.unlink()
        log("  painel anterior do MATE restaurado")
    prefixes = {
        "theme": ("xsettings|/Net/ThemeName", "xfwm4|", "xfce4-notifyd|",
                  "gsettings|org.cinnamon.desktop.interface gtk-theme",
                  "gsettings|org.cinnamon.desktop.wm.preferences theme",
                  "gsettings|org.cinnamon.theme name"),
        "icons": ("xsettings|/Net/IconThemeName", "gsettings|org.cinnamon.desktop.interface icon-theme"),
        "cursors": ("xsettings|/Gtk/CursorThemeName",
                    "gsettings|org.cinnamon.desktop.interface cursor-theme"),
        "sounds": SOUND_PREFIXES,
        "sounds-utopia": SOUND_PREFIXES,
        "wallpaper": ("xfce4-desktop|", "gsettings|org.cinnamon.desktop.background "),
        "menu": ("xfce4-panel|",),
        "terminal": ("dconf|/org/mate/terminal/", "xfce4-terminal|"),
        "mate-panel": ("dconf|/com/linuxmint/mintmenu/",),
    }[comp]
    skipped = set()
    for key in [k for k in previous if k.startswith(prefixes)]:
        channel, prop = key.split("|", 1)
        tool = channel if channel in ("dconf", "gsettings") else "xfconf-query"
        if not shutil.which(tool):
            # Sem a ferramenta (outra área de trabalho, ou o XFCE removido): o valor antigo
            # continua guardado e volta numa próxima remoção feita onde ela existir.
            if tool not in skipped:
                log(f"  {tool} não encontrado; valores anteriores mantidos em {STATE_FILE}")
                skipped.add(tool)
            continue
        kind, value = previous.pop(key)
        if channel == "dconf":
            dconf_reset(prop) if value is None else dconf_set(prop, value)
        elif channel == "gsettings":
            schema, gkey = prop.split(" ", 1)
            gsettings_reset(schema, gkey) if value is None else gsettings_set(schema, gkey, value)
        elif value is None:
            xfconf_reset(channel, prop)
        else:
            xfconf_set(channel, prop, kind, value)
        log(f"  {channel} {prop} restaurado")
    if comp == "theme" and "gtk4_existed" in state:
        gtk4, backup = HOME / ".config/gtk-4.0", STATE_DIR / "gtk-4.0.backup"
        if gtk4.exists():
            shutil.rmtree(gtk4)
        if state.pop("gtk4_existed") and backup.exists():
            backup.rename(gtk4)
        log(f"  {gtk4} restaurado")


def restart_panel(log):
    if run(["pgrep", "-u", str(os.getuid()), "-x", "xfce4-panel"]).returncode == 0:
        run(["xfce4-panel", "-r"])
        log("Painel reiniciado")


# --------------------------------------------------------------------------
# Instalação / desinstalação (como o usuário)
# --------------------------------------------------------------------------

def run_as_root(action, comps, log):
    if not shutil.which("pkexec"):
        raise RuntimeError("pkexec não encontrado (pacote polkit)")
    cmd = ["pkexec", sys.executable, "-I", str(Path(__file__).resolve()), "--root", action, *comps]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env=CHILD_ENV)
    for line in proc.stdout:
        log(line.rstrip())
    if proc.wait() in (126, 127):
        raise RuntimeError("autorização negada ou cancelada")
    if proc.returncode:
        raise RuntimeError(f"a cópia como root falhou (código {proc.returncode})")


def do_install(comps, mode, apply, log, progress=lambda f: None):
    if os.geteuid() == 0:
        raise RuntimeError("não rode o instalador como root; use o modo Sistema")
    comps = [c for c in COMPONENTS if c in comps]       # ordem fixa
    files = [c for c in comps if c in FILE_COMPONENTS]
    steps = len(files) + len([c for c in comps if c in apply or c in SETTINGS_ONLY]) or 1
    done = 0

    if mode == "system" and files:
        log("Copiando para o sistema (pkexec)...")
        run_as_root("install", files, log)
        done += len(files)
        progress(done / steps)
    else:
        for comp in files:
            log(f"{COMPONENTS[comp]['label']}:")
            install_files(comp, mode, log)
            done += 1
            progress(done / steps)

    if "sounds" in apply and "sounds-utopia" in apply:
        log("Os dois esquemas de sons pedem para ser aplicados; aplicando o Padrão do Windows")
        apply = [c for c in apply if c != "sounds-utopia"]
    state = load_state()
    # O painel antes do menu: o perfil traz o caminho do menu do sistema, que o menu corrige.
    for comp in sorted((c for c in comps if c in apply or c in SETTINGS_ONLY),
                       key=lambda c: (c != "panel", list(COMPONENTS).index(c))):
        log(f"Aplicando: {COMPONENTS[comp]['label']}")
        apply_component(comp, mode, state, log)
        save_state(state)
        done += 1
        progress(done / steps)
    if ("menu" in apply and "menu" in comps) and "panel" not in comps:
        restart_panel(log)
    if {"theme", "icons", "mate-panel"} & set(comps):
        restart_mate_panel(log)
    log("Instalação concluída.")


def do_uninstall(comps, mode, log, progress=lambda f: None):
    if os.geteuid() == 0:
        raise RuntimeError("não rode o instalador como root; use o modo Sistema")
    comps = [c for c in COMPONENTS if c in comps]
    state = load_state()
    steps, done = len(comps) * 2 or 1, 0
    for comp in comps:
        log(f"Restaurando: {COMPONENTS[comp]['label']}")
        restore_component(comp, state, log)
        save_state(state)
        done += 1
        progress(done / steps)
    files = [c for c in comps if c in FILE_COMPONENTS and installed_in(c, mode)]
    if mode == "system" and files:
        log("Removendo do sistema (pkexec)...")
        run_as_root("uninstall", files, log)
    else:
        for comp in files:
            log(f"{COMPONENTS[comp]['label']}:")
            remove_files(comp, mode, log)
    progress(1)
    if "menu" in comps:
        restart_panel(log)
    if {"theme", "icons", "mate-panel"} & set(comps):
        restart_mate_panel(log)
    log("Desinstalação concluída.")


def terminal_applied():
    return any(k.startswith(("dconf|/org/mate/terminal/", "xfce4-terminal|"))
               for k in load_state().get("previous", {}))


def status_text(comp):
    if comp == "panel":
        if (STATE_DIR / "panel-backup.tar.bz2").exists():
            return "backup salvo"
        return "" if have_xfce_panel() else "XFCE não encontrado"
    if comp == "mate-panel":
        if MATE_PANEL_BACKUP.exists():
            return "backup salvo"
        return "" if have_mate_panel() else "MATE não encontrado"
    if comp == "terminal":
        return "aplicado" if terminal_applied() else ""
    where = [n for m, n in (("user", "usuário"), ("system", "sistema")) if installed_in(comp, m)]
    return " + ".join(where) if where else "não instalado"


# --------------------------------------------------------------------------
# Janela: assistente no estilo da instalação do Windows 2000
# --------------------------------------------------------------------------

SETUP_DIR = SRC / "Setup"
TITLE = "Instalação do tema Windows 2000"

DESCRIPTIONS = {
    "theme": "Janelas, botões e menus no estilo Windows 2000 para GTK 2, 3 e 4, "
             "bordas do xfwm4, balões de notificação e painel e menus do Cinnamon.",
    "icons": "Pacote de ícones do Windows 2000 para aplicativos, pastas e ações.",
    "cursors": "Ponteiros do mouse do Windows 2000.",
    "sounds": "Esquema de sons \"Padrão do Windows\": Ding, Chord, Notify, logon e logoff. "
              "Aplicado no XFCE, no MATE e no Cinnamon.",
    "sounds-utopia": "Esquema de sons \"Utopia\" do Windows 2000: também toca ao maximizar, "
                     "minimizar, restaurar e abrir menus. Aplicado no XFCE, no MATE e no Cinnamon; "
                     "só um esquema fica ativo.",
    "wallpaper": "Papel de parede do Windows 2000.",
    "menu": "Menu Iniciar clássico com Programas, Documentos, Configurações, Pesquisar, "
            "Executar, Fazer logoff e Desligar.",
    "panel": "Barra de tarefas do XFCE no estilo Windows 2000. Substitui o painel atual; um "
             "backup é salvo e volta ao remover este componente.",
    "mate-panel": "Barra de tarefas do MATE no estilo Windows 2000: MintMenu como botão Iniciar, "
                  "Inicialização rápida, lista de janelas, área de notificação e relógio. "
                  "Substitui o painel atual; um backup é salvo e volta ao remover.",
    "terminal": "Tema de cores do prompt do MS-DOS para o MATE Terminal e o Xfce Terminal: "
                "texto cinza sobre fundo preto, as 16 cores do DOS e cursor sublinhado. "
                "As cores anteriores voltam ao remover.",
}

# A janela simula o diálogo do Setup sobre o fundo: moldura em relevo e barra de título
# em degradê, com cores fixas para ficar igual em qualquer tema GTK.
WIZARD_CSS = b"""
.w2k-setup-dialog {
  background-color: #d4d0c8;
  color: #000000;
  border-style: solid;
  border-width: 1px;
  border-color: #d4d0c8 #404040 #404040 #d4d0c8;
  box-shadow: inset 1px 1px #ffffff, inset -1px -1px #808080;
  padding: 3px; }
.w2k-setup-caption {
  background-image: linear-gradient(to right, #0a246a, #a6caf0);
  padding: 3px 4px; }
.w2k-setup-caption label {
  color: #ffffff;
  font-weight: bold; }
.w2k-setup-banner {
  background-color: #ffffff; }
"""


def use_project_theme():
    """A janela usa sempre o tema e os ícones Win2k do projeto, qualquer que seja o tema do
    sistema. Links com nome próprio numa pasta temporária, colocada no XDG_DATA_DIRS antes de
    o GTK iniciar, evitam que uma cópia Win2k já instalada (talvez antiga) seja usada no lugar."""
    tmp = Path(tempfile.mkdtemp(prefix="win2k-setup-", dir=os.environ.get("XDG_RUNTIME_DIR")))
    atexit.register(shutil.rmtree, tmp, True)
    for kind, src in (("themes", "Theme/Win2k"), ("icons", "Icon/Win2k")):
        (tmp / kind).mkdir()
        (tmp / kind / "Win2k-Setup").symlink_to(SRC / src)
    os.environ["XDG_DATA_DIRS"] = f"{tmp}:" + os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    os.environ["GTK_THEME"] = "Win2k-Setup"


def gui_main():
    use_project_theme()
    import cairo
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango
    Gtk.Settings.get_default().props.gtk_icon_theme_name = "Win2k-Setup"

    def bold(text, size=None):
        lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
        size_attr = f" size='{size}'" if size else ""
        lbl.set_markup(f"<span weight='bold'{size_attr}>{GLib.markup_escape_text(text)}</span>")
        return lbl

    def text(content):
        return Gtk.Label(label=content, xalign=0, wrap=True, max_width_chars=60)

    def page(title, subtitle=None, big=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(bold(title, "large" if big else None), False, False, 0)
        if subtitle is not None:
            sub = text(subtitle)
            sub.set_margin_start(0 if big else 12)
            box.pack_start(sub, False, False, 0)
        return box

    class Background(Gtk.DrawingArea):
        """setup_w.bmp no canto, em escala inteira, e o padrão do fundo repetido no resto."""

        def __init__(self):
            super().__init__()
            self.image = GdkPixbuf.Pixbuf.new_from_file(str(SETUP_DIR / "background.png"))
            # 8x8 de uma área lisa, alinhado à grade do padrão (período 4)
            self.tile = self.image.new_subpixbuf(256, 416, 8, 8)

        def do_draw(self, cr):
            w, h = self.get_allocated_width(), self.get_allocated_height()
            scale = max(1, min(w // 640, h // 480))
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self.tile, 0, 0)
            cr.get_source().set_extend(cairo.EXTEND_REPEAT)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint()
            Gdk.cairo_set_source_pixbuf(cr, self.image, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.rectangle(0, 0, 640, 480)
            cr.fill()
            return False

    class Wizard(Gtk.Window):
        def __init__(self):
            super().__init__(title=TITLE)
            self.set_default_size(980, 740)
            self.set_icon_name("computer")
            self.busy = False
            self.finished = False

            provider = Gtk.CssProvider()
            provider.load_from_data(WIZARD_CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            self.overlay = overlay = Gtk.Overlay()
            overlay.add(Background())
            self.add(overlay)

            # O diálogo começa centralizado; arrastar a barra de título o move dentro da janela.
            self.dialog = dialog = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            dialog.set_size_request(610, 570)   # fixo: não muda de tamanho entre as páginas
            dialog.get_style_context().add_class("w2k-setup-dialog")
            overlay.add_overlay(dialog)
            self.dialog_pos = None              # None = centralizado
            self.drag = None
            overlay.connect("get-child-position", self.place_dialog)

            caption = Gtk.Box(spacing=4)
            caption.get_style_context().add_class("w2k-setup-caption")
            caption.pack_start(Gtk.Image.new_from_icon_name("computer", Gtk.IconSize.MENU),
                               False, False, 0)
            caption.pack_start(Gtk.Label(label=TITLE, xalign=0), True, True, 0)
            handle = Gtk.EventBox()
            handle.add(caption)
            handle.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                              | Gdk.EventMask.BUTTON1_MOTION_MASK)
            handle.connect("button-press-event", self.on_drag_start)
            handle.connect("motion-notify-event", self.on_drag_motion)
            handle.connect("button-release-event", self.on_drag_end)
            dialog.pack_start(handle, False, False, 0)

            banner = Gtk.EventBox()
            banner.get_style_context().add_class("w2k-setup-banner")
            logo = Gtk.Image.new_from_file(str(SETUP_DIR / "banner.png"))
            logo.set_halign(Gtk.Align.START)
            banner.add(logo)
            dialog.pack_start(banner, False, False, 0)
            dialog.pack_start(Gtk.Separator(), False, False, 0)

            self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
            self.stack.set_size_request(-1, 300)
            for m in ("start", "end", "top", "bottom"):
                getattr(self.stack, f"set_margin_{m}")(16 if m in ("start", "end") else 12)
            dialog.pack_start(self.stack, True, True, 0)
            dialog.pack_start(Gtk.Separator(), False, False, 0)

            buttons = Gtk.Box(spacing=6, margin=8, halign=Gtk.Align.END)
            self.back_btn = Gtk.Button.new_with_mnemonic("< _Voltar")
            self.next_btn = Gtk.Button.new_with_mnemonic("_Avançar >")
            self.cancel_btn = Gtk.Button.new_with_mnemonic("Cancelar")
            for b in (self.back_btn, self.next_btn, self.cancel_btn):
                b.set_size_request(80, -1)
            self.next_btn.set_can_default(True)
            self.back_btn.connect("clicked", lambda _b: self.go(-1))
            self.next_btn.connect("clicked", lambda _b: self.go(+1))
            self.cancel_btn.connect("clicked", lambda _b: self.close())
            buttons.pack_start(self.back_btn, False, False, 0)
            buttons.pack_start(self.next_btn, False, False, 6)
            buttons.pack_start(self.cancel_btn, False, False, 0)
            dialog.pack_start(buttons, False, False, 0)

            self.buffer = Gtk.TextBuffer()
            self.end_mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
            self.views = []

            self.pages = ["welcome", "type", "components", "ready", "progress", "finish"]
            self.build_welcome()
            self.build_type()
            self.build_components()
            self.build_ready()
            self.build_progress()
            self.build_finish()
            self.index = 0
            self.connect("delete-event", self.on_delete)
            self.show_page()

        # Posição do diálogo ------------------------------------------------

        def place_dialog(self, overlay, child, rect):
            if child is not self.dialog:
                return False
            width, height = overlay.get_allocated_width(), overlay.get_allocated_height()
            nat = child.get_preferred_size()[1]
            w, h = min(nat.width, width), min(nat.height, height)
            if self.dialog_pos is None:
                x, y = (width - w) // 2, (height - h) // 2
            else:   # mantém o diálogo inteiro dentro da janela, inclusive ao redimensioná-la
                x = min(max(self.dialog_pos[0], 0), width - w)
                y = min(max(self.dialog_pos[1], 0), height - h)
            self.shown_pos = (x, y)
            rect.x, rect.y, rect.width, rect.height = x, y, w, h
            return True

        def on_drag_start(self, _widget, event):
            if event.button == 1:
                self.drag = (event.x_root, event.y_root, *self.shown_pos)
            return True

        def on_drag_motion(self, _widget, event):
            if self.drag:
                x0, y0, dx, dy = self.drag
                self.dialog_pos = (int(dx + event.x_root - x0), int(dy + event.y_root - y0))
                self.overlay.queue_allocate()
            return True

        def on_drag_end(self, _widget, event):
            if event.button == 1 and self.drag:
                # Guarda a posição já limitada à janela, para não "grudar" na borda depois
                self.dialog_pos = self.shown_pos
                self.drag = None
            return True

        # Páginas -----------------------------------------------------------

        def build_welcome(self):
            box = page("Bem-vindo ao Assistente de instalação do tema Windows 2000", big=True)
            box.pack_start(text(
                "Este assistente instala o visual do Windows 2000 no XFCE, no MATE e no Cinnamon: "
                "janelas, ícones, cursores, sons, papel de parede, menu Iniciar e barra de tarefas.\n\n"
                "Você escolhe os componentes e se a instalação vale só para você ou para "
                "todos os usuários deste computador. O assistente também remove o tema e "
                "devolve as configurações anteriores.\n\n"
                "Para continuar, clique em Avançar."), False, False, 8)
            self.stack.add_named(box, "welcome")

        def build_type(self):
            box = page("Tipo de instalação", "Escolha o que fazer e para quem.")
            frame = Gtk.Frame(label="Operação")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, border_width=8)
            self.op_install = Gtk.RadioButton.new_with_mnemonic(None, "_Instalar ou atualizar componentes")
            self.op_remove = Gtk.RadioButton.new_with_mnemonic_from_widget(self.op_install,
                                                                           "_Remover componentes")
            inner.pack_start(self.op_install, False, False, 0)
            inner.pack_start(self.op_remove, False, False, 0)
            frame.add(inner)
            box.pack_start(frame, False, False, 4)

            frame = Gtk.Frame(label="Instalar para")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, border_width=8)
            self.mode_user = Gtk.RadioButton.new_with_mnemonic(None, "_Somente para mim")
            self.mode_system = Gtk.RadioButton.new_with_mnemonic_from_widget(
                self.mode_user, "_Todos os usuários deste computador")
            inner.pack_start(self.mode_user, False, False, 0)
            inner.pack_start(self.mode_system, False, False, 0)
            note = text("A instalação para todos os usuários copia os arquivos para /usr/share "
                        "e pede a senha de administrador.")
            note.set_margin_start(24)
            inner.pack_start(note, False, False, 0)
            frame.add(inner)
            box.pack_start(frame, False, False, 4)
            self.stack.add_named(box, "type")

        def build_components(self):
            self.comp_box = page("Componentes", "")
            self.store = Gtk.ListStore(bool, str, bool, bool, str, str)
            view = Gtk.TreeView(model=self.store, headers_visible=True)
            col = Gtk.TreeViewColumn("Componente")
            toggle = Gtk.CellRendererToggle()
            toggle.connect("toggled", self.on_toggle, 0)
            col.pack_start(toggle, False)
            col.add_attribute(toggle, "active", 0)
            label = Gtk.CellRendererText()
            col.pack_start(label, True)
            col.add_attribute(label, "text", 1)
            col.set_expand(True)
            view.append_column(col)
            self.apply_toggle = Gtk.CellRendererToggle()
            self.apply_toggle.connect("toggled", self.on_toggle, 2)
            self.apply_col = Gtk.TreeViewColumn("Aplicar", self.apply_toggle, active=2, visible=3,
                                                sensitive=0, activatable=0)
            view.append_column(self.apply_col)
            view.append_column(Gtk.TreeViewColumn("Situação", Gtk.CellRendererText(), text=4))
            scroll = Gtk.ScrolledWindow(min_content_height=176)
            scroll.set_shadow_type(Gtk.ShadowType.IN)
            scroll.add(view)
            self.comp_box.pack_start(scroll, True, True, 0)

            frame = Gtk.Frame(label="Descrição")
            self.desc = text("")
            self.desc.set_margin_start(8)
            self.desc.set_margin_end(8)
            self.desc.set_margin_bottom(6)
            self.desc.set_size_request(-1, 36)
            self.desc.set_valign(Gtk.Align.START)
            frame.add(self.desc)
            self.comp_box.pack_start(frame, False, False, 0)
            view.get_selection().connect("changed", self.on_select)
            self.comp_view = view
            for comp in COMPONENTS:
                self.store.append([False, COMPONENTS[comp]["label"], False,
                                   comp not in SETTINGS_ONLY, "", comp])
            self.stack.add_named(self.comp_box, "components")

        def build_ready(self):
            self.ready_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.ready_title = bold("")
            self.ready_text = text("")
            self.ready_list = text("")
            self.ready_list.set_margin_start(16)
            self.ready_warn = text("")
            for w in (self.ready_title, self.ready_text, self.ready_list, self.ready_warn):
                self.ready_box.pack_start(w, False, False, 0)
            self.stack.add_named(self.ready_box, "ready")

        def log_view(self):
            view = Gtk.TextView(buffer=self.buffer, editable=False, cursor_visible=False,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
            scroll = Gtk.ScrolledWindow(min_content_height=110)
            scroll.set_shadow_type(Gtk.ShadowType.IN)
            scroll.add(view)
            self.views.append(view)
            return scroll

        def build_progress(self):
            self.progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.progress_title = bold("")
            self.progress_box.pack_start(self.progress_title, False, False, 0)
            self.status = text("Preparando...")
            self.status.set_ellipsize(Pango.EllipsizeMode.END)
            self.status.set_line_wrap(False)
            self.progress_box.pack_start(self.status, False, False, 8)
            self.progress = Gtk.ProgressBar()
            self.progress_box.pack_start(self.progress, False, False, 0)
            exp = Gtk.Expander(label="_Detalhes", use_underline=True)
            exp.add(self.log_view())
            self.progress_box.pack_start(exp, True, True, 8)
            self.stack.add_named(self.progress_box, "progress")

        def build_finish(self):
            self.finish_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.finish_title = bold("", "large")
            self.finish_text = text("")
            self.finish_box.pack_start(self.finish_title, False, False, 0)
            self.finish_box.pack_start(self.finish_text, False, False, 8)
            # Como no Setup do Windows 2000: reiniciar agora ou depois.
            self.reboot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.reboot_now = Gtk.RadioButton.new_with_mnemonic(
                None, "_Sim, desejo reiniciar o computador agora.")
            self.reboot_later = Gtk.RadioButton.new_with_mnemonic_from_widget(
                self.reboot_now, "_Não, reiniciarei o computador mais tarde.")
            self.reboot_later.set_active(True)
            for w in (self.reboot_now, self.reboot_later):
                self.reboot_box.pack_start(w, False, False, 0)
            self.finish_box.pack_start(self.reboot_box, False, False, 0)
            self.finish_exp = Gtk.Expander(label="_Detalhes", use_underline=True)
            self.finish_exp.add(self.log_view())
            self.finish_box.pack_start(self.finish_exp, True, True, 0)
            self.stack.add_named(self.finish_box, "finish")

        # Estado ------------------------------------------------------------

        @property
        def removing(self):
            return self.op_remove.get_active()

        @property
        def mode(self):
            return "system" if self.mode_system.get_active() else "user"

        def selected(self, col=0):
            return [row[5] for row in self.store if row[col]]

        def fill_components(self):
            removing = self.removing
            for row in self.store:
                comp = row[5]
                if removing:
                    if comp == "panel":
                        row[0] = (STATE_DIR / "panel-backup.tar.bz2").exists()
                    elif comp == "mate-panel":
                        row[0] = MATE_PANEL_BACKUP.exists()
                    elif comp == "terminal":
                        row[0] = terminal_applied()
                    else:
                        row[0] = installed_in(comp, self.mode)
                else:
                    row[0] = comp not in DEFAULT_OFF
                    row[2] = comp not in SETTINGS_ONLY and comp not in DEFAULT_OFF
                row[4] = status_text(comp)
            self.apply_col.set_visible(not removing)
            subtitle = self.comp_box.get_children()[1]
            subtitle.set_text(
                "Marque os componentes a remover. As configurações anteriores voltam."
                if removing else
                "Marque os componentes a instalar. \"Aplicar\" ativa o componente no XFCE, "
                "no MATE ou no Cinnamon logo após a cópia.")
            self.comp_view.get_selection().select_path(Gtk.TreePath.new_first())

        def on_toggle(self, _cell, path, col):
            self.store[path][col] = not self.store[path][col]
            # Só um esquema de sons pode ser aplicado: marcar "Aplicar" num desmarca o outro.
            comp = self.store[path][5]
            if col == 2 and self.store[path][col] and comp in SOUND_THEMES:
                for row in self.store:
                    if row[5] in SOUND_THEMES and row[5] != comp:
                        row[2] = False
            self.update_buttons()

        def on_select(self, selection):
            model, it = selection.get_selected()
            if it:
                self.desc.set_text(DESCRIPTIONS.get(model[it][5], ""))

        def fill_ready(self):
            removing = self.removing
            comps = self.selected()
            names = [COMPONENTS[c]["label"] for c in comps]
            where = ("todos os usuários (/usr/share)" if self.mode == "system"
                     else "somente para você (pasta pessoal)")
            if removing:
                self.ready_title.set_markup("<b>Pronto para remover</b>")
                self.ready_text.set_text(f"O assistente vai remover, da instalação para {where}:")
            else:
                self.ready_title.set_markup("<b>Pronto para instalar</b>")
                self.ready_text.set_text(f"O assistente vai instalar para {where}:")
            apply = set(self.selected(2))
            self.ready_list.set_text("\n".join(
                f"•  {n}" + ("  (aplicar)" if c in apply and not removing else "")
                for c, n in zip(comps, names)))
            warn = []
            if "panel" in comps:
                warn.append("O painel atual do XFCE será substituído; um backup é salvo."
                            if not removing else
                            "O painel do XFCE salvo antes da instalação será restaurado.")
            if "mate-panel" in comps:
                warn.append("O painel atual do MATE será substituído; um backup é salvo."
                            if not removing else
                            "O painel do MATE salvo antes da instalação será restaurado.")
            if "terminal" in comps:
                warn.append("As cores do MATE Terminal e do Xfce Terminal serão trocadas."
                            if not removing else
                            "As cores anteriores dos terminais serão restauradas.")
            if self.mode == "system":
                warn.append("Será pedida a senha de administrador.")
            warn.append(f"Clique em {'Remover' if removing else 'Instalar'} para começar, "
                        "ou em Voltar para rever as opções.")
            self.ready_warn.set_text("\n\n".join(warn))

        # Navegação ---------------------------------------------------------

        def show_page(self):
            name = self.pages[self.index]
            self.stack.set_visible_child_name(name)
            self.update_buttons()

        def update_buttons(self):
            name = self.pages[self.index]
            self.back_btn.set_sensitive(name in ("type", "components", "ready"))
            self.cancel_btn.set_sensitive(name not in ("progress", "finish"))
            self.next_btn.set_sensitive(name != "progress"
                                        and (name != "components" or bool(self.selected())))
            label = {"ready": "_Remover" if self.removing else "_Instalar",
                     "finish": "_Concluir"}.get(name, "_Avançar >")
            self.next_btn.set_label(label)
            self.next_btn.grab_default()

        def go(self, step):
            name = self.pages[self.index]
            if name == "finish":
                if self.reboot_box.get_visible() and self.reboot_now.get_active():
                    subprocess.Popen(["systemctl", "reboot"], env=CHILD_ENV, start_new_session=True)
                self.destroy()
                return
            if step > 0 and name == "type":
                self.fill_components()
            if step > 0 and name == "components":
                self.fill_ready()
            self.index += step
            self.show_page()
            if self.pages[self.index] == "progress":
                self.start()

        def on_delete(self, *_):
            if self.busy:
                return True
            if self.finished or self.pages[self.index] == "finish":
                return False
            d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.YES_NO, text=TITLE,
                                  secondary_text="Tem certeza de que deseja cancelar a instalação?")
            ok = d.run() == Gtk.ResponseType.YES
            d.destroy()
            return not ok

        # Execução ----------------------------------------------------------

        def log(self, msg):
            def add():
                self.buffer.insert(self.buffer.get_end_iter(), msg + "\n")
                for v in self.views:
                    v.scroll_mark_onscreen(self.end_mark)
                if msg and not msg.startswith(" "):
                    self.status.set_text(msg)
            GLib.idle_add(add)

        def set_progress(self, fraction):
            GLib.idle_add(self.progress.set_fraction, fraction)

        def start(self):
            removing, mode = self.removing, self.mode
            comps, apply = self.selected(), self.selected(2)
            self.progress_title.set_markup(
                f"<b>{'Removendo' if removing else 'Instalando'} o tema Windows 2000</b>")
            self.busy = True
            self.update_buttons()

            def work():
                try:
                    if removing:
                        do_uninstall(comps, mode, self.log, self.set_progress)
                    else:
                        do_install(comps, mode, apply, self.log, self.set_progress)
                    error = None
                except Exception as e:  # mostra qualquer falha na página final
                    self.log(f"ERRO: {e}")
                    error = str(e)
                GLib.idle_add(self.done, removing, error)

            threading.Thread(target=work, daemon=True).start()

        def done(self, removing, error):
            self.busy = False
            self.finished = True
            if error:
                self.finish_title.set_markup("<span weight='bold' size='large'>"
                                             "O assistente não foi concluído</span>")
                self.finish_text.set_text(f"Ocorreu um erro: {error}\n\nVeja os detalhes abaixo. "
                                          "Nenhuma configuração foi aplicada depois do erro.")
                self.finish_exp.set_expanded(True)
                self.reboot_box.hide()
            else:
                verb = "removido" if removing else "instalado"
                self.finish_title.set_markup("<span weight='bold' size='large'>Concluindo o Assistente "
                                             "de instalação do tema Windows 2000</span>")
                extra = ("" if removing else
                         "\n\nAlguns aplicativos abertos só mudam de aparência depois de reabertos. "
                         "Os cursores podem exigir sair e entrar de novo na sessão.")
                self.finish_text.set_text(f"O tema Windows 2000 foi {verb} com êxito.{extra}"
                                          "\n\nPara ver todas as mudanças, reinicie o computador. "
                                          "Para fechar o assistente, clique em Concluir.")
                self.reboot_box.show_all()
            self.index = self.pages.index("finish")
            self.show_page()

    win = Wizard()
    win.connect("destroy", Gtk.main_quit)
    # Encerrar por sinal (Ctrl+C, kill) também sai pelo laço do GTK, para o atexit
    # apagar a pasta temporária do tema.
    # GLibUnix.signal_add só existe no GLib 2.84+; em versões anteriores o módulo GLibUnix
    # pode existir sem ela (Debian/Ubuntu), e o nome antigo é GLib.unix_signal_add.
    signal_add = None
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        signal_add = getattr(GLibUnix, "signal_add", None)
    except (ValueError, ImportError):      # PyGObject antigo
        pass
    if signal_add is None:
        signal_add = GLib.unix_signal_add
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal_add(GLib.PRIORITY_DEFAULT, sig, Gtk.main_quit)
    win.show_all()
    Gtk.main()


# --------------------------------------------------------------------------

def parse_list(value):
    if value == "all":
        return [c for c in COMPONENTS if c not in DEFAULT_OFF]
    comps = [c.strip() for c in value.split(",") if c.strip()]
    bad = [c for c in comps if c not in COMPONENTS]
    if bad:
        raise argparse.ArgumentTypeError(f"componente desconhecido: {', '.join(bad)}"
                                          f" (use: {', '.join(COMPONENTS)})")
    return comps


def main():
    ap = argparse.ArgumentParser(description="Instalador do tema Windows 2000 para XFCE, MATE e Cinnamon.")
    ap.add_argument("--list", action="store_true", help="lista os componentes e onde estão instalados")
    ap.add_argument("--install", type=parse_list, metavar="LISTA",
                    help=f"'all' ou componentes separados por vírgula: {','.join(COMPONENTS)}")
    ap.add_argument("--uninstall", type=parse_list, metavar="LISTA", help="idem, para remover")
    ap.add_argument("--system", action="store_true", help="instala em /usr/share (pede senha pelo pkexec)")
    ap.add_argument("--no-apply", action="store_true", help="só copia, não ativa no XFCE nem no Cinnamon")
    ap.add_argument("--with-panel", action="store_true", help="também carrega o painel Windows 2000")
    ap.add_argument("--root", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.root:
        root_main(args.root[0], args.root[1:])
        return

    mode = "system" if args.system else "user"
    try:
        if args.list:
            for comp in COMPONENTS:
                print(f"{comp:10} {COMPONENTS[comp]['label']:48} {status_text(comp)}")
        elif args.install:
            comps = args.install + (["panel"] if args.with_panel and "panel" not in args.install else [])
            do_install(comps, mode, [] if args.no_apply else comps, print)
        elif args.uninstall:
            do_uninstall(args.uninstall, mode, print)
        elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            gui_main()
        else:
            ap.print_help()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as e:
        sys.exit(f"Erro: {e}")


if __name__ == "__main__":
    main()
