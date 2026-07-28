# -*- coding: utf-8 -*-
"""
把某个角色的最终成品（Buff/Debuff 图标、技能图标、图文对照表）汇总到
最终输出/<角色名>/ 下面，方便整体打包发出去。所有文件平铺放在角色文件夹
下，不再分 Buff-Debuff/技能图标 子文件夹（三类文件名前缀本来就不同
buff_/debuff_/icon_skill_/unitpersonality_，平铺不会互相覆盖）。

只是复制文件，不重新生成任何内容——生成/修改请用各自的脚本
（composite_buff_icons.py / normalize_skill_icon.py / generate_comparison_chart.py），
这个脚本跑在它们之后，汇总当前最新结果。

用法：python package_character.py <角色名>
"""
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)  # 最终输出/ 的上一级，即项目根目录

BUFF_SRC_ROOT = os.path.join(ROOT, "Buff-Debuff", "合成成品")
SKILL_SRC_ROOT = os.path.join(ROOT, "技能图标", "合成成品")
CHART_SRC_ROOT = os.path.join(ROOT, "图文技能对照表")


def copy_pngs(src_dir, dst_dir):
    if not os.path.isdir(src_dir):
        return 0
    count = 0
    for name in sorted(os.listdir(src_dir)):
        if not name.lower().endswith(".png"):
            continue
        shutil.copy2(os.path.join(src_dir, name), os.path.join(dst_dir, name))
        count += 1
    return count


def package(char_name):
    out_dir = os.path.join(SCRIPT_DIR, char_name)
    os.makedirs(out_dir, exist_ok=True)

    n_buff = copy_pngs(os.path.join(BUFF_SRC_ROOT, char_name), out_dir)
    n_skill = copy_pngs(os.path.join(SKILL_SRC_ROOT, char_name), out_dir)
    n_chart = copy_pngs(os.path.join(CHART_SRC_ROOT, char_name), out_dir)

    print(f"{char_name}: Buff-Debuff {n_buff} 张，技能图标 {n_skill} 张，图文对照表 {n_chart} 张（全部平铺在同一目录）")
    print(f"输出目录：{out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python package_character.py <角色名>")
        sys.exit(1)
    package(sys.argv[1])
