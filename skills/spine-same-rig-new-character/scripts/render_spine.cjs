#!/usr/bin/env node
// 用官方 spine-webgl 运行库在无头 Chrome 里渲染任意姿势, 输出 PNG 与几何信息。
//
// 用法: node render_spine.cjs job.json
// 依赖: playwright (在当前目录或本脚本目录可 require 到即可: npm i playwright)、本机 Chrome
//       (环境变量 CHROME_PATH 或 job.chrome 指定, 默认 macOS 路径)。
//
// job.json (相对路径一律相对 job.json 所在目录):
// {
//   "runtime":  "spine-webgl-3.4.js",        // 与数据同版本的官方 spine-webgl 构建
//   "skeleton": "rig.json", "atlas": "rig.atlas",   // 图集页 png 与 atlas 同目录
//   "out": "frames",                          // PNG 输出目录
//   "width": 900, "height": 700,              // 画布像素
//   "scale": 3.5, "cx": 0, "cy": 80,          // 像素/骨架单位, 画面中心 (骨架坐标)
//   "bg": "#dddddd" | null,                   // null = 透明
//   "bones": false,                           // 叠加骨骼调试线
//   "info": "info.json",                      // 可选: 输出骨骼世界矩阵与每个 slot 的世界多边形
//   "poses": [ { "anim": "idle", "time": 0, "file": "idle0.png",
//                "cx": 0, "cy": 80,             // 可选: 本姿势单独取景
//                "only": ["slotA", "slotB"],    // 可选: 只画这些 slot (其余清空附件)
//                "stress": {"bone35": 20} } ]   // 可选: 额外旋转 (度), 做关节压力测试
// }
//
// info.json: { file: { bones: [[name, worldX, worldY, a, b, c, d], ...],
//                      slots: [[slot, attachment, alpha, [[x,y],...], triangles|null], ...] } }
// slots 按实际绘制顺序排列; region 的 4 个角顺序为 BL, TL, TR, BR (spine-ts updateWorldVertices)。
// 注意 3.4: bone.worldX 不含 skeleton.x; 本脚本不设置 skeleton.x。
const fs = require('fs'), path = require('path');
function need(mod) { return require(require.resolve(mod, { paths: [process.cwd(), __dirname] })); }
const { chromium } = need('playwright');

(async () => {
  const jobPath = path.resolve(process.argv[2]);
  const job = JSON.parse(fs.readFileSync(jobPath, 'utf8'));
  const rd = p => path.resolve(path.dirname(jobPath), p);
  const atlasText = fs.readFileSync(rd(job.atlas), 'utf8');
  const payload = { json: JSON.parse(fs.readFileSync(rd(job.skeleton), 'utf8')), atlas: atlasText, pages: {} };
  for (const line of atlasText.split('\n')) {
    const t = line.trim();
    if (/\.png$/i.test(t)) payload.pages[t] = 'data:image/png;base64,' + fs.readFileSync(path.join(path.dirname(rd(job.atlas)), t)).toString('base64');
  }
  const chrome = job.chrome || process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: job.width, height: job.height }, deviceScaleFactor: 1 });
  const errors = []; page.on('pageerror', e => errors.push(String(e))); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.setContent(`<html><body style="margin:0;background:transparent"><canvas id=c width=${job.width} height=${job.height}></canvas></body></html>`);
  await page.addScriptTag({ path: rd(job.runtime) });
  await page.evaluate(async ({ payload, job }) => {
    const c = document.getElementById('c');
    const gl = c.getContext('webgl', { alpha: true, premultipliedAlpha: false, preserveDrawingBuffer: true, antialias: true });
    const pot = v => (v & (v - 1)) === 0, imgs = {};
    for (const [name, url] of Object.entries(payload.pages)) {
      const im = new Image(); im.src = url; await im.decode();
      imgs[name] = new spine.webgl.GLTexture(gl, im, pot(im.width) && pot(im.height));   // WebGL1: 只有 2 的幂才能 mipmap
    }
    const atlas = new spine.TextureAtlas(payload.atlas, p => imgs[p]);
    const data = new spine.SkeletonJson(new spine.TextureAtlasAttachmentLoader(atlas)).readSkeletonData(payload.json);
    const sk = new spine.Skeleton(data);
    const renderer = new spine.webgl.SkeletonRenderer(gl); renderer.premultipliedAlpha = false;
    const batch = new spine.webgl.PolygonBatcher(gl), shader = spine.webgl.Shader.newColoredTextured(gl), mvp = new spine.webgl.Matrix4();
    const shapes = new spine.webgl.ShapeRenderer(gl), cshader = spine.webgl.Shader.newColored(gl);
    window.__render = (pose) => {
      sk.setToSetupPose();
      if (pose.anim) data.findAnimation(pose.anim).apply(sk, -1, pose.time, false, []);
      if (pose.stress) for (const [b, d] of Object.entries(pose.stress)) sk.findBone(b).rotation += d;
      if (pose.only) for (const sl of sk.slots) if (!pose.only.includes(sl.data.name)) sl.attachment = null;
      sk.updateWorldTransform();
      const W = job.width, H = job.height, s = job.scale;
      const cx = pose.cx != null ? pose.cx : job.cx, cy = pose.cy != null ? pose.cy : job.cy;
      mvp.ortho2d(cx - W / 2 / s, cy - H / 2 / s, W / s, H / s);
      gl.viewport(0, 0, W, H);
      if (job.bg) { const h = job.bg; gl.clearColor(parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255, 1); }
      else gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT); gl.enable(gl.BLEND);
      shader.bind(); shader.setUniformi(spine.webgl.Shader.SAMPLER, 0); shader.setUniform4x4f(spine.webgl.Shader.MVP_MATRIX, mvp.values);
      batch.begin(shader); renderer.draw(batch, sk); batch.end(); shader.unbind();
      if (job.bones) {
        cshader.bind(); cshader.setUniform4x4f(spine.webgl.Shader.MVP_MATRIX, mvp.values); shapes.begin(cshader);
        for (const b of sk.bones) {
          shapes.setColor(new spine.Color(1, 0, 0, 0.9)); shapes.line(b.worldX, b.worldY, b.worldX + b.a * b.data.length, b.worldY + b.c * b.data.length);
          shapes.setColor(new spine.Color(0, 0.4, 1, 1)); shapes.circle(true, b.worldX, b.worldY, 0.9, null, 8);
        }
        shapes.end(); cshader.unbind();
      }
      const info = {};
      info.bones = sk.bones.map(b => [b.data.name, b.worldX, b.worldY, b.a, b.b, b.c, b.d]);
      info.slots = sk.drawOrder.map(sl => {
        const a = sl.getAttachment(); let poly = null;
        if (a && a.updateWorldVertices) { const v = a.updateWorldVertices(sl, false); poly = []; for (let i = 0; i < v.length; i += 8) poly.push([v[i], v[i + 1]]); }
        return [sl.data.name, a ? a.name : null, sl.color.a, poly, a && a.triangles ? Array.from(a.triangles) : null];
      });
      return { png: c.toDataURL('image/png'), info };
    };
  }, { payload, job });
  fs.mkdirSync(rd(job.out), { recursive: true });
  const infos = {};
  for (const pose of job.poses) {
    const r = await page.evaluate(p => window.__render(p), pose);
    fs.writeFileSync(path.join(rd(job.out), pose.file), Buffer.from(r.png.split(',')[1], 'base64'));
    infos[pose.file] = r.info;
  }
  if (job.info) fs.writeFileSync(rd(job.info), JSON.stringify(infos));
  await browser.close();
  if (errors.length) { console.error('ERRORS', errors); process.exit(1); }
  console.log('rendered', job.poses.length);
})().catch(e => { console.error(e); process.exit(1); });
