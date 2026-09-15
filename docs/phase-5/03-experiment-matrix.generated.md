# Ma trận thí nghiệm Phase 5 (tự sinh — đừng sửa tay)

- git: `5518cca1492ef84e6b0418433ebcde01aa544797` dirty=`True`
- 18 run, base_rate test dự kiến **27.1%**
- accuracy của mô hình ngu "luôn nói bình thường": **72.9%**

| # | run_id | split | profile | tải (Mbps/client) | fault | target | t_inject | tick bất thường | link dự kiến đổi |
|--:|---|---|---|---|---|---|--:|--:|---|
| 0 | `F-shift-s1-s2-s3007-r1` | test | normal | 2 | shift | `s1-s2` | 20s | 20 | `h1-s1`, `h3-s1`, `s1-s2`, `s2-s3`, `s2-srv1`, `s3-srv2` |
| 1 | `F-degrade-s1-s2-s3003-r1` | test | normal | 2 | degrade | `s1-s2` | 20s | 20 | `h1-s1`, `h3-s1`, `s1-s2`, `s2-srv1` |
| 2 | `F-degrade-s2-s3-s3004-r1` | test | normal | 2 | degrade | `s2-s3` | 20s | 20 | `s2-s3`, `s2-srv1`, `s3-srv2` |
| 3 | `N-vary-s1007-r1` | train | normal_varying | biến thiên | — | — | — | 0 | — |
| 4 | `N-load4M-s1005-r1` | train | normal | 4 | — | — | — | 0 | — |
| 5 | `C-vary-s2002-r1` | test | normal_varying | biến thiên | — | — | — | 0 | — |
| 6 | `F-admin_down-s1-s2-s3001-r1` | test | normal | 2 | admin_down | `s1-s2` | 20s | 20 | `h1-s1`, `h3-s1`, `s1-s2`, `s2-srv1` |
| 7 | `F-flood-h2_to_srv2-s3006-r1` | test | normal | 2 | flood | `h2->srv2` | 20s | 20 | `h2-s1`, `s1-s3`, `s3-srv2` |
| 8 | `F-flood-h1_to_srv1-s3005-r1` | test | normal | 2 | flood | `h1->srv1` | 20s | 20 | `h1-s1`, `s1-s2`, `s2-srv1` |
| 9 | `F-shift-s1-s3-s3008-r1` | test | normal | 2 | shift | `s1-s3` | 20s | 20 | `h2-s1`, `s1-s3`, `s2-s3`, `s2-srv1`, `s3-srv2` |
| 10 | `N-load1M-s1001-r1` | train | normal | 1 | — | — | — | 0 | — |
| 11 | `N-vary-s1008-r2` | train | normal_varying | biến thiên | — | — | — | 0 | — |
| 12 | `F-admin_down-s1-s3-s3002-r1` | test | normal | 2 | admin_down | `s1-s3` | 20s | 20 | `h2-s1`, `s1-s3`, `s3-srv2` |
| 13 | `N-load4M-s1006-r2` | train | normal | 4 | — | — | — | 0 | — |
| 14 | `N-load1M-s1002-r2` | train | normal | 1 | — | — | — | 0 | — |
| 15 | `N-load2M-s1004-r2` | train | normal | 2 | — | — | — | 0 | — |
| 16 | `N-load2M-s1003-r1` | train | normal | 2 | — | — | — | 0 | — |
| 17 | `C-load2M-s2001-r1` | test | normal | 2 | — | — | — | 0 | — |
