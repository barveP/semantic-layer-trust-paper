"""Exercise local annotation, persistence, export and responsive layout with synthetic answers.

Run python3 audit-site/build_site.py first, then python3 audit-site/qa_site.py.
Requires Playwright and its Chromium browser. QA output stays under local/.
"""
import csv
import functools
import http.server
import json
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main():
    site = ROOT / 'local/slstudy-audit-site/v1'
    output = ROOT / 'local/slstudy-audit-site/qa'
    output.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks, errors = {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
        page.wait_for_function("/Answers save/.test(document.querySelector('#who').textContent)")
        checks['empty_start'] = page.inner_text('#crumb').startswith('0 of 417')
        page.click('.itemchip[data-n="1"]')
        page.keyboard.press('1'); page.keyboard.press('3')
        page.wait_for_timeout(200)
        checks['fault_answers'] = page.get_attribute('#q1yes', 'aria-pressed') == 'true' and page.get_attribute('#q2yes', 'aria-pressed') == 'true'
        page.fill('#noteField', 'Synthetic QA note'); page.wait_for_timeout(800)
        page.reload(); page.wait_for_function("/Answers save/.test(document.querySelector('#who').textContent)")
        checks['persist_after_reload'] = page.inner_text('#crumb').startswith('1 of 417')
        page.click('.itemchip[data-n="1"]')
        checks['note_retained'] = page.input_value('#noteField') == 'Synthetic QA note'
        page.keyboard.press('4')
        checks['answer_edit'] = page.get_attribute('#q2no', 'aria-pressed') == 'true'
        page.click('button:has-text("All items")')
        page.click('.itemchip[data-n="2"]'); page.keyboard.press('2')
        checks['nonfault_na'] = page.locator('#q2yes').count() == 0
        page.click('button:has-text("All items")')
        with page.expect_download() as downloaded:
            page.click('#exportBtn')
        target = output / 'synthetic-ratings.csv'
        downloaded.value.save_as(target)
        with target.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        checks['export_all_items'] = len(rows) == 417
        checks['export_values'] = rows[0]['about_layer'] == 'yes' and rows[0]['identifies_fault'] == 'no' and rows[0]['note'] == 'Synthetic QA note'
        checks['export_sample_hash'] = len({row['sample_csv_sha256'] for row in rows}) == 1 and len(rows[0]['sample_csv_sha256']) == 64
        page.set_viewport_size({'width': 390, 'height': 844})
        checks['mobile_width'] = page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
        page.screenshot(path=str(output / 'mobile.png'), full_page=True)
        checks['no_script_errors'] = not errors
        browser.close()
    server.shutdown()
    (output / 'QA-RESULT.json').write_text(json.dumps({'checks': checks, 'errors': errors}, indent=2) + '\n')
    print(json.dumps(checks))
    if not all(checks.values()):
        raise SystemExit('Browser QA failed')


if __name__ == '__main__':
    main()
