import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import json
import shutil
import glob
import re

# [STYLE CONFIGURATION]
BOX_COLOR_RED = "red"
BOX_COLOR_BLUE = "blue"
BOX_WIDTH = 2
FONT_GUIDE = ("Arial", 16, "bold")
FONT_STATUS = ("Arial", 12)

class DropTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Classification Tool - SAVE vs DROP")
        self.root.geometry("1400x900")
        
        # State
        self.image_list = []
        self.current_index = 0
        self.base_dir = ""
        self.save_dir = None
        self.drop_dir = None
        
        self.tk_image = None
        self.raw_pil_image = None
        
        # UI Setup
        self.setup_ui()
        
    def setup_ui(self):
        # 1. Top Frame (Status & Buttons)
        top_frame = tk.Frame(self.root, height=50)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        # Buttons (Visual Aid)
        btn_frame = tk.Frame(top_frame)
        btn_frame.pack(side=tk.LEFT)
        
        self.btn_open = tk.Button(btn_frame, text="1. Open Folder", command=self.open_directory, height=2, width=15)
        self.btn_open.pack(side=tk.LEFT, padx=5)
        
        self.btn_back = tk.Button(btn_frame, text="< Back (B)", command=self.undo, height=2, width=15, bg="#eeeeee")
        self.btn_back.pack(side=tk.LEFT, padx=5)
        
        self.btn_save = tk.Button(btn_frame, text="SAVE (S)", command=self.save_current, height=2, width=15, bg="#ddffdd")
        self.btn_save.pack(side=tk.LEFT, padx=5)
        
        self.btn_drop = tk.Button(btn_frame, text="DROP (D)", command=self.drop_current, height=2, width=15, bg="#ffdddd")
        self.btn_drop.pack(side=tk.LEFT, padx=5)
        
        # Status Label
        self.lbl_status = tk.Label(top_frame, text="Open a folder to start.", font=FONT_STATUS)
        self.lbl_status.pack(side=tk.LEFT, padx=15)
        
        # 2. Canvas Frame
        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="gray",
                                yscrollcommand=self.v_scroll.set,
                                xscrollcommand=self.h_scroll.set,
                                cursor="arrow")
        
        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)
        
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 3. Bottom Guide Label
        bottom_frame = tk.Frame(self.root, height=40, bg="#dddddd")
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.lbl_guide = tk.Label(bottom_frame, text="단축키: [S] Save  |  [D] Drop  |  [B] Back", font=FONT_GUIDE, bg="#dddddd", fg="#333333")
        self.lbl_guide.pack(pady=10)
        
        # 4. Keyboard Binds (Global)
        self.root.bind("<s>", lambda e: self.save_current())
        self.root.bind("<S>", lambda e: self.save_current())
        self.root.bind("<d>", lambda e: self.drop_current())
        self.root.bind("<D>", lambda e: self.drop_current())
        self.root.bind("<b>", lambda e: self.undo())
        self.root.bind("<B>", lambda e: self.undo())
        # Keep arrow keys as backup
        self.root.bind("<Left>", lambda e: self.undo())
        
        # --- Mouse Wheel Scrolling ---
        self.root.bind("<MouseWheel>", self._on_mousewheel)
        self.root.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        # Linux
        self.root.bind("<Button-4>", self._on_mousewheel)
        self.root.bind("<Button-5>", self._on_mousewheel)
        self.root.bind("<Shift-Button-4>", self._on_shift_mousewheel)
        self.root.bind("<Shift-Button-5>", self._on_shift_mousewheel)

    def _on_mousewheel(self, event):
        """Vertical scroll logic"""
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        elif event.delta:
            if event.delta > 0:
                self.canvas.yview_scroll(-1, "units")
            else:
                self.canvas.yview_scroll(1, "units")

    def _on_shift_mousewheel(self, event):
        """Horizontal scroll logic (Shift + Wheel)"""
        if event.num == 4:
            self.canvas.xview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.xview_scroll(1, "units")
        elif event.delta:
            if event.delta > 0:
                self.canvas.xview_scroll(-1, "units")
            else:
                self.canvas.xview_scroll(1, "units")

    def open_directory(self):
        directory = filedialog.askdirectory()
        if not directory:
            return
            
        self.base_dir = directory
        
        # Setup Output Dirs
        self.save_dir = directory + "_save"
        self.drop_dir = directory + "_drop"
        
        for d in [self.save_dir, self.drop_dir]:
            if not os.path.exists(d):
                try:
                    os.makedirs(d)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create dir: {d}\n{e}")
                    return
        
        # Load Images
        search_pattern = os.path.join(directory, "**", "*.jpg")
        all_jpgs = glob.glob(search_pattern, recursive=True)
        self.image_list = sorted(all_jpgs)
        
        if not self.image_list:
            messagebox.showerror("Error", f"No .jpg files found in: {directory}")
            return
            
        # Resume Logic
        self.resume_progress()
        self.load_image()
        
        # Ensure focus is on the main window for key binds to work
        self.root.focus_set()

    def load_progress(self):
        if not self.save_dir: return 0
        json_path = os.path.join(self.save_dir, "progress_drop.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("last_index", 0)
            except:
                pass
        return 0

    def resume_progress(self):
        last_idx = self.load_progress()
        if last_idx > 0:
            if messagebox.askyesno("Resume", f"Resume from index {last_idx}?"):
                if 0 <= last_idx < len(self.image_list):
                    self.current_index = last_idx
                else:
                    self.current_index = 0
            else:
                self.current_index = 0
        else:
            self.current_index = 0
            
    def save_progress_file(self):
        if not self.save_dir: return
        data = {
            "last_index": self.current_index,
            "total": len(self.image_list)
        }
        json_path = os.path.join(self.save_dir, "progress_drop.json")
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to auto-save progress: {e}")

    def load_image(self):
        if self.current_index >= len(self.image_list):
            self.tk_image = None
            self.canvas.delete("all")
            self.lbl_status.config(text=f"All images processed! ({len(self.image_list)}/{len(self.image_list)})")
            messagebox.showinfo("Done", "모든 이미지가 처리되었습니다!")
            return
            
        img_path = self.image_list[self.current_index]
        self.lbl_status.config(text=f"[{self.current_index+1}/{len(self.image_list)}] {os.path.basename(img_path)}")
        
        try:
            pil_img = Image.open(img_path)
            self.raw_pil_image = pil_img
            self.tk_image = ImageTk.PhotoImage(pil_img)
            
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, pil_img.width, pil_img.height))
            self.canvas.create_image(0, 0, image=self.tk_image, anchor=tk.NW)
            
            # Visualize Labels
            self.load_existing_labels()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def load_existing_labels(self):
        """
        Load and visualize existing labels from the corresponding JSON file.
        - Box: Red outline
        - Polygon: Blue outline
        """
        if not self.tk_image: return
        
        current_img_path = self.image_list[self.current_index]
        basename = os.path.basename(current_img_path)
        base_name_no_ext = os.path.splitext(basename)[0]
        json_path = os.path.join(os.path.dirname(current_img_path), base_name_no_ext + ".json")
        
        if not os.path.exists(json_path):
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            labeling_info = data.get("labelingInfo", [])
            
            for item in labeling_info:
                # 1. Box
                if "box" in item:
                    box_data = item["box"]
                    loc_list = box_data.get("location", [])
                    # location could be a list of dicts
                    for loc in loc_list:
                        x = loc.get("x", 0)
                        y = loc.get("y", 0)
                        w = loc.get("width", 0)
                        h = loc.get("height", 0)
                        self.canvas.create_rectangle(x, y, x+w, y+h, outline=BOX_COLOR_RED, width=BOX_WIDTH, tags="existing_label")
                        
                # 2. Polygon
                if "polygon" in item:
                    poly_data = item["polygon"]
                    loc_list = poly_data.get("location", [])
                    for loc in loc_list:
                        # loc is like {"x1": 100, "y1": 100, "x2": 105, "y2": 105, ...}
                        # We need to flatten this to [x1, y1, x2, y2, ...]
                        coords = []
                        i = 1
                        while True:
                            kx = f"x{i}"
                            ky = f"y{i}"
                            if kx in loc and ky in loc:
                                coords.append(loc[kx])
                                coords.append(loc[ky])
                                i += 1
                            else:
                                break
                        
                        if coords:
                            self.canvas.create_polygon(coords, outline=BOX_COLOR_BLUE, width=BOX_WIDTH, fill="", tags="existing_label")
                            
        except Exception as e:
            print(f"Failed to load existing labels for {basename}: {e}")

    def copy_files(self, target_dir):
        if self.current_index >= len(self.image_list): return False
        
        img_path = self.image_list[self.current_index]
        basename = os.path.basename(img_path)
        base_name_no_ext = os.path.splitext(basename)[0]
        json_path = os.path.join(os.path.dirname(img_path), base_name_no_ext + ".json")
        
        try:
            shutil.copy2(img_path, target_dir)
            if os.path.exists(json_path):
                shutil.copy2(json_path, target_dir)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy files: {e}")
            return False

    def save_current(self):
        if not self.save_dir: return
        if self.copy_files(self.save_dir):
            print(f"SAVED: {os.path.basename(self.image_list[self.current_index])}")
            self.current_index += 1
            self.save_progress_file()
            self.load_image()

    def drop_current(self):
        if not self.drop_dir: return
        if self.copy_files(self.drop_dir):
            print(f"DROPPED: {os.path.basename(self.image_list[self.current_index])}")
            self.current_index += 1
            self.save_progress_file()
            self.load_image()

    def undo(self):
        if self.current_index <= 0:
            messagebox.showinfo("First Image", "This is the first image.")
            return

        # 1. Move back
        self.current_index -= 1
        
        # 2. Identify and delete the copied file from _save OR _drop
        img_path = self.image_list[self.current_index]
        basename = os.path.basename(img_path)
        base_name_no_ext = os.path.splitext(basename)[0]
        
        # Possible paths
        save_img = os.path.join(self.save_dir, basename)
        save_json = os.path.join(self.save_dir, base_name_no_ext + ".json")
        
        drop_img = os.path.join(self.drop_dir, basename)
        drop_json = os.path.join(self.drop_dir, base_name_no_ext + ".json")
        
        deleted_log = []
        
        try:
            if os.path.exists(save_img):
                os.remove(save_img)
                deleted_log.append("SAVE_IMG")
            if os.path.exists(save_json):
                os.remove(save_json)
                deleted_log.append("SAVE_JSON")
                
            if os.path.exists(drop_img):
                os.remove(drop_img)
                deleted_log.append("DROP_IMG")
            if os.path.exists(drop_json):
                os.remove(drop_json)
                deleted_log.append("DROP_JSON")
                
            print(f"Undo complete for {basename}: {', '.join(deleted_log)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Undo failed to delete files: {e}")
            
        # 3. Reload
        self.save_progress_file()
        self.load_image()

if __name__ == "__main__":
    root = tk.Tk()
    app = DropTool(root)
    root.mainloop()
