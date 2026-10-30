#!/usr/bin/env python3
"""Testador do tema de sons Win2k.

Lista os eventos do tema e toca cada um pelo libcanberra (canberra-gtk-play),
do mesmo jeito que o GTK e o xfce4-notifyd tocam: respeita o tema de sons
selecionado e a opcao "Habilitar sons de eventos".

Uso: python3 tools/win2k-sounds.py
"""

import os
import shutil

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

THEME = "Win2k"
THEME_DIRS = [
    os.path.join(GLib.get_user_data_dir(), "sounds", THEME),
    *(os.path.join(d, "sounds", THEME) for d in GLib.get_system_data_dirs()),
]

# (evento freedesktop, som original do Windows 2000, quando toca no XFCE)
EVENTS = [
    ("bell", "Ding (Padrão)", "Bipe do sistema"),
    ("bell-terminal", "Ding (Padrão)", "Bipe do terminal"),
    ("bell-window-system", "Ding (Padrão)", "Bipe de janela"),
    ("dialog-error", "Chord (Parada crítica)", "Diálogo de erro"),
    ("dialog-warning", "Chord (Exclamação)", "Diálogo de aviso"),
    ("dialog-question", "Chord (Pergunta)", "Diálogo de pergunta"),
    ("dialog-information", "Chord (Asterisco)", "Diálogo de informação"),
    ("message-new-email", "Notify (Novo e-mail)", "Clientes de e-mail"),
    ("trash-empty", "Recycle (Esvaziar Lixeira)", "Não é disparado pelo Thunar"),
    ("desktop-login", "Windows Logon Sound", "Ao entrar no XFCE"),
    ("desktop-logout", "Windows Logoff Sound", "Iniciar > Desligar..."),
]


def theme_file(event):
    """Caminho do som no tema Win2k instalado, ou None."""
    for d in THEME_DIRS:
        for ext in ("wav", "oga", "ogg"):
            path = os.path.join(d, "stereo", f"{event}.{ext}")
            if os.path.exists(path):
                return path
    return None


def xfconf_get(prop):
    if not shutil.which("xfconf-query"):
        return None
    try:
        ok, out, _err, status = GLib.spawn_sync(
            None, ["xfconf-query", "-c", "xsettings", "-p", prop],
            None, GLib.SpawnFlags.SEARCH_PATH, None)
    except GLib.Error:
        return None
    return out.decode().strip() if ok and status == 0 else None


def xfconf_set(prop, kind, value):
    GLib.spawn_sync(
        None, ["xfconf-query", "-c", "xsettings", "-p", prop, "-n", "-t", kind, "-s", value],
        None, GLib.SpawnFlags.SEARCH_PATH, None)


class SoundTester(Gtk.Window):
    def __init__(self):
        super().__init__(title="Sons do Windows 2000")
        self.set_default_size(760, -1)
        self.set_border_width(8)
        self.set_icon_name("preferences-desktop-sound")
        self.proc = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(box)

        # Situacao atual: tema de sons e sons de eventos
        frame = Gtk.Frame(label="Configuração")
        grid = Gtk.Grid(column_spacing=8, row_spacing=6, border_width=8)
        frame.add(grid)
        box.pack_start(frame, False, False, 0)

        grid.attach(Gtk.Label(label="Tema de sons:", xalign=0), 0, 0, 1, 1)
        self.theme_label = Gtk.Label(xalign=0, hexpand=True)
        grid.attach(self.theme_label, 1, 0, 1, 1)
        self.use_theme = Gtk.Button(label=f"Usar {THEME}")
        self.use_theme.connect("clicked", self.on_use_theme)
        grid.attach(self.use_theme, 2, 0, 1, 1)

        self.enable = Gtk.CheckButton(label="Habilitar sons de eventos")
        self.enable_handler = self.enable.connect("toggled", self.on_enable_toggled)
        grid.attach(self.enable, 0, 1, 3, 1)

        # Lista de eventos
        frame = Gtk.Frame(label="Eventos")
        box.pack_start(frame, True, True, 0)
        self.store = Gtk.ListStore(str, str, str, str)
        for event, original, when in EVENTS:
            self.store.append([event, original, when, ""])
        self.view = Gtk.TreeView(model=self.store)
        for i, title in enumerate(("Evento", "Som do Windows 2000", "Quando toca", "Arquivo")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            self.view.append_column(col)
        self.view.connect("row-activated", lambda *_: self.play())
        self.view.get_selection().select_path(Gtk.TreePath.new_first())
        scroll = Gtk.ScrolledWindow(border_width=4)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_min_content_height(260)
        scroll.add(self.view)
        frame.add(scroll)

        # Botoes
        buttons = Gtk.ButtonBox(spacing=6, layout_style=Gtk.ButtonBoxStyle.END)
        box.pack_start(buttons, False, False, 0)
        for label, callback in (("_Tocar", self.play),
                                ("_Parar", self.stop),
                                ("Tocar via _notificação", self.notify),
                                ("_Fechar", self.close)):
            b = Gtk.Button.new_with_mnemonic(label)
            b.connect("clicked", lambda _b, cb=callback: cb())
            buttons.add(b)

        self.status = Gtk.Statusbar()
        box.pack_start(self.status, False, False, 0)

        self.refresh()
        self.say("Duplo clique num evento, ou selecione e clique em Tocar.")

    # Situacao -------------------------------------------------------------

    def refresh(self):
        settings = Gtk.Settings.get_default()
        theme = settings.props.gtk_sound_theme_name or "?"
        self.theme_label.set_text(theme)
        self.use_theme.set_sensitive(theme != THEME)
        with self.enable.handler_block(self.enable_handler):
            self.enable.set_active(settings.props.gtk_enable_event_sounds)
        for row in self.store:
            path = theme_file(row[0])
            row[3] = os.path.basename(os.path.realpath(path)) if path else "(não instalado)"

    def on_use_theme(self, _button):
        xfconf_set("/Net/SoundThemeName", "string", THEME)
        GLib.timeout_add(300, self.refresh_once)

    def on_enable_toggled(self, check):
        xfconf_set("/Net/EnableEventSounds", "bool", "true" if check.get_active() else "false")
        GLib.timeout_add(300, self.refresh_once)

    def refresh_once(self):
        self.refresh()
        return GLib.SOURCE_REMOVE

    def say(self, text):
        self.status.pop(0)
        self.status.push(0, text)

    def selected_event(self):
        model, it = self.view.get_selection().get_selected()
        return model[it][0] if it else None

    # Acoes ----------------------------------------------------------------

    def play(self):
        event = self.selected_event()
        if not event:
            return
        if not shutil.which("canberra-gtk-play"):
            self.say("canberra-gtk-play não encontrado (pacote libcanberra).")
            return
        self.stop()
        self.say(f"Tocando {event}...")
        self.proc = Gio.Subprocess.new(
            ["canberra-gtk-play", "-i", event, "-d", "Teste de sons Win2k"],
            Gio.SubprocessFlags.STDERR_PIPE)
        self.proc.communicate_utf8_async(None, None, self.on_played, event)

    def on_played(self, proc, result, event):
        _ok, _out, err = proc.communicate_utf8_finish(result)
        if proc is not self.proc:
            return
        self.proc = None
        if proc.get_if_exited() and proc.get_exit_status() == 0:
            self.say(f"{event}: tocado.")
        elif not proc.get_if_exited():
            self.say(f"{event}: interrompido.")
        else:
            msg = (err or "").strip().replace("Failed to play sound: ", "")
            hints = {
                "Sound disabled": "sons de eventos desligados",
                "Not found": "o evento não existe no tema atual",
                "File or data not found": "o evento não existe no tema atual",
            }
            self.say(f"{event}: não tocou ({hints.get(msg, msg or 'erro')}).")

    def stop(self):
        if self.proc:
            self.proc.force_exit()

    def notify(self):
        event = self.selected_event()
        if not event:
            return
        if not shutil.which("notify-send"):
            self.say("notify-send não encontrado (pacote libnotify).")
            return
        GLib.spawn_async(
            ["notify-send", "-a", "Sons do Windows 2000", "-i", "preferences-desktop-sound",
             "-h", f"string:sound-name:{event}",
             "Teste de som", f"Notificação com o som \"{event}\""],
            flags=GLib.SpawnFlags.SEARCH_PATH)
        self.say(f"Notificação enviada com sound-name={event}.")


def main():
    win = SoundTester()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
