# -*- coding: utf-8 -*-
"""
把 AI 生成的技能图标定稿（1024x1024，圆形构图，背景可能是纯白或纯黑）
规范化成游戏标准格式：128x128 画布，圆形直径精确 120px，圆外完全透明。

有两种抠图模式，脚本自动选：

【通道贴图模式】（推荐，只要 圆形通道贴图.png 存在就自动启用）
外部背景完全由圆形通道贴图决定，不做任何按颜色抠图：
1. 先量出通道贴图里圆的实际外接框（alpha>=128 的范围），这就是"图标要撑满的目标"。
   贴图可以是 128x128 整张画布（圆周围自带留白），也可以是别的尺寸（会先缩到 128）。
2. 再量出每张原图里圆的实际外接框和圆心（用"和背景色的色差"只做测量用途，不用
   来定最终 alpha），按两者比例缩放，让原图的圆正好撑满通道圆、圆心对准通道圆心。
   不认死 120px：原图的圆有的顶满 1024 画布、有的四周留一圈白边（实测同一批里
   直径能差 100px），都会被自动拉到同一个大小，不需要手工给每张图指定缩放比例。
3. 缩放时按 OVERSCAN_PX 多放大一点点，让原图圆边缘那一圈白色羽化过渡溢出到通道圆
   外面、被裁掉。原图圆的外轮廓不是硬边，边界上有 1~3px（1024 尺度）半白半彩的
   过渡像素；如果只是"刚好撑满"，这圈过渡正好落在通道圆最外圈，成品圆周就会看到
   一圈白边（实测边缘会出现 RGB 255,255,255 的纯白像素）。
4. 直接把通道贴图的灰度/alpha 当成成品 alpha：圆内像素 100% 原样保留，圆外一律
   裁掉。这样圆环高光白、星芒白这些"接近背景色但属于画面本体"的像素不会再被打穿
   （旧的按色差抠图模式会把它们误判成背景，这是"圆环中心白色被擦掉"的根因）。

【色差抠图模式】（回退用：通道贴图文件不存在时）
按"跟背景色的距离"映射透明度的老逻辑，圆内接近背景色的高光会被误擦，只在没有
通道贴图时兜底：
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
# 圆形 alpha 通道贴图：白=保留、黑=裁掉，尺寸应为 TARGET_CIRCLE x TARGET_CIRCLE。
# 放在本脚本同目录。存在就走通道贴图模式，不存在就回退到按色差抠图。
CIRCLE_MASK_PATH = os.path.join(SCRIPT_DIR, "圆形通道贴图.png")

TARGET_CIRCLE = 120
CANVAS = 128
SUPERSAMPLE = 4
ALPHA_RAMP_LOW = 8     # 跟背景色距离 <= 这个值，判定为纯背景，alpha=0
ALPHA_RAMP_HIGH = 40   # 跟背景色距离 >= 这个值，判定为图案本体，alpha=255
# 通道贴图模式下的"过冲"像素数：让原图的圆比通道圆再大这么多像素（成品尺度），
# 把原图圆边缘那一圈白色羽化过渡推到通道圆外面裁掉，避免成品圆周留一圈白边。
# 实测原图圆边缘有 1~3px（1024 尺度）的半透明白色过渡，换算到 128 成品不足 1px，
# 但正好压在通道圆最外圈上，视觉上就是明显的白边。
OVERSCAN_PX = 1.0


def load_circle_mask():
    """读圆形通道贴图，返回 (128x128 alpha 数组, 圆的外接框)。

    贴图可以是 128x128 整张画布（圆周围自带留白），也可以是 120x120 只有圆本身：
    - 尺寸 == CANVAS：原样当成品 alpha，圆在画布里的位置由贴图自己决定。
    - 其它尺寸：先缩到 CANVAS 再用，保证 mask 始终是成品画布尺寸。
    通道来源：有 alpha 通道的用 alpha，纯 RGB/灰度图用灰度（白=保留、黑=裁掉）。

    返回的外接框 (x0, y0, x1, y1) 是"半透明中线"（alpha>=128）的范围，用来告诉
    调用方圆实际有多大、圆心在哪，图标要撑满的就是这个范围。

    不存在就返回 (None, None)，调用方回退到色差抠图模式。
    """
    if not os.path.exists(CIRCLE_MASK_PATH):
        return None, None
    mask = Image.open(CIRCLE_MASK_PATH)
    mask = mask.getchannel("A") if mask.mode in ("RGBA", "LA") else mask.convert("L")
    if mask.size != (CANVAS, CANVAS):
        print(f"[提示] 圆形通道贴图尺寸是 {mask.size}，按成品画布 {CANVAS}x{CANVAS} 缩放使用。")
        mask = mask.resize((CANVAS, CANVAS), Image.LANCZOS)

    arr = np.array(mask).astype(float)
    ys, xs = np.where(arr >= 128)
    if len(xs) == 0:
        raise RuntimeError(f"圆形通道贴图里找不到不透明区域：{CIRCLE_MASK_PATH}")
    return arr, (xs.min(), ys.min(), xs.max(), ys.max())


def bg_to_alpha(im_rgb, ref):
    arr = np.array(im_rgb).astype(float)
    dist = np.linalg.norm(arr - ref, axis=-1)
    alpha = (dist - ALPHA_RAMP_LOW) / (ALPHA_RAMP_HIGH - ALPHA_RAMP_LOW)
    alpha = np.clip(alpha, 0, 1) * 255
    out = np.dstack([arr, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def normalize_icon(src_path, out_path, circle_mask=None, mask_bbox=None):
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    arr = np.array(im).astype(float)
    corners = np.stack([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]])
    ref = corners.mean(axis=0)

    # 这一步的 alpha 只用来"量圆"（找圆心和直径），圆内高光被误判成背景不影响测量，
    # 因为量的是 alpha>128 区域的外接框，靠的是圆的外轮廓。
    rgba = bg_to_alpha(im, ref)
    alpha_arr = np.array(rgba)[..., 3]
    ys, xs = np.where(alpha_arr > 128)
    if len(xs) == 0:
        raise RuntimeError(f"检测不到圆形内容：{src_path}")

    src_w_px = xs.max() - xs.min() + 1
    src_h_px = ys.max() - ys.min() + 1
    diameter = (src_w_px + src_h_px) / 2
    cx = (xs.min() + xs.max()) / 2
    cy = (ys.min() + ys.max()) / 2

    if circle_mask is not None:
        # 通道贴图模式：不认死 120px，按通道贴图里圆的实际大小算缩放，
        # 让原图的圆正好撑满通道圆——原图圆大小不一（有的顶满画布、有的四周留白）
        # 也能自动对齐，不需要手工给缩放比例。
        mx0, my0, mx1, my1 = mask_bbox
        mask_w = mx1 - mx0 + 1 + OVERSCAN_PX * 2
        mask_h = my1 - my0 + 1 + OVERSCAN_PX * 2
        # 用两个方向里更"紧"的比例，保证撑满通道圆；加了 OVERSCAN 后会略微溢出，
        # 溢出的正是原图圆边缘的白色羽化带，被通道 alpha 裁掉，成品圆周就没有白边。
        scale = min(mask_w / src_w_px, mask_h / src_h_px)
        # 对齐目标是通道圆自己的中心，不是画布中心（贴图的圆可能本来就不居中）
        target_cx = (mx0 + mx1) / 2
        target_cy = (my0 + my1) / 2
    else:
        scale = TARGET_CIRCLE / diameter
        target_cx = target_cy = CANVAS / 2

    new_w, new_h = round(w * scale), round(h * scale)
    new_cx, new_cy = cx * scale, cy * scale
    paste_x = round(target_cx - new_cx)
    paste_y = round(target_cy - new_cy)

    if circle_mask is not None:
        # 贴不透明原图，外部完全由通道贴图裁切，圆内像素原样保留。
        resized = im.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (CANVAS, CANVAS), (0, 0, 0))
        canvas.paste(resized, (paste_x, paste_y))
        final_arr = np.dstack([np.array(canvas), circle_mask]).astype(np.uint8)
    else:
        # 回退模式：按色差得到的 alpha + 程序画的硬边正圆做保险裁切。
        resized = rgba.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        canvas.paste(resized, (paste_x, paste_y), resized)

        big = CANVAS * SUPERSAMPLE
        mask_img = Image.new("L", (big, big), 0)
        d = ImageDraw.Draw(mask_img)
        r = (TARGET_CIRCLE / 2) * SUPERSAMPLE
        d.ellipse([big / 2 - r, big / 2 - r, big / 2 + r, big / 2 + r], fill=255)
        mask_img = mask_img.resize((CANVAS, CANVAS), Image.LANCZOS)

        canvas_alpha = np.array(canvas)[..., 3].astype(float)
        mask_alpha = np.array(mask_img).astype(float)
        final_arr = np.array(canvas)
        final_arr[..., 3] = (canvas_alpha * (mask_alpha / 255)).astype(np.uint8)

    Image.fromarray(final_arr, mode="RGBA").save(out_path)
    return diameter, (cx, cy)


def load_characters():
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else CONFIG_EXAMPLE_PATH
    if path == CONFIG_EXAMPLE_PATH:
        print(f"[提示] 未找到 {CONFIG_PATH}，先用示例配置跑一遍；"
              f"正式使用请复制一份改成 skill_characters.json（该文件不进 git）。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_character(char_name, mapping, circle_mask=None, mask_bbox=None):
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
        diameter, center = normalize_icon(src_path, out_path, circle_mask, mask_bbox)
        print(f"[OK] {char_name}/{src_name} -> {dev_name}.png (原图圆直径={diameter:.0f}px 圆心={center})")


if __name__ == "__main__":
    characters = load_characters()
    circle_mask, mask_bbox = load_circle_mask()
    if circle_mask is not None:
        mx0, my0, mx1, my1 = mask_bbox
        print(f"[模式] 通道贴图模式：{os.path.basename(CIRCLE_MASK_PATH)} 里圆的范围 "
              f"x{mx0}-{mx1} y{my0}-{my1}（{mx1 - mx0 + 1}x{my1 - my0 + 1}px），"
              f"每张原图都会自动缩放到撑满这个圆，圆外按通道裁切、圆内原样保留。")
    else:
        print(f"[模式] 色差抠图模式（没找到 {os.path.basename(CIRCLE_MASK_PATH)}）："
              f"圆内接近背景色的高光可能被误擦，建议放一张圆形通道贴图进来。")
    targets = sys.argv[1:] or characters.keys()
    for char_name in targets:
        if char_name not in characters:
            print(f"[MISS] 配置里没有角色: {char_name}")
            continue
        run_character(char_name, characters[char_name], circle_mask, mask_bbox)
