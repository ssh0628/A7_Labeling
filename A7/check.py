import os
import glob
import json
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import re

ORIGINAL_ROOT = r"/Users/sonseunghyeon/Desktop/creamoff/workspace/labeling/테스트용 파일/변환 전"
DEFAULT_INPUT_DIR = r"/Users/sonseunghyeon/Desktop/creamoff/workspace/labeling/테스트용 파일/변환 후"

REJECT_FOLDER_NAME = "_REJECTED"
PROGRESS_FILE = "verify_progress.json"

class VerifyTool:
    def __init__(self, root):
        self.root = root
        self.root.title("A7 Verification Tool (Regex ID Match)")
        self.root.geometry("1400x1000")

        # --- 상태 변수 ---
        self.image_list = []      # (jpg_path, json_path) 튜플 리스트
        self.current_index = 0
        self.input_dir = ""
        self.reject_dir = ""
        
        self.count_ok = 0
        self.count_reject = 0
        
        self.scale_factor = 1.0
        self.img_tk = None
        self.current_jpg_path = None
        self.current_json_path = None
        
        # Undo 스택
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
        self.root.after(100, self.try_auto_load)

    def _init_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        btn_open = tk.Button(top_frame, text="Open Folder", command=self.open_folder, bg="#ddd")
        btn_open.pack(side=tk.LEFT, padx=5)
        
        self.lbl_stats = tk.Label(top_frame, text="Ready", font=("Arial", 14, "bold"))
        self.lbl_stats.pack(side=tk.LEFT, padx=20)
        
        self.var_show_original = tk.BooleanVar(value=True)
        chk_show_orig = tk.Checkbutton(top_frame, text="Show Original (Blue)", variable=self.var_show_original, command=self.refresh_view)
        chk_show_orig.pack(side=tk.RIGHT, padx=5)

        mid_frame = tk.Frame(self.root)
        mid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(mid_frame, bg="#333")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        lbl_guide = tk.Label(bottom_frame, text="[S]: OK (Keep)   |   [R]: Reject (Move)   |   [B]: Back (Undo)", font=("Arial", 12), fg="blue")
        lbl_guide.pack()

    def try_auto_load(self):
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
        print(f"[DEBUG] Loading directory: {path}")
        self.input_dir = path
        self.reject_dir = os.path.join(self.input_dir, REJECT_FOLDER_NAME)
        os.makedirs(self.reject_dir, exist_ok=True)
        
        self.load_file_list()

        if self.load_progress():
             print("[DEBUG] Progress found. Resumed.")
        
        if not self.image_list:
            messagebox.showinfo("Info", "No jpg files found (or all moved).")
            return
            
        self.load_current_image()

    def load_file_list(self):
        jpgs = sorted(glob.glob(os.path.join(self.input_dir, "*.jpg")))
        self.image_list = []
        print(f"[DEBUG] Scanning for jpg files in {self.input_dir}")
        for img_path in jpgs:
            json_path = os.path.splitext(img_path)[0] + ".json"
            if os.path.exists(json_path):
                self.image_list.append((img_path, json_path))
        print(f"[DEBUG] Loaded {len(self.image_list)} valid image-json pairs.")

    def load_progress(self):
        path = os.path.join(self.input_dir, PROGRESS_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saved_idx = data.get("last_index", 0)
                    self.count_ok = data.get("count_ok", 0)
                    self.count_reject = data.get("count_reject", 0)
                    if 0 <= saved_idx < len(self.image_list):
                        self.current_index = saved_idx
                    else:
                        self.current_index = 0
                return True
            except:
                pass
        return False

    def save_progress(self):
        if not self.input_dir: return
        path = os.path.join(self.input_dir, PROGRESS_FILE)
        data = { "last_index": self.current_index, "count_ok": self.count_ok, "count_reject": self.count_reject }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------------------------------------------------------
    # [A] 수정된 extract_id: Regex를 사용하여 A7 제거
    # ---------------------------------------------------------
    def extract_id(self, filename):
        base = os.path.basename(filename)
        name_only = os.path.splitext(base)[0]
        
        # 정규식: _A7_ 혹은 _A7 패턴을 빈문자열로 치환
        # 예: IMG_D_A7_496645 -> IMG_D_496645
        # 예: IMG_A7_001 -> IMG_001
        # re.IGNORECASE는 필요시 사용, 여기선 대문자 A7 가정
        # 일반적인 _A숫자_ 패턴을 모두 지우고 싶다면: r"_A[0-9]+(_|$)"
        # 여기서는 user request대로 A7에 집중하되, 구조를 살림.
        
        # 방법 1: 직접적인 _A7 제거
        # id_str = name_only.replace("_A7", "")
        
        # 방법 2: 정규식 활용 (더 안전)
        # _A7 다음에 _가 오거나 문자열 끝인 경우 처리
        id_str = re.sub(r"_A7", "", name_only)
        
        # 혹시 __가 생기면 _로 치환 (IMG_D__496645 -> IMG_D_496645) - 미관상
        # id_str = id_str.replace("__", "_") 
        # (하지만 원본에서 A6을 지웠을때 나오는 형태와 일치해야하므로, 단순 제거가 나을 수 있음)
        # 사용자 예시: IMG_D_A6_496645  vs IMG_D_A7_496645
        # replace("_A6", "") -> IMG_D_496645
        # replace("_A7", "") -> IMG_D_496645
        # 딱 맞음.
        
        return id_str

    # ---------------------------------------------------------
    # [B] 수정된 find_original_json: 정규화 매칭
    # ---------------------------------------------------------
    def find_original_json(self, file_id):
        # file_id: "IMG_D_496645" (예시)
        print(f"[DEBUG] Searching for Original ID: [{file_id}] in {ORIGINAL_ROOT}")
        for root, dirs, files in os.walk(ORIGINAL_ROOT):
            for f in files:
                if f.endswith(".json"):
                    cand_name = os.path.splitext(f)[0]
                    
                    # 1. 정규화 매칭 (Normalized Match)
                    # 원본 파일명에서 _A1 ~ _A6 제거 후 비교
                    # 예: IMG_D_A6_496645 -> IMG_D_496645
                    cand_norm = re.sub(r"_A[1-6]", "", cand_name)
                    
                    if cand_norm == file_id:
                        print(f"[DEBUG] -> Match found (Normalized): {f}")
                        return os.path.join(root, f)
                    
                    # 2. 포함 여부 확인 (Fallback)
                    # ID의 핵심(고유번호)이 포함되어 있는지 확인
                    # 예: file_id = "IMG_D_496645"
                    # 고유번호 부분이 있는지 체크? (숫자 4자리 이상)
                    match = re.search(r"(\d{4,})", file_id)
                    if match:
                        unique_num = match.group(1)
                        if unique_num in cand_name:
                             # 접두사도 맞는지 확인하면 더 정확함
                             # 여기서는 단순 unique_num 매칭을 우선순위 낮게 둠.
                             # 일단 정규화 매칭 실패시, 숫자 포함되는 파일 리턴? (위험할 수 있음)
                             # -> 사용자 요청: "고유 번호가 포함된 파일을 우선적으로"
                             # 따라서 정규화 매칭이 안되면, 이걸로 퉁칠 수도 있음.
                             pass

        # 재탐색: 못찾았을 경우, 고유 번호 기반으로 느슨한 매칭 시도
        # (위 loop에서 하면 너무 많이 잡힐 수 있으니, 2 pass로 진행)
        match = re.search(r"(\d{4,})", file_id)
        if match:
             unique_num = match.group(1)
             print(f"[DEBUG] Exact match failed. Trying loose match with unique number: {unique_num}")
             for root, dirs, files in os.walk(ORIGINAL_ROOT):
                for f in files:
                    if f.endswith(".json"):
                        if unique_num in f:
                            print(f"[DEBUG] -> Match found (Loose): {f}")
                            return os.path.join(root, f)

        print(f"[DEBUG] Original NOT found for [{file_id}]")
        return None

    def load_current_image(self):
        if 0 <= self.current_index < len(self.image_list):
            img_path, json_path = self.image_list[self.current_index]
            print(f"[DEBUG] Loading [{self.current_index}] {os.path.basename(img_path)}")
            
            self.current_jpg_path = img_path
            self.current_json_path = json_path
            
            self.display_image(img_path)
            self.draw_overlays()
            self.update_stats()
            self.save_progress()
            self.root.focus_set()
        else:
            self.canvas.delete("all")
            self.lbl_stats.config(text="End of List.")
            if self.image_list:
                 messagebox.showinfo("Done", "End of list reached.")

    def display_image(self, img_path):
        try:
            pil_img = Image.open(img_path)
        except Exception as e:
            print(f"[ERROR] Open image failed: {e}")
            return
        
        w, h = pil_img.size
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        max_w, max_h = sw * 0.9, sh * 0.9
        ratio = min(max_w/w, max_h/h)
        
        if ratio < 1.0:
            self.scale_factor = ratio
            pil_img = pil_img.resize((int(w*ratio), int(h*ratio)), Image.Resampling.LANCZOS)
        else:
            self.scale_factor = 1.0
            
        self.img_tk = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0,0,self.img_tk.width(), self.img_tk.height()))
        self.canvas.create_image(0,0, anchor=tk.NW, image=self.img_tk)

    def draw_overlays(self):
        def parse_box(node):
            if "location" in node and isinstance(node["location"], list) and node["location"]:
                loc = node["location"][0]
                return [loc.get('x',0), loc.get('y',0), loc.get('width',0), loc.get('height',0)]
            elif "x" in node:
                return [node.get('x',0), node.get('y',0), node.get('width',0), node.get('height',0)]
            elif isinstance(node, list) and len(node)>=4:
                return node
            return None

        def parse_poly(node):
            pts = []
            if "location" in node and isinstance(node["location"], list) and node["location"]:
                loc = node["location"][0]
                i = 1
                while True:
                    kx, ky = f"x{i}", f"y{i}"
                    if kx in loc and ky in loc:
                        pts.extend([loc[kx], loc[ky]])
                        i+=1
                    else: break
            return pts

        def draw_poly_shape(pts, color, w, txt=None):
            if not pts or len(pts)<4: return
            s_pts = [p * self.scale_factor for p in pts]
            try:
                self.canvas.create_polygon(s_pts, outline=color, fill='', width=w)
                if txt:
                    self.canvas.create_text(s_pts[0], s_pts[1]-10, text=txt, fill=color, anchor=tk.SW, font=("Arial", 10, "bold"))
            except: pass

        # 1. A7 (Green)
        try:
            with open(self.current_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "labelingInfo" in data:
                c_b, c_p = 0, 0
                for item in data["labelingInfo"]:
                    lbl = item.get("label", {}).get("labelName", "A7") if isinstance(item.get("label"), dict) else "A7"
                    if "box" in item:
                        b = parse_box(item["box"])
                        if b:
                            self.draw_box(b, "green", 3, f"A7:{lbl}")
                            c_b+=1
                    if "polygon" in item:
                        p = parse_poly(item["polygon"])
                        if p:
                            draw_poly_shape(p, "green", 3, f"A7:{lbl}")
                            c_p+=1
                print(f"[DEBUG] Drawn A7 (Green) -> Box:{c_b}, Poly:{c_p}")
        except Exception as e:
            print(f"[ERROR] A7 Read Error: {e}")

        # 2. Original (Blue)
        if self.var_show_original.get():
            fid = self.extract_id(self.current_jpg_path)
            orig_path = self.find_original_json(fid)
            if orig_path:
                try:
                    with open(orig_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if "labelingInfo" in data:
                        c_b, c_p = 0, 0
                        for item in data["labelingInfo"]:
                            lbl = item.get("label", {}).get("labelName", "Orig") if isinstance(item.get("label"), dict) else "Orig"
                            if "box" in item:
                                b = parse_box(item["box"])
                                if b:
                                    self.draw_box(b, "blue", 1, f"Org:{lbl}")
                                    c_b+=1
                            if "polygon" in item:
                                p = parse_poly(item["polygon"])
                                if p:
                                    draw_poly_shape(p, "red", 1, f"Org:{lbl}")
                                    c_p+=1
                        print(f"[DEBUG] Drawn Orig (Blue) -> Box:{c_b}, Poly:{c_p}")
                except Exception as e:
                    print(f"[ERROR] Orig Read Error: {e}")

    def draw_box(self, box, color, width, label_text=None):
        x, y, w, h = box
        x *= self.scale_factor
        y *= self.scale_factor
        w *= self.scale_factor
        h *= self.scale_factor
        self.canvas.create_rectangle(x, y, x+w, y+h, outline=color, width=width)
        if label_text:
            self.canvas.create_text(x, y-10, text=label_text, fill=color, anchor=tk.SW, font=("Arial", 10, "bold"))

    def update_stats(self):
        name = os.path.basename(self.current_jpg_path) if self.current_jpg_path else "-"
        idx = self.current_index + 1 if self.image_list else 0
        self.lbl_stats.config(text=f"[{idx}/{len(self.image_list)}] {name} | OK: {self.count_ok} | REJECT: {self.count_reject}")

    def refresh_view(self):
        if self.image_list: self.load_current_image()

    def action_ok(self, event=None):
        if not self.image_list or self.current_index >= len(self.image_list): return
        print(f"[ACTION] OK: {os.path.basename(self.current_jpg_path)}")
        self.history_stack.append({'action':'OK', 'index':self.current_index})
        self.count_ok +=1
        self.current_index +=1
        self.load_current_image()

    def action_reject(self, event=None):
        if not self.image_list or self.current_index >= len(self.image_list): return
        jpg, json_f = self.image_list[self.current_index]
        t_jpg = os.path.join(self.reject_dir, os.path.basename(jpg))
        t_json = os.path.join(self.reject_dir, os.path.basename(json_f))
        print(f"[ACTION] REJECT: {os.path.basename(jpg)}")
        try:
            shutil.move(jpg, t_jpg)
            if os.path.exists(json_f): shutil.move(json_f, t_json)
            self.history_stack.append({'action':'REJECT', 'index':self.current_index, 'src':(jpg, json_f), 'dst':(t_jpg, t_json)})
            self.count_reject +=1
            self.image_list.pop(self.current_index)
            self.load_current_image()
        except Exception as e:
            print(f"[ERROR] Move Failed: {e}")

    def action_back(self, event=None):
        if not self.history_stack: return
        last = self.history_stack.pop()
        print(f"[ACTION] UNDO {last['action']}")
        if last['action']=='OK':
            self.current_index = last['index']
            self.count_ok -=1
            self.load_current_image()
        elif last['action']=='REJECT':
            idx = last['index']
            s_j, s_js = last['src']
            d_j, d_js = last['dst']
            try:
                if os.path.exists(d_j): shutil.move(d_j, s_j)
                if os.path.exists(d_js): shutil.move(d_js, s_js)
                self.image_list.insert(idx, (s_j, s_js))
                self.current_index = idx
                self.count_reject -=1
                self.load_current_image()
            except Exception as e:
                print(f"[ERROR] Undo Failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VerifyTool(root)
    root.mainloop()
