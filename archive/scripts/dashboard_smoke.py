import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('results/report')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:5173',wait_until='domcontentloaded'); page.wait_for_timeout(5000)
 page.screenshot(path=str(out/'dashboard_initial.png'),full_page=True)
 first=page.locator('body').inner_text()
 page.reload(wait_until='domcontentloaded'); page.wait_for_timeout(3000)
 page.screenshot(path=str(out/'dashboard_reload.png'),full_page=True)
 second=page.locator('body').inner_text()
 print(first)
 (out/'dashboard_smoke.json').write_text(json.dumps({'url':'http://localhost:5173','initial_text':first,'reload_text':second,'page_errors':errors,'canvas_count':page.locator('canvas').count()},indent=2,ensure_ascii=False))
 browser.close()
