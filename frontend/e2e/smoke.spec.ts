import { test, expect } from "@playwright/test";

test.describe("Frontend smoke and navigation", () => {
  test("public explorer page loads successfully", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/frontend|Model/i);
    // Navbar or brand text should be visible
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });

  test("login page renders email and password fields", async ({ page }) => {
    await page.goto("/login");
    const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name*="email" i]');
    const passwordInput = page.locator('input[type="password"]');
    await expect(emailInput.first()).toBeVisible();
    await expect(passwordInput.first()).toBeVisible();
  });

  test("register page renders signup form", async ({ page }) => {
    await page.goto("/register");
    const passwordInput = page.locator('input[type="password"]');
    await expect(passwordInput.first()).toBeVisible();
  });

  test("docs page loads documentation content", async ({ page }) => {
    await page.goto("/docs");
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });

  test("unknown route redirects to 404 page", async ({ page }) => {
    await page.goto("/unknown-nonexistent-route-12345");
    await expect(page).toHaveURL(/.*404/);
    await expect(page.locator("h1")).toContainText("404");
  });
});
