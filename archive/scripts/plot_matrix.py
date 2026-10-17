"""Plot the locked design; this figure contains planned timing, not live data."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results/report'
    matrix = json.loads((out / 'experiment_matrix.json').read_text())
    runs = sorted(matrix['runs'], key=lambda r:r['exec_index'])
    fig, ax = plt.subplots(figsize=(13, 9))
    colors = {'N':'#447fb7', 'C':'#3f9a73', 'F':'#b9c9d5'}
    for i, run in enumerate(runs):
        ax.broken_barh([(0,run['duration_sec'])], (i-.35,.7), facecolors=colors[run['group']])
        ax.broken_barh([(0,matrix['constants']['warmup_ticks'])], (i-.35,.7), facecolors='#aaaaaa')
        if run['fault']:
            ax.broken_barh([(run['t_inject'],run['t_revert']-run['t_inject'])], (i-.35,.7),facecolors='#d5773f')
    ax.set_yticks(range(len(runs)), [f"{r['exec_index']:02d}  {r['run_id']}" for r in runs], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0,60)
    ax.set_xticks(range(0,61,10))
    ax.set_xlabel('Planned seconds from recording start (pre-roll: 5 s before t=0)')
    ax.grid(axis='x', alpha=.25)
    ax.set_title('Lesson 5.3 — PLANNED, NOT COLLECTED\n18 runs: train 8 / test 10; fault window [20,40); expected test base rate 27.1%')
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color='#447fb7',label='Train normal'),Patch(color='#3f9a73',label='Test control'),
                       Patch(color='#d5773f',label='Fault intervention'),Patch(color='#aaaaaa',label='Warmup dropped')],
              loc='lower right',fontsize=8)
    fig.tight_layout()
    fig.savefig(out / 'experiment_matrix.png',dpi=150)
    print(out / 'experiment_matrix.png')


if __name__ == '__main__':
    main()
