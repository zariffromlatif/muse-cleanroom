// Render video.html to frames with headless Chromium and pipe them to ffmpeg.
//
//   node render.mjs --stills 0,6,12.6,22,40 out/   one PNG per time, for checking layout
//   node render.mjs out/frames.mp4                 the whole video, silent (build.sh adds audio)
//   CUT=1 node render.mjs out/overlay.mov          the Seedance cut's graphics and captions, with
//                                                  alpha where the shots go (cut.py composites them)
//   PAGE=../launch/launch.html SIZE=1920x1080 ALPHA=1 node render.mjs out.mov
//                                                  any other page, any size, with alpha
//
// Each worker owns a contiguous slice of frames and writes its own segment; the
// segments are joined losslessly at the end.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch { playwright = require("/opt/node-tools/node_modules/playwright"); }

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CUT = !!process.env.CUT;
const ALPHA = CUT || !!process.env.ALPHA;
const PAGE = pathToFileURL(path.resolve(HERE, process.env.PAGE || "video.html")).href + (CUT ? "?still&cut" : "?still");
const [W, H] = (process.env.SIZE || "1080x1080").split("x").map(Number);
const FPS = 30;
// With alpha, frames go into a PNG-in-MOV stream; otherwise straight to H.264.
const ENCODE = ALPHA ? ["-c:v", "png", "-pix_fmt", "rgba"] : ["-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p"];

async function openPage(browser) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto(PAGE);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })));
  });
  return page;
}

function ffmpeg(args) {
  const p = spawn("ffmpeg", args, { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => p.on("close", c => c === 0 ? res() : rej(new Error("ffmpeg exit " + c))));
  return { stdin: p.stdin, done };
}

async function renderSegment(browser, from, to, file) {
  const page = await openPage(browser);
  const ff = ffmpeg(["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-", ...ENCODE, file]);
  for (let i = from; i < to; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    const png = await page.screenshot({ type: "png", omitBackground: ALPHA });
    if (!ff.stdin.write(png)) await new Promise(r => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  await ff.done;
  await page.close();
}

const args = process.argv.slice(2);
const browser = await playwright.chromium.launch();
try {
  if (args[0] === "--stills") {
    const times = args[1].split(",").map(Number);
    const out = args[2] || path.join(HERE, "out");
    mkdirSync(out, { recursive: true });
    const page = await openPage(browser);
    for (const t of times) {
      await page.evaluate(t => window.render(t), t);
      writeFileSync(path.join(out, `still-${t.toFixed(2)}.png`), await page.screenshot({ type: "png", omitBackground: ALPHA }));
    }
  } else {
    const out = path.resolve(args[0] || path.join(HERE, "out", "frames.mp4"));
    const tmp = path.join(path.dirname(out), "segments");
    mkdirSync(tmp, { recursive: true });
    const page = await openPage(browser);
    const total = Math.round(await page.evaluate(() => window.DURATION) * FPS);
    await page.close();
    const workers = Number(process.env.WORKERS || 4);
    const per = Math.ceil(total / workers);
    const files = [];
    const jobs = [];
    for (let w = 0; w < workers; w++) {
      const from = w * per, to = Math.min(total, from + per);
      if (from >= to) break;
      const f = path.join(tmp, `seg${w}${path.extname(out)}`);
      files.push(f);
      jobs.push(renderSegment(browser, from, to, f));
    }
    await Promise.all(jobs);
    const list = path.join(tmp, "list.txt");
    writeFileSync(list, files.map(f => `file '${f}'`).join("\n"));
    await ffmpeg(["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", out]).done;
    rmSync(tmp, { recursive: true, force: true });
    console.log(`rendered ${total} frames -> ${out}`);
  }
} finally {
  await browser.close();
}
