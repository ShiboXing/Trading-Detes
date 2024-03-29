from ..detes_helper import db_helper
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from os import path, listdir, getenv
from datetime import datetime

import time
import torch
import decimal
import numpy as np


class Domains(db_helper):
    def __init__(self, initialize_db=False):
        super().__init__(initialize_db=initialize_db)
        sql_dir = path.join(path.dirname(__file__), "sql")
        self.engine = super().connect_to_db(db_name="detes")
        if initialize_db:
            for sql_file in listdir(sql_dir):
                super().run_sqlfile(self.engine, path.join(sql_dir, sql_file))

        device_id = getenv("RANK")
        if device_id and torch.cuda.is_available():
            self.device = torch.device(f"cuda:{device_id}")
        else:
            self.device = torch.device("cpu")

    def streaks(self, num: int, min_date="2000-01-01"):
        with Session(self.engine) as sess:
            samples = sess.execute(
                text(
                    """
                    select code, bar_date from us_daily_bars
                    where streak = :streak and bar_date >= :min_date
                    order by code asc, bar_date asc
                    """
                ),
                {"streak": num, "min_date": min_date},
            ).fetchall()

        return samples

    def get_index_rets(self, start_date, end_date):
        """Returns the log of mean returns of NASDAQ, DOW JONES, S&P 500"""
        rets = None
        with Session(self.engine) as sess:
            rets = sess.execute(
                text(
                    """
                    select avgret, avgvol from get_agg_index_rets(:start, :end)
                    order by bar_date
                """
                ),
                {
                    "start": start_date,
                    "end": end_date,
                },
            ).fetchall()

        return np.array(rets).transpose((1, 0))

    def update_agg_dates(self, is_industry=True):
        """Insert the missing trading dates to aggregate signal tables"""
        agg = "industry" if is_industry else "sector"
        with Session(self.engine) as sess:
            sess.execute(
                text(
                    f"""
                    insert into us_{agg}_signals ({agg}, bar_date)
                    select distinct {agg}, trade_date
                    from us_stock_list, us_cal
                    where is_open = 1
                    except
                    select distinct {agg}, bar_date
                    from us_{agg}_signals
                    """
                )
            )
            sess.commit()
            print(f"finished adding dates to us_{agg}_signals")

    def process_agg_signals(self, is_industry=True):
        "initialize all the null scope value with empty string"
        agg = "industry" if is_industry else "sector"
        with Session(
            self.engine.execution_options(isolation_level="REPEATABLE READ")
        ) as sess:
            sess.execute(
                text(
                    f"""
                update us_stock_list
                set {agg} = ''
                where {agg} is null
                """
                )
            )
            sess.commit()

    def iter_sector_hist(self, filter_vol=True):
        """Fetch daily hist data of sector"""
        if filter_vol:
            filter_str = "where vol_ret is null"
        with Session(self.engine) as sess:
            res = sess.execute(
                text(
                    f"""
                    select * from us_industry_signals
                    {filter_str}
                    """
                )
            )
        pass

    def fetch_agg_rets(self, bar_date: datetime or str, scope_val: str, scope: str):
        with Session(self.engine) as sess:
            res = sess.execute(
                text(
                    # set session properties to avoid division by zero error
                    f"""
                    SET ARITHABORT OFF
                    SET ANSI_WARNINGS OFF
                    select * from get_{scope}_rets(:filter_val, :bar_date)
                    """
                    # (for debugging) order by 1, 2, 3
                ),
                {"filter_val": scope_val, "bar_date": bar_date},
            )
            return res.fetchall()

    def write_agg_rets(self, bar_date: datetime or str, scope: str, scope_val: str):
        """Calculate and fill the daily aggregate signals"""
        start_time = time.time()
        rets = self.fetch_agg_rets(bar_date, scope_val, scope)
        sql1_time = time.time() - start_time
        start_time = time.time()
        rets = torch.tensor(
            np.array(rets, dtype=np.float32), dtype=torch.float32, device=self.device
        )
        rets = rets.nan_to_num(nan=1.0, neginf=1.0, posinf=1.0)
        # not data for the (bar_date, scope_val)
        if len(rets) == 0:
            close_cv, vol_cv, vol_ret, close_ret = (
                torch.tensor(0, dtype=torch.float32),
                torch.tensor(0, dtype=torch.float32),
                torch.tensor(0, dtype=torch.float32),
                torch.tensor(0, dtype=torch.float32),
            )
        else:
            rets[:, 2][
                rets[:, 2] == 0
            ] = 1  # prevent inf log values in vol returns (sometimes vol is 0)
            rets[:, 1:] = torch.log(rets[:, 1:])  # element-wise log on the ret columns

            all_cap = torch.sum(rets[:, 0])
            if all_cap == 0:  # no trade then full weight ratio
                rets[:, 0] = 1
            else:  # get weight ratio, vol
                rets[:, 0] /= all_cap

            rets[:, 1] *= rets[:, 0]  # get weighted close returns
            rets[:, 2] *= rets[:, 0]  # get weighted vol returns
            close_ret = torch.sum(rets[:, 1])  # get weighted close return
            vol_ret = torch.sum(rets[:, 2])  # get weighted volume return
            close_cv = (
                (torch.std(rets[:, 1]).nan_to_num(nan=0.0) / close_ret)
                if close_ret != 0
                else torch.tensor(0, dtype=torch.float32)
            )  # get weighted close coefficient of variation
            vol_cv = (
                (torch.std(rets[:, 2]).nan_to_num(nan=0.0) / vol_ret)
                if vol_ret != 0
                else torch.tensor(0, dtype=torch.float32)
            )  # get weighted vol return coefficient of variation
        comp_time = time.time() - start_time
        start_time = time.time()
        with Session(
            self.engine.execution_options(isolation_level="REPEATABLE READ")
        ) as sess:
            dec_qunat = decimal.Decimal(".0000000001")
            sess.execute(
                text(
                    f"""
                    update us_{scope}_signals
                    set vol_ret = :vol_ret, 
                        close_ret = :close_ret,
                        vol_cv = :vol_cv,
                        close_cv = :close_cv
                    where bar_date = :bar_date and
                        {scope} = :scope_val
                    """
                ),
                {
                    "vol_ret": decimal.Decimal(vol_ret.item()).quantize(dec_qunat),
                    "close_ret": decimal.Decimal(close_ret.item()).quantize(dec_qunat),
                    "vol_cv": decimal.Decimal(vol_cv.item()).quantize(dec_qunat),
                    "close_cv": decimal.Decimal(close_cv.item()).quantize(dec_qunat),
                    "scope_val": scope_val,
                    "bar_date": bar_date,
                },
            )
            sess.commit()
            sql2_time = time.time() - start_time
            print(
                f"[{datetime.now()}] updated us_{scope}_signals for {scope_val}, {bar_date}, device: {self.device}, comp_time: {comp_time}, sql_select_io_time:{sql1_time}, sql_update_io_time: {sql2_time}",
                flush=True,
            )

    def update_agg_signals(self, is_industry=True):
        scope = "industry" if is_industry else "sector"
        # single row fetch (computation bound function)
        rows = next(self.__iter_unfilled_agg_signals(scope))
        if len(rows) == 0:
            return False
        else:
            key = rows[0]
            self.write_agg_rets(key[1], scope, key[0])
            return True

    @db_helper.iter_batch
    def __iter_unfilled_agg_signals(self, scope):
        """Fetch unfilled agg signals rows and update"""

        return (
            text(
                f"""
                select top 1 {scope}, bar_date from us_{scope}_signals
                where (vol_ret is null or
                    close_ret is null or
                    vol_cv is null or
                    close_cv is null)
                order by newid()
                """
            ),
            self.engine,
        )
