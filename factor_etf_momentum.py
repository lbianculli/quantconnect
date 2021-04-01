# Like GAA, this is implemented as long-only. The idea is that factors with positive performance in the past month are long. This is a pure autocorrelation bet.
# strongest with a one-month lookback

import pandas as pd
import numpy as np

class TAA(QCAlgorithm):

    def Initialize(self):
        # self.SetStartDate(2014, 9, 1) # latest inception for these ETFs is July 2013
        # self.SetEndDate(2020, 1, 1)

        self.SetStartDate(2020, 1, 1)  # OOS
        self.SetCash(100000)  

        # collections
        self.symbols = []
        self.indexes = ["USMV", "VLUE", "QUAL", "MTUM"]
        self.equity_sma = {}
        self.current_mom = {}
        
        # variables
        self.max_leverage = 1.0
        self.momentum_window = 21   
        self.pct_invested = 0
        spy = self.AddEquity("SPY", Resolution.Minute)

        for t in self.indexes:
            sec = self.AddEquity(t, Resolution.Minute)
            self.symbols.append(sec.Symbol)
            self.equity_sma[t] = self.SMA(t, self.momentum_window, Resolution.Daily)
            self.Securities[t].FeeModel = ConstantFeeModel(0)
            self.current_mom[t] = 0
            self.Securities[t].SlippageModel = ConstantSlippageModel(0)

        self.Schedule.On(self.DateRules.MonthStart("SPY", 5), self.TimeRules.AfterMarketOpen("SPY", 60), self.trade) 
        self.Schedule.On(self.DateRules.MonthStart("SPY", 5), self.TimeRules.AfterMarketOpen("SPY", 60), self.plot)  
        
        self.prior_leverage = 0  # might be a better way, but this should work
        
        # warm up momentum indicator
        self.SetWarmUp(self.momentum_window+1)
        

    def OnData(self, data):
        '''OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
            Arguments:
                data: Slice object keyed by symbol containing the stock data
        '''
        pass
        
    
    def trade(self):
        """ momentum calcs and trade logic """
        if len(str(self.Time.month)) == 1:
            month = f"0{self.Time.month}"
        else: 
            month = self.Time.month
            
        if len(str(self.Time.day)) == 1:
            day = f"0{self.Time.day}"
        else: 
            day = self.Time.day
        
        self.current_date = f"{self.Time.year}-{month}-{day}"
        
        for holding in self.Portfolio.Values:  # liquidate
            self.Liquidate(holding.Symbol)
            
        self.pct_invested = 0
    
        for sec in self.indexes:  # calculate momentum
            current_price = self.Securities[sec].Price
            sma = self.equity_sma[sec].Current.Value
            
            try:
                self.current_mom[sec] = current_price / sma - 1
                
            except ZeroDivisionError as e: # no data for the security. m
                self.current_mom[sec] = -1
                           
        # if momentum is positive, allocate % of portfolio. Otherwise the % should be cash
        for sec in self.current_mom.keys(): 
            if self.current_mom[sec] > 0:
                self.SetHoldings(sec, self.max_leverage / len(self.indexes)) 
                self.pct_invested += self.max_leverage / len(self.indexes)         
        
    def plot(self):
        # plot indicator values and leverage. Chart name, series name, variable
        for sec in self.indexes:
            self.Plot("Momentum Chart", sec, self.current_mom[sec])
            
        self.Plot("Portion Invested", "% Invested", self.pct_invested)
