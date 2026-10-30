#!/usr/bin/env python3
"""Start menu "Log Off..." for the Windows 2000 theme.

Shows the Windows 2000 "Log Off Windows" confirmation. On "Yes" it plays the
sound theme's logout sound (only when event sounds are enabled) and then ends
the Xfce session; xfce4-session still asks open applications to save.
"""

import locale
import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

PT = (locale.getlocale(locale.LC_MESSAGES)[0] or os.environ.get("LANG", "")).startswith("pt")

TITLE = "Fazer logoff do Windows" if PT else "Log Off Windows"
QUESTION = "Tem certeza de que deseja fazer logoff?" if PT else "Are you sure you want to log off?"
YES, NO = ("_Sim", "_Não") if PT else ("_Yes", "_No")


def main():
    dialog = Gtk.Dialog(title=TITLE)
    dialog.set_resizable(False)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.set_keep_above(True)
    dialog.set_icon_name("system-log-out")
    dialog.add_button(YES, Gtk.ResponseType.YES)
    dialog.add_button(NO, Gtk.ResponseType.NO)
    dialog.set_default_response(Gtk.ResponseType.YES)

    box = Gtk.Box(spacing=16, border_width=12)
    box.pack_start(Gtk.Image.new_from_icon_name("system-log-out", Gtk.IconSize.DIALOG), False, False, 0)
    box.pack_start(Gtk.Label(label=QUESTION, xalign=0), True, True, 0)
    dialog.get_content_area().add(box)
    dialog.show_all()

    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.YES:
        return

    # Windows plays the logoff sound before the session ends: wait for it
    # (returns at once when event sounds are disabled).
    subprocess.run(["canberra-gtk-play", "-i", "desktop-logout", "-d", "Logoff"],
                   stderr=subprocess.DEVNULL, check=False)
    subprocess.run(["xfce4-session-logout", "--logout"], check=False)


if __name__ == "__main__":
    main()
