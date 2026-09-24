# 提示词模板（已验证有效）

调用参数统一如下：

- 接口 `/images/edits`，参考图用 `image[]` 多张；
- `model=gpt-image-2.5`、`quality=high`、`input_fidelity=high`、`background=transparent`、`n=1`；
- 尺寸：竖图 `1024x1536`，横图 `1536x1024`，方图 `1024x1024`。

每次调用只发一次，不自动重试；请求、提示词、参考图、原始返回、解码后的 PNG、耗时都保存下来。返回尺寸不等于请求尺寸（1536 请求实际得到 1121×1403 或 1403×1121），要缩放回画布尺寸再用。

提示词用英文写。下面 `{…}` 是占位符。

## 1. 人台上色（设计稿第一次）

参考图：灰色人台。

```
Image 1 is a flat gray MANNEQUIN template exported from a 2D skeletal-animation rig. Repaint it into the finished full-color character. This is a production template: keep the figure at EXACTLY the same position, scale, pose and outer silhouette as the gray shapes. Every {列出关键部件: hair lock, sleeve drape, skirt panel, limb, hand, foot, 新增形状如 the two rings on the head / the straight sword} stay exactly where they are and keep their outlines and overlaps. The gray tones only separate materials; replace them completely with the design below.

Character: {名字}, a brand-new ORIGINAL {题材} character. {年龄体型}, {朝向: three-quarter view facing the viewer's right}, {姿态}.
Art style: {画风: polished CARTOON game character art, bold clean dark-brown outlines, flat cel shading with two tones plus small crisp highlights, bright clean pastel colors …}.
Hair: {…，说明哪个灰形状是什么: two looped buns sitting exactly on the two gray rings …}
Face: {…}
Outfit: {逐个灰块说明: the large light-gray drapes hanging from both upper arms are long flowing chiffon sleeves, painted as solid opaque fabric …}
Weapon: {…；the fist grips it exactly where the gray fist is}
It must NOT resemble any existing character: {列出原角色的发色、配色、标志性饰物、武器类型}.
Output: only this single character on a transparent background. No text, no frame, no ground shadow, no extra objects, no second figure.
```

要点：

- 每个灰块代表什么都要写明，不然模型会把长袖画成手臂、把发束画成衣服。
- 半透明材质要求画成 opaque，否则后面切图 alpha 很难处理。

## 2. 平涂稿精修（设计稿第二次）

参考图 1：按新配色平涂的人台（含五官占位）；参考图 2：上一步的设计稿。

```
Image 1 is a FLAT-COLOR LAYOUT of a 2D game character, exported from an animation rig. Every flat region is a separate animation part and its outline is fixed. Render image 1 into the finished cartoon illustration by adding line art, cel shading, highlights and small design details INSIDE the existing regions.

STRICT LAYOUT RULES (mandatory, the pixels are used directly for rigging):
- Keep the exact canvas, position, scale and pose. Do not move, enlarge, shrink, merge or redraw any region; keep every boundary between regions where it is.
- Every {颜色} region stays {材质} … (逐色说明)
- The face stays in the same {朝向} with the eyes, brows and mouth exactly at the marked positions.
- Nothing may be added outside the colored silhouette except tiny anti-aliasing.

Image 2 is the approved design sheet of the same character. Copy the design language and art style from image 2 ({要保留的细节}), but follow image 1 for every shape and position.
Output only the character on a transparent background, no text, no ground shadow.
```

## 3. 部件图纸补全（通用部分 + 每张图纸的部件说明）

参考图 1：图纸（灰底）；参考图 2：定稿设计稿。

```
Image 1 is a production PARTS SHEET for the 2D skeletal-animation rig of the character shown in image 2. Every separate shape on the gray sheet is ONE rig part, drawn in the same orientation as it sits on the body in image 2. Some parts are already partly painted with pixels taken from image 2; the remaining flat-colored areas are hidden areas (normally covered by other parts) that must be painted too.

Task: paint every part as a complete, clean, finished piece of the character in image 2, in image 2's exact art style: {画风}.

Mandatory rules (the result is cut out automatically by position, so layout must not change):
- Keep every part exactly where it is, with the same outline, size and orientation. Fill the entire shape edge to edge. Do not paint outside a shape, do not add new parts, do not connect, merge, duplicate or mirror parts, never draw a whole person or a face on a non-head part.
- Keep the pre-painted details and continue them naturally into the flat areas (same folds, trims, embroidery, strand directions and colors).
- Each part must look complete on its own: where another part used to cover it, finish it with its own design. No cast shadows of missing neighbors, no holes.
- The small gray text labels are notes for you; leave them unchanged.
- Output the sheet with a transparent background.

Part notes for this sheet:
- {标签名}: {这个部件是什么、只能画什么、不能画什么}
```

部件说明的写法，例：

- `UPPER ARM and FOREARM: white fitted sleeves only (no hands, no skin).`
- `THIGH and LOWER LEG: legs in loose white trousers only (no feet, no skin).`
- `LONG HAIR: … Only hair, no ribbons or skin inside these shapes.`
- 头部：把五官、发型、饰品逐项写全；其中"会单独摆动的鬓发"要写明**不在头部部件里**。这一条当时没写，后来导致鬓发被画进脸里。

## 4. 其他视角：在画面里补画占位部分

参考图 1：模板骨架摆成背身或侧身姿势的渲染图；参考图 2：定稿设计稿。

```
Image 1 is a frame from the 2D skeletal animation of the character shown in image 2: a close-up of {背面/侧面描述}. Most of the frame is already finished art ({列出已完成部件}). The FLAT-COLORED shapes with thin outlines are unfinished rig parts that you must paint as finished art in exactly the same style and design as image 2:
- the flat {颜色} {形状}: {它是什么，例如 the back of her hair and her two ring buns seen from behind …};
- …
Rules: keep the exact framing, pose and every shape outline; paint only inside the flat shapes; leave all already finished areas unchanged; no new objects; no text. Same style as image 2: {画风}. Output on a transparent background.
```

## 5. 展开空间重画（折叠部件）

参考图 1：展开空间的贴图模板；参考图 2：设计稿。

```
Image 1 is a TEXTURE SHEET with {N} unfolded 2D-rig parts of the character in image 2. Each gray-background shape is one flat texture piece; its outline is fixed and is used directly by the animation mesh. Paint each piece completely as a clean finished texture in image 2's exact art style ({画风}).
- {标签}: {内容；例：long mass of glossy black hair, strands flow from the top edge down to tapered tips, following the shape's long direction; keep the painted strands and repaint the flat area as matching hair … Only hair.}
Rules: keep every piece exactly where it is with the same outline, size and orientation; fill each shape edge to edge; do not paint outside the shapes; do not add new objects; leave the small gray labels unchanged. Output the sheet with a transparent background.
```

大面积浅色布料要加一句：`gentle pleats rendered only with very light, soft shading (low contrast, wide soft shapes, no dark or thin hard lines inside the fabric)`。否则动作拉伸时，深色褶线会被拉成难看的拉丝。

## 6. 局部重画（如脸侧残留头发）

参考图：只有放大后的头部贴图，重画区域已平涂成肤色。

```
This image is the HEAD part of a 2D skeletal-animation character, shown on a flat gray background. Her side hair lock is a SEPARATE animated part, so it must not be painted on this head part.
On the left side of her face there is a flat, unshaded skin-colored patch ({位置}). Repaint only that patch and its edges so that it shows her bare skin: {要画出的结构: cheek and temple in front of her ear, natural temple hairline, outer tip of the eyelashes, a clean jawline outline from chin to ear lobe}. Match the face exactly: same skin color, same soft cel shading and blush, same line weight.
Rules:
- Do NOT draw any hair lock, strand or sideburn hanging in front of her ear or over her cheek or jaw.
- The head part ends at her jawline and chin: below the jaw keep the plain gray background (no neck, no hair, no collar).
- Keep everything else exactly unchanged, pixel for pixel: {列出必须不动的部分}.
- Keep the exact same framing, size and position. No new objects, no text.
Output with a transparent background.
```

模型会顺手改动别处（例如把耳坠画大）。所以只按修复区域的羽化掩码贴回，其余像素保持原样。
