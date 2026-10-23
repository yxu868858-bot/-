/**
 * 把动态汇报逐帧录制成 MP4 视频（手机 / 微信可直接播放）。
 *
 * 原理：以 ?render 模式打开 index.html，逐页切换；每一帧通过 __deck.seek(ms)
 * 把所有动画精确拨到该时刻再截图，画面写入 ffmpeg 编码为 H.264。
 * 因为不是实时录屏，不会掉帧，速度慢也不影响成片流畅度。
 *
 * 用法：
 *   node tools/make_video.js [输出.mp4] [--jobs 3]        整片录制（可分段并行后拼接）
 *   node tools/make_video.js 输出.mp4 起始页 结束页         只录指定页段
 * 依赖：playwright（Chromium，需在 NODE_PATH 中）、ffmpeg（含 libx264）
 */
const { chromium } = require('playwright');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const FPS = 25;
const RENDER_PAGE_SECONDS = 5;   // 效果图满屏页在视频中的停留时间
const INDEX = 'file://' + path.join(__dirname, '..', 'index.html') + '?render#1';

const args = process.argv.slice(2);
const jobsAt = args.indexOf('--jobs');
const jobs = jobsAt >= 0 ? +args.splice(jobsAt, 2)[1] : 1;
const out = path.resolve(args[0] || path.join(__dirname, '..', 'dist', '义巷漫游集-动态汇报.mp4'));

async function openDeck() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.goto(INDEX, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const deck = await page.evaluate(() => ({ N: __deck.N, durs: __deck.durs, titles: __deck.titles,
    kinds: [...document.querySelectorAll('#stage > .slide')].map(s => s.className) }));
  deck.dur = i => (/\brd\b/.test(deck.kinds[i]) ? RENDER_PAGE_SECONDS : deck.durs[i]);
  return { browser, page, deck };
}

async function record(file, from, to) {
  const { browser, page, deck } = await openDeck();
  const last = to || deck.N;
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(FPS), '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', file], { stdio: ['pipe', 'inherit', 'inherit'] });
  const write = buf => new Promise(res => (ff.stdin.write(buf) ? res() : ff.stdin.once('drain', res)));
  const seek = ms => page.evaluate(ms => __deck.seek(ms), ms);

  if (from > 1) {               // 分段录制时，先停在上一页的结尾，保证页间过渡与整片一致
    await page.evaluate(i => __deck.go(i), from - 2);
    await seek(deck.dur(from - 2) * 1000);
  }
  const t0 = Date.now();
  for (let i = from - 1; i < last; i++) {
    const ms = deck.dur(i) * 1000, frames = Math.round(deck.dur(i) * FPS);
    await page.evaluate(i => __deck.go(i), i);
    await seek(ms);                                   // 预热：拨到页尾截一次图，确保图片都已解码
    await page.screenshot({ type: 'jpeg', quality: 50 });
    for (let f = 0; f < frames; f++) {
      await seek((f * 1000) / FPS);
      await write(await page.screenshot({ type: 'jpeg', quality: 92 }));
    }
    console.log(`${String(i + 1).padStart(2, '0')} ${deck.titles[i]}  ${deck.dur(i)}s  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end();
  await new Promise(res => ff.on('close', res));
  await browser.close();
}

async function parallel() {
  const { browser, deck } = await openDeck();
  await browser.close();
  const durs = [...Array(deck.N).keys()].map(deck.dur);
  const total = durs.reduce((a, b) => a + b, 0);
  console.log(`共 ${deck.N} 页，${(total / 60).toFixed(1)} 分钟，分 ${jobs} 段并行录制`);
  // 按时长均分页段
  const ranges = [];
  let start = 1, acc = 0;
  durs.forEach((d, i) => {
    acc += d;
    if (ranges.length < jobs - 1 && acc >= (total / jobs) * (ranges.length + 1)) { ranges.push([start, i + 1]); start = i + 2; }
  });
  ranges.push([start, deck.N]);
  const tmp = fs.mkdtempSync(path.join(path.dirname(out), '.video-'));
  const parts = ranges.map((_, k) => path.join(tmp, `part${k}.mp4`));
  await Promise.all(ranges.map(([a, b], k) => new Promise((res, rej) => {
    const p = spawn(process.execPath, [__filename, parts[k], String(a), String(b)], { stdio: ['ignore', 'pipe', 'inherit'] });
    p.stdout.on('data', d => process.stdout.write(d.toString().replace(/^/gm, `[段${k + 1}] `)));
    p.on('close', code => (code ? rej(new Error(`段 ${k + 1} 失败`)) : res()));
  })));
  const list = path.join(tmp, 'list.txt');
  fs.writeFileSync(list, parts.map(p => `file '${p}'`).join('\n'));
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', out]);
  fs.rmSync(tmp, { recursive: true });
  console.log('完成：', out);
}

(async () => {
  if (args[1]) await record(out, +args[1], args[2] ? +args[2] : null);
  else if (jobs > 1) await parallel();
  else { await record(out, 1, null); console.log('完成：', out); }
})().catch(e => { console.error(e); process.exit(1); });
