import os
import glob
import json
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk


ORIGINAL_ROOT = r"/Users/sonseunghyeon/Desktop/creamoff/workspace/labeling/테스트용 파일/변환 전"
DEFAULT_INPUT_DIR = r"/Users/sonseunghyeon/Desktop/creamoff/workspace/labeling/테스트용 파일/변환 후"

REJECT_FOLDER_NAME = "_REJECTED"
PROGRESS_FILE = "verify_progress.json"

class VerifyTool:
    def __init__(self, root):
        self.root = root
        self.root.title("A7 Verification Tool (OK=Keep, REJECT=Move)")
        self.root.geometry("1400x1000")

        # --- 상태 변수 ---
        self.image_list = [] # (jpg_path, json_path) 튜플 리스트
        self.current_index = 0
        self.input_dir = ""
        self.reject_dir = ""
        
        self.count_ok = 0
        self.count_reject = 0
        
        self.scale_factor = 1.0
        self.img_tk = None
        self.current_jpg_path = None
        self.current_json_path = None
        
        # Undo(Back) 스택: {'action': 'OK'|'REJECT', 'index': int, 'files': (jpg, json)}
        self.history_stack = []

        # --- GUI 초기화 ---
        self._init_ui()
        
        # --- 키보드 이벤트 ---
        self.root.bind("<Key-s>", self.action_ok)
        self.root.bind("<Key-r>", self.action_reject)
        self.root.bind("<Key-b>", self.action_back)
        self.root.bind("<Key-S>", self.action_ok)
        self.root.bind("<Key-R>", self.action_reject)
        self.root.bind("<Key-B>", self.action_back)

        # [Auto Load]
        # 실행 후 UI가 준비되면 자동으로 기본 폴더 로드 시도
        self.root.after(100, self.try_auto_load)

    def _init_ui(self):
        # 1. 상단 패널
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        btn_open = tk.Button(top_frame, text="Open Folder", command=self.open_folder, bg="#ddd")
        btn_open.pack(side=tk.LEFT, padx=5)
        
        self.lbl_stats = tk.Label(top_frame, text="Ready", font=("Arial", 14, "bold"))
        self.lbl_stats.pack(side=tk.LEFT, padx=20)
        
        self.var_show_original = tk.BooleanVar(value=True)
        chk_show_orig = tk.Checkbutton(top_frame, text="Show Original (Blue)", variable=self.var_show_original, command=self.refresh_view)
        chk_show_orig.pack(side=tk.RIGHT, padx=5)

        # 2. 중앙 캔버스
        mid_frame = tk.Frame(self.root)
        mid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(mid_frame, bg="#333")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 3. 하단 안내
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        lbl_guide = tk.Label(bottom_frame, text="[S]: OK (Keep)   |   [R]: Reject (Move)   |   [B]: Back (Undo)", font=("Arial", 12), fg="blue")
        lbl_guide.pack()

    def try_auto_load(self):
        """기본 설정된 폴더가 존재하면 자동으로 로드합니다."""
        print(f"[DEBUG] Checking Default Input Dir: {DEFAULT_INPUT_DIR}")
        if os.path.exists(DEFAULT_INPUT_DIR):
            print("[DEBUG] Default dir exists. Auto-loading...")
            self.load_directory(DEFAULT_INPUT_DIR)
        else:
            print("[DEBUG] Default dir does not exist.")

    def open_folder(self):
        initial_dir = DEFAULT_INPUT_DIR if os.path.exists(DEFAULT_INPUT_DIR) else os.getcwd()
        path = filedialog.askdirectory(initialdir=initial_dir, title="Select A7 Output Folder")
        if not path:
            return
        self.load_directory(path)

    def load_directory(self, path):
        """실질적인 폴더 로드 로직"""
        print(f"[DEBUG] Loading directory: {path}")
        self.input_dir = path
        self.reject_dir = os.path.join(self.input_dir, REJECT_FOLDER_NAME)
        os.makedirs(self.reject_dir, exist_ok=True)
        
        self.load_file_list()

        if self.load_progress():
             print("[DEBUG] Progress file found. Resuming...")
             # 자동 로드 시에는 사용자 확인 없이 로드하거나 로그만 남김
             pass 
        
        if not self.image_list:
            print("[DEBUG] No jpg files found.")
            messagebox.showinfo("Info", "No jpg files found (or all moved).")
            return
            
        self.load_current_image()

    def load_file_list(self):
        # JPG 파일 스캔
        jpgs = sorted(glob.glob(os.path.join(self.input_dir, "*.jpg")))
        self.image_list = []
        print(f"[DEBUG] Scanning for jpg files in {self.input_dir}")
        for img_path in jpgs:
            json_path = os.path.splitext(img_path)[0] + ".json"
            if os.path.exists(json_path):
                self.image_list.append((img_path, json_path))
            else:
                print(f"[DEBUG] Skipping {os.path.basename(img_path)} (No JSON found)")
        print(f"[DEBUG] Loaded {len(self.image_list)} valid image-json pairs.")

    def load_progress(self):
        progress_path = os.path.join(self.input_dir, PROGRESS_FILE)
        if os.path.exists(progress_path):
            try:
                with open(progress_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saved_idx = data.get("last_index", 0)
                    self.count_ok = data.get("count_ok", 0)
                    self.count_reject = data.get("count_reject", 0)
                    
                    if 0 <= saved_idx < len(self.image_list):
                        self.current_index = saved_idx
                    else:
                        print(f"[DEBUG] Saved index {saved_idx} out of range (List len: {len(self.image_list)}). Reset to 0.")
                        self.current_index = 0
                print(f"[DEBUG] Progress loaded. Index: {self.current_index}, OK: {self.count_ok}, REJECT: {self.count_reject}")
                return True
            except Exception as e:
                print(f"[ERROR] Error loading progress: {e}")
        return False

    def save_progress(self):
        if not self.input_dir:
            return
        progress_path = os.path.join(self.input_dir, PROGRESS_FILE)
        data = {
            "last_index": self.current_index,
            "count_ok": self.count_ok,
            "count_reject": self.count_reject
        }
        with open(progress_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def extract_id(self, filename):
        base = os.path.basename(filename)
        id_str = ""
        if "_A7" in base:
            id_str = base.split("_A7")[0]
        else:
            id_str = os.path.splitext(base)[0]
        return id_str

    def find_original_json(self, file_id):
        # ORIGINAL_ROOT 재귀 탐색
        print(f"[DEBUG] Searching for Original JSON ID: {file_id}")
        for root, dirs, files in os.walk(ORIGINAL_ROOT):
            for f in files:
                if f.endswith(".json"):
                    name_body = os.path.splitext(f)[0]
                    if name_body == file_id or name_body.startswith(file_id + "_"):
                        full_path = os.path.join(root, f)
                        print(f"[DEBUG] Found Original JSON: {full_path}")
                        return full_path
        print(f"[DEBUG] Original JSON NOT found for ID: {file_id}")
        return None

    def load_current_image(self):
        if 0 <= self.current_index < len(self.image_list):
            img_path, json_path = self.image_list[self.current_index]
            print(f"[DEBUG] Loading Image [{self.current_index}]: {os.path.basename(img_path)}")
            
            self.current_jpg_path = img_path
            self.current_json_path = json_path
            
            self.display_image(img_path)
            self.draw_overlays()
            self.update_stats()
            self.save_progress()
            
            self.root.focus_set()
        else:
            print("[DEBUG] End of list reached.")
            self.canvas.delete("all")
            self.lbl_stats.config(text="End of List.")
            if self.image_list:
                 messagebox.showinfo("Done", "End of list reached.")

    def display_image(self, img_path):
        try:
            pil_img = Image.open(img_path)
        except Exception as e:
            print(f"[ERROR] Failed to open image {img_path}: {e}")
            return
            
        w, h = pil_img.size
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        
        max_w, max_h = sw * 0.9, sh * 0.9
        ratio = min(max_w / w, max_h / h)
        
        if ratio < 1.0:
            new_w, new_h = int(w * ratio), int(h * ratio)
            self.scale_factor = ratio
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            self.scale_factor = 1.0
        
        self.img_tk = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, self.img_tk.width(), self.img_tk.height()))
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)

    def draw_box(self, box, color, width, label_text=None):
        x, y, w, h = box
        x *= self.scale_factor
        y *= self.scale_factor
        w *= self.scale_factor
        h *= self.scale_factor
        
        self.canvas.create_rectangle(x, y, x+w, y+h, outline=color, width=width)
        if label_text:
            self.canvas.create_text(x, y-10, text=label_text, fill=color, anchor=tk.SW, font=("Arial", 10, "bold"))

    def draw_overlays(self):
        # Helper to parse box
        def parse_box(item_node):
            # item_node could be item["box"]
            # Structure A: { "location": [ { "x":... } ] }
            if "location" in item_node and isinstance(item_node["location"], list) and len(item_node["location"]) > 0:
                loc = item_node["location"][0]
                return [loc.get('x',0), loc.get('y',0), loc.get('width',0), loc.get('height',0)]
            # Structure B: { "x": ..., "y": ... }
            elif "x" in item_node:
                return [item_node.get('x',0), item_node.get('y',0), item_node.get('width',0), item_node.get('height',0)]
            # Structure C: [x, y, w, h]
            elif isinstance(item_node, list) and len(item_node) >= 4:
                return item_node
            return None

        # Helper to parse polygon
        def parse_polygon(item_node):
            # item_node could be item["polygon"]
            # Structure: { "location": [ { "x1":..., "y1":..., "x2":... } ] }
            points = []
            if "location" in item_node and isinstance(item_node["location"], list) and len(item_node["location"]) > 0:
                loc = item_node["location"][0]
                # Extract x1, y1, x2, y2 ...
                i = 1
                while True:
                    kx, ky = f"x{i}", f"y{i}"
                    if kx in loc and ky in loc:
                        points.append(loc[kx])
                        points.append(loc[ky])
                        i += 1
                    else:
                        break
            return points

        # Helper to draw polygon
        def draw_poly(points, color, width, label_text=None):
            if not points or len(points) < 4:
                return
            # Scale points
            scaled_points = [p * self.scale_factor for p in points]
            try:
                self.canvas.create_polygon(scaled_points, outline=color, fill='', width=width)
                if label_text:
                    self.canvas.create_text(scaled_points[0], scaled_points[1] - 10, text=label_text, fill=color, anchor=tk.SW, font=("Arial", 10, "bold"))
            except Exception as e:
                print(f"[ERROR] draw_poly failed: {e}")

        # 1. A7 (Green)
        if self.current_json_path and os.path.exists(self.current_json_path):
            try:
                with open(self.current_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if "labelingInfo" in data:
                    count_box = 0
                    count_poly = 0
                    for item in data["labelingInfo"]:
                        # Box
                        if "box" in item:
                            b = parse_box(item["box"])
                            if b:
                                lbl = item.get("label", {}).get("labelName", "A7") if isinstance(item.get("label"), dict) else "A7"
                                self.draw_box(b, "green", 3, f"A7:{lbl}")
                                count_box += 1
                        # Polygon
                        if "polygon" in item:
                            pts = parse_polygon(item["polygon"])
                            if pts:
                                lbl = item.get("label", {}).get("labelName", "A7") if isinstance(item.get("label"), dict) else "A7"
                                draw_poly(pts, "green", 3, f"A7:{lbl}")
                                count_poly += 1
                    print(f"[DEBUG] Drawn A7 -> Box: {count_box}, Poly: {count_poly}")
            except Exception as e:
                print(f"[ERROR] A7 JSON Error: {e}")

        # 2. Original (Blue)
        if self.var_show_original.get() and self.current_jpg_path:
            fid = self.extract_id(self.current_jpg_path)
            orig_path = self.find_original_json(fid)
            if orig_path:
                try:
                    with open(orig_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if "labelingInfo" in data:
                        count_box = 0
                        count_poly = 0
                        for item in data["labelingInfo"]:
                            # Box
                            if "box" in item:
                                b = parse_box(item["box"])
                                if b:
                                    lbl = item.get("label", {}).get("labelName", "Orig") if isinstance(item.get("label"), dict) else "Orig"
                                    self.draw_box(b, "blue", 1, f"Org:{lbl}")
                                    count_box += 1
                            # Polygon
                            if "polygon" in item:
                                pts = parse_polygon(item["polygon"])
                                if pts:
                                    lbl = item.get("label", {}).get("labelName", "Orig") if isinstance(item.get("label"), dict) else "Orig"
                                    draw_poly(pts, "red", 1, f"Org:{lbl}")
                                    count_poly += 1
                        print(f"[DEBUG] Drawn Orig -> Box: {count_box}, Poly: {count_poly}")
                except Exception as e:
                    print(f"[ERROR] Orig JSON Error: {e}")

    def update_stats(self):
        name = os.path.basename(self.current_jpg_path) if self.current_jpg_path else "-"
        total = len(self.image_list)
        idx_display = self.current_index + 1 if self.image_list else 0
        self.lbl_stats.config(text=f"[{idx_display}/{total}] {name} | OK: {self.count_ok} | REJECT: {self.count_reject}")

    def refresh_view(self):
        if self.image_list:
            self.load_current_image()

    def action_ok(self, event=None):
        if not self.image_list or self.current_index >= len(self.image_list):
            return

        print(f"[ACTION] OK: {os.path.basename(self.current_jpg_path)}")
        self.history_stack.append({
            'action': 'OK',
            'index': self.current_index
        })
        
        self.count_ok += 1
        self.current_index += 1
        self.load_current_image()

    def action_reject(self, event=None):
        if not self.image_list or self.current_index >= len(self.image_list):
            return
            
        jpg_src, json_src = self.image_list[self.current_index]
        fname_jpg = os.path.basename(jpg_src)
        fname_json = os.path.basename(json_src)
        
        dst_jpg = os.path.join(self.reject_dir, fname_jpg)
        dst_json = os.path.join(self.reject_dir, fname_json)
        
        print(f"[ACTION] REJECT: Moving {fname_jpg} to {self.reject_dir}")
        try:
            shutil.move(jpg_src, dst_jpg)
            if os.path.exists(json_src):
                shutil.move(json_src, dst_json)
            
            self.history_stack.append({
                'action': 'REJECT',
                'index': self.current_index,
                'src_files': (jpg_src, json_src),
                'dst_files': (dst_jpg, dst_json)
            })
            
            self.count_reject += 1
            self.image_list.pop(self.current_index)
            self.load_current_image()
            
        except Exception as e:
            print(f"[ERROR] Move failed: {e}")
            messagebox.showerror("Error", f"Move failed: {e}")

    def action_back(self, event=None):
        if not self.history_stack:
            print("[DEBUG] History stack empty, cannot Undo.")
            return
            
        last = self.history_stack.pop()
        action = last['action']
        print(f"[ACTION] UNDO {action}")
        
        if action == 'OK':
            self.current_index = last['index']
            self.count_ok -= 1
            self.load_current_image()
            
        elif action == 'REJECT':
            saved_idx = last['index']
            orig_jpg, orig_json = last['src_files']
            moved_jpg, moved_json = last['dst_files']
            
            try:
                if os.path.exists(moved_jpg):
                    shutil.move(moved_jpg, orig_jpg)
                if os.path.exists(moved_json):
                    shutil.move(moved_json, orig_json)
                
                self.image_list.insert(saved_idx, (orig_jpg, orig_json))
                self.current_index = saved_idx
                self.count_reject -= 1
                self.load_current_image()
                
            except Exception as e:
                print(f"[ERROR] Undo Reject failed: {e}")
                messagebox.showerror("Error", f"Undo Reject failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VerifyTool(root)
    root.mainloop()
