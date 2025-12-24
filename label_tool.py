import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import json
import shutil
import copy
import glob
import re

# 1. TARGET_OUTPUT_DIR: 정상적으로 라벨링(A7)된 결과물이 저장될 폴더
# 2. AMBIGUOUS_DIR: 'Next(애매함)' 버튼 클릭 시 원본 이미지가 격리될 폴더
TARGET_OUTPUT_DIR = None
AMBIGUOUS_DIR = None

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
        self.root.title("Data Labeling Tool - A7 Converter & Ambiguous Filter")
        self.root.geometry("1400x900")
        
        # State
        self.image_list = []
        self.current_index = 0
        self.base_dir = ""
        self.target_dir = TARGET_OUTPUT_DIR
        self.ambiguous_dir = AMBIGUOUS_DIR
        self.tk_image = None
        self.raw_pil_image = None
        self.box_w = 224
        self.box_h = 224
        self.rect_id = None
        
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
        
        self.btn_back = tk.Button(btn_frame, text="< Back (수정/Undo)", command=self.on_back_click, height=2, width=15, bg="#eeeeee")
        self.btn_back.pack(side=tk.LEFT, padx=5)
        
        self.btn_next = tk.Button(btn_frame, text="2. Next (애매함/Skip)", command=self.on_ambiguous_click, height=2, width=20, bg="#ffdddd")
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
            
            self.current_index = 0
            self.load_image()
            
    def load_image(self):
        # Guard: End of list
        if self.current_index >= len(self.image_list):
            self.tk_image = None
            self.canvas.delete("all")
            messagebox.showinfo("Done", "모든 이미지가 처리되었습니다!")
            self.lbl_status.config(text="완료")
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
            
            # Cursor Box
            self.rect_id = self.canvas.create_rectangle(0, 0, 0, 0, outline=BOX_COLOR, width=BOX_WIDTH)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def get_clamped_box_coords(self, mouse_x, mouse_y):
        if not self.raw_pil_image: return 0, 0
        
        # Center the box on mouse
        tl_x = mouse_x - (self.box_w // 2)
        tl_y = mouse_y - (self.box_h // 2)
        
        final_x, final_y = clamp_coordinates(tl_x, tl_y, self.raw_pil_image.width, self.raw_pil_image.height)
        return final_x, final_y

    def on_mouse_move(self, event):
        if not self.tk_image: return
        
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        lx, ly = self.get_clamped_box_coords(canvas_x, canvas_y)
        self.canvas.coords(self.rect_id, lx, ly, lx + self.box_w, ly + self.box_h)
        
    def on_click_canvas(self, event):
        # Guard
        if not self.tk_image: return
        if self.current_index >= len(self.image_list): return
        
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        final_x, final_y = self.get_clamped_box_coords(canvas_x, canvas_y)
        
        # Regular Process: Label and Save
        self.process_image_labeled(final_x, final_y)
        
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
        
        deleted_msg = []
        
        # Try Delete
        try:
            if os.path.exists(target_jpg):
                os.remove(target_jpg)
                deleted_msg.append("Labeled JPG")
            if os.path.exists(target_json):
                os.remove(target_json)
                deleted_msg.append("Labeled JSON")
            if os.path.exists(amb_jpg):
                os.remove(amb_jpg)
                deleted_msg.append("Ambiguous JPG")
                
            print(f"Undo (Deleted): {', '.join(deleted_msg)} for {basename}")
            
        except Exception as e:
            print(f"Undo Error (Delete failed): {e}")
            
        # 3. Load the image again
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

            out_img = os.path.join(self.target_dir, new_img_name)
            out_json = os.path.join(self.target_dir, new_json_name)
            
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
                
            shutil.copy2(current_img_path, out_img)
            
            print(f"Labeled: {basename} -> {out_img}")
            
            # 4. Next
            self.current_index += 1
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

            # Just copy image to AMBIGUOUS_DIR
            out_img = os.path.join(self.ambiguous_dir, basename)
            shutil.copy2(current_img_path, out_img)
            
            print(f"Ambiguous (Skipped): {basename} -> {out_img}")
            
            # Next
            self.current_index += 1
            self.load_image()
            
        except Exception as e:
            messagebox.showerror("Error", f"Ambiguous data move failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LabelTool(root)
    root.mainloop()
