import subprocess,time
while True:
 subprocess.run(['python3','scripts/build_report.py'],stdout=subprocess.DEVNULL)
 time.sleep(30)
