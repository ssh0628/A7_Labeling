import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import json
import shutil
import copy
import glob
import re
import math

# 1. TARGET_OUTPUT_DIR: 정상적으로 라벨링(A7)된 결과물이 저장될 폴더
# 2. AMBIGUOUS_DIR: 'Next(애매함)' 버튼 클릭 시 원본 이미지가 격리될 폴더
TARGET_OUTPUT_DIR = r"."
AMBIGUOUS_DIR = r"."

# [STYLE CONFIGURATION]
BOX_COLOR = "#27b73c" # 건들지 마세요
BOX_WIDTH = 2 # 건들지 마세요

# --- Shared Logic ---

def clamp_coordinates(x, y, img_w, img_h, box_w=224, box_h=224):
    """
    Ensure the box defined by top-left (x, y) stays within image bounds.
    """
    if img_w < box_w:
        final_x = 0
    else:
        final_x = max(0, min(x, img_w - box_w))
        
    if img_h < box_h:
        final_y = 0
    else:
        final_y = max(0, min(y, img_h - box_h))
        
    return final_x, final_y

def transform_json_data(original_data, top_left_x, top_left_y, box_w=224, box_h=224):
    new_data = copy.deepcopy(original_data)
    
    # Text Substitution Helper
    def replace_text_strict_path(text):
        if not isinstance(text, str): return text
        text = text.replace("유증상", "무증상")
        # Regex: A[1-6]_[^/]+ -> A7_정상
        text = re.sub(r'A[1-6]_[^/]+', 'A7_정상', text)
        return text
        
    def replace_text_filename(text):
        if not isinstance(text, str): return text
        text = re.sub(r'A[1-6]', 'A7', text)
        return text

    # Metadata Transformation
    meta = new_data.get("metaData", {})
    
    if "Raw data ID" in meta:
        meta["Raw data ID"] = replace_text_filename(meta["Raw data ID"])
        
    meta["lesions"] = "A7"
    meta["Path"] = "무증상"
    meta["diagnosis"] = "정상" # Strict Rule
    
    if "src_path" in meta:
        meta["src_path"] = replace_text_strict_path(meta["src_path"])
    if "label_path" in meta:
        meta["label_path"] = replace_text_strict_path(meta["label_path"])
        
    # Labeling Info
    x1 = int(top_left_x)
    y1 = int(top_left_y)
    x2 = x1 + box_w
    y2 = y1
    x3 = x2
    y3 = y1 + box_h
    x4 = x1
    y4 = y3
    x5 = x1
    y5 = y1
    
    polygon_item = {
        "polygon": {
            "color": BOX_COLOR,
            "location": [
                {
                    "x1": x1, "y1": y1,
                    "x2": x2, "y2": y2,
                    "x3": x3, "y3": y3,
                    "x4": x4, "y4": y4,
                    "x5": x5, "y5": y5
                }
            ],
            "label": "A7_정상",
            "type": "polygon"
        }
    }
    
    box_item = {
        "box": {
            "color": BOX_COLOR,
            "location": [
                {"x": x1, "y": y1, "width": box_w, "height": box_h}
            ],
            "label": "A7_정상",
            "type": "box"
        }
    }
    
    new_data["labelingInfo"] = [polygon_item, box_item]
    new_data["inspRejectYn"] = "N"
    
    return new_data

# --- GUI Class ---

class LabelTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Labeling Tool - A7 Converter & Ambiguous Filter (Auto-Resize + Stats)")
        self.root.geometry("1400x900")
        
        # State
        self.image_list = []
        self.current_index = 0
        self.base_dir = ""
        self.target_dir = TARGET_OUTPUT_DIR
        self.ambiguous_dir = AMBIGUOUS_DIR
        self.tk_image = None
        self.raw_pil_image = None
        self.scale_factor = 1.0  # Resize factor (visual / original)
        self.box_w = 224
        self.box_h = 224
        self.rect_id = None
        
        # Stats
        self.count_labeled = 0
        self.count_skipped = 0
        
        # Ensure Dirs (Only if paths are set)
        self.ensure_dirs()
        
        # UI Setup
        self.setup_ui()
        
    def ensure_dirs(self):
        # If paths are empty strings, do not try to create them yet.
        # User might set them before running or we warn at runtime.
        for d in [self.target_dir, self.ambiguous_dir]:
            if d and not os.path.exists(d):
                try:
                    os.makedirs(d)
                    print(f"Created dir: {d}")
                except Exception as e:
                    messagebox.showerror("Config Error", f"Failed to create dir: {d}\n{e}")

    def setup_ui(self):
        # Top Frame
        top_frame = tk.Frame(self.root, height=50)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        # Left Side Buttons
        btn_frame = tk.Frame(top_frame)
        btn_frame.pack(side=tk.LEFT)
        
        self.btn_open = tk.Button(btn_frame, text="1. 폴더 열기", command=self.open_directory, height=2, width=15)
        self.btn_open.pack(side=tk.LEFT, padx=5)
        
        self.btn_back = tk.Button(btn_frame, text="< Back (수정/Undo) [B]", command=self.on_back_click, height=2, width=20, bg="#eeeeee")
        self.btn_back.pack(side=tk.LEFT, padx=5)
        
        self.btn_next = tk.Button(btn_frame, text="2. Next (애매함/Skip) [N]", command=self.on_ambiguous_click, height=2, width=22, bg="#ffdddd")
        self.btn_next.pack(side=tk.LEFT, padx=5)
        
        # Status Label
        self.lbl_status = tk.Label(top_frame, text="폴더를 선택해주세요.", font=("Arial", 12))
        self.lbl_status.pack(side=tk.LEFT, padx=10)
        
        # Canvas Frame
        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="gray",
                                yscrollcommand=self.v_scroll.set,
                                xscrollcommand=self.h_scroll.set,
                                cursor="cross")
        
        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)
        
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Events
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_click_canvas)

        # --- Mouse Wheel Scrolling ---
        # Windows/MacOS
        self.root.bind("<MouseWheel>", self._on_mousewheel)
        self.root.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)

        # Linux (Button-4/5)
        self.root.bind("<Button-4>", self._on_mousewheel)
        self.root.bind("<Button-5>", self._on_mousewheel)
        self.root.bind("<Shift-Button-4>", self._on_shift_mousewheel)
        self.root.bind("<Shift-Button-5>", self._on_shift_mousewheel)

        # Keyboard Shortcuts
        self.root.bind("<n>", lambda e: self.on_ambiguous_click())
        self.root.bind("<N>", lambda e: self.on_ambiguous_click())
        self.root.bind("<b>", lambda e: self.on_back_click())
        self.root.bind("<B>", lambda e: self.on_back_click())

    def _on_mousewheel(self, event):
        """Vertical scroll logic"""
        # Linux (Button-4: Up, Button-5: Down)
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
            return
        if event.num == 5:
            self.canvas.yview_scroll(1, "units")
            return

        # Windows/MacOS (event.delta)
        if event.delta:
            # Scroll direction depends on delta sign
            if event.delta > 0:
                self.canvas.yview_scroll(-1, "units") # Scroll up
            else:
                self.canvas.yview_scroll(1, "units")  # Scroll down

    def _on_shift_mousewheel(self, event):
        """Horizontal scroll logic (Shift + Wheel)"""
        # Linux
        if event.num == 4:
            self.canvas.xview_scroll(-1, "units")
            return
        if event.num == 5:
            self.canvas.xview_scroll(1, "units")
            return

        # Windows/MacOS
        if event.delta:
            if event.delta > 0:
                self.canvas.xview_scroll(-1, "units") # Scroll left
            else:
                self.canvas.xview_scroll(1, "units")  # Scroll right
        
    def save_progress(self):
        """
        Auto-save current index and counts to progress.json in TARGET_OUTPUT_DIR.
        """
        if not self.target_dir or not os.path.exists(self.target_dir):
            return
            
        last_file = ""
        if 0 <= self.current_index < len(self.image_list):
            last_file = os.path.basename(self.image_list[self.current_index])
            
        data = {
            "last_index": self.current_index,
            "last_file": last_file,
            "count_labeled": self.count_labeled,
            "count_skipped": self.count_skipped
        }
        
        json_path = os.path.join(self.target_dir, "progress.json")
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            # print(f"Auto-saved: {data}")
        except Exception as e:
            print(f"Failed to auto-save progress: {e}")

    def open_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.base_dir = directory
            
            if not self.target_dir or not self.ambiguous_dir:
                messagebox.showwarning("Warning", "코드 상단의 TARGET_OUTPUT_DIR 및 AMBIGUOUS_DIR 변수가 비어있을 수 있습니다.\n경로를 확인해주세요.")
            
            # Recursive Search
            search_pattern = os.path.join(directory, "**", "*.jpg")
            all_jpgs = glob.glob(search_pattern, recursive=True)
            all_jpgs = sorted(all_jpgs)
            
            # Filter: filenames containing A1~A6
            self.image_list = [f for f in all_jpgs if re.search(r'A[1-6]', os.path.basename(f))]
            
            if not self.image_list:
                messagebox.showerror("Error", f"No proper image files (A1~A6) found in: {directory}")
                return
            
            # --- Resume Logic ---
            self.current_index = 0
            self.count_labeled = 0
            self.count_skipped = 0
            
            if self.target_dir:
                progress_path = os.path.join(self.target_dir, "progress.json")
                if os.path.exists(progress_path):
                    try:
                        with open(progress_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            last_idx = data.get("last_index", 0)
                            
                            # Restore Stats
                            self.count_labeled = data.get("count_labeled", 0)
                            self.count_skipped = data.get("count_skipped", 0)
                            
                        # Confirm Resume
                        if messagebox.askyesno("Resume", f"이전 작업 기록({last_idx}번째)이 있습니다.\n"
                                                         f"- Labeled: {self.count_labeled}\n"
                                                         f"- Skipped: {self.count_skipped}\n"
                                                         f"이어서 하시겠습니까?"):
                            if 0 <= last_idx < len(self.image_list):
                                self.current_index = last_idx
                            else:
                                messagebox.showwarning("Warning", "저장된 인덱스가 범위를 벗어났습니다. 처음부터 시작합니다.")
                                self.current_index = 0
                                self.count_labeled = 0
                                self.count_skipped = 0
                        else:
                            # Reset if user chooses NO
                            self.count_labeled = 0
                            self.count_skipped = 0
                            
                    except Exception as e:
                        print(f"Failed to load progress: {e}")
            
            self.load_image()
            self.save_progress() # Save initial state (0 or resumed)
            
    def load_existing_labels(self):
        """
        Load and visualize existing labels from the corresponding JSON file.
        Scale coordinates by self.scale_factor.
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
            factor = self.scale_factor
            
            for item in labeling_info:
                # 1. Box
                if "box" in item:
                    box_data = item["box"]
                    loc_list = box_data.get("location", [])
                    # location could be a list of dicts
                    for loc in loc_list:
                        # Original Coords
                        x = loc.get("x", 0)
                        y = loc.get("y", 0)
                        w = loc.get("width", 0)
                        h = loc.get("height", 0)
                        
                        # Scaled Coords for Visual
                        sx = x * factor
                        sy = y * factor
                        sw = w * factor
                        sh = h * factor
                        
                        self.canvas.create_rectangle(sx, sy, sx+sw, sy+sh, outline="red", width=2, tags="existing_label")
                        
                # 2. Polygon
                if "polygon" in item:
                    poly_data = item["polygon"]
                    loc_list = poly_data.get("location", [])
                    for loc in loc_list:
                        # loc is like {"x1": 100, "y1": 100, ...}
                        # We need to flatten and scale
                        coords = []
                        i = 1
                        while True:
                            kx = f"x{i}"
                            ky = f"y{i}"
                            if kx in loc and ky in loc:
                                coords.append(loc[kx] * factor)
                                coords.append(loc[ky] * factor)
                                i += 1
                            else:
                                break
                        
                        if coords:
                            self.canvas.create_polygon(coords, outline="blue", width=2, fill="", tags="existing_label")
                            
        except Exception as e:
            print(f"Failed to load existing labels for {basename}: {e}")

    def load_image(self):
        # Update Status Bar with Stats
        status_text = f"[{self.current_index+1}/{len(self.image_list)}]"
        if 0 <= self.current_index < len(self.image_list):
            status_text += f" {os.path.basename(self.image_list[self.current_index])}"
            
        status_text += f" | Labeled: {self.count_labeled} | Skipped: {self.count_skipped}"
        
        self.lbl_status.config(text=status_text)
        
        # Guard: End of list
        if self.current_index >= len(self.image_list):
            self.tk_image = None
            self.canvas.delete("all")
            messagebox.showinfo("Done", "모든 이미지가 처리되었습니다!")
            return
            
        img_path = self.image_list[self.current_index]
        
        try:
            pil_img = Image.open(img_path)
            self.raw_pil_image = pil_img
            
            # --- Auto-Resize Logic ---
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            
            target_w = screen_w * 0.9
            target_h = screen_h * 0.9
            
            img_w, img_h = pil_img.size
            self.scale_factor = 1.0
            
            # Check if scaling is needed
            scale_w = target_w / img_w
            scale_h = target_h / img_h
            
            if scale_w < 1.0 or scale_h < 1.0:
                self.scale_factor = min(scale_w, scale_h)
                
            new_w = int(img_w * self.scale_factor)
            new_h = int(img_h * self.scale_factor)
            
            # Create Resized Image for display
            # Compatibility for older Pillow versions
            resample_method = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
            display_img = pil_img.resize((new_w, new_h), resample_method)
            self.tk_image = ImageTk.PhotoImage(display_img)
            
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, new_w, new_h))
            self.canvas.create_image(0, 0, image=self.tk_image, anchor=tk.NW)
            
            # Cursor Box (Reset ID)
            self.rect_id = self.canvas.create_rectangle(0, 0, 0, 0, outline=BOX_COLOR, width=BOX_WIDTH)
            
            # Load & Visualize Existing Labels
            self.load_existing_labels()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def get_clamped_box_coords(self, mouse_x, mouse_y):
        """
        Returns SCALED coordinates clamped to the RESIZED image.
        Uses this for visual drawing of the cursor box.
        """
        if not self.tk_image: return 0, 0
        
        # Display Box Size
        disp_w = self.box_w * self.scale_factor
        disp_h = self.box_h * self.scale_factor
        
        # Center the box on mouse (Visual Coords)
        tl_x = mouse_x - (disp_w / 2)
        tl_y = mouse_y - (disp_h / 2)
        
        # Clamp to RESIZED image dimensions
        img_w = self.tk_image.width()
        img_h = self.tk_image.height()
        
        final_x = max(0, min(tl_x, img_w - disp_w))
        final_y = max(0, min(tl_y, img_h - disp_h))
        
        return final_x, final_y

    def on_mouse_move(self, event):
        if not self.tk_image: return
        
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        lx, ly = self.get_clamped_box_coords(canvas_x, canvas_y)
        
        # Scaled Dimensions for Visual Box
        disp_w = self.box_w * self.scale_factor
        disp_h = self.box_h * self.scale_factor
        
        self.canvas.coords(self.rect_id, lx, ly, lx + disp_w, ly + disp_h)
        
    def on_click_canvas(self, event):
        # Guard
        if not self.tk_image: return
        if self.current_index >= len(self.image_list): return
        
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Get Visual (Scaled) Coords
        final_x, final_y = self.get_clamped_box_coords(canvas_x, canvas_y)
        
        # Convert to Original Coords for Saving
        orig_x = final_x / self.scale_factor
        orig_y = final_y / self.scale_factor
        
        # Regular Process: Label and Save
        self.process_image_labeled(orig_x, orig_y)
        
    def on_ambiguous_click(self):
        # Guard
        if not self.tk_image: return
        if self.current_index >= len(self.image_list): return
        
        # Ambiguous Process: Just Copy
        self.process_image_ambiguous()
        
    def on_back_click(self):
        # Back Logic
        if self.current_index <= 0:
            messagebox.showinfo("First Image", "첫 번째 이미지입니다.")
            return
            
        # 1. Decrement Index to go to "previous" image (which is the one we want to undo)
        self.current_index -= 1
        
        # 2. Cleanup output for this image
        prev_img_path = self.image_list[self.current_index]
        basename = os.path.basename(prev_img_path)
        base_name_no_ext = os.path.splitext(basename)[0]
        
        # Calculate potential output paths to delete
        
        # A. Labeled Paths (TARGET_OUTPUT_DIR)
        new_base = re.sub(r'A[1-6]', 'A7', base_name_no_ext)
        if new_base == base_name_no_ext and "A7" not in new_base:
            new_base += "_A7"
            
        target_jpg = os.path.join(self.target_dir, new_base + ".jpg")
        target_json = os.path.join(self.target_dir, new_base + ".json")
        
        # B. Ambiguous Path (AMBIGUOUS_DIR)
        amb_jpg = os.path.join(self.ambiguous_dir, basename)
        
        deleted_count_labeled = False
        deleted_count_skipped = False
        
        deleted_msg = []
        
        # Try Delete
        try:
            if os.path.exists(target_jpg):
                os.remove(target_jpg)
                deleted_msg.append("Labeled JPG")
                deleted_count_labeled = True # Was labeled
                
            if os.path.exists(target_json):
                os.remove(target_json)
                deleted_msg.append("Labeled JSON")
                
            if os.path.exists(amb_jpg):
                os.remove(amb_jpg)
                deleted_msg.append("Ambiguous JPG")
                deleted_count_skipped = True # Was skipped
                
            print(f"Undo (Deleted): {', '.join(deleted_msg)} for {basename}")
            
            # Decrement Stats
            if deleted_count_labeled:
                self.count_labeled = max(0, self.count_labeled - 1)
            elif deleted_count_skipped:
                self.count_skipped = max(0, self.count_skipped - 1)
            
        except Exception as e:
            print(f"Undo Error (Delete failed): {e}")
            
        # 3. Load the image again + Auto Save
        self.save_progress() # Save the decremented index and stats
        self.load_image()

    def process_image_labeled(self, x, y):
        current_img_path = self.image_list[self.current_index]
        basename = os.path.basename(current_img_path)
        base_name_no_ext = os.path.splitext(basename)[0]
        json_path = os.path.join(os.path.dirname(current_img_path), base_name_no_ext + ".json")
        
        if not os.path.exists(json_path):
            messagebox.showerror("Error", f"JSON not found: {json_path}")
            return # Block progress
            
        try:
            # 1. Read & Transform
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # x, y are ORIGINAL coordinates here
            new_data = transform_json_data(data, x, y, self.box_w, self.box_h)
            
            # 2. Filename Generation
            new_base = re.sub(r'A[1-6]', 'A7', base_name_no_ext)
            if new_base == base_name_no_ext and "A7" not in new_base:
                new_base += "_A7"
                
            new_img_name = new_base + ".jpg"
            new_json_name = new_base + ".json"
            
            # 3. Save to TARGET_OUTPUT_DIR
            if not self.target_dir:
                messagebox.showerror("Error", "TARGET_OUTPUT_DIR is not set!")
                return
            
            # Ensure target output directory exists (safe check)
            if not os.path.exists(self.target_dir):
                 os.makedirs(self.target_dir)

            out_img = os.path.join(self.target_dir, new_img_name)
            out_json = os.path.join(self.target_dir, new_json_name)
            
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
                
            shutil.copy2(current_img_path, out_img)
            
            print(f"Labeled: {basename} -> {out_img}")
            
            # 4. Next & Save
            self.count_labeled += 1
            print(f"DEBUG: Label Count incremented to {self.count_labeled}")
            self.current_index += 1
            self.save_progress()
            self.load_image()
            
        except Exception as e:
            messagebox.showerror("Error", f"Labeling failed: {e}")

    def process_image_ambiguous(self):
        current_img_path = self.image_list[self.current_index]
        basename = os.path.basename(current_img_path)
        
        try:
            if not self.ambiguous_dir:
                messagebox.showerror("Error", "AMBIGUOUS_DIR is not set!")
                return
            
            if not os.path.exists(self.ambiguous_dir):
                os.makedirs(self.ambiguous_dir)

            # Just copy image to AMBIGUOUS_DIR
            out_img = os.path.join(self.ambiguous_dir, basename)
            shutil.copy2(current_img_path, out_img)
            
            print(f"Ambiguous (Skipped): {basename} -> {out_img}")
            
            # Next & Save
            self.count_skipped += 1
            print(f"DEBUG: Skip Count incremented to {self.count_skipped}")
            self.current_index += 1
            self.save_progress()
            self.load_image()
            
        except Exception as e:
            messagebox.showerror("Error", f"Ambiguous data move failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LabelTool(root)
    root.mainloop()
