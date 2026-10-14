#!/bin/bash
# Chạy toàn bộ GĐ1.5 theo đúng thứ tự hướng dẫn. INVALID -> chạy lại CÙNG số rep (tối đa 3 lần).
cd /home/vantai/dt4n-core
export AWS_REGION=ap-southeast-1 PYTHONUNBUFFERED=1
P=~/.venvs/dt4n-cloud/bin/python
O=results/cloud/console; mkdir -p $O
log(){ echo "$(date +%T) $*" | tee -a $O/driver.txt; }
last(){ tail -1 results/cloud/gd1_trials.jsonl | python3 -c "import sys,json;r=json.loads(sys.stdin.read());print(r['scenario'],r.get('rep'),r['outcome'],r.get('reason',''))"; }
trial(){ # scenario rep [extra]
  for a in 1 2 3; do
    log "▶ $1 rep $2 (lần thử $a)"
    if [ "$1" = flood ]; then $P /tmp/gd15/flood_wrapper.py trial flood --rep $2 > $O/${1}_rep$2_try$a.txt 2>&1
    else $P -m cloud.experiment trial $1 --rep $2 $3 > $O/${1}_rep$2_try$a.txt 2>&1; fi
    r=$(last); log "   => $r"
    case "$r" in *INVALID*) ;; *) return ;; esac
  done
}
start_ctl(){ nohup $P -m cloud.controller run > $O/controller_$1.txt 2>&1 & echo $! > /tmp/gd15/ctl.pid; sleep 6; log "controller THẬT bật (pid $(cat /tmp/gd15/ctl.pid))"; }
stop_ctl(){ kill -TERM $(cat /tmp/gd15/ctl.pid) 2>/dev/null; sleep 15; log "controller đã tắt"; }

log "=== GĐ1.5 bắt đầu"
start_ctl AB
for r in 1 2 3 4 5; do trial flood $r; done
for r in 1 2 3 4 5; do trial linkdown $r; done
log "▶ quiet 10 phút"; $P -m cloud.experiment quiet --minutes 10 > $O/quiet.txt 2>&1; log "   => $(last)"
stop_ctl
trial replace 1 --prep
for r in 2 3 4 5; do trial replace $r; done
log "▶ lb: set 2"; $P -m cloud.actuator set 2 --reason "gd1.5 lb" | tee -a $O/driver.txt
$P -m cloud.experiment lb --n 100 > $O/lb.txt 2>&1; log "   => $(last)"
$P -m cloud.experiment report > $O/report.txt 2>&1
log "=== GĐ1.5 xong"
