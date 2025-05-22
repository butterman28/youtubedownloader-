#!/usr/bin/env python3
# myscript.py

# Copyright (C) 2025 Alegbeleye Ithamar Ibukunoluwade
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


import gi
import subprocess
import threading
import os
import re

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib


class YTDLPWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("yt-dlp GTK Downloader")
        self.set_default_size(600, 450)
        #self.set_decorated(True)
        self.set_deletable(True)
        self.set_resizable(True)
        self.set_decorated(True)  # Make sure window is movable and has decorations

        self.output_folder = os.path.expanduser("~/Downloads")
        self.available_formats = []

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_top=10,
            margin_bottom=10,
            margin_start=10,
            margin_end=10,
        )
        self.set_content(box)

        # URL Entry
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Enter YouTube URL")
        box.append(self.entry)

        # Fetch Formats Button
        self.fetch_button = Gtk.Button(label="Fetch Formats")
        self.fetch_button.connect("clicked", self.on_fetch_formats)
        box.append(self.fetch_button)

        # Format dropdown (empty initially)
        box.append(Gtk.Label(label="Select format:"))
        self.format_combo = Gtk.DropDown.new()
        box.append(self.format_combo)

        # Output folder chooser
        self.folder_button = Gtk.Button(label=f"Output folder: {self.output_folder}")
        self.folder_button.connect("clicked", self.choose_folder)
        box.append(self.folder_button)

        # Progress bar
        self.progress = Gtk.ProgressBar(show_text=True)
        box.append(self.progress)

        # Output TextView for logs
        self.output = Gtk.TextView(editable=False)
        self.output_buffer = self.output.get_buffer()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self.output)
        scrolled.set_vexpand(True)
        box.append(scrolled)

        # Download button - disabled until formats fetched
        # Download & Close Button Row
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)

        self.button = Gtk.Button(label="Download")
        self.button.set_sensitive(False)
        self.button.connect("clicked", self.on_click)
        button_box.append(self.button)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda btn: self.close())
        button_box.append(close_button)

        box.append(button_box)


    def choose_folder(self, _):
        dialog = Gtk.FileChooserNative.new(
            title="Select Output Folder",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.set_modal(True)
        dialog.connect("response", self.on_folder_selected)
        dialog.show()

    def on_folder_selected(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            self.output_folder = dialog.get_file().get_path()
            self.folder_button.set_label(f"Output folder: {self.output_folder}")
        dialog.destroy()

    def on_fetch_formats(self, button):
        url = self.entry.get_text()
        if not url.strip():
            self._append_text("Enter a URL before fetching formats.\n")
            return
        self._append_text("Fetching formats...\n")
        self.fetch_button.set_sensitive(False)
        self.button.set_sensitive(False)
        threading.Thread(
            target=self.fetch_formats_thread, args=(url,), daemon=True
        ).start()

    def fetch_formats_thread(self, url):
        cmd = ["yt-dlp", "-F", url]
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            GLib.idle_add(self._append_text, f"Failed to fetch formats:\n{stderr}\n")
            GLib.idle_add(self.fetch_button.set_sensitive, True)
            return

        formats = self.parse_formats(stdout)
        if not formats:
            GLib.idle_add(self._append_text, "No formats found.\n")
            GLib.idle_add(self.fetch_button.set_sensitive, True)
            return

        GLib.idle_add(self.populate_format_combo, formats)
        GLib.idle_add(self._append_text, f"Found {len(formats)} video formats.\n")
        GLib.idle_add(self.fetch_button.set_sensitive, True)
        GLib.idle_add(self.button.set_sensitive, True)  # enable download

    def parse_formats(self, formats_text):
        # Parses yt-dlp -F output to extract video format codes and descriptions (exclude audio-only)
        formats = []
        lines = formats_text.splitlines()
        for line in lines:
            # Example line:
            # 137          mp4        1080p     4628k , avc1.640028, 30fps, video only, 102.75MiB
            m = re.match(r"^\s*(\d+)\s+(\S+)\s+(.+)$", line)
            if m:
                code = m.group(1)
                ext = m.group(2)
                desc = m.group(3).strip()
                if "audio only" in desc.lower():
                    continue  # skip audio-only for this dropdown
                # Format display: "code - ext - description"
                formats.append((code, f"{code} - {ext} - {desc}"))
        return formats

    def populate_format_combo(self, formats):
        self.available_formats = formats
        model = Gtk.StringList.new([desc for _, desc in formats])
        self.format_combo.set_model(model)
        self.format_combo.set_selected(0)

    def on_click(self, button):
        url = self.entry.get_text().strip()
        if not url:
            self._append_text("Please enter a valid URL.\n")
            return
        idx = self.format_combo.get_selected()
        if idx < 0 or idx >= len(self.available_formats):
            self._append_text("Please fetch and select a format first.\n")
            return
        fmt_code = self.available_formats[idx][0]
        output_template = os.path.join(self.output_folder, "%(title)s.%(ext)s")

        self._append_text(f"Starting download: format {fmt_code}\n")
        self.progress.set_fraction(0.0)
        self.progress.set_text("0.0%")
        self.button.set_sensitive(False)
        self.fetch_button.set_sensitive(False)
        threading.Thread(
            target=self.download_video,
            args=(url, fmt_code, output_template),
            daemon=True,
        ).start()

    def download_video(self, url, fmt, out_path):
        cmd = [
            "yt-dlp",
            "-f",
            fmt,
            "-o",
            out_path,
            "--newline",  # force line-by-line progress output for parsing
            url,  # <-- add the URL here!
        ]
        print(cmd)
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        for line in process.stdout:
            GLib.idle_add(self._append_text, line)
            percent = self.extract_percent(line)
            if percent is not None:
                GLib.idle_add(self.progress.set_fraction, percent / 100.0)
                GLib.idle_add(self.progress.set_text, f"{percent:.1f}%")

        process.wait()
        GLib.idle_add(self._append_text, "\nDownload finished.\n")
        GLib.idle_add(self.progress.set_fraction, 0.0)
        GLib.idle_add(self.progress.set_text, "")
        GLib.idle_add(self.button.set_sensitive, True)
        GLib.idle_add(self.fetch_button.set_sensitive, True)

    def extract_percent(self, line):
        # yt-dlp progress line looks like: [download]  42.3%
        m = re.search(r"(\d{1,3}\.\d)%", line)
        if m:
            try:
                return float(m.group(1))
            except:
                return None
        # alternative: look for [download]  42.3%
        m2 = re.search(r"\[download\]\s+(\d{1,3}\.\d)%", line)
        if m2:
            try:
                return float(m2.group(1))
            except:
                return None
        return None

    def _append_text(self, text):
        end_iter = self.output_buffer.get_end_iter()
        self.output_buffer.insert(end_iter, text)


class YTDLPApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.example.ytdlp")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = YTDLPWindow(self)
        win.present()


app = YTDLPApp()
app.run()
