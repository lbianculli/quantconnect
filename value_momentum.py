import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

class MomVal(QCAlgorithm):

    def Initialize(self):
        # self.SetStartDate(2007, 1, 1) 

        self.SetStartDate(2003, 1, 1) # Non-index start is 2007
        self.SetEndDate(2007, 1, 1) 
        
        ####### GRID SEARCH PARAMS #######
        # fast_window = self.GetParameter("ema-fast")
        # slow_window = self.GetParameter("ema-slow")
        # num_coarse = self.GetParameter("num_coarse")
        # num_fine = self.GetParameter("num_fine")
        
        # self.fast_window = 40 if fast_window is None else int(fast_window)
        # self.slow_window = 200 if slow_window is None else int(slow_window)
        # self.num_coarse = 500 if num_coarse is None else int(num_coarse)
        # self.num_fine = 35 if num_coarse is None else int(num_fine)

        ###################################
        
        self.SetCash(100000)  # Set Strategy Cash
        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.CoarseSelectionFunction, self.FineSelectionFunction)

        self.AddEquity("SPY", Resolution.Daily)

        self.symbols = []
        self.longs = []
        self.averages = {}
        self.previous_rev = {}
        self.alphas = {}
        self.betas = {}
        
        self.slow_window = 200
        self.fast_window = 40
        self.num_coarse = 500
        self.num_fine = 35

        self.max_leverage = 1.0

        
        self.reb = 1
        
        self.Schedule.On(self.DateRules.MonthStart("SPY", 6), self.TimeRules.AfterMarketOpen("SPY", 30),
                Action(self.prep_rebalance)) 
        
        self.Schedule.On(self.DateRules.MonthStart("SPY", 7), self.TimeRules.AfterMarketOpen("SPY", 30),
                Action(self.rebalance))  # rebalance the 7th trading day of each month. 7 is arbitrary


    def prep_rebalance(self):
        """ one day before rebalancing, switch flag so that universe filters/calcs are run """
        self.Debug(f"Calling for rebalance prep on {self.Time}")
        self.reb = 0  # would love a better way to do 
        
        
    def CoarseSelectionFunction(self, coarse):
        """
        filter base universe if ~8000 based on momentum.
        return a list of securities with positive 2m/10m momentum
        """ 
        if self.reb == 1: 
            return self.longs
        self.Debug(f"Reconstructing Universe on {self.Time}")

        coarse_selected = []
        base_universe = [c for c in coarse if c.Price > 5 and c.HasFundamentalData]
        volume_sorted = sorted(base_universe, key=lambda x: x.DollarVolume, reverse=True)
        volume_sorted = volume_sorted[:self.num_coarse]
        
        for sec in volume_sorted:  
            symbol = sec.Symbol
            
            # TODO: Replace Mmentum with just .Returns?
            
            if symbol not in self.averages:  # get initial history if havent already done so
                # Call history to get an array of history data
                history = self.History(symbol, self.slow_window, Resolution.Daily)
                self.averages[symbol] = Momentum(history, self.fast_window, self.slow_window) 
    
            self.averages[symbol].update(self.Time, sec.AdjustedPrice)  # update with new time/price
            
            if self.averages[symbol].is_ready() and self.averages[symbol].fast > self.averages[symbol].slow:
                coarse_selected.append(symbol)
        
        return coarse_selected
        
    def FineSelectionFunction(self, fine):
        # return the same symbol list if it's not time to rebalance
        if self.reb == 1:
            return self.longs
        self.reb = 1  # reset the flag
        final_filtered = []

        filtered_fine = [x for x in fine if x.ValuationRatios.PERatio and x.ValuationRatios.FCFYield and \
                         x.ValuationRatios.EVToEBITDA]
                         
        ################################
        # having a lot of trouble ordering these operations. The math is right, but not sure how to make it flow
        self.industries = set([x.AssetClassification.MorningstarSectorCode for x in fine])
        for i in self.industries:
            intersection = []
            main_sgas = []
            xs = []
            stocks_of_interest = [x for x in fine if x.AssetClassification.MorningstarSectorCode == i]
            for s in stocks_of_interest:
                if s in self.previous_rev.keys():
                    intersection.append(s)
                else:
                    self.previous_rev[s] = s.FinancialStatements.IncomeStatement.TotalRevenue.TwelveMonths

            intersection = [x for x in stocks_of_interest if x in list(self.previous_rev.keys())]

            if len(intersection) > 10:  # we want a sufficient number to run regression
                final_filtered += intersection
                for s in intersection:  # this is working
                    if s in self.previous_rev.keys():
                        main_sga = s.FinancialStatements.IncomeStatement.SellingGeneralAndAdministration.TwelveMonths - \
                                   s.FinancialStatements.IncomeStatement.ResearchAndDevelopment.TwelveMonths -\
                                   s.FinancialStatements.IncomeStatement.SellingAndMarketingExpense.TwelveMonths
                        main_sgas.append(main_sga)
                        rev_change = s.FinancialStatements.IncomeStatement.TotalRevenue.TwelveMonths - self.previous_rev[s]
                        
                        if rev_change >= 0:
                            dummy_rev = 0
                        else:
                            dummy_rev = 1
                            
                        if s.FinancialStatements.IncomeStatement.NetIncome.TwelveMonths >= 0:
                            dummy_income = 0
                        else:
                            dummy_income = 1
                        
                        xs.append([s.FinancialStatements.IncomeStatement.TotalRevenue.Value, dummy_rev, dummy_income])
                    
                    else:
                        self.previous_rev[s] = s.FinancialStatements.IncomeStatement.TotalRevenue.TwelveMonths
                
                # industry regression:
                x = np.array(xs)
                y = np.array(main_sgas)
                # self.Debug(f"xs shape: {x.shape}")
                # self.Debug(f"ys shape: {y.shape}")
                model = LinearRegression().fit(x, y)  # ERROR HERE
                self.betas[i] = model.coef_[0]
                self.alphas[i] = model.intercept_

                # Loop back through to calculate investment portion of sga (so we can sort)
                for s in intersection:    
                    main_sga = (s.FinancialStatements.IncomeStatement.SellingGeneralAndAdministration.TwelveMonths - \
                                   s.FinancialStatements.IncomeStatement.ResearchAndDevelopment.TwelveMonths -\
                                   s.FinancialStatements.IncomeStatement.SellingAndMarketingExpense.TwelveMonths)
                    maintenance_main_sga = self.betas[i] * s.FinancialStatements.IncomeStatement.TotalRevenue.TwelveMonths
                    assets = s.FinancialStatements.BalanceSheet.TotalAssets.Value
                    
                    # s.InvestmentSGA = main_sga - maintenance_main_sga
                    s.InvestmentSGA = (main_sga - maintenance_main_sga) / assets

        # THIS RUNS, WHY DOES IT NOT ORDER?
        # after iterating thru all industries and stocks, get ranks 
        self.Debug(f"LEN FINAL FILTERED: {len(final_filtered)}")
        factor_rank1 = sorted(final_filtered, key=lambda x: x.ValuationRatios.FCFYield, reverse=True)  # descending
        factor_rank2 = sorted(final_filtered, key=lambda x: x.ValuationRatios.EVToEBITDA, reverse=True)
        factor_rank3 = sorted(final_filtered, key=lambda x: x.InvestmentSGA, reverse=True)
        factor_rank4 = sorted(final_filtered, key=lambda x: x.ValuationRatios.TotalYield, reverse=True) 
        score_dict = {}
        # i know it works up to here
        for i,ele in enumerate(factor_rank1):
            rank1 = i
            rank2 = factor_rank2.index(ele)
            rank3 = factor_rank3.index(ele)
            rank4 = factor_rank4.index(ele)
            score = sum([rank1, rank2, rank3, rank4])*1/4

            score_dict[ele] = score
        
        self.Debug("Ranking 2!")
        # sort the stocks by their scores
        self.sorted_stock = sorted(score_dict.items(), key=lambda d:d[1],reverse=False)
        sorted_symbol = [x[0] for x in self.sorted_stock]
        
        # sotre the top stocks into the long_list and the bottom ones into the short_list
        self.longs = [x.Symbol for x in sorted_symbol[:self.num_fine]]
            
        return self.longs
        
        
    def rebalance(self):
        """ monthly function to rebalance the portfolio according to current universe/rankings """ 
        self.Debug(f"Rebalancing on {self.Time}")
        self.Debug(f"Number of longs: {len(self.longs)}")

        for sec in self.Portfolio.Values:  
            if sec.Symbol not in self.longs:  # annoying how this is symbol, but below isnt
                self.Liquidate(sec.Symbol)
                
        for sec in self.longs:
            self.SetHoldings(sec, self.max_leverage/self.num_fine)
            
            
class Momentum:
    def __init__(self, history, fast_window, slow_window):
        self.fast = ExponentialMovingAverage(fast_window)
        self.slow = ExponentialMovingAverage(slow_window)
        
        for bar in history.itertuples():  # index level 0 is symbol, level 1 is time
            self.fast.Update(bar.Index[1], bar.close)
            self.slow.Update(bar.Index[1], bar.close)
        
    def is_ready(self):
        return self.fast.IsReady and self.slow.IsReady
        
    def update(self, time, price):
        self.fast.Update(time, price)
        self.slow.Update(time, price)
