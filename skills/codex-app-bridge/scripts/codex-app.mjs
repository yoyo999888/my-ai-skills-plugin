#!/usr/bin/env node
// codex-app.mjs — 从 Claude Code 侧驱动 Codex 桌面 app 的 app-server
//
// 用法：
//   node codex-app.mjs list <cwd>
//   node codex-app.mjs send <threadId> <cwd> <sandbox> <outJson|-> <prompt...>
//   node codex-app.mjs new  <cwd> <sandbox> <outJson|-> <prompt...>
//
// sandbox: read-only | workspace-write
//   注意：send（resume 已有 thread）实测一律按 read-only 执行，此参数不生效。
//   要让 codex 写盘，必须用 new 开新 thread + workspace-write，且写入路径在 workspace root 内。
//
// outJson 传 "-" 表示不落文件，只打印到 stdout。

import fs from "node:fs";
import path from "node:path";

function resolveCodexLib() {
  const roots = [
    `${process.env.HOME}/.claude/plugins/cache/openai-codex/codex`,
    `${process.env.HOME}/.claude/plugins/marketplaces/openai-codex/plugins/codex`
  ];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const direct = path.join(root, "scripts/lib/codex.mjs");
    if (fs.existsSync(direct)) return direct;
    const versions = fs.readdirSync(root).sort().reverse();
    for (const v of versions) {
      const p = path.join(root, v, "scripts/lib/codex.mjs");
      if (fs.existsSync(p)) return p;
    }
  }
  throw new Error("找不到 openai-codex 插件的 scripts/lib/codex.mjs，请先安装 codex 插件。");
}

const libPath = resolveCodexLib();
const { runAppServerTurn } = await import(libPath);

const [cmd, ...rest] = process.argv.slice(2);

if (cmd === "list") {
  const cwd = rest[0] ?? process.cwd();
  const appServer = await import(path.join(path.dirname(libPath), "app-server.mjs"));
  const client = await appServer.CodexAppServerClient.connect(cwd);
  const res = await client.request("thread/list", { cwd, limit: 30, sortKey: "updated_at" });
  for (const t of res.data) console.log(`${t.id}\t${t.updatedAt ?? ""}\t${t.name ?? "(unnamed)"}`);
  await client.close();
  process.exit(0);
}

if (cmd !== "send" && cmd !== "new") {
  console.error("用法: list <cwd> | send <threadId> <cwd> <sandbox> <outJson|-> <prompt> | new <cwd> <sandbox> <outJson|-> <prompt>");
  process.exit(2);
}

const threadId = cmd === "send" ? rest.shift() : null;
const [cwd, sandbox, outJson, ...promptParts] = rest;
const prompt = promptParts.join(" ");
if (!cwd || !prompt) {
  console.error("缺少 cwd 或 prompt");
  process.exit(2);
}

const startedAt = new Date().toISOString();
const progress = [];
let result;
try {
  result = await runAppServerTurn(cwd, {
    resumeThreadId: threadId ?? undefined,
    prompt,
    sandbox: sandbox || "read-only",
    onProgress: (u) => {
      const line = typeof u === "string" ? u : u.message;
      progress.push(line);
      process.stderr.write(`[p] ${line}\n`);
    }
  });
} catch (err) {
  result = { status: 1, error: String(err?.message ?? err) };
}

const payload = {
  startedAt,
  finishedAt: new Date().toISOString(),
  threadId: result.threadId ?? threadId,
  turnId: result.turnId ?? null,
  status: result.status,
  finalMessage: result.finalMessage ?? null,
  error: result.error ?? null,
  touchedFiles: result.touchedFiles ?? [],
  progress
};

if (outJson && outJson !== "-") {
  fs.mkdirSync(path.dirname(path.resolve(outJson)), { recursive: true });
  fs.writeFileSync(outJson, JSON.stringify(payload, null, 2), "utf8");
}
console.log(JSON.stringify(payload, null, 2));
process.exit(payload.status === 0 ? 0 : 1);
