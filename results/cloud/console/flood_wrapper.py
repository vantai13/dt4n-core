"""Chạy cloud.experiment nhưng tự 'bấm Enter': gửi lệnh flood vào FIFO của mininet>."""
import builtins
import sys

sys.path.insert(0, '/home/vantai/dt4n-core')
CMD = 'h1 iperf -c 10.0.0.4 -u -b 30M -t 60 &'


def auto_input(prompt=''):
    print(prompt, end='')
    with open('/tmp/mn_in', 'w') as f:
        f.write(CMD + '\n')
    print('[auto] đã gửi vào mininet>: %s' % CMD, flush=True)
    return ''


builtins.input = auto_input
from cloud.experiment import main  # noqa: E402
main(sys.argv[1:])
