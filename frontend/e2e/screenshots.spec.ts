import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Captures the README screenshots from a running stack (best on a fresh volume: `make clean && make up`).
//   E2E_BASE_URL=http://localhost:3000 E2E_API_URL=http://localhost:8000 npx playwright test e2e/screenshots.spec.ts
const OUT = path.resolve(__dirname, "../../docs/screenshots");
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const TERMINAL_DIR = path.resolve(__dirname, "../../docs/terminal");

fs.mkdirSync(OUT, { recursive: true });
const shot = (name: string) => path.join(OUT, name);

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
}

async function send(page: Page, text: string) {
  const count = await page.getByTestId("assistant-message").count();
  const errors = await page.getByTestId("error-message").count();
  await page.getByTestId("chat-input").fill(text);
  await page.getByTestId("send-button").click();
  await expect
    .poll(async () => (await page.getByTestId("assistant-message").count()) + (await page.getByTestId("error-message").count()))
    .toBeGreaterThan(count + errors);
  await page.waitForTimeout(450); // let entry animations settle
}

test.describe.configure({ mode: "serial" });

test("desktop light: empty state, live, cache, failover, 503, system prompt", async ({ page }) => {
  await setTheme(page, "light");
  await page.goto("/");
  await expect(page.getByTestId("backend-status")).toHaveClass(/status-ok/);
  await page.screenshot({ path: shot("01-empty-state-light.png") });

  await send(page, "What is the capital of France?");
  await send(page, "Explain response caching in one short paragraph, with a bullet list of two benefits.");
  await page.screenshot({ path: shot("02-light-chat.png") });
  await page.getByTestId("assistant-message").first().screenshot({ path: shot("03-live-inference-reply.png") });

  await page.getByTestId("new-chat-button").click();
  await send(page, "What is the capital of France?");
  const cached = page.getByTestId("assistant-message").last();
  await expect(cached.getByTestId("meta-source")).toHaveText("LLM_CACHE");
  await cached.screenshot({ path: shot("04-llm-cache-reply.png") });

  await page.getByTestId("tools-button").click(); // simulator lives in the Tools panel
  await page.getByTestId("sim-preset-k1-429").click();
  await send(page, "Write a haiku about failover.");
  await expect(page.getByTestId("assistant-message").last().getByTestId("meta-key")).toHaveText("key_2");
  await page.screenshot({ path: shot("05-failover-key1-to-key2.png") });

  await page.getByTestId("sim-preset-all-429").click();
  await send(page, "Give me three tips for writing clean Python.");
  await expect(page.getByTestId("error-message").last()).toBeVisible();
  await page.screenshot({ path: shot("06-error-503-all-keys-failed.png") });

  await page.getByTestId("new-chat-button").click();
  await page.getByRole("button", { name: "Pirate" }).click();
  await send(page, "Describe the sea in two sentences.");
  await page.screenshot({ path: shot("07-system-prompt.png") });
});

test("desktop dark: chat with code highlighting", async ({ page }) => {
  await setTheme(page, "dark");
  await page.goto("/");
  await send(page, "What is the capital of France?");
  await send(page, "Show a tiny Python function that reverses a string, then one sentence explaining it.");
  await page.screenshot({ path: shot("08-dark-chat.png") });
});

for (const theme of ["light", "dark"] as const) {
  test(`mobile ${theme}`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await setTheme(page, theme);
    await page.goto("/");
    await send(page, "What is the capital of France?");
    await send(page, "Write a haiku about failover.");
    await page.screenshot({ path: shot(`09-mobile-${theme}.png`) });
    await ctx.close();
  });
}

test("swagger /docs", async ({ page }) => {
  await page.goto(`${API}/docs`);
  await expect(page.locator(".swagger-ui")).toBeVisible();
  await page.getByText("/chat", { exact: true }).first().click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: shot("10-swagger-docs.png") });
});

// ---------------------------------------------------------------- terminal output
const ANSI: Record<string, string> = { "1": "font-weight:700", "31": "color:#ff6b6b", "32": "color:#7ee787", "33": "color:#f2cc60", "36": "color:#79c0ff", "2": "opacity:.7" };

function ansiToHtml(text: string): string {
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  let html = "";
  let open = 0;
  for (const part of text.split(/(\u001b\[[0-9;]*m)/)) {
    const m = part.match(/^\u001b\[([0-9;]*)m$/);
    if (!m) {
      html += esc(part);
      continue;
    }
    const codes = m[1].split(";").filter(Boolean);
    if (codes.length === 0 || codes.includes("0") || codes.some((c) => c === "22" || c === "39")) {
      html += "</span>".repeat(open);
      open = 0;
      continue;
    }
    const style = codes.map((c) => ANSI[c]).filter(Boolean).join(";");
    if (style) {
      html += `<span style="${style}">`;
      open++;
    }
  }
  return html + "</span>".repeat(open);
}

for (const [file, title, out] of [
  ["make-up.txt", "make up", "11-terminal-make-up.png"],
  ["pytest.txt", "make test  (pytest)", "12-terminal-pytest.png"],
  ["smoke-test.txt", "make smoke  (scripts/smoke_test.sh)", "13-terminal-smoke-test.png"],
] as const) {
  test(`terminal: ${title}`, async ({ page }) => {
    const src = path.join(TERMINAL_DIR, file);
    test.skip(!fs.existsSync(src), `${src} missing`);
    const body = ansiToHtml(fs.readFileSync(src, "utf8"));
    await page.setViewportSize({ width: 1100, height: 400 });
    await page.setContent(`<!doctype html><html><body style="margin:0;background:#15171a;padding:24px;font-family:'JetBrains Mono',Consolas,monospace">
      <div style="border-radius:12px;overflow:hidden;box-shadow:0 20px 50px rgba(0,0,0,.5);background:#1e2124;border:1px solid #3f444b">
        <div style="display:flex;gap:8px;align-items:center;padding:10px 14px;background:#2a2d31;border-bottom:1px solid #3f444b">
          <span style="width:12px;height:12px;border-radius:50%;background:#e5322d"></span>
          <span style="width:12px;height:12px;border-radius:50%;background:#f2cc60"></span>
          <span style="width:12px;height:12px;border-radius:50%;background:#7ee787"></span>
          <span style="margin-left:10px;color:#a9b0ba;font-size:13px">$ ${title}</span></div>
        <pre style="margin:0;padding:16px 18px;color:#e6e9ee;font-size:12.5px;line-height:1.5;white-space:pre-wrap">${body}</pre>
      </div></body></html>`);
    await page.screenshot({ path: shot(out), fullPage: true });
  });
}
