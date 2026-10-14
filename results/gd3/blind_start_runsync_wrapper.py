"""sudo -v rồi khởi động run_sync làm tiến trình CON của chính tiến trình này (chung thẻ sudo)."""
import subprocess, sys
pw = sys.stdin.readline()
subprocess.run(['sudo', '-S', '-p', '', '-v'], input=pw, text=True, check=True)
fifo = open('/tmp/mn_in', 'rb')
log = open('/tmp/gd35/mininet.txt', 'w')
p = subprocess.Popen(['sudo', '-n', '/usr/bin/python3', '-m', 'mininet.run_sync', '--period', '1.0'],
                     stdin=fifo, stdout=log, stderr=subprocess.STDOUT,
                     cwd='/home/vantai/dt4n-core')
print('run_sync pid', p.pid, flush=True)
sys.exit(p.wait())
