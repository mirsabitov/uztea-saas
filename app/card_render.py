import logging

logger = logging.getLogger('app')


def render_card_png(html: str, selector: str = '.card', scale: int = 3) -> bytes:
    """Render an HTML string with headless Chromium and screenshot one element.

    Returns PNG bytes of the matched element (the membership card).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        try:
            page = browser.new_page(
                viewport={'width': 800, 'height': 1200},
                device_scale_factor=scale,
            )
            page.set_content(html, wait_until='networkidle')
            # Ensure web fonts are loaded before snapshot
            try:
                page.evaluate('document.fonts && document.fonts.ready')
                page.wait_for_timeout(300)
            except Exception:
                pass
            el = page.query_selector(selector)
            if el is None:
                # Fallback: full-page screenshot
                return page.screenshot(type='png')
            return el.screenshot(type='png')
        finally:
            browser.close()
