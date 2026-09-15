import json,time,collections
from pathlib import Path
from bridge.bootstrap import entities_from_spec,bootstrap_all,delete_thing
from bridge.ditto_common import DITTO_BASE_URL,DITTO_AUTH,HTTP_TIMEOUT
import requests
spec=json.loads(Path('ditto/topology_spec.json').read_text())
for i in range(4,21):
 spec['hosts'].append({'name':'h%d'%i,'ip':'10.0.0.%d'% (i+2),'role':'client'})
 spec['links'].append(['h%d'%i,'s1'])
path=Path('results/report/topology_scale20.json'); path.write_text(json.dumps(spec,indent=2))
pol=json.loads(Path('ditto/policy.json').read_text()); pol['policyId']='org.dt4n.scale:default-policy'
ents=entities_from_spec(str(path)); t=time.monotonic(); a=bootstrap_all(ents,pol); first=time.monotonic()-t
t=time.monotonic(); b=bootstrap_all(ents,pol); second=time.monotonic()-t
present=[]
for e in ents:
 r=requests.get(DITTO_BASE_URL+'/things/'+e['thing_id'],auth=DITTO_AUTH,timeout=HTTP_TIMEOUT)
 if r.status_code==200: present.append(e['thing_id'])
report={'scope':'bootstrap only; not maximum Mininet capacity','client_hosts':20,'total_hosts':len(spec['hosts']),'switches':len(spec['switches']),'expected_things':len(ents),'readable_things':len(present),'first_s':first,'repeat_s':second,'first':a,'repeat':b}
# Delete only objects created by this run, in its dedicated namespace.
for e in ents: delete_thing(e['thing_id'])
requests.delete(DITTO_BASE_URL+'/policies/'+pol['policyId'],auth=DITTO_AUTH,timeout=HTTP_TIMEOUT)
Path('results/report/bootstrap_scale.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
