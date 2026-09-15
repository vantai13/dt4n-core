#!/usr/bin/env python3
import json
import statistics
import hashlib
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root/'results/report'

def dataset(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    links = {}
    for key in rows[0]['things']:
        if not key.startswith('link-'): continue
        samples = [r['things'][key]['features'].get('traffic',{}) for r in rows[1:]]
        def mean(key):
            vals = [x[key] for x in samples if isinstance(x.get(key),(int,float))]
            return statistics.mean(vals) if vals else None
        valid = [x for x in samples if x.get('qdiscValid') is True]
        losses = [x['lossPct'] for x in valid if isinstance(x.get('lossPct'),(int,float))]
        rates = [max(x.get('rxRate',0), x.get('txRate',0))*8/1e6 for x in samples]
        links[key] = {'mean_peak_direction_mbps':statistics.mean(rates),
                      'rate_std_mbps':statistics.pstdev(rates),
                      'mean_rx_mbps':mean('rxRate')*8/1e6,
                      'mean_tx_mbps':mean('txRate')*8/1e6,
                      'mean_interface_loss_pct':mean('interfaceLossPct') if 'interfaceLossPct' in samples[0] else mean('lossPct'),
                      'qdisc_valid_samples':len(valid),
                      'loss_positive_samples':sum(x>0 for x in losses),
                      'loss_max_pct':max(losses) if losses else None,
                      'loss_mean_pct':statistics.mean(losses) if losses else None,
                      'loss_std_pct':statistics.pstdev(losses) if losses else None}
    return {'file':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'snapshots':len(rows),'warmup_excluded':1,'links':links}

summary = {}
for label,path in [('normal_v1','logs/snapshots_normal.jsonl'),('flood_v1','logs/snapshots_flood.jsonl'),
                   ('normal_v2','logs/ml_normal_v2.jsonl'),('flood_v2','logs/ml_flood_v2.jsonl'),
                   ('injection_v2','logs/ml_injection_v2.jsonl')]:
    summary[label] = dataset(root/path)
normal = summary['normal_v2']['links']; flood = summary['flood_v2']['links']
summary['gates'] = {
 'normal_flood_have_60_snapshots':all(summary[x]['snapshots']==60 for x in ['normal_v2','flood_v2']),
 'all_8_links_active_in_normal':len(normal)==8 and all(x['mean_peak_direction_mbps']>.1 for x in normal.values()),
 'all_clients_flood_rate_exceeds_normal_2x':all(flood[k]['mean_peak_direction_mbps']>2*normal[k]['mean_peak_direction_mbps'] for k in normal if k.startswith('link-h')),
 'flood_qdisc_loss_observed':any(x['loss_positive_samples']>0 for x in flood.values()),
 'injection_qdisc_loss_observed':any(x['loss_positive_samples']>0 for x in summary['injection_v2']['links'].values()),
 'all_v2_qdisc_samples_valid_after_warmup':all(x['qdisc_valid_samples']==summary[d]['snapshots']-1 for d in ['normal_v2','flood_v2','injection_v2'] for x in summary[d]['links'].values()),
}
log=(root/'logs/ml_preflight_runtime.log').read_text()
summary['runtime_error_lines']=[x for x in log.splitlines() if re.search(r'\b(ERROR|CRITICAL)\b|Traceback \(most recent call last\)',x)]
summary['measurement_semantics']={'rate':'mean of per-snapshot max(rxRate,txRate), bytes/s converted to Mbps',
 'lossPct':'local bidirectional leaf-qdisc drop delta / (sent packet delta + drop delta); not path loss',
 'v1_loss':'legacy interface counters only; not comparable with qdisc loss',
 'dataset_scope':'pilot for feature validation, not a training/test split or ML performance evidence'}
(out/'ml_dataset_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(json.dumps(summary['gates'],indent=2))
if not all(summary['gates'].values()): raise SystemExit('ML feature validation gate failed; inspect summary')
