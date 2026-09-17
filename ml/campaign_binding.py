#!/usr/bin/env python3
"""Điểm tích hợp duy nhất giữa runner/launcher và một chiến dịch cụ thể.

Các hàm ``C.xxx`` được tra lúc chạy để monkeypatch trong test vẫn có hiệu lực.
Module chỉ dùng thư viện chuẩn vì runner chạy bằng Python hệ thống dưới sudo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from ml import campaign as C


@dataclass(frozen=True)
class CampaignBinding:
    name: str
    load_contract: Callable[[], dict]
    contract_hash: Callable[[dict], str]
    run_paths: Callable[[str], dict]
    verify: Callable
    manifest_path: object
    build_manifest: Callable
    startup_log: str
    namespace_default: str
    supports_interventions: bool


def _phase5() -> CampaignBinding:
    return CampaignBinding(
        name='phase5',
        load_contract=lambda: C.load_contract(),
        contract_hash=lambda doc: C.contract_hash(doc),
        run_paths=lambda rid: C.run_paths(rid),
        verify=lambda *args: C.verify_run(*args),
        manifest_path=C.MANIFEST_PATH,
        build_manifest=lambda *args: C.build_manifest(*args),
        startup_log='logs/ml_dataset_startup.log',
        namespace_default='org.dt4n.ml',
        supports_interventions=False,
    )


def _phase6r() -> CampaignBinding:
    from ml import rcampaign as R
    from ml import rcampaign_runtime as RT
    return CampaignBinding(
        name='phase6r',
        load_contract=lambda: R.load_contract(),
        contract_hash=lambda doc: R.design_hash(doc),
        run_paths=lambda rid: R.run_paths(rid),
        verify=lambda *args: R.verify_rrun(*args),
        manifest_path=C.ROOT / 'results/report/phase6r_rcampaign_manifest.json',
        build_manifest=lambda *args: RT.build_manifest(*args),
        startup_log='logs/rcampaign_startup.log',
        namespace_default='org.dt4n.ml',
        supports_interventions=True,
    )


BINDINGS = {'phase5': _phase5, 'phase6r': _phase6r}


def get(name: str = 'phase5') -> CampaignBinding:
    if name not in BINDINGS:
        raise SystemExit('campaign khong biet: %r' % name)
    return BINDINGS[name]()


def integrity_ok(binding: CampaignBinding, contract: dict,
                 integrity_env: str) -> bool:
    """Runner chỉ tin integrity do launcher tính độc lập và truyền qua env."""
    integ = json.loads(integrity_env or '{}')
    sha = contract['design_content_sha256']
    if binding.name == 'phase5':
        return (integ.get('match') is True and
                integ.get('stored') == integ.get('content') ==
                integ.get('recomputed') == sha == binding.contract_hash(contract))
    return (integ.get('match') is True and
            integ.get('stored') == integ.get('recomputed') == sha ==
            binding.contract_hash(contract))
