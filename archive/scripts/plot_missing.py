"""Render measured pilot missingness and per-Thing timestamp spans."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results/report'
    report = json.loads((out / 'missing_analysis.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    profiles = report['by_profile']
    bars = axes[0].bar([r['profile'] for r in profiles],
                       [r['pct_cells_missing'] for r in profiles], color='#3879b7')
    axes[0].bar_label(bars, labels=[f"{r['cells_missing']}/{r['n_cells']} ({r['pct_cells_missing']:.3f}%)"
                                   for r in profiles], padding=5)
    axes[0].set_ylim(0, 5)
    axes[0].set_ylabel('Missing loss cells (%)')
    axes[0].set_title('All 24 missing cells: warmup at tick 0')
    policy = report['policy_applied']
    bars = axes[1].bar(['Input', 'Warmup dropped', 'Retained', 'Residual missing rows'],
                       [policy['rows_before'], policy['rows_dropped_warmup'],
                        policy['rows_after_warmup_drop'], policy['rows_with_residual_missing']],
                       color=['#3879b7', '#e7943c', '#428f68', '#b55656'])
    axes[1].bar_label(bars, padding=5)
    axes[1].set_ylim(0, 175)
    axes[1].set_ylabel('Snapshots')
    axes[1].tick_params(axis='x', labelsize=8)
    axes[1].set_title('DT4N-M1: one warmup tick per segment')
    fig.suptitle('Lesson 5.2 — pilot v2 (3 segments, 150 snapshots)')
    fig.tight_layout()
    path = out / 'missing_analysis.png'
    fig.savefig(path, dpi=150)
    print(path)


if __name__ == '__main__':
    main()
