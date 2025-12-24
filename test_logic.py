import json
import os
import copy
import re
"""
    진짜 말 그대로 테스트용 코드입니다.
"""
def clamp_coordinates(x, y, img_w, img_h, box_w=224, box_h=224):
    """
    Ensure the box defined by top-left (x, y) stays within image bounds.
    """
    # Clamp x
    # If the box width is larger than image, just set to 0 (or handle appropriately, but assuming img > 224)
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
    
    # Updated Text Substitution Helper
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

    # 2.A & 2.B. Metadata Transformation
    meta = new_data.get("metaData", {})
    
    if "Raw data ID" in meta:
        meta["Raw data ID"] = replace_text_filename(meta["Raw data ID"])
        
    meta["lesions"] = "A7"
    meta["Path"] = "무증상"
    meta["diagnosis"] = "정상" 
    
    # Use Strict Path Regex for paths
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

def test_transformation_revised():
    # Mock Input with specific Path issues
    mock_inputs = [
        {
            "metaData": {
                "Raw data ID": "IMG_D_A2_001.jpg",
                "lesions": "A2",
                "diagnosis": "비듬",
                "Path": "유증상",
                "src_path": "/라벨링데이터/반려견/피부/일반카메라/유증상/A2_비듬_각질_상피성잔고리",
                "label_path": "/라벨링데이터/반려견/피부/일반카메라/유증상/A2_비듬_각질_상피성잔고리"
            },
            "labelingInfo": ["old_data"]
        }
    ]
    
    print("--- Logic Test (Path Regex) ---")
    for i, data in enumerate(mock_inputs):
        res = transform_json_data(data, 100, 100)
        meta = res["metaData"]
        
        print(f"Original Src: {data['metaData']['src_path']}")
        print(f"Result Src  : {meta['src_path']}")
        
        expected = "/라벨링데이터/반려견/피부/일반카메라/무증상/A7_정상"
        if meta['src_path'] == expected:
            print("  -> PASS")
        else:
            print(f"  -> FAIL (Expected: {expected})")
        
        print(f"Raw data ID: {meta['Raw data ID']} (Expected IMG_D_A7_001.jpg)")


if __name__ == "__main__":
    test_transformation_revised()
