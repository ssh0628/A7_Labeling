import os
import glob
import json
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

ORIGINAL_ROOT = r""
DEFAULT_INPUT_DIR = r""
REJECT_FOLDER_NAME = "_REJECTED"

# 진행 상황 저장 파일
PROGRESS_FILE = "verify_progress.json"

# =============================================================================
# 2. 메인 클래스 (VerifyTool)
# =============================================================================
class VerifyTool:
    def __init__(self, root):
        self.root = root
        self.root.title("A7 Verification Tool (OK=Keep, REJECT=Move)")
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

    def open_folder(self):
        initial_dir = DEFAULT_INPUT_DIR if os.path.exists(DEFAULT_INPUT_DIR) else os.getcwd()
        path = filedialog.askdirectory(initialdir=initial_dir, title="Select A7 Output Folder")
        if not path:
            return
        
        self.input_dir = path
        self.reject_dir = os.path.join(self.input_dir, REJECT_FOLDER_NAME)
        os.makedirs(self.reject_dir, exist_ok=True)
        
        self.load_file_list()

        if self.load_progress():
             ans = messagebox.askyesno("Resume", "이전 작업 기록이 있습니다. 이어서 하시겠습니까?")
             if not ans:
                 self.current_index = 0
                 self.count_ok = 0
                 self.count_reject = 0
        
        if not self.image_list:
            messagebox.showinfo("Info", "No jpg files found (or all moved).")
            return
            
        self.load_current_image()

    def load_file_list(self):
        # JPG 파일 스캔
        jpgs = sorted(glob.glob(os.path.join(self.input_dir, "*.jpg")))
        self.image_list = []
        for img_path in jpgs:
            json_path = os.path.splitext(img_path)[0] + ".json"
            if os.path.exists(json_path):
                self.image_list.append((img_path, json_path))
        print(f"Loaded {len(self.image_list)} files.")

    def load_progress(self):
        progress_path = os.path.join(self.input_dir, PROGRESS_FILE)
        if os.path.exists(progress_path):
            try:
                with open(progress_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saved_idx = data.get("last_index", 0)
                    self.count_ok = data.get("count_ok", 0)
                    self.count_reject = data.get("count_reject", 0)
                    
                    # 파일 리스트가 변경되었을 수 있으므로 인덱스 유효성 체크
                    if 0 <= saved_idx < len(self.image_list):
                        self.current_index = saved_idx
                    else:
                        self.current_index = 0
                return True
            except Exception as e:
                print(f"Error loading progress: {e}")
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
        # IMG_123_A7_정상.jpg -> IMG_123
        base = os.path.basename(filename)
        if "_A7" in base:
            return base.split("_A7")[0]
        return os.path.splitext(base)[0]

    def find_original_json(self, file_id):
        # ORIGINAL_ROOT 재귀 탐색
        for root, dirs, files in os.walk(ORIGINAL_ROOT):
            for f in files:
                if f.endswith(".json"):
                    # 정확한 매칭 로직
                    name_body = os.path.splitext(f)[0]
                    # IMG_123.json or IMG_123_meta.json etc. 
                    # 단순 startswith만 하면 IMG_1이 IMG_10에 매칭될 수 있으므로 주의
                    if name_body == file_id or name_body.startswith(file_id + "_"):
                        return os.path.join(root, f)
        return None

    def load_current_image(self):
        if 0 <= self.current_index < len(self.image_list):
            img_path, json_path = self.image_list[self.current_index]
            self.current_jpg_path = img_path
            self.current_json_path = json_path
            
            self.display_image(img_path)
            self.draw_overlays()
            self.update_stats()
            self.save_progress()
            
            # 포커스 유지
            self.root.focus_set()
        else:
            self.canvas.delete("all")
            self.lbl_stats.config(text="End of List.")
            if self.image_list:
                # 마지막 처리 후
                 messagebox.showinfo("Done", "End of list reached.")

    def display_image(self, img_path):
        try:
            pil_img = Image.open(img_path)
        except Exception:
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
        # Box: [x, y, w, h]
        x, y, w, h = box
        x *= self.scale_factor
        y *= self.scale_factor
        w *= self.scale_factor
        h *= self.scale_factor
        
        self.canvas.create_rectangle(x, y, x+w, y+h, outline=color, width=width)
        if label_text:
            self.canvas.create_text(x, y-10, text=label_text, fill=color, anchor=tk.SW, font=("Arial", 10, "bold"))

    def draw_overlays(self):
        # 1. A7 (Green)
        if self.current_json_path and os.path.exists(self.current_json_path):
            try:
                with open(self.current_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if "labelingInfo" in data:
                    for item in data["labelingInfo"]:
                        if "box" in item:
                            bx = item["box"]
                            if isinstance(bx, dict):
                                b = [bx.get('x',0), bx.get('y',0), bx.get('width',0), bx.get('height',0)]
                            else: b = bx
                            lbl = item.get("label", {}).get("labelName", "A7")
                            self.draw_box(b, "green", 3, f"A7:{lbl}")
            except Exception as e:
                print(f"A7 JSON Error: {e}")

        # 2. Original (Blue)
        if self.var_show_original.get() and self.current_jpg_path:
            fid = self.extract_id(self.current_jpg_path)
            orig_path = self.find_original_json(fid)
            if orig_path:
                try:
                    with open(orig_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if "labelingInfo" in data:
                        for item in data["labelingInfo"]:
                            if "box" in item:
                                bx = item["box"]
                                if isinstance(bx, dict):
                                    b = [bx.get('x',0), bx.get('y',0), bx.get('width',0), bx.get('height',0)]
                                else: b = bx
                                lbl = item.get("label", {}).get("labelName", "Orig")
                                self.draw_box(b, "blue", 1, f"Org:{lbl}")
                except Exception as e:
                    print(f"Orig JSON Error: {e}")

    def update_stats(self):
        name = os.path.basename(self.current_jpg_path) if self.current_jpg_path else "-"
        total = len(self.image_list)
        # 1-based index display
        idx_display = self.current_index + 1 if self.image_list else 0
        self.lbl_stats.config(text=f"[{idx_display}/{total}] {name} | OK: {self.count_ok} | REJECT: {self.count_reject}")

    def refresh_view(self):
        if self.image_list:
            self.load_current_image()

    # --- Actions ---

    def action_ok(self, event=None):
        """ OK: Keep file, Next index """
        if not self.image_list or self.current_index >= len(self.image_list):
            return

        # History 기록
        # OK의 경우 파일 이동이 없으므로 단순 인덱스 기록
        self.history_stack.append({
            'action': 'OK',
            'index': self.current_index
        })
        
        self.count_ok += 1
        self.current_index += 1
        self.load_current_image()

    def action_reject(self, event=None):
        """ REJECT: Move file, Pop from list """
        if not self.image_list or self.current_index >= len(self.image_list):
            return
            
        jpg_src, json_src = self.image_list[self.current_index]
        fname_jpg = os.path.basename(jpg_src)
        fname_json = os.path.basename(json_src)
        
        dst_jpg = os.path.join(self.reject_dir, fname_jpg)
        dst_json = os.path.join(self.reject_dir, fname_json)
        
        try:
            shutil.move(jpg_src, dst_jpg)
            if os.path.exists(json_src):
                shutil.move(json_src, dst_json)
            
            # History 기록 (이동된 경로, 원래 리스트에서의 인덱스)
            self.history_stack.append({
                'action': 'REJECT',
                'index': self.current_index,
                'src_files': (jpg_src, json_src),
                'dst_files': (dst_jpg, dst_json)
            })
            
            self.count_reject += 1
            # 리스트에서 제거
            self.image_list.pop(self.current_index)
            # 인덱스는 그대로 (다음 파일이 당겨짐). 
            # 단, 마지막 파일이었다면 index가 len과 같아짐 -> load_current_image에서 처리.
            self.load_current_image()
            
        except Exception as e:
            messagebox.showerror("Error", f"Move failed: {e}")

    def action_back(self, event=None):
        """ UNDO: Revert last action """
        if not self.history_stack:
            return
            
        last = self.history_stack.pop()
        action = last['action']
        
        if action == 'OK':
            # OK 취소: 인덱스 되돌리고 카운트 감소
            self.current_index = last['index']
            self.count_ok -= 1
            self.load_current_image()
            
        elif action == 'REJECT':
            # REJECT 취소: 파일 복귀 -> 리스트 삽입 -> 인덱스 복구 -> 카운트 감소
            saved_idx = last['index']
            orig_jpg, orig_json = last['src_files']
            moved_jpg, moved_json = last['dst_files']
            
            try:
                if os.path.exists(moved_jpg):
                    shutil.move(moved_jpg, orig_jpg)
                if os.path.exists(moved_json):
                    shutil.move(moved_json, orig_json)
                
                # 리스트 복구
                self.image_list.insert(saved_idx, (orig_jpg, orig_json))
                self.current_index = saved_idx
                self.count_reject -= 1
                self.load_current_image()
                
            except Exception as e:
                messagebox.showerror("Error", f"Undo Reject failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VerifyTool(root)
    root.mainloop()
