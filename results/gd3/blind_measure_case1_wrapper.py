"""Chạy `whatif.blind measure case1`; thay việc bấm Enter bằng ghi lệnh 2 vào FIFO của mininet>."""
import builtins, sys
sys.path.insert(0, '/home/vantai/dt4n-core')
from whatif import blind as B
CMD2 = B.CASES['case1']['operator'][1]
def auto_input(prompt=''):
    print(prompt, end='')
    with open('/tmp/mn_in', 'w') as f:
        f.write(CMD2 + '\n')
    print('[auto] đã gửi vào mininet>: %s' % CMD2, flush=True)
    return ''
builtins.input = auto_input
sys.exit(B.main(['measure', 'case1']))
