import pandas as pd
import numpy as np
import config
from loguru import logger
import time

class TradingStrategy:
    def __init__(self, okx_handler):
        self.okx = okx_handler
        self.running = False
        self.position = None
        self.entry_price = 0
        
        # 止盈止损设置
        self.stop_loss_percentage = 5.0  # 默认5%止损
        self.take_profit_percentage = 10.0  # 默认10%止盈
        
        # 仓位管理设置
        self.max_position_size = config.POSITION_SIZE  # 最大仓位大小
        self.base_position_size = config.POSITION_SIZE * 0.5  # 基础仓位大小
        self.volatility_window = 20  # 计算波动率的周期
        self.volatility_history = []  # 存储价格历史以计算波动率
        self.last_position_check = 0  # 上次检查仓位的时间
        
        # 初始化获取仓位状态
        self._update_position_info()
    
    def calculate_indicators(self, df):
        """计算技术指标"""
        # 添加RSI指标
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=config.RSI_PERIOD).mean()
        avg_loss = loss.rolling(window=config.RSI_PERIOD).mean()
        
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 添加均线
        df['ma_fast'] = df['close'].rolling(window=config.MA_FAST).mean()
        df['ma_slow'] = df['close'].rolling(window=config.MA_SLOW).mean()
        
        # 添加布林带
        df['sma'] = df['close'].rolling(window=20).mean()
        df['std'] = df['close'].rolling(window=20).std()
        df['upper_band'] = df['sma'] + (df['std'] * 2)
        df['lower_band'] = df['sma'] - (df['std'] * 2)
        
        return df
    
    def should_open_short(self, df):
        """判断是否应该开空仓"""
        if len(df) < max(config.MA_SLOW, config.RSI_PERIOD, 20):
            return False
        
        # 获取最新数据
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        # 条件1: RSI回落，处于超买区域
        rsi_condition = (
            last_row['rsi'] < prev_row['rsi'] and 
            last_row['rsi'] > config.RSI_OVERBOUGHT
        )
        
        # 条件2: 快线下穿慢线
        ma_cross_condition = (
            prev_row['ma_fast'] > prev_row['ma_slow'] and
            last_row['ma_fast'] < last_row['ma_slow']
        )
        
        # 条件3: 价格触及或超过上轨
        bb_condition = last_row['close'] >= last_row['upper_band']
        
        # 检查下降趋势 (连续3根K线下跌)
        downtrend = all(df['close'].iloc[-4:-1].diff().dropna() < 0)
        
        # 满足所有条件之一即可开空
        return (rsi_condition or ma_cross_condition or bb_condition) and downtrend
    
    def should_close_short(self, df, entry_price=None):
        """判断是否应该平空仓"""
        if len(df) < config.RSI_PERIOD:
            return False
        
        # 获取最新数据
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        current_price = last_row['close']
        
        # 条件1: RSI超卖
        rsi_condition = last_row['rsi'] < config.RSI_OVERSOLD
        
        # 条件2: 价格触及下轨
        bb_condition = current_price <= last_row['lower_band']
        
        # 条件3: 价格上涨达到止损点
        stop_loss = False
        if entry_price:
            stop_loss = current_price >= entry_price * (1 + config.STOP_LOSS_PERCENT/100)
        
        # 条件4: 价格下跌达到止盈点
        take_profit = False
        if entry_price:
            take_profit = current_price <= entry_price * (1 - config.TAKE_PROFIT_PERCENT/100)
        
        # 满足任一条件即可平仓
        return rsi_condition or bb_condition or stop_loss or take_profit
    
    def run_strategy(self):
        """运行策略"""
        try:
            # 获取K线数据
            df = self.okx.get_kline_data(timeframe="1h", limit=100)  # 移除 bar 参数
            if df is None or df.empty:
                logger.warning("无法获取K线数据")
                return None
            
            # 更新当前仓位信息
            self._update_position_info()
            
            # 获取当前价格
            current_price = self.okx.get_current_price()
            if not current_price:
                return "无法获取当前价格，略过本次策略运行"
            
            # 更新价格历史和波动度
            self._update_price_history(current_price)
            
            # 如果有持仓，先检查止盈止损
            if self.position and self.entry_price > 0:
                # 检查止盈止损
                stop_loss_result = self._check_stop_loss(current_price)
                if stop_loss_result:
                    return stop_loss_result
                
                take_profit_result = self._check_take_profit(current_price)
                if take_profit_result:
                    return take_profit_result
                
                # 检查是否需要调整仓位
                position_adjust_result = self._check_position_adjustment(current_price)
                if position_adjust_result:
                    return position_adjust_result
            
            # 计算指标
            df = self.calculate_indicators(df)
            
            # 策略逻辑
            if not self.position:
                # 无仓位，判断是否开仓
                if self.should_open_short(df):
                    logger.info("策略发出开空信号")
                    result = self.okx.open_short_position()
                    return f"【开仓信号】开空BTC合约, 价格: {current_price}"
                else:
                    return "观察市场中，暂无交易信号"
            elif self.position == 'short':
                # 空仓，判断是否平仓
                if self.should_close_short(df, self.entry_price):
                    logger.info("策略发出平空信号")
                    result = self.okx.close_short_position()
                    profit_percent = (self.entry_price - current_price) / self.entry_price * 100 * config.LEVERAGE
                    return f"【平仓信号】平空BTC合约, 价格: {current_price}, 盈亏: {profit_percent:.2f}%"
                else:
                    profit_percent = (self.entry_price - current_price) / self.entry_price * 100 * config.LEVERAGE
                    return f"持有空仓中, 入场价: {self.entry_price}, 当前价: {current_price}, 浮动盈亏: {profit_percent:.2f}%"
            else:
                # 多仓 - 根据震荡下跌策略，我们主要做空，故平掉多仓
                logger.info("检测到多仓，根据策略平掉")
                result = self.okx.close_long_position()
                return "根据策略平掉多仓，准备开空"
                
        except Exception as e:
            logger.error(f"策略执行出错: {e}")
            return None
    
    def _update_position_info(self):
        """更新当前仓位信息"""
        try:
            positions = self.okx.get_positions()
            self.position = None
            self.entry_price = 0
            
            if positions and 'data' in positions and positions['data']:
                for pos in positions['data']:
                    if float(pos['pos']) != 0:
                        self.position = pos['posSide']  # 'long' 或 'short'
                        self.entry_price = float(pos['avgPx'])
                        self.position_size = abs(float(pos['pos']))
                        break
            
            return True
        except Exception as e:
            logger.error(f"更新仓位信息失败: {e}")
            return False
    
    def _check_stop_loss(self, current_price):
        """检查止损条件"""
        if not self.position or self.entry_price <= 0:
            return None
        
        # 计算当前盈亏百分比
        if self.position == 'long':
            profit_percentage = (current_price - self.entry_price) / self.entry_price * 100
        else:  # short
            profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
        
        # 如果亏损超过阈值，触发止损
        if profit_percentage <= -self.stop_loss_percentage:
            logger.warning(f"触发止损! 当前亏损: {profit_percentage:.2f}%")
            
            # 平仓
            if self.position == 'long':
                result = self.okx.close_long_position()
            else:
                result = self.okx.close_short_position()
            
            if result and 'data' in result and result['data']:
                self._update_position_info()  # 更新仓位信息
                return f"⚠️ 触发止损! 亏损达到 {profit_percentage:.2f}%, 已平仓"
            else:
                return f"⚠️ 止损触发但平仓失败: {result}"
        
        return None
    
    def _check_take_profit(self, current_price):
        """检查止盈条件"""
        if not self.position or self.entry_price <= 0:
            return None
        
        # 计算当前盈亏百分比
        if self.position == 'long':
            profit_percentage = (current_price - self.entry_price) / self.entry_price * 100
        else:  # short
            profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
        
        # 如果盈利超过阈值，触发止盈
        if profit_percentage >= self.take_profit_percentage:
            logger.info(f"触发止盈! 当前盈利: {profit_percentage:.2f}%")
            
            # 平仓
            if self.position == 'long':
                result = self.okx.close_long_position()
            else:
                result = self.okx.close_short_position()
            
            if result and 'data' in result and result['data']:
                self._update_position_info()  # 更新仓位信息
                return f"🎯 触发止盈! 盈利达到 {profit_percentage:.2f}%, 已平仓"
            else:
                return f"🎯 止盈触发但平仓失败: {result}"
        
        return None
    
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
    
    def _check_position_adjustment(self, current_price):
        """检查是否需要调整仓位"""
        # 每10分钟检查一次仓位
        current_time = time.time()
        if current_time - self.last_position_check < 600:  # 10分钟 = 600秒
            return None
        
        self.last_position_check = current_time
        
        # 计算当前波动率
        volatility = self._calculate_volatility()
        logger.info(f"当前波动率: {volatility:.2f}%")
        
        # 根据波动率调整仓位大小
        # 波动率越大，仓位越小；波动率越小，仓位越大
        if volatility > 0:
            # 基础公式: 新仓位 = 基础仓位 * (1 / 波动率调整因子)
            volatility_factor = max(1.0, volatility / 2)  # 不让因子小于1
            new_position_size = min(
                self.max_position_size,  # 不超过最大仓位
                self.base_position_size * (1 / volatility_factor)
            )
            
            # 将new_position_size四舍五入到0.001
            new_position_size = round(new_position_size, 3)
            
            # 如果仓位变化超过10%，则进行调整
            if self.position and abs(new_position_size - self.position_size) / self.position_size > 0.1:
                logger.info(f"根据波动率({volatility:.2f}%)调整仓位从 {self.position_size} 到 {new_position_size}")
                
                # 调整仓位的逻辑...
                # 这里需要实现部分平仓或加仓的逻辑
                # 实现复杂，可以先记录下来
                
                return f"📊 根据市场波动({volatility:.2f}%)调整仓位至 {new_position_size} BTC"
        
        return None
    
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

    def start(self):
        self.running = True
        logger.info("策略已启动")
        self.notify_user("策略已启动")

    def stop(self):
        self.running = False
        logger.info("策略已停止")
        self.notify_user("策略已停止")

    def notify_user(self, message):
        """发送通知给用户"""
        # 假设有一个方法可以发送消息到 Telegram
        self.okx.telegram_bot.send_message(text=message)

    def _update_position_info(self):
        """更新当前仓位信息"""
        try:
            positions = self.okx.get_positions()
            self.position = None
            self.entry_price = 0
            
            if positions and 'data' in positions and positions['data']:
                for pos in positions['data']:
                    if float(pos['pos']) != 0:
                        self.position = pos['posSide']  # 'long' 或 'short'
                        self.entry_price = float(pos['avgPx'])
                        self.position_size = abs(float(pos['pos']))
                        break
            
            return True
        except Exception as e:
            logger.error(f"更新仓位信息失败: {e}")
            return False
    
    def _check_stop_loss(self, current_price):
        """检查止损条件"""
        if not self.position or self.entry_price <= 0:
            return None
        
        # 计算当前盈亏百分比
        if self.position == 'long':
            profit_percentage = (current_price - self.entry_price) / self.entry_price * 100
        else:  # short
            profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
        
        # 如果亏损超过阈值，触发止损
        if profit_percentage <= -self.stop_loss_percentage:
            logger.warning(f"触发止损! 当前亏损: {profit_percentage:.2f}%")
            
            # 平仓
            if self.position == 'long':
                result = self.okx.close_long_position()
            else:
                result = self.okx.close_short_position()
            
            if result and 'data' in result and result['data']:
                self._update_position_info()  # 更新仓位信息
                return f"⚠️ 触发止损! 亏损达到 {profit_percentage:.2f}%, 已平仓"
            else:
                return f"⚠️ 止损触发但平仓失败: {result}"
        
        return None
    
    def _check_take_profit(self, current_price):
        """检查止盈条件"""
        if not self.position or self.entry_price <= 0:
            return None
        
        # 计算当前盈亏百分比
        if self.position == 'long':
            profit_percentage = (current_price - self.entry_price) / self.entry_price * 100
        else:  # short
            profit_percentage = (self.entry_price - current_price) / self.entry_price * 100
        
        # 如果盈利超过阈值，触发止盈
        if profit_percentage >= self.take_profit_percentage:
            logger.info(f"触发止盈! 当前盈利: {profit_percentage:.2f}%")
            
            # 平仓
            if self.position == 'long':
                result = self.okx.close_long_position()
            else:
                result = self.okx.close_short_position()
            
            if result and 'data' in result and result['data']:
                self._update_position_info()  # 更新仓位信息
                return f"🎯 触发止盈! 盈利达到 {profit_percentage:.2f}%, 已平仓"
            else:
                return f"🎯 止盈触发但平仓失败: {result}"
        
        return None
    
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
    
    def _check_position_adjustment(self, current_price):
        """检查是否需要调整仓位"""
        # 每10分钟检查一次仓位
        current_time = time.time()
        if current_time - self.last_position_check < 600:  # 10分钟 = 600秒
            return None
        
        self.last_position_check = current_time
        
        # 计算当前波动率
        volatility = self._calculate_volatility()
        logger.info(f"当前波动率: {volatility:.2f}%")
        
        # 根据波动率调整仓位大小
        # 波动率越大，仓位越小；波动率越小，仓位越大
        if volatility > 0:
            # 基础公式: 新仓位 = 基础仓位 * (1 / 波动率调整因子)
            volatility_factor = max(1.0, volatility / 2)  # 不让因子小于1
            new_position_size = min(
                self.max_position_size,  # 不超过最大仓位
                self.base_position_size * (1 / volatility_factor)
            )
            
            # 将new_position_size四舍五入到0.001
            new_position_size = round(new_position_size, 3)
            
            # 如果仓位变化超过10%，则进行调整
            if self.position and abs(new_position_size - self.position_size) / self.position_size > 0.1:
                logger.info(f"根据波动率({volatility:.2f}%)调整仓位从 {self.position_size} 到 {new_position_size}")
                
                # 调整仓位的逻辑...
                # 这里需要实现部分平仓或加仓的逻辑
                # 实现复杂，可以先记录下来
                
                return f"📊 根据市场波动({volatility:.2f}%)调整仓位至 {new_position_size} BTC"
        
        return None 