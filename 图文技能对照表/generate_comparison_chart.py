# -*- coding: utf-8 -*-
"""
把某个角色的 Buff-Debuff 成品 + 技能图标 成品，按顺序拼成一张带中文标签的
图文对照图，方便一次性核对全套图标。

标签数据来自同目录下 labels/<角色名>.json（不进 git，内容来自具体需求表，
可能含未发布信息）；labels/_example.json 是进 git 的占位示例，展示怎么写。

用法：python generate_comparison_chart.py <角色名>
"""
from PIL import Image, ImageDraw, ImageFont
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)  # 图文技能对照表/ 的上一级，即项目根目录
SKILL_OUT_ROOT = os.path.join(ROOT, "技能图标", "合成成品")
BUFF_OUT_ROOT = os.path.join(ROOT, "Buff-Debuff", "合成成品")
LABELS_DIR = os.path.join(SCRIPT_DIR, "labels")

COLS = 5
CELL_W, CELL_H = 180, 200
ICON_SIZE = 96


def load_labels(char_name):
    path = os.path.join(LABELS_DIR, f"{char_name}.json")
    example_path = os.path.join(LABELS_DIR, "_example.json")
    if not os.path.exists(path):
        print(f"[提示] 未找到 {path}，先用 {example_path} 跑一遍占位示例。")
        path = example_path
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_source_dir(source):
    if source == "skill":
        return SKILL_OUT_ROOT
    if source == "buff":
        return BUFF_OUT_ROOT
    raise ValueError(f"未知来源类型: {source}（只支持 skill / buff）")


def generate(char_name):
    items = load_labels(char_name)
    out_dir = os.path.join(SCRIPT_DIR, char_name)
    os.makedirs(out_dir, exist_ok=True)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    rows = (len(items) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL_W, rows * CELL_H), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)

    missing = []
    for idx, item in enumerate(items):
        label = item["label"]
        source = item["source"]
        fname = item["file"]
        r, c = divmod(idx, COLS)
        x0, y0 = c * CELL_W, r * CELL_H
        draw.rectangle([x0 + 2, y0 + 2, x0 + CELL_W - 2, y0 + CELL_H - 2], outline=(220, 220, 220), width=1)
        draw.text((x0 + 8, y0 + 6), f"{idx + 1}.", fill=(120, 120, 120), font=font_small)

        src_dir = os.path.join(resolve_source_dir(source), char_name)
        fpath = os.path.join(src_dir, fname)
        if os.path.exists(fpath):
            icon = Image.open(fpath).convert("RGBA").resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
            sheet.paste(icon, (x0 + (CELL_W - ICON_SIZE) // 2, y0 + 24), icon)
        else:
            missing.append(fname)
            box = [x0 + (CELL_W - ICON_SIZE) // 2, y0 + 24,
                   x0 + (CELL_W - ICON_SIZE) // 2 + ICON_SIZE, y0 + 24 + ICON_SIZE]
            draw.rectangle(box, outline=(255, 0, 0), width=2)
            draw.text((x0 + 20, y0 + 24 + ICON_SIZE // 2 - 10), "缺图", fill=(200, 0, 0), font=font)

        max_chars = 12
        lines = [label[i:i + max_chars] for i in range(0, len(label), max_chars)]
        ty = y0 + 24 + ICON_SIZE + 6
        for line in lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=font_small)
            tw = bbox[2] - bbox[0]
            draw.text((x0 + (CELL_W - tw) // 2, ty), line, fill=(40, 40, 40), font=font_small)
            ty += 18

    out_path = os.path.join(out_dir, f"{char_name}_图文对照表.png")
    sheet.save(out_path)
    print(f"保存至 {out_path}，共 {len(items)} 项，缺图 {len(missing)} 个：{missing}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python generate_comparison_chart.py <角色名>")
        sys.exit(1)
    generate(sys.argv[1])
