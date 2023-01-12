#include <string>
#include <iostream>
#include <vector>
#include <Python.h>
#include <assert.h>
#include <boost/version.hpp>
#include <boost/interprocess/managed_shared_memory.hpp>
#include <boost/interprocess/containers/map.hpp>
#include <boost/interprocess/containers/string.hpp>
#include <boost/interprocess/containers/vector.hpp>
#include <boost/interprocess/allocators/allocator.hpp>
#include <boost/interprocess/sync/interprocess_mutex.hpp>
#include <boost/interprocess/sync/scoped_lock.hpp>

namespace bip = boost::interprocess;
typedef bip::managed_shared_memory msm;

struct Sample
{
    std::string code = "", trade_date = "";
    float price = 0, neg_prev_ma = 0, pos_prev_ma = 0;

    Sample(PyObject *df_row)
    {
        char *ts_code_tmp, *trade_date_tmp;
        // parse stock code
        PyArg_Parse(PyTuple_GetItem(df_row, 0), "s", &ts_code_tmp);
        code = std::string(ts_code_tmp);

        // parse date
        PyObject *date_str_obj = PyObject_CallMethod(PyTuple_GetItem(df_row, 1), "strftime", "s", "%Y%m%d");
        PyArg_Parse(date_str_obj, "s", &trade_date_tmp);
        trade_date = std::string(trade_date_tmp);

        // parse stock price
        PyArg_Parse(PyTuple_GetItem(df_row, 2), "f", &price);

        // parse previous moving averages
        PyObject *price_obj = PyTuple_GetItem(df_row, 3);
        if (price_obj != Py_None)
            PyArg_Parse(price_obj, "f", &pos_prev_ma);
        price_obj = PyTuple_GetItem(df_row, 4);
        if (price_obj != Py_None)
            PyArg_Parse(price_obj, "f", &neg_prev_ma);
    }

    bool operator>(Sample &rhs)
    {
        if (code != rhs.code)
            return code > rhs.code;
        else
            return trade_date > rhs.trade_date;
    }

    operator std::string() const
    {
        return "code, trade_date, price, pos_prev_ma, neg_prev_ma\n" + code + " " +
               trade_date + " " + std::to_string(price) + " " +
               std::to_string(pos_prev_ma) + " " + std::to_string(neg_prev_ma) + "\n";
    }
};

int get_streaks(std::vector<Sample> &input, unsigned int streak_len, bool is_up, std::vector<std::string> &res_vec);
