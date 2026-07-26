"""オフィス候補の組み合わせ列挙。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List

from cest.engine.combo.common import _index_offices


def enumerate_combinations(
    offices: List[Dict[str, Any]],
    num_offices_list: List[int],
    fixed_offices: List[str],
) -> List[List[Dict[str, Any]]]:
    office_by_id = _index_offices(offices)
    fixed = [office_by_id[oid] for oid in fixed_offices if oid in office_by_id]
    fixed_ids = {o["office_id"] for o in fixed}
    remaining = [o for o in offices if o["office_id"] not in fixed_ids]

    combos: List[List[Dict[str, Any]]] = []
    for k in num_offices_list:
        if len(fixed) > k:
            continue
        choose = k - len(fixed)
        if choose == 0:
            combos.append(list(fixed))
        else:
            for subset in itertools.combinations(remaining, choose):
                combos.append(list(fixed) + list(subset))
    return combos
