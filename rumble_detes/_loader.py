from .detes_helper import db_helper as db
from .detes_helper import _us_stock_list_cols, _cn_stock_list_cols
from .web_helper import ts_helper as th
from copy import copy

import rumble_cpp as rc


class TechBuilder:
    def __init__(self):
        self.db = db()
        self.th = th()

    def update_ma(self):
        for rows in self.db.iter_stocks_hist(
            select_close=True,
            select_prevma=True,
            nullma_filter=True,
            select_pk=True,
        ):
            print(f"ma data fetched: {len(rows)} rows", flush=True)
            # get moving averages from c++
            averages = rc.ma(copy(rows))  # copy rows since it will be deferenced in cpp
            # reformat the data
            rows = [(*rows[i][:2], *averages[i][:2]) for i in range(len(rows))]
            step = 100000
            for i in range(0, len(rows), step):
                self.db.update_ma(rows[i : min(len(rows), i + step)])

    def update_streaks(self):
        for rows in self.db.iter_stocks_hist(
            select_close=True,
            lag_degree=2,
            select_pk=True,
            nullstreak_filter=True,
            select_prevstreak=True,
        ):
            print(f"streak data fetched: {len(rows)} rows", flush=True)
            # get streak counts from c++
            num_streaks = rc.day_streak(
                copy(rows)
            )  # copy rows since it will be deferenced in cpp
            # reformat the data
            rows = [(*r[:2], num_streaks[i]) for i, r in enumerate(rows)]
            self.db.update_streaks(rows)
            step = 100000
            for i in range(0, len(rows), step):
                self.db.update_streaks(rows[i : min(len(rows), i + step)])
