import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock


TEMP_OUTPUT_DIR = tempfile.mkdtemp(prefix="asx-report-tests-")
os.environ["OUTPUT_DIR"] = TEMP_OUTPUT_DIR

import asx_weekly_reporter as reporter  # noqa: E402


def make_snapshot():
    return {
        "asx200": {
            "price": 8123.4,
            "change_pct": 0.75,
            "volume": 1_250_000,
        },
        "history": [],
        "key_stocks": [
            {"code": "QAN", "name": "Qantas Airways", "price": 8.55, "change_pct": -4.0, "volume": 900_000},
            {"code": "BHP", "name": "BHP Group", "price": 48.1, "change_pct": 3.0, "volume": 850_000},
            {"code": "CBA", "name": "Commonwealth Bank", "price": 155.3, "change_pct": 1.0, "volume": 2_400_000},
        ],
        "news_items": [
            "Bank shares react as rate outlook shifts",
            "CBA and other banks track mortgage repricing expectations",
        ],
        "reason_items": [
            "银行股跟随利率预期重新定价",
            "航空与资源股出现明显分化",
        ],
        "weekly_return": -2.2,
        "monthly_return": 3.6,
        "volatility": 1.6,
        "current_volume": 1_250_000,
        "recent_avg_volume": 1_200_000,
        "volume_change_pct": 9.5,
        "generated_at": datetime(2026, 7, 25, 8, 0, 0),
    }


class DeterministicReportTests(unittest.TestCase):
    def test_market_overview_uses_rule_thresholds(self):
        overview = reporter._generate_market_overview(make_snapshot())
        self.assertIn("过去5个交易日 -2.20%", overview)
        self.assertIn("过去1个月 +3.60%", overview)
        self.assertIn("高波动轮动", overview)
        self.assertIn("波动率约 1.60%", overview)

    def test_stock_analysis_is_ranked_deterministically(self):
        analysis = reporter._generate_stock_analysis(make_snapshot())
        self.assertTrue(analysis.startswith("**QAN (Qantas Airways)**"))
        self.assertIn("**CBA (Commonwealth Bank)**", analysis)
        self.assertIn("相关主题在抓取新闻中出现 2 次", analysis)

    def test_calendar_and_risk_alert_are_rule_based(self):
        snapshot = make_snapshot()
        calendar = reporter._generate_investment_calendar(snapshot)
        risk_alert = reporter._generate_risk_alert(snapshot)
        self.assertIn("**8月1日** - 财报与经营更新窗口", calendar)
        self.assertIn("**8月4日** - RBA利率决议", calendar)
        self.assertIn("波动率抬升风险", risk_alert)
        self.assertIn("事件前重定价风险", risk_alert)

    def test_generate_market_research_does_not_require_llm_keys(self):
        snapshot = make_snapshot()
        with mock.patch.object(reporter, "_build_market_snapshot", return_value=snapshot):
            research = reporter.generate_market_research()
        self.assertEqual(
            set(research.keys()),
            {"market_overview", "stock_analysis", "investment_calendar", "risk_alert"},
        )
        self.assertIn("ASX 200最新报", research["market_overview"])


if __name__ == "__main__":
    unittest.main()
