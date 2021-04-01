import pandas as pd
import numpy as np

class TAA(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2011, 1, 1) # holdout is 2006-2011 (SPY only)
        # self.SetStartDate(2006, 1, 1)
        # self.SetEndDate(2011, 1, 1)
        self.SetCash(100000)  # Set Strategy Cash

        # collections
        self.symbols = []
        self.indexes = ["SPY", "GSG", "EEM", "TLT", "IYR"]
        self.equity_sma = {}
        self.current_mom = {}
        
        # variables
        self.max_leverage = 1.5
        self.momentum_window = 200        
        self.pct_invested = 0

        for t in self.indexes:
            sec = self.AddEquity(t, Resolution.Minute)
            self.symbols.append(sec.Symbol)
            self.equity_sma[t] = self.SMA(t, self.momentum_window, Resolution.Daily)
            self.Securities[t].FeeModel = ConstantFeeModel(0)
            self.current_mom[t] = 0
            # self.Securities[t].SlippageModel = ConstantSlippageModel(0)

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
                
        # if momentum is positive, allocate 20% of portfolio. Otherwise the 20% should be cash
        for sec in self.current_mom.keys(): 
            if self.current_mom[sec] > 0:
                self.SetHoldings(sec, self.max_leverage / len(self.indexes)) 
                self.pct_invested += self.max_leverage / len(self.indexes)
            
        
    def plot(self):
        # plot indicator values and leverage. Chart name, series name, variable
        for sec in self.indexes:
            self.Plot("Momentum Chart", sec, self.current_mom[sec])
            
        self.Plot("Portion Invested", "% Invested", self.pct_invested)
