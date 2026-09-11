from pathlib import Path
import unittest

import pandas as pd

from app.config_guard import load_and_verify, load_and_verify_donchian
from app.donchian_shadow import calculate_snapshot, position_weight


ROOT=Path(__file__).resolve().parent


def bars(last_close=200.0):
    count=800
    end=pd.Timestamp("2026-09-10T23:00:00Z")
    index=pd.date_range(end=end,periods=count,freq="h")
    base=pd.Series([100.0+i*0.05 for i in range(count)],dtype=float)
    base.iloc[-1]=last_close
    return pd.DataFrame({
        "symbol":"ADAUSDT", "open_time":index,
        "close_time":index+pd.Timedelta(hours=1)-pd.Timedelta(milliseconds=1),
        "open":base, "high":base+0.5, "low":base-0.5, "close":base,
        "volume":1000.0,
    })


class DonchianShadowTests(unittest.TestCase):
    def test_frozen_configs_verify(self):
        self.assertEqual(load_and_verify(ROOT)["strategy_id"],"PD_LONG_REBOUND_24H_V1")
        self.assertEqual(load_and_verify_donchian(ROOT)["sha256"],
                         "866ae4aef86fa42abe6f02b57db2c2c563189a8de2c6c0c732c1a75716fbe855")

    def test_daily_breakout_uses_prior_high(self):
        snapshot=calculate_snapshot(bars(),load_and_verify_donchian(ROOT))
        self.assertTrue(snapshot["daily_decision"])
        self.assertTrue(snapshot["breakout"])
        self.assertTrue(snapshot["trend_ok"])
        self.assertTrue(snapshot["entry_signal"])
        self.assertLess(snapshot["high_336"],snapshot["bar_close"])

    def test_non_daily_hour_never_enters(self):
        frame=bars()
        frame["open_time"]=frame.open_time-pd.Timedelta(hours=1)
        frame["close_time"]=frame.close_time-pd.Timedelta(hours=1)
        snapshot=calculate_snapshot(frame,load_and_verify_donchian(ROOT))
        self.assertTrue(snapshot["breakout"])
        self.assertFalse(snapshot["daily_decision"])
        self.assertFalse(snapshot["entry_signal"])

    def test_insufficient_warmup_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"warm-up"):
            calculate_snapshot(bars().tail(720),load_and_verify_donchian(ROOT))

    def test_position_weight_is_capped(self):
        config=load_and_verify_donchian(ROOT)
        self.assertEqual(position_weight(0.25,config),0.20)
        self.assertEqual(position_weight(1.0,config),0.10)


if __name__=="__main__":
    unittest.main()
