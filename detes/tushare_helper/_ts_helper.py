# -*- coding: UTF-8 -*-

import tushare as _ts
import pandas as pd
import socket
from datetime import date, timedelta, datetime

from . import _TOKEN, _hs300_url, _zz500_url
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ConnectionError



class ts_helper:
    def __init__(self):
        global _ts
        global _pro_ts
        _ts.set_token(_TOKEN)
        _pro_ts = _ts.pro_api()

    def get_all_quotes(self):
        print("downloading all stock quotes")
        quotes = _ts.get_today_all()[["code", "name", "open", "turnoverratio", "per"]]
        stock_info = _pro_ts.query("stock_basic")[
            ["ts_code", "symbol", "industry", "market"]
        ]  # get all listed stocks' info
        quotes = quotes.set_index("code").join(
            stock_info.set_index("symbol"), how="inner"
        )

        return quotes

    def get_stock_list(self):
        code_col_name = "成分券代码Constituent Code"
        ex_col_name = "交易所英文名称Exchange(Eng)"
        hs = pd.read_excel(_hs300_url)
        zz = pd.read_excel(_zz500_url)
        stock_list = pd.concat(
            (hs[[code_col_name, ex_col_name]], zz[[code_col_name, ex_col_name]]), axis=0
        )
        stock_list = stock_list.astype({code_col_name: "str"})

        for i in range(len(stock_list)):
            code_len = len(stock_list.iloc[i, 0])
            # add back the missing leading 0s
            if code_len < 6:
                stock_list.iloc[i, 0] = "0" * (6 - code_len) + stock_list.iloc[i, 0]

            # add exchange code into stock code
            stock_ex = stock_list.iloc[i, 1].lower()
            if "shenzhen" in stock_ex:
                stock_list.iloc[i, 0] += ".SZ"
            if "shanghai" in stock_ex:
                stock_list.iloc[i, 0] += ".SH"
        stock_list = stock_list[[code_col_name]]

        print("gotten stock list: ", stock_list.values.shape)
        return stock_list

    def get_stock_hist(self, ts_codes: list, N):
        """
        get the daily bars of a stock starting from today to N days back
        TODO: use multithreading in c++
        """
        print("downloading stock hist...")
        df = pd.DataFrame()
        end_date = date.today()
        start_date = end_date - timedelta(days=N)
        window = 5000 // N  # tushare allows 5000 lines of data for every requests

        for i in range(0, len(ts_codes), window):
            end = min(i + window, len(ts_codes))
            part_codes = ",".join(ts_codes[i:end])

            end_date_str = end_date.strftime("%Y%m%d")
            start_date_str = start_date.strftime("%Y%m%d")

            while True:  # TODO: revise timeout handling
                try:
                    tmp = _pro_ts.daily(
                        ts_code=part_codes,
                        start_date=start_date_str,
                        end_dat=end_date_str,
                    )
                    df = pd.concat((df, tmp), axis=0)
                    break
                except (ReadTimeoutError, ConnectionError,  OSError) as e:
                    print("daily bar request error, retrying...", e)

            print(f"{round(end/len(ts_codes) * 100, 2)}% fetched")

        return df

    def get_real_time_quotes(self, codes: list):
        window = 30
        df = pd.DataFrame()

        for i in range(0, len(codes), window):
            end = max(i + window, window)
            part_codes = [
                code[:-3] for code in codes[i:end]
            ]  # rid code of exchange code

            tmp = _ts.get_realtime_quotes(part_codes)
            df = pd.concat((df, tmp), axis=0)

        return df

    def get_calendar(self, N=732):
        return _pro_ts.trade_cal(exchange="")
    
    def trade_is_on(self, ex=""):
        dt = datetime.now()

    def __today(self):
        """
        get today's date string
        """
        return date.today().strftime("%Y%m%d")

    def __Nday(self, N: int):
        """
        get minus N day's date string
        """
        return (date.today() - timedelta(days=N)).strftime("%Y%m%d")
