/**
 * 把动态汇报逐帧录制成 MP4 视频（手机 / 微信可直接播放）。
 *
 * 原理：以 ?render 模式打开 index.html，逐页切换；每一帧通过 __deck.seek(ms)
 * 把所有动画精确拨到该时刻再截图，画面写入 ffmpeg 编码为 H.264。
 * 因为不是实时录屏，不会掉帧，速度慢也不影响成片流畅度。
 *
 * 用法：NODE_PATH=<playwright 所在 node_modules> node tools/make_video.js [输出.mp4] [起始页] [结束页]
 * 依赖：playwright（Chromium）、ffmpeg（含 libx264）
 */
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

const FPS = 25;
const RENDER_PAGE_SECONDS = 5;   // 效果图满屏页在视频中的停留时间
const out = process.argv[2] || path.join(__dirname, '..', 'dist', '义巷漫游集-动态汇报.mp4');
const from = +(process.argv[3] || 1), to = process.argv[4] ? +process.argv[4] : null;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.goto('file://' + path.join(__dirname, '..', 'index.html') + '?render#1', { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const deck = await page.evaluate(() => ({ N: __deck.N, durs: __deck.durs, titles: __deck.titles,
    kinds: [...document.querySelectorAll('#stage > .slide')].map(s => s.className) }));
  const last = to || deck.N;
  const durOf = i => (/\brd\b/.test(deck.kinds[i]) ? RENDER_PAGE_SECONDS : deck.durs[i]);
  let total = 0;
  for (let i = from - 1; i < last; i++) total += durOf(i);
  console.log(`录制第 ${from}–${last} 页，共 ${(total / 60).toFixed(1)} 分钟`);

  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(FPS), '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const write = buf => new Promise(res => (ff.stdin.write(buf) ? res() : ff.stdin.once('drain', res)));

  const t0 = Date.now();
  for (let i = from - 1; i < last; i++) {
    const frames = Math.round(durOf(i) * FPS);
    await page.evaluate(i => __deck.go(i), i);
    // 预热：先拨到页尾截一次图，确保本页图片都已解码
    await page.evaluate(ms => __deck.seek(ms), durOf(i) * 1000);
    await page.screenshot({ type: 'jpeg', quality: 50 });
    for (let f = 0; f < frames; f++) {
      await page.evaluate(ms => __deck.seek(ms), (f * 1000) / FPS);
      await write(await page.screenshot({ type: 'jpeg', quality: 92 }));
    }
    console.log(`${String(i + 1).padStart(2, '0')} ${deck.titles[i]}  ${durOf(i)}s  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end();
  await new Promise(res => ff.on('close', res));
  await browser.close();
  console.log('完成：', out);
})();
