import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from measurements.stats import summarize
out=Path('results/report')
while True:
 try:
  progress=json.loads((out/'soak_progress.json').read_text())
  if progress.get('complete') is False: break
 except (OSError,ValueError): pass
 time.sleep(1)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000},record_video_dir=str(out/'demo_video'))
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:5173',wait_until='domcontentloaded');page.wait_for_timeout(5000)
 statejs="""() => {let c=document.querySelector('.diagram-container').__vueParentComponent; return c.props.graph.edges.find(e=>e.id==='h1-s1')?.state} """
 selectjs="""() => {let c=document.querySelector('.diagram-container').__vueParentComponent; let n=c.setupState.networkInstance.__v_raw || c.setupState.networkInstance; n.selectEdges(['h1-s1']); n.emit('selectEdge',{edges:['h1-s1']});} """
 page.evaluate(selectjs);page.wait_for_timeout(500)
 rows=[]
 for i in range(30):
  for button,expected in [('Tắt link','down'),('Bật lại link','up')]:
   locator=page.get_by_role('button',name=button,exact=True);locator.wait_for(state='visible',timeout=25000)
   started=time.monotonic();locator.click()
   try:
    page.wait_for_function(statejs.replace("?.state}","?.state === '"+expected+"'}"),timeout=25000)
    elapsed=time.monotonic()-started
    flags=int(Path('/sys/class/net/s1-eth3/flags').read_text(),16);actual='up' if flags&1 else 'down'
    rows.append({'trial':i+1,'button':button,'expected':expected,'ui_latency_sec':elapsed,'runtime_state':actual,'runtime_matches':actual==expected,'ok':True})
   except Exception as e: rows.append({'trial':i+1,'button':button,'ok':False,'error':str(e)})
   if i==0 and expected=='down': page.screenshot(path=str(out/'dashboard_link_down.png'),full_page=True)
   (out/'dashboard_live_progress.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False));time.sleep(1)
 page.screenshot(path=str(out/'dashboard_live.png'),full_page=True)
 page.reload(wait_until='domcontentloaded');page.wait_for_timeout(3000)
 reload_state=page.evaluate(statejs);text=page.locator('body').inner_text()
 try:
  page.get_by_role('button',name='🕑 Lịch sử').click();page.wait_for_timeout(1000);history=page.locator('body').inner_text();page.screenshot(path=str(out/'dashboard_history.png'),full_page=True)
 except Exception as e:history=str(e)
 result={'samples':rows,'stats':summarize([r['ui_latency_sec'] for r in rows if r['ok']]),'requested_ops':60,'timeouts':sum(not r['ok'] for r in rows),'runtime_all_match':all(r.get('runtime_matches',False) for r in rows),'reload_link_state':reload_state,'reload_text':text,'history_text':history,'page_errors':errors}
 (out/'dashboard_live.json').write_text(json.dumps(result,indent=2,ensure_ascii=False));print(json.dumps(result['stats'],indent=2))
 page.close();browser.close()
