"""Điều khiển trang what-if thật bằng Chromium headless, đúng như người dùng bấm."""
import json, sys
from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1], sys.argv[2]
report = {}

def read_page(pg):
    topos = {}
    for t in pg.query_selector_all('.topo'):
        title = t.query_selector('h3').inner_text()
        topos[title] = [x.text_content() for x in t.query_selector_all('svg > text')]
    rows = [[c.inner_text() for c in r.query_selector_all('th,td')] for r in pg.query_selector_all('table tr')]
    warns = [li.inner_text() for li in pg.query_selector_all('.warn li')]
    err = [e.inner_text() for e in pg.query_selector_all('.error')]
    return {'labels': topos, 'table': rows, 'warnings': warns, 'errors': err}

def ask(pg, shot):
    pg.click('#askBtn')
    pg.wait_for_function("!document.querySelector('#out').innerText.includes('Đang dự đoán')")
    pg.wait_for_timeout(300)
    pg.screenshot(path=shot, full_page=True)
    return read_page(pg)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1400, 'height': 900})
    pg.goto(URL)
    pg.select_option('#source', 'snapshot')
    pg.wait_for_function("document.querySelector('#run').options.length === 10")
    report['run_selected'] = pg.input_value('#run')
    report['tick'] = pg.input_value('#tick')
    pg.check('#restore')
    # câu 1: bóp h1 xuống 7
    pg.select_option('#newOp', 'setBandwidth'); pg.click('#addBtn')
    report['q1_setBandwidth'] = ask(pg, OUT + '/browser_q1_setbw_h1_7.png')
    # câu 2: bỏ hành động trên, tắt s1-s2
    pg.click('.action button.x')
    pg.select_option('#newOp', 'disableLink'); pg.click('#addBtn')
    report['q2_disable_s1s2'] = ask(pg, OUT + '/browser_q2_disable_s1s2.png')
    # câu 3: nguồn twin khi không có sync agent -> phải từ chối (fail-closed)
    pg.click('.action button.x')
    pg.select_option('#source', 'twin')
    report['q3_twin_no_sync'] = ask(pg, OUT + '/browser_q3_twin_failclosed.png')
    b.close()
print(json.dumps(report, ensure_ascii=False, indent=1))
