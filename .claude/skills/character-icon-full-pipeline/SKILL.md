---
name: character-icon-full-pipeline
description: Use when the user asks to "整理角色技能图标" / process a character's full icon set for 铃兰之剑(Sword of Convallaria) - producing Buff/Debuff icons, skill icons, and a combined image+text reference chart together for one character
---

# 角色图标全流程（Buff/Debuff + 技能图标 + 图文对照表）

## Overview
用户说"整理角色技能图标"时，不是只处理技能图标一项，而是四件事一起做：Buff/Debuff 图标合成、技能图标规范化、生成图文对照表、把三者最终产物汇总打包到 `最终输出/<角色名>/`。四者都靠 Jira/Google 表格里的 dev_name 对齐，角色名文件夹保持一致即可关联。

## 目录总览
```
铃兰图标自动化/                        （项目根目录）
├── Buff-Debuff/                       独立 git 仓库，buff/debuff 图标合成工具
│   └── 合成脚本/  composite_buff_icons.py + characters.json(本地)
├── 技能图标/                          技能/个性图标规范化工具
│   ├── 角色原图/<角色名>/              AI 生成的定稿（1024x1024，圆形构图）
│   ├── 合成成品/<角色名>/              规范化后的 128x128 成品
│   └── 处理脚本或素材/
│       ├── normalize_skill_icon.py    通用脚本
│       └── skill_characters.json(本地)  角色映射，不进git
├── 图文技能对照表/
│   ├── generate_comparison_chart.py   通用脚本
│   ├── labels/<角色名>.json(本地)      对照表标签数据，不进git
│   └── <角色名>/<角色名>_图文对照表.png  产物
└── 最终输出/
    ├── package_character.py           通用脚本，只复制不重新生成
    └── <角色名>/                       打包给别人用的最终交付文件夹（不分子文件夹，
                                        buff/debuff/技能图标/对照表全部平铺在一起，
                                        文件名前缀不同不会互相覆盖）
```

## 完整流程
1. **找数据源**：问用户要 Jira 单链接或 Google 表格链接（`铃兰之剑2023-2026图标需求文档`，页签通常叫"1.7版本角色图标需求"之类），定位到该角色的段落。读出：
   - 个性/技能行：dev_name（`icon_skill_<角色>_xxx` / `unitpersonality_<角色>_xxx`），中文技能名
   - BUFF/DEBUFF 行：dev_name（`buff_<角色>_xxx` / `debuff_<角色>_xxx`），中文名，底色/金框备注
   - 注意通用技能（如 `icon_skill_cifu`）和赛季通用基础技能（如 `icon_skill_qianxindaogao`）dev_name 里不带角色名，容易漏看，两份表格（角色专属表 + 通用基础表）都要查。
2. **Buff/Debuff**：把 dev_name 映射写进 `Buff-Debuff/合成脚本/characters.json`（**REQUIRED SUB-SKILL:** 用 `Buff-Debuff:buff-debuff-icon-compositing` 技能的规则），跑 `composite_buff_icons.py`。
3. **技能图标**：
   - 原始 AI 定稿放进 `技能图标/角色原图/<角色名>/`。
   - 如果同一技能有多个编号变体（01/02...），问用户选哪张作定稿，不要自己猜。
   - 把 "文件名→dev_name" 映射写进 `技能图标/处理脚本或素材/skill_characters.json`（角色名为 key）。
   - 跑 `python normalize_skill_icon.py <角色名>`：脚本会检测每张图的圆形范围、把背景转成渐变透明度（不是硬阈值裁切，避免圆边缘留白边）、缩放到 120px 圆直径、贴进 128x128 透明画布。
4. **图文对照表**：把两边最终顺序和中文标签写进 `图文技能对照表/labels/<角色名>.json`（每项 `{label, source: "skill"|"buff", file}`），跑 `python generate_comparison_chart.py <角色名>`，产物在 `图文技能对照表/<角色名>/`。
5. 用 Read 工具检查对照表图（有没有"缺图"红框、图标是否居中/透明干净），脚本会在终端报"缺图 N 个"，缺的要问用户补图或确认跳过。
6. **打包**：跑 `python 最终输出/package_character.py <角色名>`，把上面三步的产物汇总复制到 `最终输出/<角色名>/`（只复制，不重新生成），这是给外部/打包发布用的最终交付目录。

## 常见坑
| 现象 | 处理 |
|---|---|
| 技能图标圆边缘有一圈白边/黑边 | 说明用的是老版本裁切逻辑（先按硬阈值找圆框、再套硬边蒙版）。现在的 `normalize_skill_icon.py` 已经改成先把背景按距离渐变转透明度、再用半透明中线量圆心/直径，边缘会自然收尾，不会再留边。如果还出现，检查 `ALPHA_RAMP_LOW/HIGH` 这两个阈值是否需要针对该图调整。 |
| 同一技能有 01/02 两个候选定稿 | 不要自己选，问用户定稿是哪张。 |
| 某个 dev_name 在角色专属表里找不到 | 去查"赛季通用基础"这类通用表格，很可能是通用技能/BUFF，不属于该角色专属列表。 |
| 图文对照表某项一直"缺图" | 检查 `labels/<角色名>.json` 里的 `file` 和 `source` 是不是跟实际生成的文件名/所在文件夹（skill→技能图标/合成成品，buff→Buff-Debuff/合成成品）对得上。 |
| `合成成品/<角色名>/` 突然变空 | 出现过一次原因不明（原图/角色原图没丢），重新跑第2、3步的生成脚本即可恢复，跑完记得重新跑第6步打包。若再出现，留意是不是有清理脚本/工具误删了这个目录。 |
| `最终输出/<角色名>/` 里有旧版重复文件（比如改过命名规则后残留的旧文件名） | `package_character.py` 只做复制、不清空目标目录，旧文件不会自动消失。先去源目录（`图文技能对照表/<角色名>/` 等）删掉过时产物，再重新跑打包脚本。 |

## 隐私边界
角色名、技能名、dev_name 本身可能是未发布内容。`characters.json`、`skill_characters.json`、`labels/*.json` 这三类文件都只在本地维护，各自目录的 `.gitignore`（或本身就不在任何 git 仓库里）已经排除，只保留 `*.example.json` 占位模板。给团队分享工具时只分享脚本本身，不分享这些本地配置。
