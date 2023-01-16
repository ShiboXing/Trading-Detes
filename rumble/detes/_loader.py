from .detes_helper import db_helper as db
from .detes_helper import _us_stock_list_cols, _cn_stock_list_cols
from .web_helper import ts_helper as th
from torch.utils.data import Dataset
import rumble_cpp as rc


class StockSet(Dataset):
    def __init__(self):
        self.db = db()

    def __getitem__(self, idx):
        pass


def rsi(avgs):
    avg_pos, avg_neg = avgs
    return 100 - 100 / (1 + avg_pos / abs(avg_neg))


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
            # get moving averages from c++
            averages = rc.ma(list(map(tuple, rows)))

            # reformat the data
            for i in range(len(rows)):
                row = rows[i]
                ma_row = averages[i]
                rows[i] = (row[0], row[1], ma_row[0], ma_row[1])
            self.db.update_ma(rows)

    def update_streaks(self):
        for rows in self.db.iter_stocks_hist(
            select_close=True,
            lag_degree=2,
            select_pk=True,
            nullstreak_filter=True,
            select_prevstreak=True,
        ):
            # get streak counts from c++
            num_streaks = rc.day_streak(rows)
            pass
