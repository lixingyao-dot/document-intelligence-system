# -*- coding: utf-8 -*-
from core.agents.agent_b import _extract_labeled_records

SAMPLE = """
青岛
GDP总量：16900亿元
常住人口：1020万
人均GDP：165000元
一般公共预算收入：1200亿元

无锡
GDP总量：16200亿元
常住人口：750万
人均GDP：172000元
一般公共预算收入：1180亿元
"""

COLS = [
    "城市名",
    "GDP总量（亿元）",
    "常住人口（万）",
    "人均GDP（元）",
    "一般公共预算收入（亿元）",
]


def test_labeled_city_paragraphs():
    rows = _extract_labeled_records(SAMPLE, COLS)
    assert len(rows) == 2
    qingdao = next(r for r in rows if r["城市名"] == "青岛")
    assert qingdao["GDP总量（亿元）"] == "16900"
    assert qingdao["常住人口（万）"] == "1020"
    assert qingdao["人均GDP（元）"] == "165000"
    assert qingdao["一般公共预算收入（亿元）"] == "1200"
