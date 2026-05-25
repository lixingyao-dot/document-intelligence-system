import fs from "node:fs/promises";
import { readFileSync } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const runtimeNodeModules =
  "C:/Users/limouma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const require = createRequire(import.meta.url);
const artifactPath = require.resolve("@oai/artifact-tool", { paths: [runtimeNodeModules] });
const { Presentation, PresentationFile, text, image, shape, fill } = await import(
  pathToFileURL(artifactPath).href
);

const W = 1920;
const H = 1080;
const root = process.cwd();
const out = path.join(root, "output");
const assetDir = path.join(out, "presentation_assets");
const previewDir = path.join(out, "presentation_previews");
const parityDir = path.join(out, "presentation_pptx_parity");
await fs.mkdir(out, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
await fs.mkdir(parityDir, { recursive: true });

const C = {
  paper: "#f7f3ea",
  paper2: "#efe8da",
  ink: "#171512",
  mute: "#6b6255",
  line: "#d7cebe",
  blue: "#2f5cff",
  cyan: "#37a4ff",
  green: "#2fb36d",
  amber: "#d59a2f",
  red: "#c9514a",
  dark: "#111827",
  white: "#ffffff",
};
const font = "Microsoft YaHei UI";
const mono = "Cascadia Mono";

function img(name) {
  const bytes = readFileSync(path.join(assetDir, name));
  return `data:image/png;base64,${bytes.toString("base64")}`;
}

function frame(left, top, width, height) {
  return { left, top, width, height };
}

function addText(slide, value, box, style, name) {
  slide.compose(
    text(value, {
      name,
      width: fill,
      height: fill,
      style: { fontFamily: font, color: C.ink, ...style },
    }),
    { frame: box, baseUnit: 8 },
  );
}

function addBox(slide, box, fillColor, line = null, radius = 0) {
  slide.compose(
    shape({
      name: "box",
      width: fill,
      height: fill,
      fill: fillColor,
      line,
      borderRadius: radius,
    }),
    { frame: box, baseUnit: 8 },
  );
}

function addRule(slide, x, y, width, color = C.blue, height = 5) {
  addBox(slide, frame(x, y, width, height), color, null, 0);
}

function addImage(slide, name, box, alt, fit = "contain", radius = 14) {
  addBox(slide, box, C.white, { color: C.line, width: 1.25 }, radius + 4);
  const pad = 10;
  slide.compose(
    image({
      name,
      dataUrl: img(name),
      width: fill,
      height: fill,
      fit,
      alt,
      borderRadius: radius,
    }),
    {
      frame: frame(box.left + pad, box.top + pad, box.width - pad * 2, box.height - pad * 2),
      baseUnit: 8,
    },
  );
}

function addHeader(slide, kicker, title, page) {
  addText(slide, kicker, frame(92, 64, 820, 30), {
    fontFamily: mono,
    fontSize: 19,
    bold: true,
    color: C.blue,
  }, `kicker-${page}`);
  addText(slide, title, frame(92, 104, 1280, 118), {
    fontSize: 56,
    bold: true,
    lineSpacingMultiple: 0.95,
  }, `title-${page}`);
}

function addFooter(slide, page) {
  addText(slide, "Document Intelligence System | 5 min presentation", frame(92, 1018, 760, 30), {
    fontFamily: mono,
    fontSize: 14,
    color: "#8a8173",
  }, `footer-${page}`);
  addText(slide, String(page).padStart(2, "0"), frame(1778, 1008, 56, 40), {
    fontFamily: mono,
    fontSize: 16,
    bold: true,
    color: C.blue,
  }, `page-${page}`);
}

function chip(slide, label, x, y, w, color) {
  addBox(slide, frame(x, y, w, 42), C.white, { color: C.line, width: 1 }, 999);
  addText(slide, label, frame(x + 18, y + 8, w - 36, 26), {
    fontSize: 17,
    bold: true,
    color,
  }, `chip-${label}`);
}

function metric(slide, value, label, x, y, color) {
  addText(slide, value, frame(x, y, 270, 64), {
    fontFamily: mono,
    fontSize: 46,
    bold: true,
    color,
  }, `metric-${value}`);
  addText(slide, label, frame(x, y + 66, 300, 34), {
    fontSize: 20,
    color: C.mute,
  }, `metric-label-${label}`);
}

function makeSlide(p, bg = C.paper) {
  const slide = p.slides.add();
  slide.background.fill = bg;
  return slide;
}

const p = Presentation.create({ slideSize: { width: W, height: H } });

// 1 Cover
{
  const s = makeSlide(p, C.dark);
  addText(s, "DOCUMENT INTELLIGENCE", frame(92, 388, 660, 32), {
    fontFamily: mono,
    fontSize: 20,
    bold: true,
    color: C.cyan,
  }, "cover-kicker");
  addText(s, "文档智能系统", frame(92, 448, 760, 112), {
    fontSize: 92,
    bold: true,
    color: C.white,
  }, "cover-title");
  addText(s, "基于大模型的多源文档理解、填表与工作流编排桌面应用", frame(92, 594, 850, 48), {
    fontSize: 30,
    color: "#d6e4ff",
  }, "cover-subtitle");
  addRule(s, 92, 666, 260, C.cyan, 5);
  addText(s, "5 分钟项目展示 | Electron + Vue + FastAPI + Agents", frame(92, 710, 760, 36), {
    fontFamily: mono,
    fontSize: 20,
    color: "#a7b5d6",
  }, "cover-meta");
  addImage(s, "img06.png", frame(1020, 146, 808, 790), "Workflow canvas screenshot", "contain", 22);
}

// 2 Background
{
  const s = makeSlide(p);
  addHeader(s, "01 / 项目背景", "问题：办公文档多、散、格式不统一", 2);
  addText(s, "人工阅读、摘录、填表，会把大量时间消耗在重复劳动上。", frame(92, 315, 760, 120), {
    fontSize: 44,
    bold: true,
    lineSpacingMultiple: 1.1,
  }, "s2-claim");
  chip(s, "PDF / Word", 92, 478, 160, C.blue);
  chip(s, "Excel", 270, 478, 110, C.green);
  chip(s, "Markdown / TXT", 398, 478, 210, C.amber);
  addText(s, "目标是把“读文档、理解信息、生成结果”收束成一个本地桌面工作台。", frame(92, 560, 780, 86), {
    fontSize: 28,
    color: C.mute,
    lineSpacingMultiple: 1.18,
  }, "s2-body");
  addBox(s, frame(1010, 302, 780, 420), C.white, { color: C.line, width: 1.25 }, 24);
  metric(s, "3", "应用入口：文档库 / 对话 / 工作流", 1072, 372, C.blue);
  metric(s, "4", "Agent 能力：理解 / 编辑 / 抽取 / 填表", 1430, 372, C.green);
  metric(s, "21+", "手工测试样例", 1072, 560, C.amber);
  metric(s, "EXE", "桌面端安装与免安装包", 1430, 560, C.red);
  addFooter(s, 2);
}

// 3 Architecture
{
  const s = makeSlide(p);
  addHeader(s, "02 / 技术架构", "架构：桌面壳承载本地 API，核心能力由 Agent 编排", 3);
  const boxes = [
    ["Electron 主进程：窗口管理、启动后端、保存文件对话框", C.ink],
    ["Vue 3 前端：文档库、智能对话、工作流画布", C.blue],
    ["FastAPI 本地服务：会话、文件、消息、工作流接口", C.green],
    ["Core Agents：理解、编辑、抽取、填表与 LLM 调用", C.amber],
  ];
  boxes.forEach(([label, color], i) => {
    const y = 292 + i * 122;
    addBox(s, frame(92, y, 920, 82), C.white, { color: C.line, width: 1 }, 18);
    addText(s, label, frame(120, y + 22, 860, 36), {
      fontSize: 26,
      bold: true,
      color,
    }, `arch-${i}`);
    if (i < boxes.length - 1) addRule(s, 534, y + 96, 36, C.line, 4);
  });
  addText(s, "桌面版把复杂部署问题降到最低：用户只需要启动应用，后端和前端在本机协同运行。", frame(1110, 292, 690, 116), {
    fontSize: 36,
    bold: true,
    lineSpacingMultiple: 1.1,
  }, "s3-claim");
  addText(s, "数据默认落在本地目录，模型 Key 通过设置页保存；后续可扩展为服务端数据库或云存储。", frame(1110, 430, 690, 92), {
    fontSize: 25,
    color: C.mute,
  }, "s3-body");
  addImage(s, "img14.png", frame(1110, 560, 590, 330), "Packaging terminal screenshot", "contain", 16);
  addFooter(s, 3);
}

// 4 Product surface
{
  const s = makeSlide(p);
  addHeader(s, "03 / 产品功能", "界面：围绕“资料、对话、流程”组织用户任务", 4);
  addImage(s, "img04.png", frame(92, 280, 760, 340), "Library view", "contain", 16);
  addImage(s, "img07.png", frame(908, 280, 420, 340), "Settings modal", "contain", 16);
  addImage(s, "img03.png", frame(1382, 280, 430, 340), "Save result", "contain", 16);
  addText(s, "本地桌面体验", frame(92, 692, 560, 56), {
    fontSize: 42,
    bold: true,
  }, "s4-point-title");
  addText(s, "文件导入、模型配置、处理结果保存都在应用内完成，减少用户在多个工具之间来回切换。", frame(92, 764, 1120, 72), {
    fontSize: 27,
    color: C.mute,
  }, "s4-point-body");
  addFooter(s, 4);
}

// 5 Chat and Agents
{
  const s = makeSlide(p);
  addHeader(s, "04 / Agent 能力", "智能对话：一个入口覆盖四类 Agent", 5);
  addImage(s, "img09.png", frame(92, 282, 1030, 610), "Chat understanding screenshot", "contain", 16);
  addText(s, "三类核心智能体（本地）", frame(1190, 292, 520, 52), {
    fontSize: 40,
    bold: true,
  }, "s5-list-title");
  const agents = [
    ["智能体 A：文档理解与自然语言编辑", C.blue],
    ["智能体 B：实体/字段抽取，输出结构化数据", C.green],
    ["智能体 D：Excel 数据筛选与模板填表", C.red],
  ];
  agents.forEach(([label, color], i) => {
    addText(s, label, frame(1190, 370 + i * 64, 610, 40), {
      fontSize: 25,
      bold: true,
      color,
    }, `agent-${i}`);
  });
  addText(s, "关键点：对话并不是单纯聊天，而是把文件、模式、结果文件和工作流连接起来。", frame(1190, 672, 600, 100), {
    fontSize: 24,
    color: C.mute,
  }, "s5-note");
  addFooter(s, 5);
}

// 6 Workflow
{
  const s = makeSlide(p);
  addHeader(s, "05 / 自动化编排", "工作流：把一次性处理沉淀成可复用流程", 6);
  addImage(s, "img06.png", frame(92, 278, 1110, 620), "Workflow canvas", "contain", 16);
  addText(s, "典型流程", frame(1260, 292, 460, 56), {
    fontSize: 40,
    bold: true,
  }, "s6-typical");
  addText(s, "文档输入 -> 摘要/翻译/抽取 -> 文件输出", frame(1260, 376, 560, 92), {
    fontFamily: mono,
    fontSize: 28,
    bold: true,
    color: C.blue,
  }, "s6-flow");
  addText(s, "节点参数来自前端配置，后端统一交给 WorkflowCoordinator 和 TaskExecutor 执行。", frame(1260, 506, 560, 112), {
    fontSize: 26,
    color: C.mute,
  }, "s6-desc");
  chip(s, "可视化", 1260, 670, 120, C.blue);
  chip(s, "可复用", 1398, 670, 120, C.green);
  chip(s, "可批量", 1536, 670, 120, C.amber);
  addFooter(s, 6);
}

// 7 Testing
{
  const s = makeSlide(p);
  addHeader(s, "06 / 测试结果", "验证：真实样例覆盖多格式处理与打包运行", 7);
  addImage(s, "img08.png", frame(92, 282, 420, 260), "Excel source data", "contain", 10);
  addImage(s, "img13.png", frame(540, 282, 420, 260), "Excel result", "contain", 10);
  addImage(s, "img12.png", frame(92, 572, 420, 260), "Word result", "contain", 10);
  addImage(s, "img10.png", frame(540, 572, 420, 260), "PDF report", "contain", 10);
  addText(s, "演示价值", frame(1060, 292, 520, 52), {
    fontSize: 42,
    bold: true,
  }, "s7-title");
  const outcomes = [
    "1. 多格式文档可以统一进入系统处理",
    "2. 大模型能力被封装为可调用的 Agent",
    "3. 处理结果可落地为 Word、Excel、PDF、Markdown 等文件",
  ];
  outcomes.forEach((label, i) => {
    addText(s, label, frame(1060, 380 + i * 72, 760, 44), {
      fontSize: 27,
      color: C.ink,
    }, `outcome-${i}`);
  });
  addBox(s, frame(1060, 668, 700, 112), "#eef5ff", { color: "#b9cffc", width: 1 }, 18);
  addText(s, "下一步：加强批量任务监控、错误恢复和更多企业模板适配。", frame(1088, 696, 640, 58), {
    fontSize: 26,
    bold: true,
    color: C.blue,
  }, "s7-next");
  addFooter(s, 7);
}

const pptxPath = path.join(out, "文档智能系统_5分钟项目展示.pptx");
const pptx = await PresentationFile.exportPptx(p);
await pptx.save(pptxPath);

for (let i = 0; i < p.slides.count; i += 1) {
  const slide = p.slides.getItem(i);
  const png = await slide.export({ format: "png" });
  await fs.writeFile(
    path.join(previewDir, `slide-${String(i + 1).padStart(2, "0")}.png`),
    new Uint8Array(await png.arrayBuffer()),
  );
}

const reloaded = await PresentationFile.importPptx(await fs.readFile(pptxPath));
for (let i = 0; i < reloaded.slides.count; i += 1) {
  const slide = reloaded.slides.getItem(i);
  const png = await slide.export({ format: "png" });
  await fs.writeFile(
    path.join(parityDir, `slide-${String(i + 1).padStart(2, "0")}.png`),
    new Uint8Array(await png.arrayBuffer()),
  );
}

console.log(`PPTX\t${pptxPath}`);
console.log(`PREVIEWS\t${previewDir}`);
console.log(`PPTX_PARITY\t${parityDir}`);
