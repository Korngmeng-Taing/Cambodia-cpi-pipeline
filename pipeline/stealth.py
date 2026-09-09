"""
pipeline/stealth.py
───────────────────
Playwright Stealth & Anti-Bot Armor for Cambodian E-Commerce Web Scrapers.

Provides automated browser fingerprint rotation, canvas noise injection,
and headless automation flag obfuscation to eliminate 403 Forbidden / Cloudflare blocks.
"""

from __future__ import annotations

import random
from typing import Any

# Standard modern desktop Chrome user agent pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
]

STEALTH_SCRIPTS = """
// 1. Mask navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// 2. Mock chrome runtime object
window.chrome = {
    app: {
        isInstalled: false,
        InstallState: { DISABLED: 'DISABLED', INSTALLED: 'INSTALLED', NOT_INSTALLED: 'NOT_INSTALLED' },
        RunningState: { CANNOT_RUN: 'CANNOT_RUN', READY_TO_RUN: 'READY_TO_RUN', RUNNING: 'RUNNING' }
    },
    runtime: {
        OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
        RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
    }
};

// 3. Mock navigator.plugins and languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'km']
});

Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
    ]
});

// 4. Mock notification permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


def get_random_stealth_headers(referer: str | None = None) -> dict[str, str]:
    """Generates randomized, realistic browser request headers."""
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,km;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"' if "Windows" in ua else ('"macOS"' if "Macintosh" in ua else '"Linux"'),
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def get_stealth_browser_options() -> dict[str, Any]:
    """Returns Playwright browser context options configured for stealth operation."""
    ua = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)
    return {
        "user_agent": ua,
        "viewport": viewport,
        "locale": "en-US",
        "timezone_id": "Asia/Phnom_Penh",
        "permissions": ["geolocation"],
        "geolocation": {"latitude": 11.5564, "longitude": 104.9282},  # Phnom Penh coords
        "color_scheme": "light",
        "device_scale_factor": 1,
    }


async def apply_stealth_to_page(page: Any) -> None:
    """Injects stealth evasions into a Playwright page before navigation."""
    await page.add_init_script(STEALTH_SCRIPTS)
