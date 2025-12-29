import os
import glob
import json
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import copy
import re

LABEL_INFO = {
    "A1": {"code": "A1", "name": "A1_구진_플라크", "path_val": "유증상"},
    "A2": {"code": "A2", "name": "A2_비듬_각질_상피성잔고리", "path_val": "유증상"},
    "A3": {"code": "A3", "name": "A3_태선화_과다색소침착", "path_val": "유증상"},
    "A4": {"code": "A4", "name": "A4_농포_여드름", "path_val": "유증상"},
    "A5": {"code": "A5", "name": "A5_미란_궤양", "path_val": "유증상"},
    "A6": {"code": "A6", "name": "A6_결절_종괴", "path_val": "유증상"}
}

INPUT_ROOT = r"/Users/sonseunghyeon/Desktop/creamoff/workspace/labeling/테스트용 파일/변환 전"
PROGRESS_FILE = "relabel_progress.json"

class RelabelTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Relabeling Tool (Smart JSON Replace)")
        self.root.geometry("1400x1000")

        self.input_root = INPUT_ROOT
        # OUTPUT_ROOT는 INPUT_ROOT의 형제 폴더 'relabeled'
        parent_dir = os.path.dirname(self.input_root.rstrip(os.sep))
        self.output_root = os.path.join(parent_dir, "relabeled")
        
        self._create_output_dirs()

        self.image_list = []  # (jpg_path, json_path)
        self.current_index = 0
        self.current_mode = "A1"
        
        self.scale_factor = 1.0
        self.img_tk = None
        self.current_jpg_path = None
        self.current_json_path = None
        
        # Undo 스택
        self.history_stack = []

        self._init_ui()
        self._bind_events()

        # --- 실행 ---
        self.root.after(100, self.start_tool)

    def _create_output_dirs(self):
        if not os.path.exists(self.output_root):
            os.makedirs(self.output_root)
        
        for code in LABEL_INFO.keys():
            p = os.path.join(self.output_root, code)
            os.makedirs(p, exist_ok=True)
        
        os.makedirs(os.path.join(self.output_root, "reject"), exist_ok=True)

    def _init_ui(self):
        # 상단 패널
        top_frame = tk.Frame(self.root, bg="#eee", pady=5)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        # 모드 버튼 [1]~[6]
        self.btn_modes = {}
        for code in sorted(LABEL_INFO.keys()):
            btn = tk.Button(top_frame, text=f"[{code[-1]}] {code}", width=8,
                            command=lambda c=code: self.set_mode(c))
            btn.pack(side=tk.LEFT, padx=2)
            self.btn_modes[code] = btn
        
        tk.Label(top_frame, text=" | ", bg="#eee").pack(side=tk.LEFT)
        
        # 액션 버튼
        tk.Button(top_frame, text="[N] Pass", bg="#ddf", command=self.action_pass).pack(side=tk.LEFT, padx=2)
        tk.Button(top_frame, text="[R] Reject", bg="#fdd", command=self.action_reject).pack(side=tk.LEFT, padx=2)
        tk.Button(top_frame, text="[B] Back", command=self.action_back).pack(side=tk.LEFT, padx=2)
        
        # 정보창
        self.lbl_status = tk.Label(top_frame, text="Ready", font=("Arial", 12, "bold"), bg="#eee", fg="blue")
        self.lbl_status.pack(side=tk.RIGHT, padx=20)
        
        # 캔버스
        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#333", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def _bind_events(self):
        for i in range(1, 7):
            self.root.bind(f"{i}", lambda e, code=f"A{i}": self.set_mode(code))
        
        self.root.bind("<n>", lambda e: self.action_pass())
        self.root.bind("<N>", lambda e: self.action_pass())
        self.root.bind("<r>", lambda e: self.action_reject())
        self.root.bind("<R>", lambda e: self.action_reject())
        self.root.bind("<b>", lambda e: self.action_back())
        self.root.bind("<B>", lambda e: self.action_back())
        
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_mouse_click)

    def start_tool(self):
        # 1. 파일 리스트 (재귀)
        self.load_file_list_recursive()
        
        # 2. Auto-Save 복구 확인
        self.check_resume()
        
        if not self.image_list:
            messagebox.showwarning("Warning", "JPG/JSON 파일을 찾을 수 없습니다.")
            return

        self.update_mode_buttons()
        self.load_current_image()

    def load_file_list_recursive(self):
        print(f"[DEBUG] Recursive scan in {self.input_root}")
        self.image_list = []
        for root, dirs, files in os.walk(self.input_root):
            for f in files:
                if f.lower().endswith(".jpg"):
                    jpg_path = os.path.join(root, f)
                    json_path = os.path.splitext(jpg_path)[0] + ".json"
                    if os.path.exists(json_path):
                        self.image_list.append((jpg_path, json_path))
        self.image_list.sort()
        print(f"[DEBUG] Found {len(self.image_list)} pairs.")

    def check_resume(self):
        prog_path = os.path.join(self.input_root, PROGRESS_FILE)
        if os.path.exists(prog_path):
            try:
                with open(prog_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                last_idx = data.get("last_index", 0)
                last_file = data.get("last_filename", "")
                
                msg = f"이전 작업 기록이 있습니다.\n파일: {last_file}\n인덱스: {last_idx}\n이어하시겠습니까?"
                if messagebox.askyesno("Resume", msg):
                    start_idx = last_idx + 1
                    if 0 <= start_idx <= len(self.image_list):
                        self.current_index = start_idx
            except: pass

    def save_progress(self):
        if not self.input_root: return
        done_idx = self.current_index - 1
        done_name = ""
        if 0 <= done_idx < len(self.image_list):
            done_name = os.path.basename(self.image_list[done_idx][0])
            
        data = {
            "last_index": done_idx,
            "last_filename": done_name,
            "input_root": self.input_root
        }
        try:
            with open(os.path.join(self.input_root, PROGRESS_FILE), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def set_mode(self, code):
        self.current_mode = code
        self.update_mode_buttons()
        self.update_status()

    def update_mode_buttons(self):
        for code, btn in self.btn_modes.items():
            if code == self.current_mode:
                btn.config(bg="yellow", relief="sunken")
            else:
                btn.config(bg="#ddd", relief="raised")
                
    def update_status(self):
        fname = "-"
        if 0 <= self.current_index < len(self.image_list):
            fname = os.path.basename(self.image_list[self.current_index][0])
            folder = os.path.basename(os.path.dirname(self.image_list[self.current_index][0]))
        else:
            folder = "-"
            
        txt = f"[{self.current_index + 1}/{len(self.image_list)}] {fname} ({folder}) | Mode: {self.current_mode}"
        self.lbl_status.config(text=txt)

    def load_current_image(self):
        if 0 <= self.current_index < len(self.image_list):
            self.current_jpg_path, self.current_json_path = self.image_list[self.current_index]
            self.display_image(self.current_jpg_path)
            self.draw_overlays(self.current_json_path)
            self.update_status()
            self.root.focus_set()
        else:
            self.canvas.delete("all")
            self.lbl_status.config(text="End of List.")
            messagebox.showinfo("Done", "End of list reached.")

    def display_image(self, path):
        try:
            pil_img = Image.open(path)
        except: return
        
        w, h = pil_img.size
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        max_w, max_h = sw * 0.85, sh * 0.85
        
        ratio = min(max_w/w, max_h/h)
        if ratio < 1.0:
            new_w, new_h = int(w*ratio), int(h*ratio)
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.scale_factor = ratio
        else:
            self.scale_factor = 1.0
            
        self.img_tk = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0,0,self.img_tk.width(), self.img_tk.height()))
        self.canvas.create_image(0,0, anchor=tk.NW, image=self.img_tk)

    def draw_overlays(self, json_path):
        if not os.path.exists(json_path): return
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "labelingInfo" in data:
                for item in data["labelingInfo"]:
                    # Polygon (Red)
                    if "polygon" in item:
                        pts = self._parse_poly(item["polygon"])
                        if pts:
                            self._draw_poly(pts, "red", 2)
                    # Box (Blue)
                    if "box" in item:
                        box = self._parse_box(item["box"])
                        if box:
                            self._draw_box(box, "blue", 2)
        except: pass

    def _parse_box(self, node):
        try:
            # location: [{"x":...}] or direct keys
            loc_list = node.get("location", [])
            if loc_list:
                loc = loc_list[0]
                return [loc.get('x',0), loc.get('y',0), loc.get('width',0), loc.get('height',0)]
            if "x" in node:
                return [node['x'], node['y'], node['width'], node['height']]
        except: pass
        return None

    def _parse_poly(self, node):
        try:
            loc_list = node.get("location", [])
            if loc_list:
                loc = loc_list[0]
                pts = []
                i=1
                while True:
                    kx, ky = f"x{i}", f"y{i}"
                    if kx in loc and ky in loc:
                        pts.extend([loc[kx], loc[ky]])
                        i+=1
                    else: break
                if len(pts)>=4: return pts
        except: pass
        return None

    def _draw_box(self, box, color, width):
        x, y, w, h = box
        self.canvas.create_rectangle(
            x*self.scale_factor, y*self.scale_factor, 
            (x+w)*self.scale_factor, (y+h)*self.scale_factor, 
            outline=color, width=width
        )

    def _draw_poly(self, pts, color, width):
        s_pts = [p*self.scale_factor for p in pts]
        self.canvas.create_polygon(s_pts, outline=color, fill='', width=width)

    # --- Mouse Interaction ---
    def on_mouse_move(self, event):
        self.canvas.delete("cursor_box")
        mx, my = event.x, event.y
        # 224x224 scaled
        s_size = 224 * self.scale_factor
        
        # Center aligned
        x1 = mx - s_size/2
        y1 = my - s_size/2
        x2 = mx + s_size/2
        y2 = my + s_size/2
        
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#00ff00", width=2, tag="cursor_box")

    def on_mouse_click(self, event):
        if not self.image_list or self.current_index >= len(self.image_list): return
        
        mx, my = event.x, event.y
        # To Image Coords
        ix = mx / self.scale_factor
        iy = my / self.scale_factor
        
        # Center aligned 224 box
        x = int(ix - 112)
        y = int(iy - 112)
        if x < 0: x = 0
        if y < 0: y = 0
        
        box_coords = [x, y, 224, 224] # x,y,w,h
        print(f"[ACTION] Clicked at {box_coords} with mode {self.current_mode}")
        
        self.process_relabel_smart(self.current_mode, box_coords)

    # =========================================================================
    # 4. JSON 변환 로직
    # =========================================================================
    def process_relabel_smart(self, label_code, box_coords):
        orig_jpg, orig_json = self.image_list[self.current_index]
        
        try:
            with open(orig_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except: data = {}
        
        new_data = self.update_json_smart(data, label_code, box_coords, orig_jpg)
        
        # Save
        new_filename = new_data["metaData"]["Raw data ID"]
        dest_dir = os.path.join(self.output_root, label_code)
        
        dest_jpg = os.path.join(dest_dir, new_filename)
        dest_json = os.path.join(dest_dir, os.path.splitext(new_filename)[0] + ".json")
        
        try:
            shutil.copy(orig_jpg, dest_jpg)
            with open(dest_json, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
                
            self.history_stack.append({
                'action': 'RELABEL',
                'index': self.current_index,
                'output_files': [dest_jpg, dest_json]
            })
            self.next_image()
            
        except Exception as e:
            print(f"[ERROR] Save failed: {e}")

    def update_json_smart(self, data, new_code, box, orig_jpg_path):
        """
        요구사항에 맞춘 스마트 JSON 데이터 치환 함수
        """
        if not data: return {}
        new_data = copy.deepcopy(data)
        meta = new_data.get("metaData", {})
        
        # 타겟 정보 조회
        target_info = LABEL_INFO.get(new_code, {})
        new_label_name = target_info.get("name", "Unknown")
        new_path_val = target_info.get("path_val", "")
        
        # 1. 파일명 (Raw data ID) 치환
        # 기존: IMG_D_{기존코드}_{고유번호}.jpg
        # 변경: IMG_D_{새코드}_{고유번호}.jpg
        old_fname = os.path.basename(orig_jpg_path)
        name, ext = os.path.splitext(old_fname)
        
        # 정규식으로 A1~A6 패턴 찾아서 교체
        # 예: IMG_D_A6_123456 -> IMG_D_A1_123456
        new_name_body = re.sub(r"_A[1-6]_", f"_{new_code}_", name)
        
        new_filename = new_name_body + ext
        meta["Raw data ID"] = new_filename
        
        # 2. 병변 및 진단 정보 업데이트
        meta["lesions"] = new_code
        meta["diagnosis"] = "" # 빈값 초기화
        meta["Path"] = new_path_val
        
        # 3. 경로 문자열 (src_path, label_path) 치환
        # LABEL_INFO의 모든 name을 순회하며, 기존 문자열에 포함되어 있으면 새 이름으로 교체
        def smart_replace_path(path_str):
            if not path_str: return ""
            for k, info in LABEL_INFO.items():
                old_name = info["name"] # 예: A6_결절_종괴
                if old_name in path_str:
                    return path_str.replace(old_name, new_label_name)
            return path_str
            
        meta["src_path"] = smart_replace_path(meta.get("src_path", ""))
        meta["label_path"] = smart_replace_path(meta.get("label_path", ""))
        
        # 4. 좌표 정보 (labelingInfo) 업데이트
        x, y, w, h = box
        
        # Box Item
        box_item = {
            "box": {
                "location": [{"x": int(x), "y": int(y), "width": int(w), "height": int(h)}],
                "label": new_label_name,
                "color": "#00ff00"
            }
        }
        
        # Polygon Item (Box 4 corners)
        poly_loc = [
            {"x1": int(x), "y1": int(y), 
             "x2": int(x+w), "y2": int(y),
             "x3": int(x+w), "y3": int(y+h),
             "x4": int(x), "y4": int(y+h)}
        ]
        poly_item = {
            "polygon": {
                "location": poly_loc,
                "label": new_label_name,
                "color": "#00ff00",
                "type": "polygon"
            }
        }
        
        new_data["labelingInfo"] = [poly_item, box_item]
        
        return new_data

    # --- Actions: Pass / Reject ---
    def action_pass(self):
        if not self.image_list: return
        self._copy_action("PASS")

    def action_reject(self):
        if not self.image_list: return
        self._copy_action("REJECT")

    def _copy_action(self, intent):
        orig_jpg, orig_json = self.image_list[self.current_index]
        fname_jpg = os.path.basename(orig_jpg)
        fname_json = os.path.basename(orig_json)
        
        if intent == "REJECT":
            dest_dir = os.path.join(self.output_root, "reject")
        else: # PASS
            # 원본 코드 폴더로 복사
            # 파일명 파싱해서 코드 추출
            parts = fname_jpg.split('_')
            found = "Unknown"
            for p in parts:
                if p in LABEL_INFO:
                    found = p
                    break
            dest_dir = os.path.join(self.output_root, found)
            os.makedirs(dest_dir, exist_ok=True)
            
        dst_jpg = os.path.join(dest_dir, fname_jpg)
        dst_json = os.path.join(dest_dir, fname_json)
        
        try:
            shutil.copy(orig_jpg, dst_jpg)
            if os.path.exists(orig_json):
                shutil.copy(orig_json, dst_json)
                
            self.history_stack.append({
                'action': intent,
                'index': self.current_index,
                'output_files': [dst_jpg, dst_json]
            })
            self.next_image()
        except: pass

    def next_image(self):
        self.save_progress()
        self.current_index += 1
        self.load_current_image()

    def action_back(self):
        if not self.history_stack: return
        last = self.history_stack.pop()
        print(f"[ACTION] UNDO {last['action']}")
        
        for f in last['output_files']:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
        
        self.current_index = last['index']
        self.load_current_image()

if __name__ == "__main__":
    root = tk.Tk()
    app = RelabelTool(root)
    root.mainloop()
