---
name: buff-debuff-icon-compositing
description: Use when generating Buff/Debuff icon PNGs for 铃兰之剑(Sword of Convallaria) characters - compositing white silhouette symbol art onto colored base card templates, converting non-transparent source PNGs to transparent, or adding a new character's buff/debuff icon set
---

# Buff/Debuff 图标合成

## Overview
把角色的白色剪影符号图自动合成到 Buff/Debuff 底图卡片上（绿底=buff、红底=debuff、金框=特殊/强化态），自动避开描边/金框、自动找安全的缩放比例和居中位置。原图不要求已经抠好透明通道。

## 何时使用
- 有新角色的 buff/debuff 需求表（颜色+金框+机制描述备注），需要出成品图标
- 拿到的原图是黑底或白底、不透明的 PNG，需要先转成透明通道再合成
- 已有角色要新增底色变体（同一个符号换绿/红底）或箭头角标（单/双层数标记）

## 目录与脚本
本技能随这个仓库（`Buff-Debuff/`）一起分发，数据就在仓库根目录下（如果是被复制到了别的项目里、找不到对应目录，问用户）：
```
Buff-Debuff/                （本仓库根目录）
├── .claude/skills/buff-debuff-icon-compositing/SKILL.md   本文件
├── 底图模板/            底色/金框/箭头角标，所有角色共用，不要改
├── 角色原图/<角色名>/    该角色原始 1024x1024 白色符号图（或黑/白底不透明图）
├── 合成成品/<角色名>/    合成结果 + 预览联系表，脚本自动生成
└── 合成脚本/composite_buff_icons.py
```
脚本内部路径全部相对自身位置，`Buff-Debuff/` 整个文件夹挪到别的机器/目录都能直接跑，不认死绝对路径。

## 新增一个角色的流程
1. 把该角色的原始白色符号 PNG 放进 `角色原图/<角色名>/`（透明底或黑/白底不透明都行）。
2. 打开 `合成脚本/composite_buff_icons.py`，在 `CHARACTERS` 字典里加一段：
   ```python
   "角色名": {
       "符号文件名.png": [
           ("底图名(不含.png)", 箭头文件名或None, "输出文件名.png"),
       ],
   },
   ```
   底图名：纯色 `green`/`red`/`purple`/`blue`/`yellow`，或金框款 `goldframe_green`/`goldframe_red`/`goldframe_yellow`/`blue_goldframe`。箭头文件名对应 `底图模板/` 里的 `{color}_arrow.png`（单）/`{color}_arrow2.png`（双），没有就传 `None`。
3. 颜色怎么选：看需求表备注——一般"绿底"=buff、"红底"=debuff，"金框"代表特殊/强化态；备注写了"参考【某图标】"就照抄那张的底色。备注含糊或自相矛盾时问用户，不要猜。
4. 运行脚本：`python composite_buff_icons.py`（会处理 CHARACTERS 里所有角色），产物在 `合成成品/<角色名>/`，附一张 `_预览联系表.png`。
5. 用 Read 工具看预览联系表 + 几张代表性单图，检查有没有压边框、居中是否合理、线条是否清晰。

## 合成规则（脚本已实现，不用重新发明）
- **安全区避让边框**：不是简单看 alpha==255，而是用底图正中心像素的颜色作参照，颜色够接近且完全不透明的区域才算"安全填充区"，再向内收缩几像素——金框底图的金色边框和纯色底图的描边都能正确排除。
- **居中锚点用原始画布几何中心**，不用裁剪后的外框中心、也不用 alpha 重心——两者都会被"主体旁边挂个小装饰"（星芒、箭头）或"形状本身一边更重"（剑+回旋纹）带偏；画布中心是唯一不受内容形状影响的稳定锚点，画师原本留的构图偏移会被完整保留。
- **缩放用递减试错**：从按内容尺寸估算的初始比例开始，每次缩小 3%，实际检查缩放+锐化后的图标像素是否完全落在安全区内，不行就再缩；形状越尖越会自动收敛到更小比例。
- **原图不需要预先抠图**：如果整张图 alpha 全不透明（没有真正的透明通道），自动采样四角判断背景深浅，用亮度反推透明度，图标统一改纯白——黑底白图标、白底深色图标都能处理。

## 常见问题
| 现象 | 原因 / 处理 |
|---|---|
| 用普通看图/Read 工具打开原图像是空白一片 | 很可能是"透明底+纯白图标"，白色背景上看白色图标本来就看不出来；套个深色背景预览一下（PIL 合成到灰色画布）就能看清，不代表文件坏了 |
| 图标压到圆角描边/金框 | 底图模板中心点采样可能落在装饰花纹上导致误判，检查 `build_safe_mask` 用的中心参照色，或调 `FILL_COLOR_DIST` |
| 需要的箭头角标/标记素材没有 | 不要拿现成素材硬凑（比如复制单箭头强行拼双箭头），找用户要设计稿或明确样式说明 |
| 需求表颜色/金框描述模糊 | 按中文备注判断，含糊或自相矛盾（比如某图标备注"参考自己"）时直接问用户，不要瞎猜 |

## 分享给团队
`Buff-Debuff/` 只依赖 Python + `pillow`/`numpy`/`scipy`。整个文件夹放到共享位置（项目仓库/共享盘）后，任何人都能在自己的 Cindy 里说"帮我按 Buff-Debuff 的规则生成 XX 角色的 buff 图标"触发这个技能，不用重新解释一遍规则。
