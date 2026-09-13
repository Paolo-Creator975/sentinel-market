from pathlib import Path
import unittest

import pandas as pd

from app.config_guard import load_crypto_24h_candidate
from app.crypto_24h import (calculate_opportunity, available_risk,
                           drawdown_risk_multiplier, plan_paper_position)


ROOT=Path(__file__).resolve().parent


def bars(end="2026-09-10T16:00:00Z", breakout=True, last_volume=1000.0):
    count=800
    index=pd.date_range(end=pd.Timestamp(end),periods=count,freq="h")
    base=pd.Series([100.0+i*0.02 for i in range(count)],dtype=float)
    high=base+0.20
    if breakout:
        base.iloc[-1]=high.iloc[-2]+2.0
    volume=pd.Series([1000.0]*count)
    volume.iloc[-1]=last_volume
    return pd.DataFrame({"symbol":"ADAUSDT","open_time":index,
        "close_time":index+pd.Timedelta(hours=1)-pd.Timedelta(milliseconds=1),
        "open":base,"high":high,"low":base-0.20,"close":base,"volume":volume})


class Crypto24HTests(unittest.TestCase):
    def setUp(self):
        self.config=load_crypto_24h_candidate(ROOT)

    def test_scope_is_crypto_only_for_90_days(self):
        self.assertEqual(self.config["configured_asset_classes"],["crypto"])
        self.assertEqual(self.config["demo_duration_days"],90)
        self.assertEqual(len(self.config["universe"]),7)
        self.assertTrue(self.config["immutable_for_demo"])
        self.assertEqual(self.config["sha256"],
                         "42e3cd9fdf9515a7144663f222de296dd8f13b9c6160c202549c8624c8a97fde")

    def test_candidate_can_be_found_at_any_hour(self):
        result=calculate_opportunity(bars(),self.config)
        self.assertNotEqual(pd.Timestamp(result["signal_time"]).hour,23)
        self.assertEqual(result["decision"],"TECHNICAL_CANDIDATE")

    def test_breakout_uses_prior_high_without_lookahead(self):
        result=calculate_opportunity(bars(),self.config)
        self.assertTrue(result["breakout"])
        self.assertTrue(result["new_breakout"])
        self.assertLess(result["prior_high"],result["bar_close"])

    def test_continuing_breakout_is_not_counted_twice(self):
        frame=bars()
        frame.loc[frame.index[-2],"close"]=frame.loc[frame.index[-3],"high"]+1.0
        result=calculate_opportunity(frame,self.config)
        self.assertTrue(result["breakout"])
        self.assertFalse(result["new_breakout"])
        self.assertEqual(result["decision"],"WATCH")

    def test_illiquid_candidate_is_rejected(self):
        result=calculate_opportunity(bars(last_volume=100.0),self.config)
        self.assertEqual(result["decision"],"REJECT")

    def test_news_conflict_waits(self):
        result=calculate_opportunity(bars(),self.config,news_state="CONFLICT")
        self.assertEqual(result["decision"],"WAIT")

    def test_execution_is_hard_disabled(self):
        self.assertFalse(self.config["execution_enabled"])
        self.assertTrue(self.config["paper_positions_enabled"])
        self.assertFalse(self.config["real_trading_enabled"])

    def test_drawdown_ladder_and_aggregate_risk(self):
        self.assertEqual(drawdown_risk_multiplier(1000,1000),1.0)
        self.assertEqual(drawdown_risk_multiplier(900,1000),0.5)
        self.assertEqual(drawdown_risk_multiplier(800,1000),0.25)
        self.assertEqual(drawdown_risk_multiplier(700,1000),0.0)
        self.assertEqual(available_risk(1000,1000,40),60.0)
        self.assertEqual(available_risk(1000,1000,100),0.0)

    def test_higher_score_gets_more_risk_without_leverage(self):
        low=plan_paper_position(100,0.01,63,1000,1000,0,self.config)
        high=plan_paper_position(100,0.01,95,1000,1000,0,self.config)
        self.assertGreater(high["risk_eur"],low["risk_eur"])
        self.assertLessEqual(high["notional_eur"],350)

    def test_position_plan_respects_aggregate_cap_and_drawdown_block(self):
        capped=plan_paper_position(100,0.01,95,1000,1000,99,self.config)
        self.assertLessEqual(capped["risk_eur"],1.0)
        self.assertIsNone(plan_paper_position(100,0.01,95,700,1000,0,self.config))


if __name__=="__main__":
    unittest.main()
