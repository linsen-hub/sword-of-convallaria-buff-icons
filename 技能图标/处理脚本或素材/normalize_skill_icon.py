# -*- coding: utf-8 -*-
"""
把 AI 生成的技能图标定稿（1024x1024，圆形构图，背景可能是纯白或纯黑）
规范化成游戏标准格式：128x128 画布，圆形直径精确 120px，圆外完全透明。

做法（先转透明再裁剪，不是先裁剪再套硬边蒙版）：
1. 用四角像素的平均颜色作为该图背景色参照（不假设一定是白或黑）。
2. 把"跟背景色的距离"直接映射成透明度（渐变斜坡，不是硬阈值一刀切）：
   距离很小 -> alpha=0（背景，彻底透明）；距离够大 -> alpha=255（图案本体）；
   中间的过渡像素按比例给半透明——这样原图边缘本来的羽化/抗锯齿被原样保留
   为渐变透明度，不会残留一圈没转干净的背景色（这是之前"白边"的根因：先按
   硬阈值找外框、再套固定硬边圆形蒙版，蒙版正好卡在"已经很淡但还没归零"的
   过渡像素上，那圈像素被强行保留成不透明，看起来就是一圈白边）。
3. 用这个新 alpha 通道里 alpha>128 的范围重新量出圆的直径和圆心（比按硬阈值
   量更准，取的是真正的视觉半透明中线）。
4. 按 120px/检测直径 算统一缩放比例，缩放整张 RGBA 图（含新算出的透明度）。
5. 把缩放后图像的圆心对准 128x128 画布正中心贴上去。
6. 最后再叠一层 120px 正圆的硬边蒙版做保险裁切（防止光效/毛刺超出圆形范围），
   但这时候圆边缘本身已经是透明渐变收尾，硬边蒙版不会再切出白边。
"""
from PIL import Image, ImageDraw
import numpy as np
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)  # 处理脚本或素材/ 的上一级，即 技能图标/ 本身
SRC_ROOT = os.path.join(ROOT, "角色原图")
OUT_ROOT = os.path.join(ROOT, "合成成品")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "skill_characters.json")
CONFIG_EXAMPLE_PATH = os.path.join(SCRIPT_DIR, "skill_characters.example.json")

TARGET_CIRCLE = 120
CANVAS = 128
SUPERSAMPLE = 4
ALPHA_RAMP_LOW = 8     # 跟背景色距离 <= 这个值，判定为纯背景，alpha=0
ALPHA_RAMP_HIGH = 40   # 跟背景色距离 >= 这个值，判定为图案本体，alpha=255


def bg_to_alpha(im_rgb, ref):
    arr = np.array(im_rgb).astype(float)
    dist = np.linalg.norm(arr - ref, axis=-1)
    alpha = (dist - ALPHA_RAMP_LOW) / (ALPHA_RAMP_HIGH - ALPHA_RAMP_LOW)
    alpha = np.clip(alpha, 0, 1) * 255
    out = np.dstack([arr, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def normalize_icon(src_path, out_path):
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    arr = np.array(im).astype(float)
    corners = np.stack([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]])
    ref = corners.mean(axis=0)

    rgba = bg_to_alpha(im, ref)
    alpha_arr = np.array(rgba)[..., 3]
    ys, xs = np.where(alpha_arr > 128)
    if len(xs) == 0:
        raise RuntimeError(f"检测不到圆形内容：{src_path}")

    diameter = ((xs.max() - xs.min() + 1) + (ys.max() - ys.min() + 1)) / 2
    cx = (xs.min() + xs.max()) / 2
    cy = (ys.min() + ys.max()) / 2

    scale = TARGET_CIRCLE / diameter
    new_w, new_h = round(w * scale), round(h * scale)
    resized = rgba.resize((new_w, new_h), Image.LANCZOS)
    new_cx, new_cy = cx * scale, cy * scale

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    paste_x = round(CANVAS / 2 - new_cx)
    paste_y = round(CANVAS / 2 - new_cy)
    canvas.paste(resized, (paste_x, paste_y), resized)

    big = CANVAS * SUPERSAMPLE
    mask_img = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask_img)
    r = (TARGET_CIRCLE / 2) * SUPERSAMPLE
    d.ellipse([big / 2 - r, big / 2 - r, big / 2 + r, big / 2 + r], fill=255)
    mask_img = mask_img.resize((CANVAS, CANVAS), Image.LANCZOS)

    canvas_alpha = np.array(canvas)[..., 3].astype(float)
    mask_alpha = np.array(mask_img).astype(float)
    final_alpha = (canvas_alpha * (mask_alpha / 255)).astype(np.uint8)
    final_arr = np.array(canvas)
    final_arr[..., 3] = final_alpha

    Image.fromarray(final_arr, mode="RGBA").save(out_path)
    return diameter, (cx, cy)


def load_characters():
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else CONFIG_EXAMPLE_PATH
    if path == CONFIG_EXAMPLE_PATH:
        print(f"[提示] 未找到 {CONFIG_PATH}，先用示例配置跑一遍；"
              f"正式使用请复制一份改成 skill_characters.json（该文件不进 git）。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_character(char_name, mapping):
    src_dir = os.path.join(SRC_ROOT, char_name)
    out_dir = os.path.join(OUT_ROOT, char_name)
    os.makedirs(out_dir, exist_ok=True)
    for src_name, dev_name in mapping.items():
        if src_name.startswith("_"):
            continue
        src_path = os.path.join(src_dir, src_name)
        out_path = os.path.join(out_dir, f"{dev_name}.png")
        if not os.path.exists(src_path):
            print(f"[MISS] {char_name}/{src_name}")
            continue
        diameter, center = normalize_icon(src_path, out_path)
        print(f"[OK] {char_name}/{src_name} -> {dev_name}.png (检测直径={diameter:.0f}px 圆心={center})")


if __name__ == "__main__":
    characters = load_characters()
    targets = sys.argv[1:] or characters.keys()
    for char_name in targets:
        if char_name not in characters:
            print(f"[MISS] 配置里没有角色: {char_name}")
            continue
        run_character(char_name, characters[char_name])
