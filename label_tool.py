import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import json
import shutil
import copy
import glob
import re

TARGET_OUTPUT_DIR = r"" 

# --- Shared Logic ---

def clamp_coordinates(x, y, img_w, img_h, box_w=224, box_h=224):
    """
    Ensure the box defined by top-left (x, y) stays within image bounds.
    """
    # Clamp x
    if img_w < box_w:
        final_x = 0
    else:
        final_x = max(0, min(x, img_w - box_w))
        
    # Clamp y
    if img_h < box_h:
        final_y = 0
    else:
        final_y = max(0, min(y, img_h - box_h))
        
    return final_x, final_y

def transform_json_data(original_data, top_left_x, top_left_y, box_w=224, box_h=224):
    new_data = copy.deepcopy(original_data)
    
    # 2.A. Text Substitution Helper
    def replace_text_strict_path(text):
        if not isinstance(text, str): return text
        # 1. Replace '유증상' -> '무증상'
        text = text.replace("유증상", "무증상")
        # 2. Path Regex: A1~A6 followed by underscore and anything not a slash -> A7_정상
        # This covers directory names like "A2_비듬_각질" => "A7_정상"
        text = re.sub(r'A[1-6]_[^/]+', 'A7_정상', text)
        return text
        
    def replace_text_filename(text):
        if not isinstance(text, str): return text
        # Filename only needs A# -> A7
        text = re.sub(r'A[1-6]', 'A7', text)
        return text

    # 2.B. Metadata Transformation
    meta = new_data.get("metaData", {})
    
    if "Raw data ID" in meta:
        meta["Raw data ID"] = replace_text_filename(meta["Raw data ID"])
        
    meta["lesions"] = "A7"
    meta["Path"] = "무증상"
    meta["diagnosis"] = "정상" # Strict Rule: Overwrite
    
    if "src_path" in meta:
        meta["src_path"] = replace_text_strict_path(meta["src_path"])
    if "label_path" in meta:
        meta["label_path"] = replace_text_strict_path(meta["label_path"])
        
    # 2.C. Labeling Info - Strict Rules
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
    
    # Polygon Structure: List with ONE dictionary
    polygon_item = {
        "polygon": {
            "color": "#27b73c",
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
            "color": "#27b73c",
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
        self.root.title("Data Labeling Tool - Recursive & Custom Output")
        self.root.geometry("1400x900")
        
        # State
        self.image_list = []
        self.current_index = 0
        self.base_dir = ""
        self.output_dir = TARGET_OUTPUT_DIR
        self.tk_image = None
        self.raw_pil_image = None # Keep reference for dimensions
        self.box_w = 224
        self.box_h = 224
        self.rect_id = None
        
        # Determine Output Dir
        self.ensure_output_dir()
        
        # UI Setup
        self.setup_ui()
        
    def ensure_output_dir(self):
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                print(f"Created output directory: {self.output_dir}")
            except Exception as e:
                messagebox.showerror("Config Error", f"Could not create output dir: {self.output_dir}\nError: {e}")
                
    def setup_ui(self):
        # Top Frame
        top_frame = tk.Frame(self.root, height=50)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        self.btn_open = tk.Button(top_frame, text="폴더 열기 (Open Folder)", command=self.open_directory)
        self.btn_open.pack(side=tk.LEFT)
        
        self.lbl_status = tk.Label(top_frame, text=f"저장 경로: {self.output_dir} | 폴더를 선택해주세요.")
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
        self.canvas.bind("<Button-1>", self.on_click)
        
    def open_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.base_dir = directory
            
            # RECURSIVE SEARCH
            # glob search for **/*.jpg with recursive=True
            search_pattern = os.path.join(directory, "**", "*.jpg")
            all_jpgs = glob.glob(search_pattern, recursive=True)
            all_jpgs = sorted(all_jpgs)
            
            # Filter: Check if filename contains A1~A6
            self.image_list = [f for f in all_jpgs if re.search(r'A[1-6]', os.path.basename(f))]
            
            if not self.image_list:
                messagebox.showerror("Error", f"No proper image files (A1~A6) found in: {directory} (Recursive)")
                return
            
            self.current_index = 0
            self.load_image()
            
    def load_image(self):
        # Fix 1: IndexError Prevention
        if self.current_index >= len(self.image_list):
            self.tk_image = None
            self.canvas.delete("all")
            messagebox.showinfo("Done", "모든 이미지가 처리되었습니다! (All images processed)")
            self.lbl_status.config(text=f"완료 - 결과는 {self.output_dir} 확인")
            return
            
        img_path = self.image_list[self.current_index]
        self.lbl_status.config(text=f"[{self.current_index+1}/{len(self.image_list)}] {os.path.basename(img_path)} -> {self.output_dir}")
        
        try:
            pil_img = Image.open(img_path)
            self.raw_pil_image = pil_img
            self.tk_image = ImageTk.PhotoImage(pil_img)
            
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, pil_img.width, pil_img.height))
            self.canvas.create_image(0, 0, image=self.tk_image, anchor=tk.NW)
            
            # Initial Cursor Box (Hidden or at 0,0)
            self.rect_id = self.canvas.create_rectangle(0, 0, 0, 0, outline="#27b73c", width=2)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def get_clamped_box_coords(self, mouse_x, mouse_y):
        if not self.raw_pil_image: return 0, 0
        
        # To make the mouse be at the center of the box:
        # TopLeft = Mouse - Box/2
        tl_x = mouse_x - (self.box_w // 2)
        tl_y = mouse_y - (self.box_h // 2)
        
        # Clamp Logic
        final_x, final_y = clamp_coordinates(tl_x, tl_y, self.raw_pil_image.width, self.raw_pil_image.height)
        return final_x, final_y

    def on_mouse_move(self, event):
        if not self.tk_image: return
        
        # Canvas Scroll Offset
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        lx, ly = self.get_clamped_box_coords(canvas_x, canvas_y)
        
        self.canvas.coords(self.rect_id, lx, ly, lx + self.box_w, ly + self.box_h)
        
    def on_click(self, event):
        # Fix 2: Safety guard
        if not self.tk_image: return
        
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        final_x, final_y = self.get_clamped_box_coords(canvas_x, canvas_y)
        self.process_current_image(final_x, final_y)
        
    def process_current_image(self, x, y):
        # Fix 3: IndexError Prevention Guard
        if self.current_index >= len(self.image_list):
            return

        current_img_path = self.image_list[self.current_index]
        basename = os.path.basename(current_img_path)
        base_name_no_ext = os.path.splitext(basename)[0]
        json_path = os.path.join(os.path.dirname(current_img_path), base_name_no_ext + ".json")
        
        if not os.path.exists(json_path):
            messagebox.showerror("Skip", f"JSON not found: {json_path}\nSkipping this image.")
            self.current_index += 1
            self.load_image()
            return
            
        try:
            # 1. Read JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 2. Transform Data (Uses new Regex Logic)
            new_data = transform_json_data(data, x, y, self.box_w, self.box_h)
            
            # 3. Determine New Filenames (Regex: A1~A6 -> A7)
            new_basename_no_ext = re.sub(r'A[1-6]', 'A7', base_name_no_ext)
            if new_basename_no_ext == base_name_no_ext and "A7" not in new_basename_no_ext:
                 # Safety fallback
                 new_basename_no_ext += "_A7"
            
            new_img_name = new_basename_no_ext + ".jpg"
            new_json_name = new_basename_no_ext + ".json"
            
            # SAVE TO GLOBALLY CONFIGURED OUTPUT DIR
            new_img_path = os.path.join(self.output_dir, new_img_name)
            new_json_path = os.path.join(self.output_dir, new_json_name)
            
            # 4. Save JSON
            with open(new_json_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2) 
            
            # 5. Copy Image
            shutil.copy2(current_img_path, new_img_path)
            
            print(f"Processed: {basename} -> {new_img_name}")
            
            # 6. Next
            self.current_index += 1
            self.load_image()
            
        except Exception as e:
            messagebox.showerror("Error", f"Processing failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LabelTool(root)
    root.mainloop()
