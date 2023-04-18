from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yfinance
import yfinance.shared
import linecache as lc
import os
import pickle
import time

starting_cash = 100000.0
all_symbols = []
bad_symbols = [ # symbols with incomplete/bad data from Yahoo Finance
    'TIE',
    'WPI',
    'BMS',
    'POM',
    '#CBE',
    'AGN',
    'ALXN',
    'APC',
    'APOL',
    'ARG',
    'AVP',
    'BBT',
    'BCR',
    'BEAM',
    'BF.B',
    'BLL',
    'BRCM',
    'BRK.B',
    'CAM',
    'CBG',
    'CBS',
    'CELG',
    'CERN',
    'CFN',
    'CHK',
    'COG',
    'COH',
    'CTL',
    'CTXS',
    'CVC',
    'DF',
    'DISCA',
    'DNB',
    'DNR',
    'DO',
    'DPS',
    'DTV',
    'DV',
    'ESV',
    'ETFC',
    'FDO',
    'FII',
    'FLIR',
    'FRX',
    'FTR',
    'HCBK',
    'HCN',
    'HCP',
    'HRS',
    'HSP',
    'JCP',
    'JDSU',
    'JEC',
    'JOY',
    'KFT',
    'LLL',
    'LLTC',
    'LM',
    'LO',
    'LTD',
    'LUK',
    'LXK',
    'MJN',
    'MON',
    'MWV',
    'MYL',
    'NBL',
    'NE',
    'NU',
    'NYX',
    'PBCT',
    'PCLN',
    'PCS',
    'PX',
    'QEP',
    'RAI',
    'RDC',
    'RHT',
    'RRD',
    'RTN',
    'S',
    'SAI',
    'SHLD',
    'SIAL',
    'SNDK',
    'SPLS',
    'STI',
    'STJ',
    'SWY',
    'SYMC',
    'TE',
    'TIF',
    'TMK',
    'TSO',
    'TSS',
    'TWC',
    'TYC',
    'UTX',
    'VAR',
    'VIAB',
    'WAG',
    'WFM',
    'WIN',
    'WLP',
    'WPO',
    'WPX',
    'WYN',
    'XL',
    'XLNX',
    'YHOO',
    'ZMH',
    'CVH',
    'CCE',
    'ACE',
    'BHI',
    'PCP',
    'DOW',
    'ANR',
    'PCL',
    'HOT',
    'PLL',
    'ALTR',
    'SE',
    'IR',
    'BTU',
    'DELL',
    'SCG',
    'MOLX',
    'TEG',
    'MHP',
    'LIFE',
    'GCI',
    'NWSA',
    'HNZ',
    'HAR',
    'EMC',
    'COL',
    'SUN',
    'GAS',
    'BMC',
    'COV',
    'CSC',
    'PSX',
    'TRIP',
    'SNI',
    'XYL',
    'TWX',
    'MPC',
    'CA',
    'KMI',
    'AET',
    'ESRX',
    'NFX',
]

class ROC252(bt.Indicator):
    lines = ('roc252',)
    params = (('period', 252),)

    def __init__(self):
        self.lines.roc252 = (self.data - self.data(-self.params.period)) / self.data(-self.params.period) * 100.0

class TestStrategy(bt.Strategy):
    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        self.curr_month = 0
        self.held_stocks = [] # list of tuple: (symbol, size)
        self.hold_count = 6 # how many different symbols to hold at one time
        self.cash_available = starting_cash
        self.sma = bt.indicators.SMA(self.data, period=200)
        self.days_passed = 0
        for data in self.datas:
            data.roc252 = ROC252(data.close, period=252)
            setattr(self, f'sma_{data._name}', bt.indicators.SimpleMovingAverage(data.close, period=200))

    def next(self):
        # Check if all indicators have enough data
        if any(line[0] is None for line in self.lines):
            return

        dt = self.datas[0].datetime.date(0)
        if dt.month == self.curr_month: # not a new month yet
            return

        self.log('First of the month, let''s get to work')
        self.curr_month = dt.month

        momentums = []
        for i, data in enumerate(self.datas):
            symbol = all_symbols[i]
            sma_value = getattr(self, f'sma_{data._name}')[0]
            close = data.close[0]
            if close > sma_value:
                roc252_value = data.roc252.lines.roc252[0]
                momentums.append((symbol, roc252_value))
        momentums.sort(key=lambda tup: tup[1]) # sort in ascending order, best stock is at back
        momentums = momentums[:self.hold_count]

        self.log(f'Held stocks: %s' % (", ".join("(%s,%d)" % tup for tup in self.held_stocks)))
        self.log(f'Most momentous symbols: %s' % (", ".join("%s" % tup[0] for tup in momentums)))

        # sell stocks which fell off top N
        for held_symbol, num_shares_held in self.held_stocks:
            if not self.in_momentous_stocks(symbol=held_symbol, momentums=momentums):
                self.log(f'Stock %s no longer in top %d (we have %d of it)' %
                        (held_symbol, self.hold_count, num_shares_held))
                all_idx = all_symbols.index(held_symbol)
                self.sell_stock(all_idx=all_idx)

        num_stocks_to_buy = self.hold_count - len(self.held_stocks)
        if (num_stocks_to_buy == 0):
            return

        # buy stocks which came into top N
        budget_per_symbol = (self.cash_available / float(num_stocks_to_buy)) * 0.98
        while num_stocks_to_buy > 0:
            self.buy_next_most_momentous_stock(momentums=momentums, budget_per_symbol=budget_per_symbol)
            num_stocks_to_buy -= 1

    def buy_next_most_momentous_stock(self, momentums, budget_per_symbol):
        symbol_to_buy = momentums[-1][0]
        idx_all = all_symbols.index(symbol_to_buy)
        closing_price = self.datas[idx_all].close[0]
        num_shares_to_buy = int(budget_per_symbol / closing_price)
        order = self.buy(data=self.datas[idx_all], size=num_shares_to_buy)
        self.held_stocks.append((symbol_to_buy, num_shares_to_buy))
        self.log(f'Trying to buy %s, budget=%.2f, price=%.2f, size=%d' %
                (symbol_to_buy, budget_per_symbol, closing_price, num_shares_to_buy))
        momentums.pop()

    def sell_stock(self, all_idx):
        symbol_to_sell = all_symbols[all_idx]
        held_idx = self.find_index_by_symbol(symbol=symbol_to_sell)
        num_shares_held = self.held_stocks[held_idx][1]
        order = self.sell(data=self.datas[all_idx], size=num_shares_held)
        del self.held_stocks[held_idx]
        self.log(f'Trying to sell %d of %s' % (num_shares_held, symbol_to_sell))

    def in_held_stocks(self, symbol):
        for symbol_, size_ in self.held_stocks:
            if symbol_ == symbol:
                return True
        return False

    def in_momentous_stocks(self, symbol, momentums):
        for symbol_, momentum_ in momentums:
            if symbol_ == symbol:
                return True
        return False

    def find_index_by_symbol(self, symbol):
        for idx, tup in enumerate(self.held_stocks):
            symbol_ = tup[0]
            if symbol_ == symbol:
                return idx
        return None

    def notify_cashvalue(self, cash, value):
        self.cash_available = cash

    def notify_order(self, order):
        if order.status == order.Submitted:
            self.log('ORDER SUBMITTED')
        elif order.status == order.Accepted:
            self.log('ORDER ACCEPTED')
        elif order.status == order.Expired:
            self.log('BUY EXPIRED')
        elif order.status == order.Completed:
            if order.isbuy():
                self.log(
                    'BUY EXECUTED, Price=%.2f, Size=%d, Cost=%.2f, Comm=%.2f' %
                    (order.executed.price,
                     order.executed.size,
                     order.executed.value,
                     order.executed.comm))
            else: # Sell
                self.log('SELL EXECUTED, Price=%.2f, Size=%d, Cost=%.2f, Comm=%.2f' %
                         (order.executed.price,
                          order.executed.size,
                          order.executed.value,
                          order.executed.comm))

if __name__ == '__main__':
    start = time.time()

    cerebro = bt.Cerebro()
    cerebro.addstrategy(TestStrategy)

    all_symbols_raw = []
    with open('tickers2.txt') as f:
        all_symbols_raw = f.read().splitlines()
    for sym in all_symbols_raw:
        if sym in bad_symbols:
            del sym

    for idx, sym in enumerate(all_symbols_raw):
        file_name = f'data/%s.pickle' % sym
        data = None
        if os.path.exists(file_name):
            if os.path.getsize(file_name) > 0:
                with open(file_name, 'rb') as f:
                    data = pickle.load(f)
                print('Loaded %s data from cache' % sym)
            else:
                continue
        else:
            df = yfinance.download(sym, '2010-01-01', '2020-01-01', auto_adjust=True)
            df.fillna(method='ffill', inplace=True)
            data = bt.feeds.PandasData(dataname=df)
            print(f'Downloaded %s data' % (sym))
            with open(file_name, 'wb') as f:
                if len(list(yfinance.shared._ERRORS.keys())) == 0:
                    pickle.dump(data, f)
        all_symbols.append(sym)
        cerebro.adddata(data)

    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(0.01)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='mydrawdown')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='mysharpe')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='myreturns')

    results = cerebro.run()
    result = results[0]

    drawdown = result.analyzers.mydrawdown.get_analysis()['drawdown']
    sharpe = result.analyzers.mysharpe.get_analysis()['sharperatio']
    returns = result.analyzers.myreturns.get_analysis()['rnorm100']

    print('')
    print('Starting Portfolio Value: %.2f' % starting_cash)
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
    print(f'Drawdown: %.2f%%' % drawdown)
    print(f'Sharpe Ratio: %.2f' % sharpe)
    print(f'Returns: %.2f%%' % returns)

    end = time.time()
    print(f'Execution took %.2lf s' % (end - start))
