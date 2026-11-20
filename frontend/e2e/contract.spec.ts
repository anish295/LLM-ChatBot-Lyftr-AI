import { expect, test, type Page } from "@playwright/test";

// UI contract checks (section 5 of the assignment) against a running stack.
const nonce = () => Math.random().toString(36).slice(2, 8);

async function send(page: Page, text: string) {
  await page.getByTestId("chat-input").fill(text);
  await page.getByTestId("send-button").click();
}

test("send a message: input clears, reply carries exact metadata", async ({ page }) => {
  await page.goto("/");
  const msg = `What is 2 + 2? Reply with just the number. (${nonce()})`;
  await send(page, msg);
  await expect(page.getByTestId("chat-input")).toHaveValue("");
  const reply = page.getByTestId("assistant-message").last();
  await expect(reply).toBeVisible();
  await expect(reply.getByTestId("meta-source")).toHaveText(/^(LIVE_INFERENCE|LLM_CACHE)$/);
  await expect(reply.getByTestId("meta-source")).toHaveText("LIVE_INFERENCE");
  await expect(reply.getByTestId("meta-model")).toHaveText(/^\S+\/\S+/);
  await expect(reply.getByTestId("meta-latency")).toHaveText(/^\d+ ms$/);
  await expect(reply.getByTestId("meta-input-tokens")).toHaveText(/^\d+$/);
  await expect(reply.getByTestId("meta-output-tokens")).toHaveText(/^\d+$/);
  await expect(reply.getByTestId("meta-key")).toHaveText("key_1");

  // Same message after a reload (new session) -> served from cache.
  const firstSession = await page.getByTestId("session-id").textContent();
  await page.reload();
  await expect(page.getByTestId("session-id")).not.toHaveText(firstSession!);
  await page.getByTestId("chat-input").fill(msg);
  await page.getByTestId("chat-input").press("Enter");
  const cached = page.getByTestId("assistant-message").last();
  await expect(cached.getByTestId("meta-source")).toHaveText("LLM_CACHE");
  await expect(cached.getByTestId("meta-key")).toHaveText("none");
});

test("multi-turn memory in one session", async ({ page }) => {
  await page.goto("/");
  await send(page, `My favourite colour is teal. Just say "noted". (${nonce()})`);
  await expect(page.getByTestId("assistant-message")).toHaveCount(1);
  await send(page, "What is my favourite colour? One word.");
  await expect(page.getByTestId("assistant-message")).toHaveCount(2);
  await expect(page.getByTestId("assistant-message").nth(1)).toContainText(/teal/i);
});

test("system prompt field changes behaviour", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("system-prompt-input").fill("Always answer in uppercase letters only.");
  await send(page, `Say hello to the reviewer. (${nonce()})`);
  const reply = page.getByTestId("assistant-message").last();
  await expect(reply).toBeVisible();
  const text = (await reply.locator(".markdown").textContent()) ?? "";
  expect(text.replace(/[^A-Za-z]/g, "")).toMatch(/^[A-Z]+$/);
});

test("failover via simulator and clean 503 error", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tools-button").click(); // simulator lives in the Tools panel
  await expect(page.getByTestId("backend-status")).toHaveClass(/status-ok/);
  await page.getByTestId("sim-preset-k1-429").click();
  await send(page, `Name a planet. (${nonce()})`);
  const reply = page.getByTestId("assistant-message").last();
  await expect(reply.getByTestId("meta-key")).toHaveText("key_2");
  await expect(reply.getByTestId("meta-fallbacks")).toHaveText("1");
  await expect(reply.getByTestId("failover-chip")).toContainText("key_1 → key_2");

  await page.getByTestId("sim-preset-all-429").click();
  await send(page, `Name another planet. (${nonce()})`);
  const err = page.getByTestId("error-message").last();
  await expect(err).toContainText("All AI providers are currently unavailable");
  await expect(page.getByTestId("assistant-message")).toHaveCount(1); // errors are not assistant messages
});

test("422 renders a readable error, never a blank screen", async ({ page }) => {
  await page.goto("/");
  await send(page, "     ");
  await expect(page.getByTestId("error-message")).toContainText("1–4000 characters");
  await expect(page.getByTestId("chat-input")).toBeVisible();
});
