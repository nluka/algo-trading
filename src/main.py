from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yfinance as yf
import linecache as lc

from AnalyzerSuite import AnalyzerSuite

starting_cash = 100000.0
symbols = []

def order_status_to_str(status):
    if status == bt.Order.Accepted: return 'ACCEPTED'
    elif status == bt.Order.Completed: return 'COMPLETED'
    elif status == bt.Order.Created: return 'CREATED'
    elif status == bt.Order.Rejected: return 'REJECTED'
    elif status == bt.Order.Submitted: return 'SUBMITTED'
    else: return None

class TestStrategy(bt.Strategy):

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        self.curr_month = 0
        self.top_stocks = []
        self.top_stocks_count = 10
        self.cash_available = starting_cash

    def in_top_stocks(self, symbol):
        for top_symbol in self.top_stocks:
            if top_symbol == symbol:
                return True
        return False

    def in_momentous_stocks(self, symbol, momentums):
        for symbol_, momentum_ in momentums:
            if symbol_ == symbol:
                return True
        return False

    def buy_next_most_momentous_stock(self, momentums):
        symbol_to_buy = momentums[-1][0]
        idx = symbols.index(symbol_to_buy)
        # TODO: find a better way of computing budget
        budget_for_symbol = self.cash_available / 2.0
        closing_price = self.datas[idx].close[0]
        num_shares_to_buy = int(budget_for_symbol / closing_price)
        order = self.buy(data=self.datas[idx], size=num_shares_to_buy)
        self.top_stocks.append(symbol_to_buy)
        self.log(f'Trying to buy %s, budget=%.2f, size=%d' % (symbol_to_buy, budget_for_symbol, num_shares_to_buy))
        momentums.pop()

    def sell_stock(self, idx):
        symbol_to_sell = symbols[idx]
        order = self.sell(data=self.datas[idx])
        self.top_stocks.remove(symbol_to_sell)
        self.log(f'Trying to sell %s' % (symbol_to_sell))

    def next(self):
        dt = self.datas[0].datetime.date(0)
        if dt.month == self.curr_month: # not a new month yet
            return

        self.curr_month = dt.month

        # compute momentum of each stock
        momentums = []
        for stock_idx, stock_data in enumerate(self.datas):
            price_today = stock_data.close[0]
            price_10_days_ago = stock_data.close[-10]
            # TODO: Try different ways of computing momentum
            momentum = price_today / price_10_days_ago
            symbol = symbols[stock_idx]
            momentums.append((symbol, momentum))

        momentums.sort(key=lambda tup: tup[1], reverse=True) # sort in descending order, best stock is at front
        momentums = momentums[:self.top_stocks_count]

        self.log(f'Previously held symbols: %s' % (", ".join(self.top_stocks)))
        self.log(f'Most momentous symbols: %s' % (", ".join("%s" % tup[0] for tup in momentums)))

        # sell stocks which fell off top N
        for prev_held_symbol in self.top_stocks:
            if not self.in_momentous_stocks(symbol=prev_held_symbol, momentums=momentums):
                self.log(f'Stock %s no longer in top %d' % (prev_held_symbol, self.top_stocks_count))
                idx = symbols.index(prev_held_symbol)
                self.sell_stock(idx)

        # buy stocks which came into top N
        stocks_to_buy = self.top_stocks_count - len(self.top_stocks)
        while stocks_to_buy > 0:
            self.buy_next_most_momentous_stock(momentums=momentums)
            stocks_to_buy -= 1

    def notify_cashvalue(self, cash, value):
        # dt = self.datas[0].datetime.date(0)
        # if dt.month == self.curr_month: # not a new month yet
        #     return
        self.cash_available = cash
        # self.log(f'Cash left = %.2f, value = %.2f' % (cash, value))

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
                    'BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm))
            else: # Sell
                self.log('SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (order.executed.price,
                          order.executed.value,
                          order.executed.comm))

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TestStrategy)

    with open('tickers.txt') as f:
        symbols = f.read().splitlines()

    for sym in symbols:
        data = bt.feeds.PandasData(dataname=yf.download(sym, '2010-01-01', '2020-01-01', auto_adjust=True))
        print(f'Downloaded %s data' % (sym))
        cerebro.adddata(data)

    AnalyzerSuite.defineAnalyzers(AnalyzerSuite, cerebro)
    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(0.01)
    print('')
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    thestrats = cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    outputs = AnalyzerSuite.returnAnalyzers(AnalyzerSuite, thestrats)
    print(f'Drawdown: %.2f%%' % outputs['DrawDown'])
    print(f'Sharpe Ratio: %.2f' % outputs['Sharpe Ratio:'])
    print(f'Returns: %.2f%%' % outputs['Returns:'])