#!/usr/bin/env python3
"""Drive Splunk Web and verify the Configuration page in a real browser.

NOT part of the pytest suite: it needs a running Splunk with the app installed,
so it is run by hand against a test instance.

    pip install playwright && playwright install chromium
    python3 tests/ui/verify_prompts_ui.py        # edit BASE for your instance

Exists because the Prompts tab uses a UCC CUSTOM CONTROL
(appserver/static/js/build/custom/), and nothing in the pytest suite can tell
whether browser-side code actually loads and renders. Its first run correctly
reported that "Restore to default" restored a differently-whitespaced copy of
the prompt, which no unit test would have caught.

Splunk Web (:8000) comes up a minute or more AFTER splunkd (:8089), so wait for
:8000 specifically after a restart or the first run fails with connection
refused.

Checks what only a browser can: that the custom control loads and renders, that
the boxes carry the shipped prompt, and that Restore to default really puts it
back after an edit. Also records every 4xx/5xx the page makes, so a broken
endpoint cannot hide behind a working-looking button.

Waits on selectors rather than sleeps; the first version of this failed purely on
timing and wrongly reported the control as missing.
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://192.168.0.222:8000"
APP = "cim-plicity"
PW = [l.split("=", 1)[1].strip() for l in open("/opt/aios/.env")
      if l.startswith("SPLUNK_PASSWORD=")][0]

TA = "textarea[data-test='prompt-editor-textarea']"
BTN = "button[data-test='prompt-editor-restore']"
NOTE = "span[data-test='prompt-editor-note']"

failures, console_errors, bad_responses = [], [], []

# Splunk's own noise, confirmed by loading a DIFFERENT UCC app's configuration
# page and seeing the same thing. Excluded by name, with the reason, rather than
# by a vague regex that could hide a real failure of ours.
PLATFORM_NOISE = (
    # Splunk Mobile telemetry, unreachable from this network.
    "splkmobile.com",
    # Splunk Web probes a limits stanza that does not exist on this instance.
    "conf-limits/structured_data_service",
)


def is_ours(url_or_msg):
    return not any(n in url_or_msg for n in PLATFORM_NOISE)


def check(label, ok, detail=""):
    print("  %-54s %s%s" % (label, "PASS" if ok else "FAIL",
                            ("  " + str(detail)) if detail and not ok else ""))
    if not ok:
        failures.append("%s %s" % (label, detail))
    return ok


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1500, "height": 1300})
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("pageerror: %s" % e))
        page.on("response", lambda r: bad_responses.append("%s %s" % (r.status, r.url))
                if r.status >= 400 else None)
        page.on("requestfailed",
                lambda r: bad_responses.append("FAILED %s %s" % (r.failure, r.url)))

        print("=== log in ===")
        page.goto("%s/en-US/account/login" % BASE, wait_until="networkidle", timeout=90000)
        page.fill("input#username", "admin")
        page.fill("input#password", PW)
        # Three submit inputs on this page, so Enter is less ambiguous than a click.
        with page.expect_navigation(wait_until="networkidle", timeout=90000):
            page.press("input#password", "Enter")
        if not check("logged in", "/account/login" not in page.url, page.url):
            page.screenshot(path=os.path.join(HERE, "ui_0_login.png"), full_page=True)
            browser.close()
            return

        print("\n=== open the Configuration page ===")
        # Only errors from OUR page count; the login flow has its own.
        console_errors.clear()
        bad_responses.clear()
        page.goto("%s/en-US/app/%s/configuration" % (BASE, APP),
                  wait_until="networkidle", timeout=90000)
        page.wait_for_selector("text=AI Configuration", timeout=60000)
        check("configuration page rendered", True)
        for tab in ("AI Configuration", "Prompts", "Logging"):
            check("tab present: %s" % tab, page.locator("text=%s" % tab).count() > 0)
        page.screenshot(path=os.path.join(HERE, "ui_1_ai_config.png"), full_page=True)

        print("\n=== AI Configuration: the LLM Backend dropdown ===")
        html = page.content()
        check("no 'No matches' anywhere", "No matches" not in page.inner_text("body"))
        for label in ("Direct (API key)", "Splunk AI Toolkit"):
            check("backend option in the DOM: %s" % label, label in html)
        check("connection field is a dropdown, not free text",
              "AI Toolkit connection" in page.inner_text("body"))

        print("\n=== Prompts tab ===")
        page.click("text=Prompts", timeout=20000)
        # Wait for the CUSTOM CONTROL, not a fixed sleep: it is loaded by a
        # dynamic import so it appears well after the tab switches.
        page.wait_for_selector(TA, timeout=60000)
        page.wait_for_selector(BTN, timeout=60000)
        areas, buttons = page.locator(TA), page.locator(BTN)
        check("custom control rendered two textareas", areas.count() == 2,
              "got %d" % areas.count())
        check("two Restore to default buttons", buttons.count() == 2,
              "got %d" % buttons.count())
        page.screenshot(path=os.path.join(HERE, "ui_2_prompts.png"), full_page=True)

        if areas.count() != 2:
            browser.close()
            return

        # Each control must be bound to its own prompt, or one would edit the other.
        prompts_seen = sorted(areas.nth(i).get_attribute("data-prompt")
                              for i in range(areas.count()))
        check("each control names its own prompt",
              prompts_seen == ["ai_detection", "cim_mapping"], prompts_seen)

        first = areas.nth(0)
        original = first.input_value()
        check("first prompt is pre-filled", len(original) > 200, "%d chars" % len(original))
        check("it is the shipped prompt",
              "You are a Splunk expert" in original, original[:60])

        # The button prefetches on render; if that failed it says so, and the
        # note is the only visible signal a user would get.
        note0 = page.locator(NOTE).nth(0).inner_text()
        check("no 'unavailable' warning from the prefetch",
              "unavailable" not in note0.lower(), repr(note0))

        print("\n=== edit, then restore ===")
        first.fill("REPLACED BY THE UI TEST {sample_data}")
        check("the edit took", first.input_value().startswith("REPLACED"))

        buttons.nth(0).click()
        page.wait_for_function(
            "() => { const t = document.querySelector(\"%s\");"
            " return t && t.value.includes('You are a Splunk expert'); }" % TA,
            timeout=30000)
        restored = first.input_value()
        page.screenshot(path=os.path.join(HERE, "ui_3_restored.png"), full_page=True)
        # Compare whitespace-normalised: the conf collapses the source template's
        # indentation, and what matters is that the prompt is the same one.
        check("Restore put the shipped prompt back",
              " ".join(restored.split()) == " ".join(original.split()),
              "%d chars vs %d" % (len(restored), len(original)))
        check("the button reported success",
              "Restored" in page.locator(NOTE).nth(0).inner_text(),
              repr(page.locator(NOTE).nth(0).inner_text()))

        print("\n=== the other control is independent ===")
        second = areas.nth(1)
        check("second prompt still its own", "CIM expert" in second.input_value(),
              second.input_value()[:60])

        print("\n=== browser errors ===")
        # Chromium echoes every network error to the console as a bare
        # "Failed to load resource: ..." with NO url, so it cannot be attributed
        # and would only double-count what the response/requestfailed listeners
        # already check precisely by url. Real JS errors (thrown exceptions,
        # pageerror) carry their own text and are what matter for the custom
        # control, so those are kept.
        real = [e for e in console_errors
                if is_ours(e)
                and not e.startswith("Failed to load resource")
                and not re.search(r"favicon|\.png|\.ico", e, re.I)]
        bad = [r for r in bad_responses if is_ours(r)
               and not re.search(r"favicon|\.png|\.ico", r, re.I)]
        for r in bad + real:
            print("     %s" % str(r)[:160])
        check("no 4xx/5xx from this app", not bad, "%d" % len(bad))
        check("no console errors from this app", not real,
              "; ".join(real[:2])[:160])
        excluded = [r for r in bad_responses + console_errors if not is_ours(r)]
        if excluded:
            print("     (%d platform-noise entries excluded by name)" % len(excluded))

        browser.close()


if __name__ == "__main__":
    main()
    print("\n" + ("ALL CHECKS PASSED" if not failures
                  else "FAILURES (%d):\n  - %s" % (len(failures), "\n  - ".join(failures))))
    print("screenshots in", HERE)
    sys.exit(1 if failures else 0)
