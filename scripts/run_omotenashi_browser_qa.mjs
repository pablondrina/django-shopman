#!/usr/bin/env node
import fs from "node:fs/promises";
import { accessSync, constants } from "node:fs";
import { execFileSync, spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_SCREENSHOTS_DIR = "/tmp/shopman-omotenashi-qa-screens";
const DEFAULT_REPORT_PATH = "/tmp/shopman-omotenashi-qa-browser.json";

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.SHOPMAN_QA_BASE_URL || DEFAULT_BASE_URL,
    screenshotsDir: process.env.SHOPMAN_QA_SCREENSHOTS_DIR || DEFAULT_SCREENSHOTS_DIR,
    reportPath: process.env.SHOPMAN_QA_BROWSER_REPORT || DEFAULT_REPORT_PATH,
    matrixPath: process.env.SHOPMAN_QA_MATRIX || "",
    chromePath: process.env.SHOPMAN_CHROME_PATH || process.env.CHROME_PATH || "",
    sessionCookie: process.env.SHOPMAN_SESSION_COOKIE || "",
    strict: false,
    ignoreCertificateErrors: false,
  };

  for (const arg of argv) {
    if (arg === "--strict") options.strict = true;
    else if (arg === "--ignore-certificate-errors") options.ignoreCertificateErrors = true;
    else if (arg.startsWith("--base-url=")) options.baseUrl = arg.slice("--base-url=".length);
    else if (arg.startsWith("--screenshots-dir=")) options.screenshotsDir = arg.slice("--screenshots-dir=".length);
    else if (arg.startsWith("--report=")) options.reportPath = arg.slice("--report=".length);
    else if (arg.startsWith("--matrix=")) options.matrixPath = arg.slice("--matrix=".length);
    else if (arg.startsWith("--chrome-path=")) options.chromePath = arg.slice("--chrome-path=".length);
    else if (arg.startsWith("--session-cookie=")) options.sessionCookie = arg.slice("--session-cookie=".length);
    else if (arg === "--help") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Argumento desconhecido: ${arg}`);
    }
  }

  options.baseUrl = options.baseUrl.replace(/\/+$/, "");
  return options;
}

function printHelp() {
  console.log(`Uso: node scripts/run_omotenashi_browser_qa.mjs [opcoes]

Opcoes:
  --base-url=http://127.0.0.1:8000        Servidor Shopman ja rodando
  --matrix=/tmp/omotenashi.json           Usa JSON gerado por omotenashi_qa
  --screenshots-dir=/tmp/screens          Diretorio das screenshots
  --report=/tmp/browser-report.json       Relatorio JSON de saida
  --chrome-path=/path/to/Chrome           Binario Chrome/Chromium
  --session-cookie=sessionid=...          Cookie admin ja autenticado
  --strict                                Exit code 1 se houver review/fail
  --ignore-certificate-errors             Util para staging com certificado local

Sem --matrix, o script executa manage.py omotenashi_qa --json.
Sem --session-cookie em localhost, o script cria uma sessao admin local via Django.`);
}

function parseViewport(raw) {
  if (raw && typeof raw === "object" && raw.width && raw.height) return raw;
  const text = String(raw || "desktop 1366x768");
  const match = text.match(/(\d+)x(\d+)/);
  return match
    ? { width: Number(match[1]), height: Number(match[2]), label: text }
    : { width: 1366, height: 768, label: text };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractJsonObject(raw, label) {
  const text = String(raw || "").trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end < start) {
    throw new Error(`Nao foi possivel ler JSON de ${label}.`);
  }
  return JSON.parse(text.slice(start, end + 1));
}

async function readMatrix(options) {
  if (options.matrixPath) {
    return JSON.parse(await fs.readFile(options.matrixPath, "utf8"));
  }

  const python = process.env.PYTHON || ".venv/bin/python";
  const output = execFileSync(python, ["manage.py", "omotenashi_qa", "--json"], {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  });
  return extractJsonObject(output, "manage.py omotenashi_qa --json");
}

function assertMatrixReady(matrix) {
  const counts = matrix.counts || {};
  if (counts.missing > 0 || matrix.status === "missing") {
    throw new Error(
      `Matriz Omotenashi incompleta: ready=${counts.ready ?? "?"} missing=${counts.missing ?? "?"}. Rode make seed.`,
    );
  }
  if (!Array.isArray(matrix.checks) || matrix.checks.length === 0) {
    throw new Error("Matriz Omotenashi sem checks navegaveis.");
  }
}

function isLocalBaseUrl(baseUrl) {
  const hostname = new URL(baseUrl).hostname;
  return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1";
}

function normalizeCookie(raw) {
  if (!raw) return null;
  const [name, ...rest] = raw.split("=");
  const value = rest.join("=");
  if (!name || !value) return { name: "sessionid", value: raw };
  return { name, value };
}

function buildLocalSessionCookie() {
  const python = process.env.PYTHON || ".venv/bin/python";
  const code = `
import json
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore

User = get_user_model()
user = User._default_manager.filter(is_superuser=True, is_active=True).order_by("pk").first()
if user is None:
    username_field = User.USERNAME_FIELD
    kwargs = {
        username_field: "omotenashi-browser-qa",
        "password": "unused-local-password",
    }
    field_names = {field.name for field in User._meta.fields}
    if "email" in field_names:
        kwargs["email"] = "omotenashi-browser-qa@example.invalid"
    user = User._default_manager.create_superuser(**kwargs)

session = SessionStore()
session[SESSION_KEY] = str(user._meta.pk.value_to_string(user))
session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
session[HASH_SESSION_KEY] = user.get_session_auth_hash()
session.save()
print(json.dumps({"name": settings.SESSION_COOKIE_NAME, "value": session.session_key}))
`;
  const output = execFileSync(python, ["manage.py", "shell", "-c", code], {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  });
  return extractJsonObject(output, "sessao admin local");
}

function resolveCookie(options) {
  const provided = normalizeCookie(options.sessionCookie);
  if (provided) return provided;
  if (isLocalBaseUrl(options.baseUrl)) return buildLocalSessionCookie();
  throw new Error("Informe --session-cookie=sessionid=... para QA browser fora de localhost.");
}

function findChrome(explicitPath) {
  const candidates = [
    explicitPath,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/opt/google/chrome/chrome",
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      accessSync(candidate, constants.X_OK);
      return candidate;
    } catch {
      // Try the next known location.
    }
  }

  throw new Error("Chrome/Chromium nao encontrado. Defina SHOPMAN_CHROME_PATH ou --chrome-path.");
}

async function waitFetch(url, options = {}, timeoutMs = 12000) {
  const started = Date.now();
  let lastErr;
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url, options);
      if (response.ok) return response;
      lastErr = new Error(`HTTP ${response.status} em ${url}`);
    } catch (err) {
      lastErr = err;
    }
    await sleep(200);
  }
  throw lastErr ?? new Error(`Timeout aguardando ${url}`);
}

async function assertServerReachable(baseUrl) {
  const healthUrl = new URL("/health/", baseUrl).toString();
  try {
    await waitFetch(healthUrl, {}, 5000);
  } catch (err) {
    throw new Error(`Servidor Shopman indisponivel em ${healthUrl}: ${err.message}`);
  }
}

function buildAuditExpression() {
  return `(${function () {
    const visible = (el) => {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
    };
    const labelFor = (el) =>
      (el.getAttribute("aria-label") || el.innerText || el.value || el.name || el.id || el.tagName || "")
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 80);
    const isWithinHorizontalScroll = (el) => {
      for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) {
        const style = getComputedStyle(node);
        const canScroll = node.scrollWidth > node.clientWidth + 1;
        const overflowX = style.overflowX;
        if (canScroll && (overflowX === "auto" || overflowX === "scroll" || overflowX === "hidden")) return true;
      }
      return false;
    };
    const controls = Array.from(
      document.querySelectorAll('a, button, input, select, textarea, [role="button"], [tabindex]'),
    ).filter(visible);
    const targetData = (el) => {
      const rect = el.getBoundingClientRect();
      return {
        label: labelFor(el),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        x: Math.round(rect.x),
        y: Math.round(rect.y),
      };
    };
    const offscreen = controls
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return {
          label: labelFor(el),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          top: Math.round(rect.top),
          bottom: Math.round(rect.bottom),
          intentionalScroll: isWithinHorizontalScroll(el),
        };
      })
      .filter((item) => item.left < -1 || item.right > window.innerWidth + 1);
    const headings = Array.from(document.querySelectorAll("h1,h2,h3"))
      .filter(visible)
      .slice(0, 10)
      .map((el) => el.tagName + ":" + el.innerText.trim().replace(/\s+/g, " ").slice(0, 90));
    const text = document.body ? document.body.innerText.replace(/\s+/g, " ").trim().slice(0, 900) : "";
    const errors = Array.from(document.querySelectorAll('.error, .errorlist, [role="alert"]'))
      .filter(visible)
      .map((el) => el.innerText.trim().replace(/\s+/g, " ").slice(0, 180));
    return {
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      bodyWidth: document.body ? document.body.scrollWidth : 0,
      hOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      loginPage: /\/login\/?/.test(location.pathname),
      headings,
      errors,
      tinyTargets: controls
        .map(targetData)
        .filter((item) => (item.width > 0 && item.width < 32) || (item.height > 0 && item.height < 32))
        .slice(0, 20),
      offscreenControls: offscreen.filter((item) => !item.intentionalScroll).slice(0, 20),
      scrollableOffscreenControls: offscreen.filter((item) => item.intentionalScroll).slice(0, 20),
      textExcerpt: text,
    };
  }.toString()})()`;
}

function createCdpClient(wsUrl) {
  let id = 0;
  const pending = new Map();
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(`${msg.error.message}: ${msg.error.data || ""}`));
      else resolve(msg.result);
    }
  };

  return {
    open: () =>
      new Promise((resolve, reject) => {
        ws.onopen = resolve;
        ws.onerror = reject;
      }),
    close: () => ws.close(),
    send: (method, params = {}) =>
      new Promise((resolve, reject) => {
        const msgId = ++id;
        pending.set(msgId, { resolve, reject });
        ws.send(JSON.stringify({ id: msgId, method, params }));
      }),
  };
}

async function waitForDocument(client, timeoutMs = 9000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const evaluated = await client.send("Runtime.evaluate", {
      expression: 'document.readyState === "complete" || document.readyState === "interactive"',
      returnByValue: true,
    });
    if (evaluated.result.value === true) return;
    await sleep(150);
  }
  throw new Error("Timeout aguardando document.readyState.");
}

async function runBrowserQa(matrix, options) {
  if (typeof WebSocket === "undefined") {
    throw new Error("Este runner precisa de Node.js com WebSocket global. Use Node 22+.");
  }

  const chromePath = findChrome(options.chromePath);
  const cookie = resolveCookie(options);
  await assertServerReachable(options.baseUrl);
  await fs.rm(options.screenshotsDir, { recursive: true, force: true });
  await fs.mkdir(options.screenshotsDir, { recursive: true });
  await fs.mkdir(path.dirname(options.reportPath), { recursive: true });

  const userDataDir = `/tmp/shopman-chrome-profile-${Date.now()}`;
  const port = 9222 + Math.floor(Math.random() * 1000);
  const chromeArgs = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--hide-scrollbars",
  ];
  if (process.env.CI) chromeArgs.push("--no-sandbox");
  if (options.ignoreCertificateErrors) chromeArgs.push("--ignore-certificate-errors");

  const chrome = spawn(chromePath, chromeArgs, { stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  chrome.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  let client;
  try {
    await waitFetch(`http://127.0.0.1:${port}/json/version`);
    const targetResponse = await waitFetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" });
    const target = await targetResponse.json();
    client = createCdpClient(target.webSocketDebuggerUrl);
    await client.open();
    await client.send("Runtime.enable");
    await client.send("Page.enable");
    await client.send("Network.enable");
    await client.send("Network.setCookie", {
      name: cookie.name,
      value: cookie.value,
      url: options.baseUrl,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    });

    const auditExpression = buildAuditExpression();
    const results = [];
    for (const check of matrix.checks) {
      const viewport = parseViewport(check.viewport);
      await client.send("Emulation.setDeviceMetricsOverride", {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: 1,
        mobile: viewport.width < 700,
      });
      const url = new URL(check.url, options.baseUrl).toString();
      await client.send("Page.navigate", { url });
      await waitForDocument(client);
      await sleep(800);
      await client.send("Runtime.evaluate", {
        expression: "document.fonts ? document.fonts.ready : Promise.resolve()",
        awaitPromise: true,
      });
      const evaluated = await client.send("Runtime.evaluate", {
        expression: auditExpression,
        returnByValue: true,
      });
      const audit = evaluated.result.value;
      const filename = `${check.id.replace(/[^a-z0-9._-]+/gi, "_")}-${viewport.width}x${viewport.height}.png`;
      const screenshot = await client.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: false,
        fromSurface: true,
      });
      const screenshotPath = path.join(options.screenshotsDir, filename);
      await fs.writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));

      const blockers = [];
      if (audit.loginPage) blockers.push("login-page");
      if (audit.hOverflow) blockers.push("horizontal-overflow");
      if (audit.offscreenControls.length) blockers.push("offscreen-controls");
      if (evaluated.exceptionDetails) blockers.push("runtime-exception");

      const status = blockers.length ? "review" : "pass";
      results.push({
        id: check.id,
        persona: check.persona,
        title: check.title,
        url,
        viewport,
        status,
        blockers,
        screenshot: screenshotPath,
        audit,
      });
      console.log(`${status} ${check.id} ${viewport.width}x${viewport.height}`);
    }

    const report = {
      generated_at: new Date().toISOString(),
      base_url: options.baseUrl,
      screenshots_dir: options.screenshotsDir,
      summary: {
        total: results.length,
        pass: results.filter((item) => item.status === "pass").length,
        review: results.filter((item) => item.status === "review").length,
      },
      results,
    };
    await fs.writeFile(options.reportPath, JSON.stringify(report, null, 2));
    return report;
  } finally {
    if (client) client.close();
    chrome.kill("SIGTERM");
    await sleep(300);
    await fs.rm(userDataDir, { recursive: true, force: true });
    if (stderr.trim()) {
      await fs.writeFile("/tmp/shopman-omotenashi-qa-chrome.stderr.log", stderr);
    }
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const matrix = await readMatrix(options);
  assertMatrixReady(matrix);
  const report = await runBrowserQa(matrix, options);
  console.log(JSON.stringify(report.summary));
  console.log(`screenshots=${options.screenshotsDir}`);
  console.log(`report=${options.reportPath}`);
  if (options.strict && report.summary.review > 0) {
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(`omotenashi-browser-qa failed: ${err.message}`);
  process.exit(1);
});
