import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
from zipfile import ZipFile
from lxml import etree
from PIL import Image, ImageTk, UnidentifiedImageError
import io
import os
import requests
import sv_ttk
import sys  # at top if not already
import re
import os
from datetime import datetime

class ComicMetadataEditor(tb.Window):
    base_font = ("Segoe UI", 12)
    header_font = ("Segoe UI", 15, "bold")

    def __init__(self):
        super().__init__(title="CBZ Comic Metadata Editor", themename="flatly")

        # Bind platform-specific shortcuts
        if sys.platform == "darwin":  # macOS uses Command key
            self.bind_all("<Command-s>", lambda e: self.save_cbz())
            self.bind_all("<Command-r>", lambda e: self.reload_cbz())
        else:  # Windows/Linux use Control key
            self.bind_all("<Control-s>", lambda e: self.save_cbz())
            self.bind_all("<Control-r>", lambda e: self.reload_cbz())

        self.setup_menu()
        self.geometry("1200x800")
        self.fields = []
        self.cbz_path = None
        self.cbz_bytes = None
        self.comicinfo_data = None
        self.cover_image = None
        self.cover_data = None
        self.cover_name = None
        self.mangadex_id = None

        self.tab_control = tb.Notebook(self)
        self.tab_control.pack(fill="both", expand=True)

        # Single Editor tab
        self.single_tab = tb.Frame(self.tab_control)
        self.tab_control.add(self.single_tab, text="Single Editor")

        self.paned = tb.PanedWindow(self.single_tab, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        self.left_frame = tb.Frame(self.paned, padding=10)
        self.paned.add(self.left_frame, weight=3)
        self.setup_metadata_ui()

        self.right_frame = tb.Frame(self.paned, padding=10)
        self.paned.add(self.right_frame, weight=2)
        self.setup_cover_ui()
        self.setup_toolbar()
        self.setup_cbz_file_list_ui()

        # Bulk Editor tab
        self.bulk_tab = tb.Frame(self.tab_control)
        self.tab_control.add(self.bulk_tab, text="Bulk Editor")
        self.setup_bulk_editor_ui()

        # Vertical separator
        # Clean UI styles for modern look
        style = self.style
        sv_ttk.set_theme("light")
        style = self.style

        # Global form & control styling


        style.configure("TButton", font=self.base_font, padding=6, relief="flat", borderwidth=1)
        style.configure("TEntry", font=self.base_font, padding=6, relief="flat", borderwidth=1)
        style.configure("TLabel", font=self.base_font, foreground="#222222")
        style.configure("TLabelframe", background=self.cget("background"), bordercolor="#666", relief="ridge",
                        borderwidth=2)
        style.configure("TLabelframe.Label", font=self.header_font, foreground="#222222", background="")  # use "" or omit

    def get_current_metadata_dict(self):
        return {f[0].get().strip(): f[1].get().strip() for f in self.fields if f is not None}

    def resolve_template(self, template, metadata, filename, index=None):
        result = template
        # Replace filename placeholder
        print(result)
        if '{filename}' in result:
            result = result.replace('{filename}', os.path.splitext(os.path.basename(filename))[0])

        # Replace chapter number from filename
        if '{chapter}' in result:
            match = re.search(r'[Cc](?:h(?:apter)?)?[ ._]*([0-9]{1,4}(?:\.[0-9]+)?)', filename)
            result = result.replace('{chapter}', match.group(1) if match else '')

        # Replace volume number from filename
        if '{volume}' in result:
            match = re.search(r'[Vv]ol(?:ume)?[ ._]*([0-9]+)', filename)
            result = result.replace('{volume}', match.group(1) if match else '')

        # Replace index if provided
        if '{index}' in result and index is not None:
            result = result.replace('{index}', str(index))

        # Replace date
        if '{date}' in result:
            result = result.replace('{date}', datetime.now().strftime('%Y-%m-%d'))

        # Replace {value:FieldName}
        matches = re.findall(r'\{value:([^}]+)\}', result)
        for match in matches:
            value = metadata.get(match, '')
            result = result.replace(f'{{value:{match}}}', value)

        return result

    def setup_bulk_editor_ui(self):
        # Split bulk editor tab horizontally
        self.bulk_paned = tb.PanedWindow(self.bulk_tab, orient="horizontal")
        self.bulk_paned.pack(fill="both", expand=True)

        # Left side: Metadata fields (same layout as single editor)
        self.bulk_left_frame = tb.Frame(self.bulk_paned, padding=10)
        self.bulk_paned.add(self.bulk_left_frame, weight=3)

        self.setup_bulk_metadata_fields_ui(self.bulk_left_frame)

        # Right side: File selector + ComicInfo preview (you were missing this)
        # Right side: File selector + ComicInfo preview
        self.bulk_right_frame = tb.Frame(self.bulk_paned, padding=10)
        self.bulk_paned.add(self.bulk_right_frame, weight=2)
        # Apply button
        apply_btn = tb.Button(
            self.bulk_right_frame,
            text="Apply to All",
            bootstyle="success",
            command=self.apply_bulk_metadata
        )
        apply_btn.pack(pady=10)

        # 🔹 Add Load Button at the top
        load_btn = tb.Button(self.bulk_right_frame, text="Load CBZ Files", bootstyle="primary",
                             command=self.load_bulk_cbz_files)
        load_btn.pack(pady=(0, 10))

        # Split right vertically into file list and preview
        rhs_pane = tb.PanedWindow(self.bulk_right_frame, orient="vertical")
        rhs_pane.pack(fill="both", expand=True)

        # Top: file list
        file_list_frame = tb.LabelFrame(rhs_pane, text="Selected CBZ Files", padding=10)
        rhs_pane.add(file_list_frame, weight=1)

        self.bulk_cbz_listbox = tk.Listbox(file_list_frame, height=10, font=self.base_font)
        self.bulk_cbz_listbox.pack(fill="both", expand=True)
        self.bulk_cbz_listbox.bind("<<ListboxSelect>>", self.preview_bulk_comicinfo)

        # Bottom: ComicInfo preview
        preview_frame = tb.LabelFrame(rhs_pane, text="ComicInfo Preview", padding=10)
        rhs_pane.add(preview_frame, weight=2)

        self.bulk_preview_text = tk.Text(preview_frame, wrap="word", state="disabled", font=self.base_font)
        self.bulk_preview_text.pack(fill="both", expand=True)

    def setup_bulk_metadata_fields_ui(self, parent):
        metadata_frame = tb.LabelFrame(parent, text="Metadata Fields (Bulk)", bootstyle="secondary", padding=10)
        metadata_frame.pack(fill="both", expand=True)

        self.bulk_canvas = tk.Canvas(metadata_frame, highlightthickness=0)
        scrollbar = tb.Scrollbar(metadata_frame, orient="vertical", command=self.bulk_canvas.yview)
        self.bulk_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.bulk_canvas.pack(side="left", fill="both", expand=True)

        self.bulk_form_frame = tb.Frame(self.bulk_canvas)
        self.bulk_form_window = self.bulk_canvas.create_window((0, 0), window=self.bulk_form_frame, anchor="nw")

        self.bulk_form_frame.bind("<Configure>",
                                  lambda e: self.bulk_canvas.configure(scrollregion=self.bulk_canvas.bbox("all")))
        self.bulk_canvas.bind("<Configure>",
                              lambda e: self.bulk_canvas.itemconfig(self.bulk_form_window, width=e.width))

        # Example: just add a dummy field initially
        self.bulk_fields = []
        self.add_bulk_field()

        # Add field button
        self.bulk_add_field_btn = tb.Button(
            metadata_frame, text="+ Add Field", bootstyle="primary-outline",
            command=self.add_bulk_field
        )
        self.bulk_add_field_btn.pack(pady=5)

    def preview_bulk_comicinfo(self, event):
        selection = self.bulk_cbz_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        path = self.bulk_cbz_paths[idx]

        try:
            with open(path, 'rb') as f:
                cbz_bytes = f.read()
            with ZipFile(io.BytesIO(cbz_bytes), 'r') as zipf:
                if 'ComicInfo.xml' in zipf.namelist():
                    xml_data = zipf.read('ComicInfo.xml').decode(errors="replace")
                else:
                    xml_data = "[No ComicInfo.xml found]"

            self.bulk_preview_text.config(state="normal")
            self.bulk_preview_text.delete("1.0", "end")
            self.bulk_preview_text.insert("1.0", xml_data)
            self.bulk_preview_text.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Could not read CBZ:\n{e}")

    def load_bulk_cbz_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Comic Book Zip", "*.cbz")])
        if not paths:
            return

        self.bulk_cbz_paths = list(paths)
        self.bulk_cbz_listbox.delete(0, "end")

        for path in self.bulk_cbz_paths:
            filename = os.path.basename(path)
            self.bulk_cbz_listbox.insert("end", filename)

    def add_bulk_field(self, key="", value=""):
        row = len(self.bulk_fields)
        key_var = tk.StringVar(value=key)
        val_var = tk.StringVar(value=value)

        key_entry = tb.Entry(self.bulk_form_frame, textvariable=key_var, font=self.base_font)
        val_entry = tb.Entry(self.bulk_form_frame, textvariable=val_var, font=self.base_font)
        delete_button = tb.Button(self.bulk_form_frame, text="❌", width=3, command=lambda: self.remove_bulk_field(row))

        key_entry.grid(row=row, column=0, padx=4, pady=3, sticky="ew")
        val_entry.grid(row=row, column=1, padx=4, pady=3, sticky="ew")
        delete_button.grid(row=row, column=2, padx=4, pady=3, sticky="e")

        self.bulk_form_frame.grid_columnconfigure(0, weight=1)
        self.bulk_form_frame.grid_columnconfigure(1, weight=2)
        self.bulk_form_frame.grid_columnconfigure(2, weight=0)

        self.bulk_fields.append((key_var, val_var, key_entry, val_entry, delete_button))

    def remove_bulk_field(self, index):
        if self.bulk_fields[index] is None:
            return
        _, _, key_widget, val_widget, del_button = self.bulk_fields[index]
        key_widget.destroy()
        val_widget.destroy()
        del_button.destroy()
        self.bulk_fields[index] = None

    def apply_bulk_metadata(self):
        if not self.bulk_fields or all(f is None for f in self.bulk_fields):
            messagebox.showwarning("No Fields", "No metadata fields to apply.")
            return

        files = self.bulk_file_listbox.get(0, "end")
        if not files:
            messagebox.showwarning("No Files", "No CBZ files selected.")
            return

        fields_to_apply = []
        for f in self.bulk_fields:
            if f is None:
                continue
            key = f[0].get().strip()
            val = str(f[1].get()).strip()
            if key:
                fields_to_apply.append((key, val))

        if not fields_to_apply:
            messagebox.showwarning("Empty Fields", "All fields are blank.")
            return

        failed = []

        for index, path in enumerate(self.bulk_cbz_paths):
            with open(path, "rb") as f:
                cbz_bytes = f.read()

            try:
                with ZipFile(io.BytesIO(cbz_bytes), 'r') as zipf:
                    if 'ComicInfo.xml' in zipf.namelist():
                        xml_data = zipf.read('ComicInfo.xml')
                        root = etree.fromstring(xml_data)
                    else:
                        root = etree.Element("ComicInfo")

                    # Convert existing to dict
                    current_data = {child.tag: child.text or "" for child in root}

                    # Apply each field
                    for key_var, val_var, *_ in self.bulk_fields:
                        key = key_var.get().strip()
                        raw_val = str(val_var.get().strip())
                        if key:
                            resolved = self.resolve_template(raw_val, current_data, path, index=index)
                            existing = root.find(key)
                            if existing is not None:
                                existing.text = resolved
                            else:
                                etree.SubElement(root, key).text = resolved

                # Save new CBZ
                temp_cbz = path + ".tmp"
                with ZipFile(io.BytesIO(cbz_bytes), 'r') as zin, ZipFile(temp_cbz, 'w') as zout:
                    for item in zin.infolist():
                        if item.filename != 'ComicInfo.xml':
                            zout.writestr(item, zin.read(item))
                    zout.writestr("ComicInfo.xml",
                                  etree.tostring(root, pretty_print=True, encoding="utf-8", xml_declaration=True))
                os.replace(temp_cbz, path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update {os.path.basename(path)}:\n{e}")

        if failed:
            messagebox.showerror("Some Files Failed",
                                 f"{len(failed)} files failed:\n\n" + "\n".join(f[0] for f in failed))
        else:
            messagebox.showinfo("Done", "Metadata applied to all selected CBZ files.")

    def remove_bulk_field(self, index):
        if self.bulk_fields[index] is None:
            return
        _, _, key_entry, val_entry, del_btn = self.bulk_fields[index]
        key_entry.destroy()
        val_entry.destroy()
        del_btn.destroy()
        self.bulk_fields[index] = None
        self.repack_bulk_fields()

    def repack_bulk_fields(self):
        new_fields = [f for f in self.bulk_fields if f is not None]
        self.bulk_fields = []
        for widget in self.bulk_form_frame.winfo_children():
            widget.destroy()
        for key_var, val_var, *_ in new_fields:
            self.add_bulk_field(key_var.get(), val_var.get())

    def bulk_apply_tag(self):
        key = self.bulk_key_var.get().strip()
        val = self.bulk_val_var.get().strip()
        if not key:
            messagebox.showwarning("Missing Field", "Metadata key is required.")
            return

        updated = 0
        for path in getattr(self, "bulk_cbz_paths", []):
            try:
                with open(path, "rb") as f:
                    data = f.read()

                with ZipFile(io.BytesIO(data), 'r') as zin:
                    namelist = zin.namelist()
                    xml_data = zin.read("ComicInfo.xml") if "ComicInfo.xml" in namelist else b"<ComicInfo/>"
                    root = etree.fromstring(xml_data)
                    found = False
                    for el in root:
                        if el.tag.lower() == key.lower():
                            el.text = val
                            found = True
                            break
                    if not found:
                        etree.SubElement(root, key).text = val
                    new_xml = etree.tostring(root, pretty_print=True, encoding="utf-8", xml_declaration=True)

                temp_path = path + ".tmp"
                with ZipFile(io.BytesIO(data), 'r') as zin, ZipFile(temp_path, 'w') as zout:
                    for item in zin.infolist():
                        if item.filename != "ComicInfo.xml":
                            zout.writestr(item, zin.read(item))
                    zout.writestr("ComicInfo.xml", new_xml)

                os.replace(temp_path, path)
                updated += 1
            except Exception as e:
                print(f"Failed to update {path}: {e}")

        messagebox.showinfo("Done", f"Updated {updated} CBZ files.")

    def clear_cbz_context(self):
        self.cbz_path = None
        self.cbz_bytes = None
        self.cover_image = None
        self.cover_data = None
        self.cover_name = None
        self.mangadex_id = None

        self.clear_all_fields()
        self.cbz_file_listbox.delete(0, "end")
        self.cbz_file_preview_canvas.delete("all")
        self.cbz_file_preview_text.config(state="normal")
        self.cbz_file_preview_text.delete("1.0", "end")
        self.cbz_file_preview_text.config(state="disabled")
        self.cbz_file_preview_text.place_forget()

        self.cover_canvas.delete("all")
        self.cover_canvas.create_rectangle(10, 10, 270, 370, fill='lightgray')
        self.cover_canvas.create_text(140, 190, text="No Cover", font=("Arial", 16))

        self.upload_btn.pack_forget()
        self.clear_cover_btn.pack_forget()
        # self.clear_btn.pack_forget()
        # self.save_btn.pack_forget()

        self.add_field_button.config(state="disabled")
        self.fetch_md_btn.config(state="disabled")
        self.fetch_cover_btn.config(state="disabled")

    def reload_cbz(self):
        if not self.cbz_path:
            messagebox.showinfo("Info", "No CBZ file loaded.")
            return

        try:
            with open(self.cbz_path, 'rb') as f:
                self.cbz_bytes = f.read()
            self.clear_all_fields()
            self.cover_canvas.delete("all")
            self.cover_image = None
            self.cover_data = None
            self.cover_name = None
            # self.upload_btn.pack(pady=5)
            # self.clear_cover_btn.pack(pady=5)
            # self.clear_btn.pack(side="left", padx=5)
            # self.save_btn.pack(side="left", padx=5)
            self.cbz_file_listbox.delete(0, "end")

            with ZipFile(io.BytesIO(self.cbz_bytes), 'r') as zipf:
                for name in zipf.namelist():
                    self.cbz_file_listbox.insert("end", name)
                if 'ComicInfo.xml' in zipf.namelist():
                    xml_data = zipf.read('ComicInfo.xml')
                    self.comicinfo_data = etree.fromstring(xml_data)
                else:
                    self.comicinfo_data = etree.Element("ComicInfo")
                    messagebox.showinfo("Info", "No ComicInfo.xml found. Starting with empty metadata.")
                series_value = ""
                for child in self.comicinfo_data:
                    tag = child.tag
                    text = child.text or ""
                    if tag.lower() == "series":
                        series_value = text
                    self.add_field(tag, text)

                # Pre-fill the MangaDex title field
                if series_value:
                    self.manga_title_var.set(series_value)

                self.show_cover(zipf)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to reload CBZ:\n{e}")

    def resize_form_frame(self, event):
        # Expand the form frame to match canvas width
        canvas_width = event.width
        self.canvas.itemconfig(self.form_window, width=canvas_width)

    def setup_menu(self):
        menu = tk.Menu(self)

        # File menu
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Open CBZ", command=self.load_cbz)
        file_menu.add_command(label="Save CBZ", command=self.save_cbz)
        file_menu.add_command(label="Reload", command=self.reload_cbz)
        file_menu.add_separator()
        # file_menu.add_command(label="Reload Without Saving", command=self.reload_cbz)
        file_menu.add_command(label="Clear CBZ", command=self.clear_cbz_context)
        menu.add_cascade(label="File", menu=file_menu)

        # Edit menu
        edit_menu = tk.Menu(menu, tearoff=0)
        edit_menu.add_command(label="Clear All Metadata Fields", command=self.clear_all_fields)
        edit_menu.add_command(label="Upload Cover", command=self.upload_cover)

        edit_menu.add_command(label="Remove Cover", command=self.clear_cover)
        menu.add_cascade(label="Edit", menu=edit_menu)



        self.config(menu=menu)


    def setup_metadata_ui(self):
        # Wrap the LHS vertical sections in a vertical PanedWindow
        vertical_paned = tb.PanedWindow(self.left_frame, orient="vertical")
        vertical_paned.pack(fill="both", expand=True)

        # ---------- Metadata Fields LabelFrame ----------
        self.metadata_frame = tb.LabelFrame(
            vertical_paned, text="Metadata Fields",
            bootstyle="secondary", padding=10
        )

        # Scrollable area inside metadata frame
        outer_frame = tb.Frame(self.metadata_frame)
        outer_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer_frame, highlightthickness=0)
        self.scrollbar = tb.Scrollbar(outer_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.form_frame = tb.Frame(self.canvas)
        self.form_window = self.canvas.create_window((0, 0), window=self.form_frame, anchor="nw")

        self.form_frame.bind("<Configure>", self._update_scrollbar_visibility)
        self.canvas.bind("<Configure>", self.resize_form_frame)

        self.form_frame.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.form_frame.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # Add Field Button (initially disabled)
        self.add_field_button = tb.Button(
            self.metadata_frame,
            text="+ Add Field",
            command=self.add_field,
            bootstyle="primary-outline",
            state="disabled"
        )
        self.add_field_button.pack(pady=5)

        # ---------- MangaDex Info LabelFrame ----------
        md_frame = tb.LabelFrame(
            vertical_paned, text="MangaDex Info",
            bootstyle="secondary", padding=12
        )
        md_frame.configure(labelanchor='nw')
        md_frame.pack(fill='both', expand=True, pady=(0, 5), ipadx=4, ipady=4)

        self.setup_mangadex_ui_body(md_frame)

        # Add both frames to vertical pane
        vertical_paned.add(self.metadata_frame, weight=3)
        vertical_paned.add(md_frame, weight=2)

    def _update_scrollbar_visibility(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        canvas_height = self.canvas.winfo_height()
        frame_height = self.form_frame.winfo_height()

        if frame_height <= canvas_height:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(self, event):
        if os.name == 'nt':  # Windows
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        else:  # macOS/Linux
            self.canvas.yview_scroll(-1 * (event.delta), "units")

    def _on_cover_canvas_resize(self, event):
        if not self.cover_image_data:
            return

        try:
            image = Image.open(io.BytesIO(self.cover_image_data))

            canvas_width = event.width
            canvas_height = event.height

            max_width = canvas_width - 20
            max_height = canvas_height - 20

            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            self.preview_image = ImageTk.PhotoImage(image)
            self.cover_preview_canvas.delete("all")
            self.cover_preview_canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=self.preview_image,
                anchor="center"
            )
        except Exception as e:
            print(f"Resize preview failed: {e}")

    def setup_mangadex_ui_body(self, parent):
        # --- Search input row (top of MangaDex panel) ---
        input_row = tb.Frame(parent)
        input_row.pack(fill='x', padx=5, pady=(5, 0))

        self.manga_title_var = tk.StringVar()
        tb.Label(input_row, text="Title:").pack(side="left")
        tb.Entry(input_row, textvariable=self.manga_title_var, width=30).pack(side="left", padx=5)
        self.fetch_md_btn = tb.Button(input_row, text="Fetch Metadata", command=self.fetch_mangadex_metadata,
                                      state="disabled")
        self.fetch_md_btn.pack(side="left", padx=5)

        # self.fetch_cover_btn = tb.Button(input_row, text="Fetch Cover", command=self.fetch_mangadex_cover,
        #                                  state="disabled")
        # self.fetch_cover_btn.pack(side="left", padx=5)

        # --- Notebook with Info + Covers ---
        notebook = tb.Notebook(parent, bootstyle="secondary")
        notebook.pack(fill="both", expand=True, pady=(5, 0))

        # Tab 1: Metadata Info (scrollable)
        metadata_tab = tb.Frame(notebook)
        self.md_canvas = tk.Canvas(metadata_tab, highlightthickness=0)
        md_scrollbar = tb.Scrollbar(metadata_tab, orient="vertical", command=self.md_canvas.yview)
        self.md_canvas.configure(yscrollcommand=md_scrollbar.set)
        md_scrollbar.pack(side="right", fill="y")
        self.md_canvas.pack(side="left", fill="both", expand=True)
        self.md_result_frame = tb.Frame(self.md_canvas)
        self.md_window = self.md_canvas.create_window((0, 0), window=self.md_result_frame, anchor="nw")
        self.md_result_frame.bind("<Configure>",
                                  lambda e: self.md_canvas.configure(scrollregion=self.md_canvas.bbox("all")))
        self.md_canvas.bind("<Configure>", lambda e: self.md_canvas.itemconfig(self.md_window, width=e.width))
        self.md_result_frame.bind("<Enter>", lambda e: self.md_canvas.bind_all("<MouseWheel>", self._on_mousewheel_md))
        self.md_result_frame.bind("<Leave>", lambda e: self.md_canvas.unbind_all("<MouseWheel>"))

        # Tab 2: Covers (same)
        covers_tab = tb.Frame(notebook)
        cover_list_frame = tb.Frame(covers_tab)
        cover_list_frame.pack(side="left", fill="y", padx=(5, 0), pady=5)
        self.cover_volume_listbox = tk.Listbox(cover_list_frame, width=20, font=self.base_font)
        self.cover_volume_listbox.pack(fill="y", expand=True)
        self.cover_volume_listbox.bind("<<ListboxSelect>>", self.preview_selected_volume_cover)
        preview_frame = tb.Frame(covers_tab)
        preview_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        # Button row above the cover preview
        cover_button_row = tb.Frame(preview_frame)
        cover_button_row.pack(fill="x", pady=(0, 10))

        self.fetch_cover_btn = tb.Button(cover_button_row, text="Fetch Covers", command=self.fetch_mangadex_cover)
        self.fetch_cover_btn.pack(side="left", padx=(0, 5))

        self.use_cover_btn = tb.Button(cover_button_row, text="Use This Cover", command=self.use_previewed_cover)
        self.use_cover_btn.pack(side="left")

        self.cover_preview_canvas = tk.Canvas(preview_frame, bg="gray")
        self.cover_preview_canvas.pack(fill="both", expand=True)
        self.cover_preview_canvas.bind("<Configure>", self._on_cover_canvas_resize)

        self.use_cover_btn["state"] = "disabled"
        self.cover_volume_map = {}
        self.cover_image_data = None

        # Tab 3: Chapter Info (scrollable)
        chapter_tab = tb.Frame(notebook)

        # Container to hold input row + scrollable canvas below
        chapter_container = tb.Frame(chapter_tab)
        chapter_container.pack(fill="both", expand=True)

        # --- Top input row ---
        chapter_input_row = tb.Frame(chapter_container)
        chapter_input_row.pack(fill="x", padx=5, pady=(5, 0))

        self.chapter_lang_var = tk.StringVar()
        self.chapter_number_var = tk.StringVar()

        tb.Label(chapter_input_row, text="Chapter #:").pack(side="left")
        tb.Entry(chapter_input_row, textvariable=self.chapter_number_var, width=10).pack(side="left", padx=5)
        tb.Button(chapter_input_row, text="Fetch Chapter Info", command=self.fetch_chapter_info).pack(side="left",
                                                                                                      padx=5)

        tb.Label(chapter_input_row, text="Lang:").pack(side="left", padx=(15, 0))
        self.chapter_lang_dropdown = tb.Combobox(chapter_input_row, textvariable=self.chapter_lang_var, width=6,
                                                 state="readonly")
        self.chapter_lang_dropdown.pack(side="left", padx=5)
        self.chapter_lang_dropdown.bind("<<ComboboxSelected>>", self.display_chapter_info_for_language)

        # --- Scrollable frame for chapter results ---
        self.chapter_canvas = tk.Canvas(chapter_container, highlightthickness=0)
        chapter_scrollbar = tb.Scrollbar(chapter_container, orient="vertical", command=self.chapter_canvas.yview)
        self.chapter_canvas.configure(yscrollcommand=chapter_scrollbar.set)

        chapter_scrollbar.pack(side="right", fill="y")
        self.chapter_canvas.pack(side="left", fill="both", expand=True)

        self.chapter_info_frame = tb.Frame(self.chapter_canvas)
        self.chapter_info_window = self.chapter_canvas.create_window((0, 0), window=self.chapter_info_frame,
                                                                     anchor="nw")

        self.chapter_info_frame.bind("<Configure>", lambda e: self.chapter_canvas.configure(
            scrollregion=self.chapter_canvas.bbox("all")))
        self.chapter_canvas.bind("<Configure>",
                                 lambda e: self.chapter_canvas.itemconfig(self.chapter_info_window, width=e.width))
        self.chapter_info_frame.bind("<Enter>",
                                     lambda e: self.chapter_canvas.bind_all("<MouseWheel>", self._on_mousewheel_ch))
        self.chapter_info_frame.bind("<Leave>", lambda e: self.chapter_canvas.unbind_all("<MouseWheel>"))

        # Store tab references
        self.mangadex_tabs = {
            "notebook": notebook,
            "metadata_tab": metadata_tab,
            "covers_tab": covers_tab,
            "chapter_tab": chapter_tab
        }

        notebook.add(metadata_tab, text="Info")

    def _on_mousewheel_md(self, event):
        if os.name == 'nt':  # Windows
            self.md_canvas.yview_scroll(-1 * (event.delta // 120), "units")
        elif os.name == 'posix':  # macOS/Linux
            self.md_canvas.yview_scroll(-1 * int(event.delta), "units")

    def _on_mousewheel_ch(self, event):
        if os.name == 'nt':
            self.chapter_canvas.yview_scroll(-1 * (event.delta // 120), "units")
        elif os.name == 'posix':
            self.chapter_canvas.yview_scroll(-1 * int(event.delta), "units")

    def fetch_chapter_info(self):
        chapter_num = self.chapter_number_var.get().strip()
        if not chapter_num:
            messagebox.showwarning("Input", "Please enter a chapter number.")
            return

        # Reset cache and UI
        self.chapter_info_cache = {}
        self.chapter_lang_dropdown["values"] = []

        # Clear old frame AND canvas window
        if hasattr(self, "chapter_info_frame"):
            self.chapter_canvas.delete(self.chapter_info_window)
            self.chapter_info_frame.destroy()

        self.chapter_info_frame = tb.Frame(self.chapter_canvas)
        self.chapter_info_window = self.chapter_canvas.create_window(
            (0, 0), window=self.chapter_info_frame, anchor="nw"
        )

        # Rebind scroll + resize behavior
        self.chapter_info_frame.bind(
            "<Configure>",
            lambda e: self.chapter_canvas.configure(
                scrollregion=self.chapter_canvas.bbox("all")
            )
        )
        self.chapter_canvas.bind(
            "<Configure>",
            lambda e: self.chapter_canvas.itemconfig(
                self.chapter_info_window, width=e.width
            )
        )
        self.chapter_info_frame.bind(
            "<Enter>",
            lambda e: self.chapter_canvas.bind_all("<MouseWheel>", self._on_mousewheel_ch)
        )
        self.chapter_info_frame.bind(
            "<Leave>",
            lambda e: self.chapter_canvas.unbind_all("<MouseWheel>")
        )

        try:
            res = requests.get("https://api.mangadex.org/chapter", params={
                "manga": self.mangadex_id,
                "chapter": chapter_num,
                "limit": 100
            })
            res.raise_for_status()
            chapters = res.json()["data"]

            if not chapters:
                tb.Label(self.chapter_info_frame, text="No chapter found.", foreground="gray").pack()
                return

            lang_map = {}
            for ch in chapters:
                lang = ch["attributes"].get("translatedLanguage", "unknown")
                lang_map[lang] = ch["attributes"]

            self.chapter_info_cache = lang_map
            lang_options = sorted(lang_map.keys())
            self.chapter_lang_dropdown["values"] = lang_options

            if "en" in lang_options:
                self.chapter_lang_var.set("en")
            else:
                self.chapter_lang_var.set(lang_options[0])

            self.display_chapter_info_for_language()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch chapter info:\n{e}")

    def display_chapter_info_for_language(self, *_):
        lang = self.chapter_lang_var.get()
        chapter = self.chapter_info_cache.get(lang)
        if not chapter:
            return

        for widget in self.chapter_info_frame.winfo_children():
            widget.destroy()

        for key, val in chapter.items():
            row = tb.Frame(self.chapter_info_frame)

            row.pack(anchor="w", fill="x", expand=True, pady=4)
            # Force layout update before resizing
            self.chapter_info_frame.update_idletasks()

            # Get current canvas width and apply it
            canvas_width = self.chapter_canvas.winfo_width()
            self.chapter_canvas.itemconfig(self.chapter_info_window, width=canvas_width)

            label_text = key.replace("_", " ").capitalize()
            tb.Label(row, text=f"{label_text}:", width=14, anchor="nw", font=self.base_font) \
                .pack(side="left", anchor="n", pady=2)
            tb.Label(row, text=str(val), wraplength=360, font=self.base_font, justify="left") \
                .pack(side="left", fill="x", expand=True, padx=(0, 5), anchor="n")
            tb.Button(row, text="+", width=2, command=lambda k=label_text, v=val: self.add_field(k, v),
                      bootstyle="success-outline").pack(side="right", anchor="n", padx=4)

            tb.Separator(self.chapter_info_frame, orient="horizontal").pack(fill="x", padx=4, pady=2)

    def setup_cover_ui(self):
        self.cover_canvas = tk.Canvas(self.right_frame, width=280, height=380, bg="gray")
        self.cover_canvas.pack(pady=5)

        # self.upload_btn = tb.Button(self.right_frame, text="Upload Cover", command=self.upload_cover, bootstyle="info")
        # self.clear_cover_btn = tb.Button(self.right_frame, text="Remove Cover", command=self.clear_cover, bootstyle="danger")
        # self.upload_btn.pack_forget()
        # self.clear_cover_btn.pack_forget()

    def setup_toolbar(self):
        self.toolbar = tb.Frame(self.right_frame)
        self.toolbar.pack(pady=20, fill="x")

        tb.Button(self.toolbar, text="Open CBZ", command=self.load_cbz, bootstyle="primary").pack(side="left", padx=5)
        # self.clear_btn = tb.Button(self.toolbar, text="Clear Fields", command=self.clear_all_fields, bootstyle="warning")
        # self.save_btn = tb.Button(self.toolbar, text="Save CBZ", command=self.save_cbz, bootstyle="success")
        # self.clear_btn.pack_forget()
        # self.save_btn.pack_forget()

    def setup_cbz_file_list_ui(self):
        tb.Separator(self.right_frame, orient='horizontal').pack(fill='x', pady=5)

        file_frame = tb.LabelFrame(self.right_frame, text="Files in CBZ", bootstyle="secondary", padding=10)
        file_frame.pack(fill="both", expand=True, pady=5)

        container = tb.Frame(file_frame)
        container.pack(fill="both", expand=True)

        self.cbz_file_listbox = tk.Listbox(container, height=8, exportselection=False, font=self.base_font)
        self.cbz_file_listbox.pack(side="left", fill="y", padx=(0, 10))
        self.cbz_file_listbox.bind("<<ListboxSelect>>", self.preview_selected_cbz_file)

        # Create a stack of preview frames for images vs text
        self.cbz_preview_frame = tb.Frame(container)
        self.cbz_preview_frame.pack(side="left", fill="both", expand=True)

        # Canvas for image preview
        self.cbz_file_preview_canvas = tk.Canvas(self.cbz_preview_frame, bg="lightgray")
        self.cbz_file_preview_canvas.pack(fill="both", expand=True)

        # Fallback text preview for non-images
        self.cbz_file_preview_text = tk.Text(self.cbz_preview_frame, wrap="word", state="disabled", font=self.base_font)
        self.cbz_file_preview_text.place_forget()  # hide by default

    def preview_selected_cbz_file(self, event):
        if not self.cbz_bytes:
            return
        selected = self.cbz_file_listbox.curselection()
        if not selected:
            return
        filename = self.cbz_file_listbox.get(selected[0])
        try:
            with ZipFile(io.BytesIO(self.cbz_bytes), 'r') as zipf:
                data = zipf.read(filename)

            # Try to open as image
            try:
                image = Image.open(io.BytesIO(data))

                # Resize to fit preview canvas
                self.cbz_file_preview_canvas.update_idletasks()
                canvas_width = self.cbz_file_preview_canvas.winfo_width()
                canvas_height = self.cbz_file_preview_canvas.winfo_height()
                image.thumbnail((canvas_width - 20, canvas_height - 20), Image.Resampling.LANCZOS)

                self.cbz_preview_image = ImageTk.PhotoImage(image)
                # Show image preview
                self.cbz_file_preview_canvas.delete("all")
                self.cbz_file_preview_canvas.create_image(
                    canvas_width // 2, canvas_height // 2,
                    image=self.cbz_preview_image,
                    anchor="center"
                )

                # Hide text view
                self.cbz_file_preview_text.place_forget()


            except UnidentifiedImageError:
                # Show as readonly text
                self.cbz_file_preview_canvas.delete("all")
                self.cbz_file_preview_text.config(state="normal")
                self.cbz_file_preview_text.delete("1.0", "end")
                self.cbz_file_preview_text.insert("1.0", data.decode(errors="replace"))
                self.cbz_file_preview_text.config(state="disabled")
                self.cbz_file_preview_text.place(relwidth=1.0, relheight=1.0)
        except Exception as e:
            messagebox.showerror("Error", f"Unable to preview file:\n{e}")

    def load_cbz(self):
        path = filedialog.askopenfilename(filetypes=[("Comic Book Zip", "*.cbz")])
        if not path:
            return
        self.cbz_path = path
        # Attempt to extract chapter number from filename
        import re
        filename = os.path.basename(path)
        pattern = re.compile(r"[Cc](?:h(?:apter)?)?[ ._]*([0-9]{1,4}(?:\.[0-9]+)?)")
        match = pattern.search(filename)
        if match:
            chapter_guess = match.group(1)
            self.chapter_number_var.set(chapter_guess)
        else:
            self.chapter_number_var.set("")

        # Enable buttons now that a CBZ is loaded
        self.add_field_button.config(state="normal")
        self.fetch_md_btn.config(state="normal")
        self.fetch_cover_btn.config(state="normal")

        filename = os.path.basename(path)
        self.metadata_frame.config(text=f"Metadata Fields – {filename}")
        self.clear_all_fields()
        self.cover_canvas.delete("all")
        self.cover_image = None
        self.cover_data = None
        self.cover_name = None
        # self.upload_btn.pack(pady=5)
        # self.clear_cover_btn.pack(pady=5)
        # self.clear_btn.pack(side="left", padx=5)
        # self.save_btn.pack(side="left", padx=5)
        self.cbz_file_listbox.delete(0, "end")

        with open(path, 'rb') as f:
            self.cbz_bytes = f.read()

        try:
            with ZipFile(io.BytesIO(self.cbz_bytes), 'r') as zipf:
                for name in zipf.namelist():
                    self.cbz_file_listbox.insert("end", name)
                if 'ComicInfo.xml' in zipf.namelist():
                    xml_data = zipf.read('ComicInfo.xml')
                    self.comicinfo_data = etree.fromstring(xml_data)
                else:
                    self.comicinfo_data = etree.Element("ComicInfo")
                    messagebox.showinfo("Info", "No ComicInfo.xml found. Starting with empty metadata.")
                series_value = ""
                for child in self.comicinfo_data:
                    tag = child.tag
                    text = child.text or ""
                    if tag.lower() == "series":
                        series_value = text
                    self.add_field(tag, text)

                # Pre-fill the MangaDex title field
                if series_value:
                    self.manga_title_var.set(series_value)

                self.show_cover(zipf)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read CBZ file:\n{e}")

    def show_cover(self, zipf):
        possible_names = ['folder.jpg', 'cover.jpg', '000.jpg', '0001.jpg']
        for name in zipf.namelist():
            if os.path.basename(name).lower() in possible_names:
                try:
                    self.cover_data = zipf.read(name)
                    self.cover_name = name
                    image = Image.open(io.BytesIO(self.cover_data))
                    image.thumbnail((280, 380))
                    self.cover_image = ImageTk.PhotoImage(image)
                    self.cover_canvas.create_image(140, 190, image=self.cover_image)
                    return
                except Exception:
                    pass
        self.cover_canvas.create_rectangle(10, 10, 270, 370, fill='lightgray')
        self.cover_canvas.create_text(140, 190, text="No Cover", font=("Arial", 16))

    def upload_cover(self):
        path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if not path:
            return
        with open(path, "rb") as f:
            self.cover_data = f.read()
            self.cover_name = "folder.jpg"
            image = Image.open(io.BytesIO(self.cover_image_data))

            # Get canvas size
            canvas_width = self.cover_preview_canvas.winfo_width()
            canvas_height = self.cover_preview_canvas.winfo_height()

            if canvas_width == 1 or canvas_height == 1:
                # Canvas not rendered yet, use defaults
                canvas_width, canvas_height = 280, 380

            # Scale image
            image.thumbnail((canvas_width - 20, canvas_height - 20))

            self.preview_image = ImageTk.PhotoImage(image)
            self.cover_preview_canvas.delete("all")
            self.cover_preview_canvas.create_image(canvas_width // 2, canvas_height // 2, image=self.preview_image)

    def clear_cover(self):
        self.cover_data = None
        self.cover_name = None
        self.cover_image = None
        self.cover_canvas.delete("all")
        self.cover_canvas.create_rectangle(10, 10, 270, 370, fill='lightgray')
        self.cover_canvas.create_text(140, 190, text="No Cover", font=("Arial", 16))

    def add_field(self, key="", value=""):
        row = len(self.fields)
        key_var = tk.StringVar(value=key)
        val_var = tk.StringVar(value=value)

        key_entry = tb.Entry(self.form_frame, textvariable=key_var, font=self.base_font)
        val_entry = tb.Entry(self.form_frame, textvariable=val_var, font=self.base_font)
        delete_button = tb.Button(self.form_frame, text="❌", width=3, command=lambda: self.remove_field(row),)

        key_entry.grid(row=row, column=0, padx=4, pady=3, sticky="ew")
        val_entry.grid(row=row, column=1, padx=4, pady=3, sticky="ew")
        delete_button.grid(row=row, column=2, padx=4, pady=3, sticky="e")

        self.form_frame.grid_columnconfigure(0, weight=1)
        self.form_frame.grid_columnconfigure(1, weight=2)
        self.form_frame.grid_columnconfigure(2, weight=0)

        self.fields.append((key_var, val_var, key_entry, val_entry, delete_button))

    def remove_field(self, index):
        _, _, key_widget, val_widget, del_button = self.fields[index]
        key_widget.destroy()
        val_widget.destroy()
        del_button.destroy()
        self.fields[index] = None
        self.repack_fields()

    def repack_fields(self):
        new_fields = [f for f in self.fields if f is not None]
        self.fields = []
        for widget in self.form_frame.winfo_children():
            widget.destroy()
        for key_var, val_var, *_ in new_fields:
            self.add_field(key_var.get(), val_var.get())

    def clear_all_fields(self):
        for widget in self.form_frame.winfo_children():
            widget.destroy()
        self.fields = []

    def save_cbz(self):
        # Gather keys and check for duplicates
        keys = []
        for f in self.fields:
            if f is None:
                continue
            key = f[0].get().strip()
            if key:
                keys.append(key)

        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            messagebox.showerror("Duplicate Fields",
                                 f"Duplicate fields found: {', '.join(dupes)}.\nPlease remove or rename them before saving.")
            return  # cancel save

        # Proceed with XML creation
        root = etree.Element("ComicInfo")
        for f in self.fields:
            if f is None:
                continue
            key = f[0].get().strip()
            val = str(f[1].get().strip())
            if key:
                resolved = self.resolve_template(val, self.get_current_metadata_dict(), self.cbz_path)
                etree.SubElement(root, key).text = resolved

        xml_data = etree.tostring(root, pretty_print=True, encoding="utf-8", xml_declaration=True)
        temp_cbz = self.cbz_path + ".tmp"
        try:
            with ZipFile(io.BytesIO(self.cbz_bytes), 'r') as zin, ZipFile(temp_cbz, 'w') as zout:
                for item in zin.infolist():
                    if item.filename != 'ComicInfo.xml' and item.filename != self.cover_name:
                        zout.writestr(item, zin.read(item))
                zout.writestr("ComicInfo.xml", xml_data)
                if self.cover_data:
                    zout.writestr(self.cover_name or "folder.jpg", self.cover_data)
            os.replace(temp_cbz, self.cbz_path)
            messagebox.showinfo("Saved", "CBZ updated successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save CBZ:\n{e}")

    def fetch_mangadex_metadata(self):
        title = self.manga_title_var.get().strip()
        if not title:
            messagebox.showwarning("Input", "Please enter a manga title.")
            return
        try:
            res = requests.get("https://api.mangadex.org/manga", params={"title": title, "limit": 1})
            res.raise_for_status()
            data = res.json()
            self.clear_md_result()
            if not data["data"]:
                tb.Label(self.md_result_frame, text="No manga found.", bootstyle="warning").pack()
                return
            manga = data["data"][0]
            attr = manga["attributes"]
            tags = attr.get("tags", [])
            info = {
                "Title": attr["title"].get("en", ""),
                "Year": attr.get("year", ""),
                "Status": attr.get("status", ""),
                "Description": attr["description"].get("en", ""),
                "Tags": ", ".join([t["attributes"]["name"].get("en", "") for t in tags])
            }
            for key, val in info.items():
                self.add_md_result_row(key, val)
            self.mangadex_id = manga["id"]
            # Show the Covers and Chapter Info tabs only after metadata is successfully fetched
            notebook = self.mangadex_tabs["notebook"]
            tabs = self.mangadex_tabs

            # Avoid adding duplicates if tabs are already shown
            if not any(notebook.tab(i, "text") == "Covers" for i in range(notebook.index("end"))):
                notebook.add(tabs["covers_tab"], text="Covers")
                notebook.add(tabs["chapter_tab"], text="Chapter Info")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch manga info:\n{e}")

    def fetch_mangadex_cover(self):
        if not self.mangadex_id:
            messagebox.showwarning("Warning", "Fetch metadata first.")
            return

        try:
            res = requests.get("https://api.mangadex.org/cover", params={
                "manga[]": self.mangadex_id,
                "limit": 100,
                "order[volume]": "asc"
            })
            res.raise_for_status()
            data = res.json()["data"]

            self.cover_volume_map.clear()
            self.cover_volume_listbox.delete(0, "end")

            for cover in data:
                vol = cover["attributes"].get("volume", "Unknown")
                locale = cover["attributes"].get("locale", "unknown").lower()
                file = cover["attributes"]["fileName"]

                display = f"Volume {vol} [{locale}]" if vol else f"Unnumbered [{locale}]"
                self.cover_volume_map[display] = file
                self.cover_volume_listbox.insert("end", display)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch cover list:\n{e}")

    def add_md_result_row(self, key, value):
        row = tb.Frame(self.md_result_frame)
        row.pack(anchor="w", fill="x", pady=4)

        # Key label (top-aligned)
        key_label = tb.Label(row, text=f"{key}:", width=12, anchor="nw", font=self.base_font, foreground="#222222")
        key_label.pack(side="left", anchor="n", pady=2)

        # Value label (wraps long text)
        text = tb.Label(row, text=value, wraplength=360, font=self.base_font, foreground="#222222", justify="left")
        text.pack(side="left", fill="x", expand=True, padx=(0, 5), anchor="n")

        # + button
        tb.Button(row, text="+", width=2, command=lambda: self.add_field(key, value), bootstyle="success-outline") \
            .pack(side="right", anchor="n", padx=4)

        # Light grey separator line below each row
        tb.Separator(self.md_result_frame, orient="horizontal").pack(fill="x", padx=4, pady=2)

    def clear_md_result(self):
        for widget in self.md_result_frame.winfo_children():
            widget.destroy()

    def preview_selected_volume_cover(self, event):
        if not self.mangadex_id:
            return
        selected = self.cover_volume_listbox.curselection()
        if not selected:
            return

        label = self.cover_volume_listbox.get(selected[0])
        filename = self.cover_volume_map.get(label)
        if not filename:
            return

        try:
            url = f"https://uploads.mangadex.org/covers/{self.mangadex_id}/{filename}"
            res = requests.get(url)
            res.raise_for_status()

            self.cover_image_data = res.content
            image = Image.open(io.BytesIO(self.cover_image_data))

            # Wait for canvas size update
            self.cover_preview_canvas.update_idletasks()
            canvas_width = self.cover_preview_canvas.winfo_width()
            canvas_height = self.cover_preview_canvas.winfo_height()

            if canvas_width < 10 or canvas_height < 10:
                # Fallback size
                canvas_width, canvas_height = 280, 380

            # Scale image to fit within canvas
            max_width = canvas_width - 20
            max_height = canvas_height - 20

            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            self.preview_image = ImageTk.PhotoImage(image)
            self.cover_preview_canvas.delete("all")
            self.cover_preview_canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=self.preview_image,
                anchor="center"
            )
            self.use_cover_btn["state"] = "normal"

        except Exception as e:
            messagebox.showerror("Error", f"Failed to preview cover:\n{e}")

    def use_previewed_cover(self):
        if not self.cover_image_data:
            return

        # Save as current CBZ cover
        self.cover_data = self.cover_image_data
        self.cover_name = "folder.jpg"

        # Display it in the right panel
        image = Image.open(io.BytesIO(self.cover_data))
        image.thumbnail((280, 380))
        self.cover_image = ImageTk.PhotoImage(image)

        self.cover_canvas.delete("all")
        self.cover_canvas.create_image(140, 190, image=self.cover_image)


if __name__ == "__main__":
    try:
        app = ComicMetadataEditor()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Press ENTER to exit...")
