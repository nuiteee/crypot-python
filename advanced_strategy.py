import pandas as pd
import numpy as np
import config
from loguru import logger
import time
import pandas_ta as ta  # 需要安装: pip install pandas_ta
from datetime import datetime, timedelta
import asyncio

class AdvancedTradingStrategy:
    def __init__(self, okx_handler):
        """初始化高级交易策略"""
        self.okx = okx_handler
        
        # 可用策略列表
        self.available_strategies = {
            "triple_signal": "三重信号验证策略",
            "volatility_breakout": "波动率突破策略",
            "trend_following": "趋势跟踪策略",
            "mean_reversion": "均值回归策略",
            "original": "原始震荡下跌策略"
        }
        
        # 当前选择的策略
        self.current_strategy = "triple_signal"  # 默认使用三重信号验证策略
        
        # 策略参数
        self.params = {
            "triple_signal": {
                "rsi_period": 14,
                "ma_fast": 5,
                "ma_slow": 20,
                "bollinger_period": 20
            },
            "volatility_breakout": {
                "atr_period": 14,
                "multiplier": 2.0
            },
            "trend_following": {
                "ema_fast": 9,
                "ema_slow": 21
            },
            "mean_reversion": {
                "lookback_period": 20,
                "std_dev": 2.0
            },
            "original": {
                "ma_period": 20,
                "rsi_period": 14
            }
        }
        
        self.running = False
        logger.info("高级交易策略初始化完成")
        
        # 止盈止损设置
        self.stop_loss_percentage = 5.0
        self.take_profit_percentage = 10.0
        
        # 加码设置
        self.pyramid_enabled = False
        self.max_pyramids = 3
        self.current_pyramids = 0
        self.last_pyramid_price = 0
        
        # 波动率历史
        self.volatility_window = 20
        self.volatility_history = []
        self.last_position_check = 0
        
        # 初始化获取仓位状态
        self._update_position_info()
        
    def calculate_indicators(self, df):
        """计算各种技术指标"""
        # 使用pandas_ta库计算指标
        
        # 基础指标
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['ema21'] = ta.ema(df['close'], length=21)
        df['ema50'] = ta.ema(df['close'], length=50)
        df['ema200'] = ta.ema(df['close'], length=200)
        df['sma20'] = ta.sma(df['close'], length=20)
        
        # 波动率指标
        df['atr'] = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=14)
        df['atr_percent'] = df['atr'] / df['close'] * 100
        
        # 布林带
        bb = ta.bbands(df['close'], length=20, std=2)
        df['bb_upper'] = bb['BBU_20_2.0']
        df['bb_middle'] = bb['BBM_20_2.0']
        df['bb_lower'] = bb['BBL_20_2.0']
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # 趋势指标
        try:
            adx = ta.adx(high=df['high'], low=df['low'], close=df['close'], length=14)
            df['adx'] = adx['ADX_14']
            df['di_plus'] = adx['DMP_14']
            df['di_minus'] = adx['DMN_14']
        except:
            logger.warning("ADX计算失败，尝试替代方法")
            # 简化版ADX
            df['adx'] = 50  # 默认中性值
        
        # 成交量指标
        if 'volume' in df.columns:
            df['obv'] = ta.obv(df['close'], df['volume'])
        
        # 计算SuperTrend指标
        try:
            st = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=10, multiplier=3)
            df['supertrend'] = st['SUPERT_10_3.0']
            df['supertrend_direction'] = st['SUPERTd_10_3.0']
        except:
            logger.warning("Supertrend计算失败")
            df['supertrend'] = df['close']
            df['supertrend_direction'] = 1
        
        # 计算最近高低点
        df['recent_high'] = df['high'].rolling(window=50).max()
        df['recent_low'] = df['low'].rolling(window=50).min()
        
        # 计算斐波那契回调水平
        range_price = df['recent_high'] - df['recent_low']
        df['fib_382'] = df['recent_low'] + range_price * 0.382
        df['fib_500'] = df['recent_low'] + range_price * 0.5
        df['fib_618'] = df['recent_low'] + range_price * 0.618
        
        # 清理NaN值
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(method='ffill')
        
        return df
    
    def detect_trend_direction(self):
        """检测趋势方向 - 日线级别"""
        try:
            # 获取日线K线数据
            df_daily = self.okx.get_kline_data(timeframe="1D", limit=50)
            
            if df_daily is None or len(df_daily) < 30:
                logger.warning("无法获取足够的日线数据进行趋势判断")
                return None
            
            df_daily = self.calculate_indicators(df_daily)
            
            # 趋势强度判定
            down_trend = (df_daily['ema21'] < df_daily['ema50']).iloc[-1]
            strong_trend = (df_daily['adx'] > 25).iloc[-1]
            price_below_st = (df_daily['close'] < df_daily['supertrend']).iloc[-1]
            
            logger.info(f"日线趋势分析: 下降趋势={down_trend}, 趋势强度高={strong_trend}, 价格低于超级趋势线={price_below_st}")
            
            return down_trend and strong_trend and price_below_st
        except Exception as e:
            logger.error(f"趋势方向检测失败: {e}")
            return None
    
    def detect_consolidation(self):
        """检测震荡结构 - 4小时级别"""
        try:
            # 获取4小时K线数据
            df_4h = self.okx.get_kline_data(timeframe="4H", limit=50)
            
            if df_4h is None or len(df_4h) < 30:
                logger.warning("无法获取足够的4小时数据进行震荡判断")
                return None
            
            df_4h = self.calculate_indicators(df_4h)
            
            # 震荡检测
            tight_bbands = (df_4h['bb_width'] < 0.1).iloc[-1]
            low_volatility = (df_4h['atr_percent'] < 2.0).iloc[-1]
            
            logger.info(f"4小时震荡分析: 布林带收窄={tight_bbands}, 低波动率={low_volatility}")
            
            return tight_bbands and low_volatility
        except Exception as e:
            logger.error(f"震荡结构检测失败: {e}")
            return None
    
    def detect_entry_signal(self):
        """检测入场信号 - 1小时级别"""
        try:
            # 获取1小时K线数据
            df_1h = self.okx.get_kline_data(timeframe="1H", limit=50)
            
            if df_1h is None or len(df_1h) < 30:
                logger.warning("无法获取足够的1小时数据进行入场信号检测")
                return None
            
            df_1h = self.calculate_indicators(df_1h)
            
            # 反弹至斐波那契38.2%阻力位
            price_at_fib = (df_1h['close'] > df_1h['fib_382']).iloc[-1]
            
            # 超卖条件
            not_oversold = (df_1h['rsi'] > 40).iloc[-1]
            
            # 量价背离检测 (需要成交量数据)
            divergence = False
            if 'volume' in df_1h.columns and 'obv' in df_1h.columns:
                price_high = df_1h['close'].rolling(5).max()
                obv_high = df_1h['obv'].rolling(5).max()
                
                price_trending_up = price_high.diff().iloc[-1] > 0
                obv_trending_down = obv_high.diff().iloc[-1] < 0
                
                divergence = price_trending_up and obv_trending_down
            
            logger.info(f"1小时信号分析: 价格位于斐波那契位置={price_at_fib}, 非超卖={not_oversold}, 量价背离={divergence}")
            
            return price_at_fib and not_oversold and (divergence or not 'volume' in df_1h.columns)
        except Exception as e:
            logger.error(f"入场信号检测失败: {e}")
            return None
    
    def calculate_dynamic_position(self):
        """基于波动率的动态仓位计算"""
        # 计算波动率指数 (0-100)
        volatility = self._calculate_volatility()
        volatility_index = min(100, max(0, volatility * 10))  # 将波动率缩放到0-100
        
        # 基础仓位大小
        base_size = config.POSITION_SIZE * 0.5
        
        # 动态仓位计算: 波动率高时仓位小，波动率低时仓位大
        position_size = base_size * (1 - np.exp(-0.03 * (100 - volatility_index)))
        
        # 确保最小仓位和最大仓位限制
        position_size = max(config.POSITION_SIZE * 0.1, min(config.POSITION_SIZE, position_size))
        
        # 四舍五入到0.001
        position_size = round(position_size, 3)
        
        logger.info(f"波动率指数: {volatility_index:.2f}, 计算的动态仓位大小: {position_size}")
        
        return position_size
    
    def check_stop_loss_conditions(self, current_price):
        """检查多重止损条件"""
        if not self.position or self.entry_price <= 0:
            return False, "无持仓"
            
        # 获取最新K线数据
        df = self.okx.get_kline_data(bar='15m', limit=20)
        if df is None:
            return False, "无法获取K线数据"
            
        df = self.calculate_indicators(df)
        
        # 计算当前盈亏百分比
        if self.position == 'long':
            profit_percentage = (current_price - self.entry_price) / self.entry_price * 100
        else:  # short
            profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
        
        # 1. 基础止损 - 亏损超过阈值
        if profit_percentage <= -self.stop_loss_percentage:
            return True, f"触发基础止损，亏损: {profit_percentage:.2f}%"
        
        # 2. 移动锚定止损
        if len(df) >= 3:
            recent_highs = df['high'][-3:].max()
            atr = df['atr'].iloc[-1]
            
            if self.position == 'short':
                trailing_stop = max(recent_highs + 2 * atr, self.entry_price * 0.98)
                if current_price >= trailing_stop:
                    return True, f"触发移动锚定止损，价格: {current_price} > {trailing_stop:.2f}"
            else:  # long
                trailing_stop = min(df['low'][-3:].min() - 2 * atr, self.entry_price * 1.02)
                if current_price <= trailing_stop:
                    return True, f"触发移动锚定止损，价格: {current_price} < {trailing_stop:.2f}"
        
        # 3. 波动突破止损
        if 'atr' in df.columns and 'adx' in df.columns:
            atr = df['atr'].iloc[-1]
            adx = df['adx'].iloc[-1]
            
            if self.position == 'short':
                if (current_price - self.entry_price) > 3 * atr and adx > 30:
                    return True, f"触发波动突破止损，ADX: {adx:.2f}, 价格变动: {current_price - self.entry_price} > {3 * atr:.2f}"
            else:  # long
                if (self.entry_price - current_price) > 3 * atr and adx > 30:
                    return True, f"触发波动突破止损，ADX: {adx:.2f}, 价格变动: {self.entry_price - current_price} > {3 * atr:.2f}"
        
        # 4. 时间衰减止损
        if self.entry_time:
            holding_time = datetime.now() - self.entry_time
            if holding_time > timedelta(hours=6) and profit_percentage < 1:
                return True, f"触发时间衰减止损，持仓时间: {holding_time}, 利润: {profit_percentage:.2f}%"
        
        return False, None
    
    def check_take_profit_conditions(self, current_price):
        """检查止盈条件"""
        if not self.position or self.entry_price <= 0:
            return False, "无持仓"
        
        # 计算当前盈亏百分比
        if self.position == 'long':
            profit_percentage = (current_price - self.entry_price) / self.entry_price * 100
        else:  # short
            profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
        
        # 基础止盈
        if profit_percentage >= self.take_profit_percentage:
            return True, f"触发基础止盈，盈利: {profit_percentage:.2f}%"
        
        return False, None
    
    def check_pyramid_conditions(self, current_price):
        """检查加码条件"""
        if not self.pyramid_enabled or not self.position:
            return False, "加码未启用或无持仓"
            
        if self.current_pyramids >= self.max_pyramids:
            return False, "已达到最大加码次数"
            
        # 获取最新K线数据
        df = self.okx.get_kline_data(bar='15m', limit=20)
        if df is None:
            return False, "无法获取K线数据"
            
        df = self.calculate_indicators(df)
        
        # 检查RSI条件
        rsi_condition = df['rsi'].iloc[-1] > 40 if self.position == 'short' else df['rsi'].iloc[-1] < 60
        
        # 检查价格条件
        new_low = False
        if self.position == 'short':
            new_low = df['close'].iloc[-1] < df['close'].iloc[-10:].min()
        else:  # long
            new_low = df['close'].iloc[-1] > df['close'].iloc[-10:].max()
        
        # 检查间距条件
        min_distance = 2 * df['atr'].iloc[-1]
        price_distance = abs(current_price - self.last_pyramid_price) if self.last_pyramid_price > 0 else float('inf')
        distance_condition = price_distance >= min_distance
        
        logger.info(f"加码条件检查: RSI={rsi_condition}, 新低/高={new_low}, 价格间距={distance_condition}")
        
        if rsi_condition and new_low and distance_condition:
            return True, f"满足加码条件，当前金字塔次数: {self.current_pyramids}/{self.max_pyramids}"
            
        return False, "不满足加码条件"
    
    def execute_pyramid(self, current_price):
        """执行加码操作"""
        if not self.pyramid_enabled or self.current_pyramids >= self.max_pyramids:
            return "加码未启用或已达到最大次数"
        
        # 计算加码仓位大小 (每次递减)
        base_size = config.POSITION_SIZE * (0.5 ** (self.current_pyramids + 1))
        size = round(max(0.001, base_size), 3)  # 确保最小仓位为0.001
        
        # 执行加码
        result = None
        if self.position == 'short':
            result = self.okx.open_short_position(size)
        else:  # long
            result = self.okx.open_long_position(size)
        
        if result and 'data' in result:
            self.current_pyramids += 1
            self.last_pyramid_price = current_price
            
            # 更新加权平均入场价
            old_value = self.entry_price * self.position_size
            new_value = current_price * size
            self.position_size += size
            self.entry_price = (old_value + new_value) / self.position_size
            
            logger.info(f"成功执行第 {self.current_pyramids} 次加码，价格: {current_price}, 仓位: {size}")
            return f"成功执行第 {self.current_pyramids} 次加码，价格: {current_price}, 仓位: {size}"
        else:
            logger.error(f"加码失败: {result}")
            return f"加码失败: {result}"
    
    def run_triple_signal_strategy(self):
        """运行三重信号验证策略"""
        try:
            # 更新当前仓位信息
            self._update_position_info()
            
            # 获取当前价格
            current_price = self.okx.get_current_price()
            if not current_price:
                return "无法获取当前价格，略过本次策略运行"
            
            # 更新价格历史和波动度
            self._update_price_history(current_price)
            
            # 如果有持仓，检查止盈止损
            if self.position and self.entry_price > 0:
                # 检查止损
                stop_loss, reason = self.check_stop_loss_conditions(current_price)
                if stop_loss:
                    # 平仓
                    if self.position == 'long':
                        result = self.okx.close_long_position()
                    else:
                        result = self.okx.close_short_position()
                    
                    if result and 'data' in result:
                        self._update_position_info()
                        return f"⚠️ {reason}，已平仓"
                    else:
                        return f"⚠️ {reason}，但平仓失败: {result}"
                
                # 检查止盈
                take_profit, reason = self.check_take_profit_conditions(current_price)
                if take_profit:
                    # 平仓
                    if self.position == 'long':
                        result = self.okx.close_long_position()
                    else:
                        result = self.okx.close_short_position()
                    
                    if result and 'data' in result:
                        self._update_position_info()
                        return f"🎯 {reason}，已平仓"
                    else:
                        return f"🎯 {reason}，但平仓失败: {result}"
                
                # 检查是否满足加码条件
                if self.pyramid_enabled:
                    can_pyramid, reason = self.check_pyramid_conditions(current_price)
                    if can_pyramid:
                        return self.execute_pyramid(current_price)
                
                # 有持仓但不需要操作
                return f"观察市场中，当前持仓: {self.position}，入场价: {self.entry_price}，当前价: {current_price}"
            
            # 无持仓时，检查开仓信号
            # 1. 日线级别趋势检测
            trend_down = self.detect_trend_direction()
            
            # 2. 4小时级别震荡结构检测
            consolidation = self.detect_consolidation()
            
            # 3. 1小时级别做空信号
            entry_signal = self.detect_entry_signal()
            
            # 如果三重信号都满足，开空仓
            if trend_down and consolidation and entry_signal:
                # 计算动态仓位大小
                position_size = self.calculate_dynamic_position()
                
                # 开空仓
                result = self.okx.open_short_position(position_size)
                
                if result and 'data' in result:
                    self._update_position_info()
                    self.entry_time = datetime.now()
                    self.position_size = position_size
                    self.current_pyramids = 0
                    self.last_pyramid_price = current_price
                    
                    return f"🔴 三重信号验证成功，开空仓，价格: {current_price}, 仓位: {position_size}"
                else:
                    return f"❌ 开空仓失败: {result}"
            else:
                signals = []
                if trend_down:
                    signals.append("趋势向下✓")
                else:
                    signals.append("趋势向下✗")
                    
                if consolidation:
                    signals.append("震荡结构✓")
                else:
                    signals.append("震荡结构✗")
                    
                if entry_signal:
                    signals.append("入场信号✓")
                else:
                    signals.append("入场信号✗")
                
                return f"观察市场中，信号状态: {', '.join(signals)}"
            
        except Exception as e:
            logger.error(f"运行三重信号策略出错: {e}", exc_info=True)
            return f"运行策略出错: {str(e)}"
    
    def run_trend_following_strategy(self):
        """运行趋势跟踪策略"""
        try:
            # 实现趋势跟踪策略逻辑
            return "趋势跟踪策略尚未实现"
        except Exception as e:
            logger.error(f"运行趋势跟踪策略出错: {e}")
            return f"运行策略出错: {str(e)}"
    
    def run_volatility_breakout_strategy(self):
        """运行波动率突破策略"""
        try:
            # 实现波动率突破策略逻辑
            return "波动率突破策略尚未实现"
        except Exception as e:
            logger.error(f"运行波动率突破策略出错: {e}")
            return f"运行策略出错: {str(e)}"
    
    def run_mean_reversion_strategy(self):
        """运行均值回归策略"""
        try:
            # 实现均值回归策略逻辑
            return "均值回归策略尚未实现"
        except Exception as e:
            logger.error(f"运行均值回归策略出错: {e}")
            return f"运行策略出错: {str(e)}"
    
    def run_original_strategy(self):
        """运行原始震荡下跌策略"""
        try:
            # 获取K线数据
            df = self.okx.get_kline_data(bar='15m', limit=100)
            if df is None:
                logger.error("无法获取K线数据，策略未执行")
                return "无法获取K线数据，策略未执行"
            
            # 计算指标
            df = self.calculate_indicators(df)
            
            # 当前持仓检查
            self._update_position_info()
            
            # 获取当前价格
            current_price = self.okx.get_current_price()
            if current_price is None:
                return "无法获取当前价格"
            
            # 如果有空仓，检查是否应该平仓
            if self.position == "short":
                last_row = df.iloc[-1]
                close_signal = last_row['rsi'] < 40 or last_row['close'] <= last_row['bb_lower']
                
                # 止盈止损检查
                if self.entry_price > 0:
                    profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
                    
                    if profit_percentage <= -config.STOP_LOSS_PERCENT:
                        logger.info(f"止损触发，亏损: {profit_percentage:.2f}%")
                        close_signal = True
                    elif profit_percentage >= config.TAKE_PROFIT_PERCENT:
                        logger.info(f"止盈触发，盈利: {profit_percentage:.2f}%")
                        close_signal = True
                
                if close_signal:
                    # 平空仓
                    result = self.okx.close_short_position()
                    
                    if result and 'data' in result:
                        self._update_position_info()
                        return f"平空仓成功，价格: {current_price}"
                    else:
                        return f"平空仓失败: {result}"
                        
                return f"持有空仓中，入场价: {self.entry_price}，当前价: {current_price}"
            
            # 如果没有持仓，检查是否应该开空仓
            if not self.position:
                # 检查开空条件
                last_row = df.iloc[-1]
                prev_row = df.iloc[-2]
                
                # 条件1: RSI回落，超买区域
                rsi_condition = last_row['rsi'] < prev_row['rsi'] and last_row['rsi'] > 60
                
                # 条件2: 快线下穿慢线
                ma_cross_condition = (prev_row['ema21'] > prev_row['ema50'] and 
                                     last_row['ema21'] < last_row['ema50'])
                
                # 条件3: 价格触及上轨
                bb_condition = last_row['close'] >= last_row['bb_upper']
                
                # 检查下降趋势 (连续3根K线下跌)
                downtrend = all(df['close'].iloc[-4:-1].diff().dropna() < 0)
                
                if (rsi_condition or ma_cross_condition or bb_condition) and downtrend:
                    # 开空仓
                    result = self.okx.open_short_position(config.POSITION_SIZE)
                    
                    if result and 'data' in result:
                        self._update_position_info()
                        return f"开空仓成功，价格: {current_price}"
                    else:
                        return f"开空仓失败: {result}"
            
            return "观察市场中"
            
        except Exception as e:
            logger.error(f"运行原始策略出错: {e}")
            return f"运行策略出错: {str(e)}"
    
    async def run_strategy(self):
        """运行当前选择的策略"""
        self.running = True
        while self.running:
            try:
                # 根据当前策略选择运行相应的策略方法
                if self.current_strategy == "triple_signal":
                    result = await self.run_triple_signal_strategy()
                elif self.current_strategy == "volatility_breakout":
                    result = await self.run_volatility_breakout_strategy()
                elif self.current_strategy == "trend_following":
                    result = await self.run_trend_following_strategy()
                elif self.current_strategy == "mean_reversion":
                    result = await self.run_mean_reversion_strategy()
                elif self.current_strategy == "original":
                    result = await self.run_original_strategy()
                else:
                    result = f"未知策略: {self.current_strategy}"
                
                # 如果有结果，返回它
                if result:
                    return result
                    
                # 等待一分钟再次检查
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"策略运行出错: {e}")
                await asyncio.sleep(5)  # 出错后等待5秒再重试

            return "策略已停止运行"
    
    def set_strategy(self, strategy_id):
        """设置当前使用的策略"""
        if strategy_id not in self.available_strategies:
            return f"❌ 未知的策略ID: {strategy_id}\n使用 /list_strategies 查看可用策略"
        
        self.current_strategy = strategy_id
        logger.info(f"切换到策略: {strategy_id} - {self.available_strategies[strategy_id]}")
        return f"✅ 已切换到策略: {strategy_id} - {self.available_strategies[strategy_id]}"
    
    def toggle_pyramid(self, enabled=None):
        """开启或关闭金字塔加码"""
        if enabled is None:
            # 如果未指定，则切换状态
            self.pyramid_enabled = not self.pyramid_enabled
        else:
            # 否则设置为指定状态
            self.pyramid_enabled = enabled
        
        status = "启用" if self.pyramid_enabled else "禁用"
        logger.info(f"金字塔加码已{status}")
        return f"✅ 金字塔加码已{status}"
    
    def set_max_pyramids(self, count):
        """设置最大加码次数"""
        try:
            count = int(count)
            if count < 1:
                return "❌ 最大加码次数必须大于0"
            
            self.max_pyramids = count
            logger.info(f"最大加码次数设置为: {count}")
            return f"✅ 最大加码次数设置为: {count}"
        except ValueError:
            return "❌ 无效的数字格式"
    
    def set_stop_loss(self, percentage):
        """设置止损百分比"""
        try:
            percentage = float(percentage)
            if percentage <= 0:
                return "止损百分比必须大于0"
            
            self.stop_loss_percentage = percentage
            return f"止损设置为 {percentage}%"
        except ValueError:
            return "无效的百分比数值"
    
    def set_take_profit(self, percentage):
        """设置止盈百分比"""
        try:
            percentage = float(percentage)
            if percentage <= 0:
                return "止盈百分比必须大于0"
            
            self.take_profit_percentage = percentage
            return f"止盈设置为 {percentage}%"
        except ValueError:
            return "无效的百分比数值"
    
    def _update_position_info(self):
        """更新当前持仓信息"""
        try:
            positions = self.okx.get_positions()
            
            self.position = None
            self.entry_price = 0
            
            if positions and 'data' in positions and positions['data']:
                for pos in positions['data']:
                    if float(pos['pos']) != 0:
                        # 正数为多仓，负数为空仓
                        pos_size = float(pos['pos'])
                        if pos_size > 0:
                            self.position = "long"
                        elif pos_size < 0:
                            self.position = "short"
                        
                        self.entry_price = float(pos['avgPx'])
                        self.position_size = abs(pos_size)
                        
                        # 如果新开仓，重置加码计数
                        if not hasattr(self, 'last_position') or self.last_position != self.position:
                            self.current_pyramids = 0
                            self.last_pyramid_price = self.entry_price
                            self.entry_time = datetime.now()
                        
                        break
            
            self.last_position = self.position
            return True
        except Exception as e:
            logger.error(f"更新仓位信息失败: {e}")
            return False
    
    def _update_price_history(self, current_price):
        """更新价格历史，用于计算波动率"""
        self.volatility_history.append(current_price)
        # 保持固定长度的历史数据
        if len(self.volatility_history) > self.volatility_window:
            self.volatility_history.pop(0)
    
    def _calculate_volatility(self):
        """计算价格波动率"""
        if len(self.volatility_history) < 5:  # 至少需要5个数据点
            return 0
        
        # 计算百分比变化
        changes = []
        for i in range(1, len(self.volatility_history)):
            prev = self.volatility_history[i-1]
            curr = self.volatility_history[i]
            pct_change = abs((curr - prev) / prev * 100)
            changes.append(pct_change)
        
        # 计算平均波动率
        avg_volatility = sum(changes) / len(changes)
        return avg_volatility
    
    def get_strategy_status(self):
        """获取当前策略状态信息"""
        status = {
            "当前策略": f"{self.current_strategy} - {self.available_strategies.get(self.current_strategy)}",
            "持仓状态": self.position if self.position else "无持仓",
            "入场价格": f"{self.entry_price:.2f}" if self.entry_price > 0 else "N/A",
            "持仓大小": f"{self.position_size}" if self.position_size > 0 else "N/A",
            "金字塔加码": "启用" if self.pyramid_enabled else "禁用",
            "已加码次数": f"{self.current_pyramids}/{self.max_pyramids}",
            "止损设置": f"{self.stop_loss_percentage}%",
            "止盈设置": f"{self.take_profit_percentage}%"
        }
        
        if self.entry_time:
            status["持仓时间"] = str(datetime.now() - self.entry_time).split('.')[0]  # 移除微秒
            
        return status

    def get_strategy_info(self):
        """获取当前策略信息"""
        return {
            "name": self.available_strategies[self.current_strategy],
            "id": self.current_strategy,
            "params": self.params[self.current_strategy]
        }

    def stop(self):
        """停止策略"""
        self.running = False
        logger.info("策略已停止")

    # 在这里实现各个具体的策略方法...
    async def run_triple_signal_strategy(self):
        """运行三重信号验证策略"""
        try:
            # 策略逻辑...
            return "三重信号验证策略执行结果"
        except Exception as e:
            logger.error(f"三重信号验证策略执行出错: {e}")
            return None

    async def run_volatility_breakout_strategy(self):
        """运行波动率突破策略"""
        try:
            # 策略逻辑...
            return "波动率突破策略执行结果"
        except Exception as e:
            logger.error(f"波动率突破策略执行出错: {e}")
            return None

    async def run_trend_following_strategy(self):
        """运行趋势跟踪策略"""
        try:
            # 策略逻辑...
            return "趋势跟踪策略执行结果"
        except Exception as e:
            logger.error(f"趋势跟踪策略执行出错: {e}")
            return None

    async def run_mean_reversion_strategy(self):
        """运行均值回归策略"""
        try:
            # 策略逻辑...
            return "均值回归策略执行结果"
        except Exception as e:
            logger.error(f"均值回归策略执行出错: {e}")
            return None

    async def run_original_strategy(self):
        """运行原始震荡下跌策略"""
        try:
            # 原有的策略逻辑...
            return "原始策略执行结果"
        except Exception as e:
            logger.error(f"原始策略执行出错: {e}")
            return None 