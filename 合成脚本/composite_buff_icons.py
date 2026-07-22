# -*- coding: utf-8 -*-
"""
Buff/Debuff 白色图标自动合成到底图模板。

目录约定（配合 Buff-Debuff/ 下的分层结构）：
  底图模板/            公共底色 + 金框 + 箭头角标素材，所有角色共用
  角色原图/<角色名>/    该角色的原始 1024x1024 白色剪影符号图
  合成成品/<角色名>/    该角色合成后的最终 PNG + 预览联系表
  合成脚本/            本脚本

规则（按实测反馈校准）：
1. 画布基准 = 底图模板 里各底图的实际像素尺寸（引擎实装尺寸，不是128备份）。
2. “安全填充区”不是简单看 alpha==255，而是用画布正中心那个像素的颜色作参照，
   只把颜色足够接近它、且完全不透明的像素当作“真正的底色填充区”——这样金框
   底图（goldframe_*，边框和底色都不透明）也能正确排除掉金色边框，只留中间
   色块。普通纯色底图因为本来就只有一种颜色，这套方法一样适用，不用分两套逻辑。
3. 安全区 = 安全填充区再向内收缩 SAFE_MARGIN_PX（默认 4px），满足“图标不能压
   到描边/金框 + 边缘留够留白”的要求，这个收缩按欧氏距离做，天然贴合圆角/花边形状。
4. 居中锚点用【原始 1024×1024 画布的几何中心】，不裁剪、不用外框中心、也不用
   alpha 重心——裁剪外框会被羽化的极淡透明边缘带偏（比如星芒的柔光尾巴），
   alpha 重心又会被形状本身的“质量”分布带偏（比如剑+回旋纹下半部更重）。
   画布中心是唯一不受图标内容形状影响的稳定锚点，等比缩小整张画布，缩放后画
   布中心对准安全区中心即可；画师原本在画布里留的构图偏移会被完整保留。
5. 缩放比例用二分/递减方式在“不压安全区”的前提下尽量取大——先用 alpha 阈值
   找一个粗略的实体范围作初始猜测，再用完整画布做真正的越界检测，形状越尖越
   会自动缩小，形状越方越能放大。
6. 缩放后做一次轻度 UnsharpMask 抵消缩小造成的发虚，但锐化后仍会重新检查是否
   越界（锐化的光晕可能让边缘往外扩一点）。
7. 箭头角标（单/双）是底图模板自带固定位置的小贴纸，合成时直接叠最上层，不
   参与安全区计算。
8. 原图不要求必须是透明底：如果给的是纯色背景（黑底白图标 / 白底深色图标，没
   有真正的透明通道），会自动识别并转换——采样四角判断背景是深是浅，用亮度
   反推透明度，图标本身统一改成纯白色，跟手工抠好的透明图效果一致，不需要提
   前用 PS 处理好透明通道再给我。
"""
from PIL import Image, ImageFilter, ImageDraw
import numpy as np
from scipy import ndimage
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)  # 合成脚本/ 的上一级，即 Buff-Debuff/ 本身
BASE_DIR = os.path.join(ROOT, "底图模板")
SYMBOL_ROOT = os.path.join(ROOT, "角色原图")
OUT_ROOT = os.path.join(ROOT, "合成成品")

SAFE_MARGIN_PX = 4          # 在“干净填充区”基础上再往里收的像素
ICON_ALPHA_THRESHOLD = 32   # 判断图标像素“算不算实体”的 alpha 阈值
FILL_COLOR_DIST = 45        # 判断底图像素“算不算填充色”的颜色距离阈值
SHRINK_STEP = 0.97
MIN_SCALE_RATIO = 0.5       # 相对“按矩形推算的初始缩放”最多再缩到这个比例，防止死循环

# 每个角色一个字典：符号图文件名 -> [(底图文件名(不含.png), 箭头角标文件名或None, 输出文件名), ...]
# 底图文件名可以是纯色（green/red/purple/blue/yellow）也可以是金框款
# （goldframe_green/goldframe_red/goldframe_yellow/blue_goldframe）。
CHARACTERS = {
    "kelaiya": {
        "戒律_绿.png": [
            ("green", None, "buff_kelaiya_jielv.png"),
        ],
        "光辉使者_绿.png": [
            ("green", None, "buff_kelaiya_guanghuishizhe.png"),
        ],
        "洞察先机·冷却_红.png": [
            ("red", None, "debuff_kelaiya_dongchaxianjilengque.png"),
        ],
        "初始戒律_紫.png": [
            ("purple", None, "buff_kelaiya_chushijielv.png"),
        ],
        "圣光之力_绿色.png": [
            ("green", None, "buff_kelaiya_shengguangzhili.png"),
        ],
        "圣光普照_绿.png": [
            ("green", None, "buff_kelaiya_shengguangpuzhao1.png"),
        ],
        "虔诚值_蓝.png": [
            ("blue", None, "buff_kelaiya_qianchengzhi.png"),
            ("green", None, "buff_kelaiya_qianchengzhi_green.png"),
            ("green", "green_arrow.png", "buff_kelaiya_qianchengzhi_green_arrow1.png"),
            ("green", "green_arrow2.png", "buff_kelaiya_qianchengzhi_green_arrow2.png"),
            ("red", None, "debuff_kelaiya_qianchengzhi_red.png"),
            ("red", "red_arrow.png", "debuff_kelaiya_qianchengzhi_red_arrow1.png"),
            ("red", "red_arrow2.png", "debuff_kelaiya_qianchengzhi_red_arrow2.png"),
        ],
        "明察_绿.png": [
            ("green", None, "buff_kelaiya_mingcha.png"),
        ],
        "巡光使_绿.png": [
            ("green", None, "buff_kelaiya_xunguangshi.png"),
        ],
    },
    # 来源：SSRPG antige buff/debuff 需求表（角色安绿歌，开发代号 antige）
    "antige": {
        "质疑之种.png": [
            ("goldframe_green", None, "buff_antige_zhiyizhizhong.png"),
        ],
        "蛊惑.png": [
            ("goldframe_red", None, "debuff_antige_guhuo.png"),
        ],
        "蛊惑单次.png": [
            ("goldframe_red", None, "debuff_antige_guhuodanci.png"),
        ],
        "无畏神明之心.png": [
            ("goldframe_green", None, "buff_antige_wujushenmingzhixin.png"),
        ],
        "引爆时机.png": [
            ("goldframe_green", None, "buff_antige_yinbaoshiji.png"),
        ],
        "信仰动摇.png": [
            ("goldframe_red", None, "debuff_antige_xinyangdongyao.png"),
        ],
        "逆神者.png": [
            ("goldframe_red", None, "buff_antige_nishenzhe.png"),
        ],
        "强化警戒.png": [
            ("green", None, "buff_qianghuajingjie.png"),
        ],
    },
    # 测试：验证“非透明背景原图”能否自动修好通道再合成
    "test": {
        "强化警戒.png": [
            ("green", None, "buff_qianghuajingjie.png"),
        ],
    },
}


def build_safe_mask(base_arr, margin_px, color_dist_threshold=FILL_COLOR_DIST):
    """用画布正中心像素的颜色作参照，找出“真正的填充色”区域（能自动排除金框）。"""
    h, w = base_arr.shape[:2]
    ref = base_arr[h // 2, w // 2, :3].astype(float)
    opaque = base_arr[..., 3] == 255
    dist = np.linalg.norm(base_arr[..., :3].astype(float) - ref, axis=-1)
    fill_mask = opaque & (dist < color_dist_threshold)
    d = ndimage.distance_transform_edt(fill_mask)
    return d > margin_px


def load_icon_rgba(path, opaque_threshold=250, flat_bg_threshold=8):
    """读取符号图，自动把“纯色背景、没有透明通道”的图转成白色+透明通道。

    判断规则：
    - 已经有正常透明通道（alpha 有明显变化）的图，直接原样返回。
    - alpha 几乎全是 255（没有真正的透明信息）时，认为背景是纯色实底：
      采样四角颜色，取平均亮度判断背景是深色还是浅色；
      深色背景 -> 亮度本身当透明度（白图标越亮越不透明）；
      浅色背景 -> 用 255-亮度当透明度（图标颜色比背景暗）。
      转换后图标颜色统一改成纯白，跟其它手工抠好的透明素材风格一致。
    """
    im = Image.open(path).convert("RGBA")
    arr = np.array(im).astype(float)
    alpha = arr[..., 3]

    if alpha.min() >= opaque_threshold:
        rgb = arr[..., :3]
        h, w = rgb.shape[:2]
        corners = np.stack([rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]])
        bg_luminance = corners.mean()
        luminance = rgb.mean(axis=-1)

        if bg_luminance < 128:
            new_alpha = luminance
        else:
            new_alpha = 255.0 - luminance

        new_alpha = np.clip(new_alpha, 0, 255)
        out_arr = np.zeros_like(arr, dtype=np.uint8)
        out_arr[..., 0] = 255
        out_arr[..., 1] = 255
        out_arr[..., 2] = 255
        out_arr[..., 3] = new_alpha.astype(np.uint8)
        return Image.fromarray(out_arr, mode="RGBA")

    return im


def icon_fits(icon_alpha, safe_mask, off_x, off_y):
    """把 icon_alpha(2D bool，实体像素) 放到 (off_x, off_y) 后，是否完全落在 safe_mask 内。"""
    h, w = icon_alpha.shape
    canvas_h, canvas_w = safe_mask.shape
    x0, y0 = off_x, off_y
    x1, y1 = off_x + w, off_y + h
    if x0 < 0 or y0 < 0 or x1 > canvas_w or y1 > canvas_h:
        return False
    canvas_solid = np.zeros((canvas_h, canvas_w), dtype=bool)
    canvas_solid[y0:y1, x0:x1] = icon_alpha
    return not np.any(canvas_solid & ~safe_mask)


def composite_one(symbol_path, base_path, out_path, arrow_path=None):
    base = Image.open(base_path).convert("RGBA")
    base_arr = np.array(base)
    safe_mask = build_safe_mask(base_arr, SAFE_MARGIN_PX)

    icon_src = load_icon_rgba(symbol_path)
    src_w, src_h = icon_src.size  # 原始画布尺寸，例如 1024x1024
    icon_alpha_arr = np.array(icon_src)[..., 3]
    solid0 = icon_alpha_arr >= ICON_ALPHA_THRESHOLD
    ys0, xs0 = np.where(solid0)
    if len(xs0) == 0:
        raise RuntimeError(f"图标没有实体像素：{symbol_path}")
    tight_w = xs0.max() - xs0.min() + 1
    tight_h = ys0.max() - ys0.min() + 1

    ys, xs = np.where(safe_mask)
    safe_w = xs.max() - xs.min() + 1
    safe_h = ys.max() - ys.min() + 1
    cx = (xs.min() + xs.max()) / 2
    cy = (ys.min() + ys.max()) / 2

    # 用“实体内容大小”粗估初始缩放，但居中永远用整张原始画布的中心
    scale = min(safe_w / tight_w, safe_h / tight_h)
    min_scale = scale * MIN_SCALE_RATIO

    final_icon = None
    final_pos = None
    while scale > min_scale:
        new_w = max(1, round(src_w * scale))
        new_h = max(1, round(src_h * scale))
        resized = icon_src.resize((new_w, new_h), Image.LANCZOS)
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=2))
        arr = np.array(resized)
        solid = arr[..., 3] >= ICON_ALPHA_THRESHOLD

        off_x = round(cx - new_w / 2)
        off_y = round(cy - new_h / 2)

        if icon_fits(solid, safe_mask, off_x, off_y):
            final_icon = resized
            final_pos = (off_x, off_y)
            break
        scale *= SHRINK_STEP

    if final_icon is None:
        raise RuntimeError(f"无法在安全区内放下图标：{symbol_path}")

    out = base.copy()
    out.alpha_composite(final_icon, final_pos)

    if arrow_path:
        arrow = Image.open(arrow_path).convert("RGBA")
        out.alpha_composite(arrow, (0, 0))

    out.save(out_path)
    return out, scale


def run_character(char_name, mapping):
    symbol_dir = os.path.join(SYMBOL_ROOT, char_name)
    out_dir = os.path.join(OUT_ROOT, char_name)
    os.makedirs(out_dir, exist_ok=True)

    results = []
    for symbol_name, variants in mapping.items():
        symbol_path = os.path.join(symbol_dir, symbol_name)
        if not os.path.exists(symbol_path):
            print(f"[MISS] symbol not found ({char_name}): {symbol_name}")
            continue
        for base_name, arrow_file, out_name in variants:
            base_path = os.path.join(BASE_DIR, f"{base_name}.png")
            out_path = os.path.join(out_dir, out_name)
            if not os.path.exists(base_path):
                print(f"[MISS] base not found: {base_name}.png")
                continue
            arrow_path = None
            if arrow_file:
                arrow_path = os.path.join(BASE_DIR, arrow_file)
                if not os.path.exists(arrow_path):
                    print(f"[MISS] arrow badge not found: {arrow_file}")
                    continue
            _, used_scale = composite_one(symbol_path, base_path, out_path, arrow_path)
            results.append(out_name)
            print(f"[OK] {char_name}/{symbol_name} + {base_name}.png"
                  f"{' + ' + arrow_file if arrow_file else ''}"
                  f" -> {out_name} (scale={used_scale:.3f})")

    if results:
        thumb = 96
        pad = 16
        label_h = 20
        cols = len(results)
        sheet = Image.new("RGB", (cols * (thumb + pad) + pad, thumb + label_h + pad * 2), (250, 250, 250))
        draw = ImageDraw.Draw(sheet)
        for i, out_name in enumerate(results):
            img = Image.open(os.path.join(out_dir, out_name)).convert("RGBA").resize((thumb, thumb), Image.LANCZOS)
            x = pad + i * (thumb + pad)
            y = pad
            sheet.paste(img, (x, y), img)
            draw.text((x, y + thumb + 2), out_name.replace(".png", ""), fill=(30, 30, 30))
        sheet.save(os.path.join(out_dir, "_预览联系表.png"))
        print(f"{char_name} 预览联系表已生成")


if __name__ == "__main__":
    for char_name, mapping in CHARACTERS.items():
        run_character(char_name, mapping)
