#!/usr/bin/env python3
"""Drive the app's main (Data Input) page and prove its REST calls work at runtime.

NOT part of the pytest suite: needs a running Splunk with the app installed.

    pip install playwright && playwright install chromium
    python3 tests/ui/verify_data_input_ui.py        # edit BASE for your instance

Written for the @splunk/splunk-utils 3 -> 4 upgrade. The front end builds every
request with that package (createRESTURL for the URL, getDefaultFetchInit for
the CSRF form key and credentials), and the jest suite mocks it, so neither a
green build nor green unit tests say anything about whether a real POST from
the page still reaches splunkd. This does: it pastes a sample, presses Auto
Detect Fields, and checks the resulting ai_detection POST went to the right
URL, carried the form key, came back 200 with real fields, and that the page
accepted the result. ("Auto Detect Fields" is the local regex detector and makes
no request at all; the AI call is Ask AI -> Detect Fields with AI.)
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("UI_OUT", HERE)
BASE = os.environ.get("SPLUNK_WEB", "https://192.168.0.222:8000")
APP = "cim-plicity"
PW = os.environ.get("SPLUNK_PASSWORD") or [
    l.split("=", 1)[1].strip() for l in open("/opt/aios/.env")
    if l.startswith("SPLUNK_PASSWORD=")][0]

SAMPLE = ("2026-09-14T08:12:44.113Z site=MCR-NORTH door=D-114 badge=BK-88412 "
          "holder=j.okafor email=j.okafor@example.com decision=DENY")

failures = []
calls = []          # every request the page makes to our endpoints
page_errors = []


def check(label, ok, detail=""):
    print("  %-56s %s%s" % (label, "PASS" if ok else "FAIL",
                            ("  " + str(detail)) if detail and not ok else ""))
    if not ok:
        failures.append("%s %s" % (label, detail))
    return ok


def is_ours(url):
    # REST calls only. A looser pattern also matched static assets under
    # /static/app/cim-plicity/, and reading a PNG body as text crashed the logger.
    return "/splunkd/__raw/" in url and bool(re.search(
        r"/(pii_detection|ai_detection|cim_mapping|cim-plicity/[a-z_]+)", url))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1500, "height": 1300})
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        def on_response(r):
            if is_ours(r.url):
                req = r.request
                calls.append({
                    "method": req.method,
                    "url": r.url,
                    "status": r.status,
                    "form_key": bool(req.headers.get("x-splunk-form-key")),
                    "body": "",
                })
        page.on("response", on_response)

        print("=== log in ===")
        page.goto("%s/en-US/account/login" % BASE, wait_until="networkidle", timeout=90000)
        page.fill("input#username", "admin")
        page.fill("input#password", PW)
        with page.expect_navigation(wait_until="networkidle", timeout=90000):
            page.press("input#password", "Enter")
        if not check("logged in", "/account/login" not in page.url, page.url):
            return browser.close()

        print("\n=== open the main page ===")
        page.goto("%s/en-US/app/%s/main" % (BASE, APP),
                  wait_until="networkidle", timeout=120000)
        page.wait_for_selector("text=Paste Data", timeout=90000)
        check("main page rendered (bundle loaded)", True)
        check("no JavaScript errors on load", not page_errors, "; ".join(page_errors)[:200])

        print("\n=== paste a sample, then Detect Fields with AI ===")
        page.click("text=Paste Data")
        # Splunk UI's TextArea renders a hidden, aria-hidden "shadow" textarea
        # (for auto-sizing) before the real one, so .first is the wrong element.
        area = page.locator("textarea:not([aria-hidden='true'])").first
        area.wait_for(state="visible", timeout=30000)
        area.fill(SAMPLE)
        page.click("button:has-text('Use Pasted Text')")
        page.wait_for_selector("button:has-text('Auto Detect Fields')", timeout=60000)
        check("advanced to Field Extraction", True)
        # "Auto Detect Fields" is the LOCAL regex detector and makes no request;
        # the AI call lives on the Ask AI tab.
        page.click("text=Ask AI")
        page.wait_for_selector("button:has-text('Detect Fields with AI')", timeout=30000)
        with page.expect_response(lambda r: "ai_detection" in r.url
                                  and r.request.method == "POST",
                                  timeout=240000) as resp_info:
            page.click("button:has-text('Detect Fields with AI')")
        resp = resp_info.value
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(OUT, "ui_data_input_detected.png"),
                        full_page=True)

        print("\n=== the ai_detection POST, made through splunk-utils ===")
        req = resp.request
        check("POST reached splunkd with 200", resp.status == 200, resp.status)
        check("URL built by createRESTURL is the app-scoped one",
              re.search(r"/splunkd/__raw/servicesNS/-/%s/ai_detection" % APP, resp.url),
              resp.url)
        check("CSRF form key attached by getDefaultFetchInit",
              bool(req.headers.get("x-splunk-form-key")))
        try:
            body = resp.json()
        except Exception:
            body = {}
        fields = [f.get("name") for f in (body.get("fields") or [])]
        check("a real result came back (fields extracted)", len(fields) >= 3, fields)
        # AI results arrive as SUGGESTIONS: they only become fields once accepted,
        # so Continue is correctly disabled until then. Do what a user does.
        page.wait_for_selector("button:has-text('Accept Combined Regex')", timeout=60000)
        check("suggestions rendered on the page", True)
        page.click("button:has-text('Accept Combined Regex')")
        page.wait_for_timeout(1500)
        check("accepted fields enable Continue to Mapping",
              page.locator("button:has-text('Continue to Mapping')").is_enabled())
        page.screenshot(path=os.path.join(OUT, "ui_data_input_accepted.png"),
                        full_page=True)

        print("\n=== everything the page sent to our endpoints ===")
        for c in calls:
            print("     %-4s %s %s form_key=%s" % (
                c["method"], c["status"], c["url"].split("?")[0][-70:], c["form_key"]))
        bad = [c for c in calls if c["status"] >= 400]
        check("no failed calls to our endpoints", not bad,
              [(c["status"], c["url"][-60:]) for c in bad])
        check("no JavaScript errors after the call", not page_errors,
              "; ".join(page_errors)[:200])
        browser.close()


if __name__ == "__main__":
    main()
    print("\n" + ("ALL CHECKS PASSED" if not failures
                  else "FAILURES (%d):\n  - %s" % (len(failures), "\n  - ".join(failures))))
    sys.exit(1 if failures else 0)
