import gi
import subprocess
import threading
import os
import re

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib


class DownloadRow(Gtk.Box):
    def __init__(self, url, fmt_code, output_folder, playlist_mode=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.textview = Gtk.TextView(editable=False)
        self.buffer = self.textview.get_buffer()

        self.append(Gtk.Label(label=f"Downloading: {url}"))
        self.append(self.progress)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.textview)
        scroll.set_vexpand(True)
        self.append(scroll)

        threading.Thread(
            target=self.download_video,
            args=(url, fmt_code, output_folder, playlist_mode),
            daemon=True,
        ).start()

    def append_text(self, text):
        end = self.buffer.get_end_iter()
        self.buffer.insert(end, text)

    def extract_percent(self, line):
        match = re.search(r"(\d{1,3}\.\d)%", line)
        return float(match.group(1)) if match else None

    def download_video(self, url, fmt, output_folder, playlist_mode):
        output_template = os.path.join(output_folder, "%(title)s.%(ext)s")
        cmd = ["yt-dlp", "-f", fmt, "-o", output_template, "--newline"]
        if playlist_mode:
            cmd.append("--yes-playlist")
        else:
            cmd.append("--no-playlist")
        cmd.append(url)

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        for line in process.stdout:
            GLib.idle_add(self.append_text, line)
            percent = self.extract_percent(line)
            if percent is not None:
                GLib.idle_add(self.progress.set_fraction, percent / 100.0)
                GLib.idle_add(self.progress.set_text, f"{percent:.1f}%")

        process.wait()
        GLib.idle_add(self.append_text, "\nDownload finished.\n")


class YTDLPWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("yt-dlp GTK Downloader")
        self.set_default_size(700, 600)

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

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Enter YouTube URL")
        box.append(self.entry)

        self.fetch_button = Gtk.Button(label="Fetch Formats")
        self.fetch_button.connect("clicked", self.on_fetch_formats)
        box.append(self.fetch_button)

        box.append(Gtk.Label(label="Select format:"))
        self.format_combo = Gtk.DropDown.new()
        box.append(self.format_combo)

        self.playlist_check = Gtk.CheckButton(label="Download full playlist")
        box.append(self.playlist_check)

        self.folder_button = Gtk.Button(label=f"Output folder: {self.output_folder}")
        self.folder_button.connect("clicked", self.choose_folder)
        box.append(self.folder_button)

        self.download_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.download_list.set_vexpand(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.download_list)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        box.append(scroll)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls.set_halign(Gtk.Align.END)

        self.download_button = Gtk.Button(label="Download")
        self.download_button.set_sensitive(False)
        self.download_button.connect("clicked", self.on_start_download)
        controls.append(self.download_button)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda btn: self.close())
        controls.append(close_button)

        box.append(controls)

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
            return
        self.fetch_button.set_sensitive(False)
        self.download_button.set_sensitive(False)
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
            GLib.idle_add(lambda: self._append_format_log(f"Failed to fetch formats:\n{stderr}\n"))
            GLib.idle_add(self.fetch_button.set_sensitive, True)
            return

        formats = self.parse_formats(stdout)
        if not formats:
            GLib.idle_add(lambda: self._append_format_log("No formats found.\n"))
            GLib.idle_add(self.fetch_button.set_sensitive, True)
            return

        GLib.idle_add(self.populate_format_combo, formats)
        GLib.idle_add(self.fetch_button.set_sensitive, True)
        GLib.idle_add(self.download_button.set_sensitive, True)

    def _append_format_log(self, msg):
        print(msg)

    def parse_formats(self, formats_text):
        formats = []
        lines = formats_text.splitlines()
        for line in lines:
            m = re.match(r"^\s*(\d+)\s+(\S+)\s+(.+)$", line)
            if m:
                code = m.group(1)
                ext = m.group(2)
                desc = m.group(3).strip()
                if "audio only" in desc.lower():
                    continue
                formats.append((code, f"{code} - {ext} - {desc}"))
        return formats

    def populate_format_combo(self, formats):
        self.available_formats = formats
        model = Gtk.StringList.new([desc for _, desc in formats])
        self.format_combo.set_model(model)
        self.format_combo.set_selected(0)

    def on_start_download(self, _):
        url = self.entry.get_text().strip()
        if not url:
            return
        idx = self.format_combo.get_selected()
        if idx < 0 or idx >= len(self.available_formats):
            return
        fmt_code = self.available_formats[idx][0]

        row = DownloadRow(url, fmt_code, self.output_folder, self.playlist_check.get_active())
        self.download_list.append(row)


class YTDLPApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.example.ytdlp")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = YTDLPWindow(self)
        win.present()


app = YTDLPApp()
app.run()
