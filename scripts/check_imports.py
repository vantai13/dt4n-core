import importlib,json,pathlib
mods=['bridge.bootstrap', 'bridge.collector', 'bridge.sync_agent', 'bridge.command_agent', 'bridge.ditto_reader', 'bridge.verify', 'bridge.health', 'bridge.adapter', 'bridge.pusher', 'bridge.differ', 'bridge.diagnose', 'measurements.measure_latency', 'measurements.measure_command_latency', 'measurements.measure_command_flow', 'measurements.trace_latency', 'rl.scenarios', 'rl.injection', 'mininet.topology_meta', 'mininet.gen_routes', 'mininet.aoi_norm', 'mininet.env_runner', 'twin.link_direction']
results=[]
for m in mods:
 try:
  obj=importlib.import_module(m); results.append({"module":m,"ok":True,"path":obj.__file__}); print("OK",m,obj.__file__)
 except Exception as e:
  results.append({"module":m,"ok":False,"error":str(e)}); print("FAIL",m,e)
pathlib.Path("results/report/imports.json").write_text(json.dumps(results,indent=2))
print("Failures:",sum(not r["ok"] for r in results),"/",len(results))
raise SystemExit(any(not r["ok"] for r in results))
