import json,time,subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('results/report')
started_at=time.time()
while True:
 try:
  target=out/'soak_30min.json'
  if target.stat().st_mtime >= started_at and json.loads(target.read_text()).get('ok') is True: break
 except (OSError,ValueError): pass
 time.sleep(1)
while any(line.strip() == '/usr/bin/python3 scripts/run_acceptance.py' for line in subprocess.check_output(['ps','-eo','args'],text=True).splitlines()):time.sleep(1)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']); page=browser.new_page(viewport={'width':1440,'height':1000})
 page.goto('http://127.0.0.1:5173',wait_until='domcontentloaded');page.wait_for_timeout(3000)
 c=page.evaluate("() => {let g=document.querySelector('.diagram-container').__vueParentComponent.props.graph; return {nodes:g.nodes.length,links:g.edges.length}}")
 page.screenshot(path=str(out/'dashboard_last_known.png'),full_page=True)
 (out/'dashboard_last_known.json').write_text(json.dumps({'network_runner_stopped':True,'graph':c,'text':page.locator('body').inner_text()},indent=2,ensure_ascii=False))
 page.goto('http://127.0.0.1:8765/report.html',wait_until='domcontentloaded');page.screenshot(path=str(out/'results_screen.png'),full_page=True)
 browser.close();print('Verified last-known state:',c)
