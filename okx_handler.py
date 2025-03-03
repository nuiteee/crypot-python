import sys
import os
import config
import time
import pandas as pd
import numpy as np
from loguru import logger
import requests
import ssl
import random
import ccxt
import datetime

# 添加目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(os.path.join(parent_dir, 'python-okx'))

# 简化导入逻辑
try:
    # 直接导入
    from okx.Account import AccountAPI
    from okx.Trade import TradeAPI
    from okx.PublicData import PublicAPI
    from okx.MarketData import MarketAPI
    
    # 设置全局HTTP请求默认超时
    import httpx
    httpx.Timeout(30.0)  # 增加默认超时到30秒
    
    logger.info("成功导入OKX模块")
except ImportError as e:
    logger.error(f"导入错误: {e}")
    
    # 检查目录结构
    okx_dir = os.path.join(parent_dir, 'python-okx', 'okx')
    if os.path.exists(okx_dir):
        logger.info(f"OKX目录内容: {os.listdir(okx_dir)}")
    
    raise

# 创建代理URL处理函数
def format_proxy_url(proxy_config):
    """格式化代理URL，确保格式正确"""
    if not proxy_config:
        return None
        
    # 如果代理配置不包含协议，添加http://
    if proxy_config and not proxy_config.startswith(('http://', 'https://', 'socks://')):
        return f"http://{proxy_config}"
    
    return proxy_config

# OkxHandler类定义
class OkxHandler:
    def __init__(self):
        """初始化OKX API处理器"""
        try:
            logger.info("正在初始化OKX API处理器...")
            
            # 添加 symbol 属性
            self.symbol = config.SYMBOL
            
            # 初始化 CCXT exchange
            exchange_config = {
                'apiKey': config.OKX_API_KEY,
                'secret': config.OKX_API_SECRET_KEY,
                'password': config.OKX_PASSPHRASE,
                'enableRateLimit': True,
                'timeout': 30000,  # 30秒超时
                'options': {
                    'defaultType': 'swap',  # 设置为永续合约模式
                    'adjustForTimeDifference': True
                }
            }
            
            # 设置代理
            if config.PROXY_URL:
                proxy = config.PROXY_URL
                if not proxy.startswith(('http://', 'https://', 'socks5://')):
                    proxy = f"http://{proxy}"
                
                exchange_config.update({
                    'proxies': {
                        'http': proxy,
                        'https': proxy
                    }
                })
            
            self.exchange = ccxt.okx(exchange_config)
            
            # 设置测试网络
            if config.OKX_FLAG == '0':
                self.exchange.set_sandbox_mode(True)
            
            # 初始化时不加载市场数据
            self.markets_loaded = False
            
            logger.info("OKX API处理器初始化成功")
            
        except Exception as e:
            logger.error(f"初始化OKX API处理器失败: {e}")
            raise

    def _ensure_markets_loaded(self):
        """确保市场数据已加载"""
        try:
            if not self.exchange.markets:
                self.exchange.load_markets()
        except Exception as e:
            logger.error(f"加载市场数据失败: {e}")
            return False
        return True

    def get_current_price(self):
        """获取当前价格"""
        try:
            if not self._ensure_markets_loaded():
                return None
            
            ticker = self.exchange.fetch_ticker(self.symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"获取价格时发生错误: {e}")
            return None

    def get_account_balance(self):
        """获取账户余额"""
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"获取账户余额时发生错误: {e}")
            return None

    def get_positions(self):
        """获取持仓信息"""
        try:
            if not self._ensure_markets_loaded():
                return None
            
            result = self.exchange.fetch_positions([self.symbol])
            if result:
                return {'data': result}
            return None
        except Exception as e:
            logger.error(f"获取持仓信息时发生错误: {e}")
            return None

    def get_trade_history(self, since=None, limit=100):
        """获取交易历史"""
        try:
            trades = self.exchange.fetch_my_trades(symbol=self.symbol, since=since, limit=limit)
            return trades
        except Exception as e:
            logger.error(f"获取交易历史时发生错误: {e}")
            return None

    def get_kline_data(self, timeframe="1h", limit=100):
        """获取K线数据"""
        try:
            if not self._ensure_markets_loaded():
                return None
            
            # 标准化时间框架格式
            standard_timeframe = self._normalize_timeframe(timeframe)
            logger.info(f"获取K线数据，时间框架: {standard_timeframe}, 数量: {limit}")
            
            # 使用 CCXT 获取K线数据
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe=standard_timeframe.lower(),
                limit=limit
            )
            
            # 转换为 DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.sort_values('timestamp')
            df.reset_index(drop=True, inplace=True)
            
            logger.info(f"成功获取 {len(df)} 条K线数据")
            return df
            
        except Exception as e:
            logger.error(f"获取K线数据异常: {e}")
            return None

    def _create_dummy_kline_data(self, timeframe, limit):
        """创建模拟K线数据用于测试"""
        logger.warning(f"创建模拟K线数据 {timeframe}, {limit}条")
        
        # 确定时间间隔
        if timeframe in ['1H', '1h', '60m']:
            freq = '1H'
        elif timeframe in ['4H', '4h', '240m']:
            freq = '4H'
        elif timeframe in ['1D', '1d']:
            freq = '1D'
        else:
            freq = '1H'  # 默认1小时
        
        # 创建时间序列
        end_time = pd.Timestamp.now()
        time_index = pd.date_range(end=end_time, periods=limit, freq=freq)
        
        # 创建模拟价格数据
        current_price = 85000  # 假设当前价格
        price_range = 500  # 价格波动范围
        
        # 创建DataFrame
        df = pd.DataFrame({
            'timestamp': time_index,
            'open': [current_price + np.random.uniform(-price_range, price_range) for _ in range(limit)],
            'high': [current_price + np.random.uniform(0, price_range*1.5) for _ in range(limit)],
            'low': [current_price - np.random.uniform(0, price_range*1.5) for _ in range(limit)],
            'close': [current_price + np.random.uniform(-price_range, price_range) for _ in range(limit)],
            'volume': [np.random.uniform(10, 100) for _ in range(limit)],
        })
        
        # 确保high >= open, close, low且low <= open, close
        for i in range(len(df)):
            df.at[i, 'high'] = max(df.at[i, 'high'], df.at[i, 'open'], df.at[i, 'close'])
            df.at[i, 'low'] = min(df.at[i, 'low'], df.at[i, 'open'], df.at[i, 'close'])
        
        # 按时间升序排序
        df = df.sort_values('timestamp')
        
        logger.info(f"成功创建 {len(df)} 条模拟K线数据")
        return df

    def _normalize_timeframe(self, timeframe):
        """标准化时间框架格式"""
        # 转换为大写
        timeframe = timeframe.upper()
        
        # 确保格式正确
        if timeframe in ['1H', '4H', '1D']:
            return timeframe
        
        # 如果格式不正确，返回默认值
        logger.warning(f"不支持的时间框架 {timeframe}，使用默认值 1H")
        return '1H'

    def open_short_position(self):
        """开空仓"""
        try:
            return self.trade_api.place_order(
                instId=config.SYMBOL,
                tdMode='cross',
                side='sell',
                posSide='short',
                ordType='market',
                sz=str(config.POSITION_SIZE)
            )
        except Exception as e:
            logger.error(f"开空仓失败: {e}")
            return None

    def close_short_position(self):
        """平空仓"""
        try:
            # 先获取当前持仓
            positions = self.get_positions()
            if not positions or 'data' not in positions or not positions['data']:
                logger.warning("没有找到持仓，无法平仓")
                return {"code": "1", "msg": "没有找到持仓，无法平仓"}
            
            # 查找空仓持仓
            short_position = None
            for pos in positions['data']:
                if pos['posSide'] == 'short' and float(pos['pos']) < 0:
                    short_position = pos
                    break
            
            if not short_position:
                logger.warning("没有找到空仓持仓，无法平仓")
                return {"code": "1", "msg": "没有找到空仓持仓，无法平仓"}
            
            # 平仓
            return self.trade_api.place_order(
                instId=config.SYMBOL,
                tdMode='cross',
                side='buy',
                posSide='short',
                ordType='market',
                sz=abs(float(short_position['pos']))
            )
        except Exception as e:
            logger.error(f"平空仓失败: {e}")
            return None

    def _print_available_methods(self):
        """打印AccountAPI可用的方法列表，帮助调试"""
        methods = [method for method in dir(self.account_api) if not method.startswith('_')]
        logger.info(f"AccountAPI可用方法: {methods}")
        return methods

    def get_order_history(self, instType="SWAP", begin=None, end=None, limit="50"):
        """获取订单历史"""
        try:
            # 获取可用的方法列表
            methods = [method for method in dir(self.trade_api) if not method.startswith('_')]
            logger.info(f"TradeAPI可用方法: {methods}")
            
            # 尝试几个可能的方法名
            if hasattr(self.trade_api, 'orders_history'):
                return self.trade_api.orders_history(
                    instType=instType, begin=begin, end=end, limit=limit
                )
            elif hasattr(self.trade_api, 'get_orders_history'):
                return self.trade_api.get_orders_history(
                    instType=instType, begin=begin, end=end, limit=limit
                )
            elif hasattr(self.trade_api, 'order_history_archive'):
                return self.trade_api.order_history_archive(
                    instType=instType, begin=begin, end=end, limit=limit
                )
            else:
                logger.error("找不到获取订单历史的方法")
                return None
        except Exception as e:
            logger.error(f"获取订单历史失败: {e}")
            return None

    def _send_request_with_retry(self, method, path, params=None, data=None, **kwargs):
        """带重试机制的API请求，支持额外参数"""
        
        # 增加超时和重试次数
        max_retries = 5
        retry_count = 0
        base_timeout = 30  # 基础超时时间，秒
        success = False
        last_error = None
        
        # 确保headers和proxies存在
        headers = getattr(self, 'headers', {'Content-Type': 'application/json'})
        proxies = getattr(self, 'proxies', None)
        
        # 如果有额外的参数，合并到params或data中
        if kwargs:
            if method == 'GET' and params is None:
                params = {}
            elif method == 'POST' and data is None:
                data = {}
            
            if method == 'GET':
                params.update(kwargs)
            else:
                data.update(kwargs)
        
        # 使用指数退避和抖动策略
        while retry_count < max_retries and not success:
            try:
                # 计算超时时间，随着重试次数增加
                current_timeout = base_timeout * (1 + 0.5 * retry_count)
                
                # 进行HTTP/HTTPS请求
                if method == 'GET':
                    response = requests.get(
                        f"{self.base_url}{path}",
                        params=params,
                        headers=headers,
                        timeout=current_timeout,
                        proxies=proxies,
                        verify=False  # 禁用SSL验证
                    )
                elif method == 'POST':
                    response = requests.post(
                        f"{self.base_url}{path}",
                        json=data,
                        headers=headers,
                        timeout=current_timeout,
                        proxies=proxies,
                        verify=False  # 禁用SSL验证
                    )
                    
                # 检查响应状态码
                if response.status_code < 400:
                    success = True
                    if retry_count > 0:
                        logger.info(f"经过 {retry_count+1} 次尝试后成功执行API请求")
                    return response.json()
                else:
                    error_msg = f"API请求失败，状态码: {response.status_code}, 响应: {response.text}"
                    logger.error(error_msg)
                    last_error = Exception(error_msg)
                    
            except (requests.exceptions.SSLError, ssl.SSLError) as e:
                # 针对SSL错误特殊处理
                retry_count += 1
                wait_time = min(30, 2 ** retry_count + random.uniform(0, 1))  # 最多等待30秒
                logger.warning(f"SSL错误，第 {retry_count} 次重试: {e}，等待 {wait_time:.2f} 秒")
                time.sleep(wait_time)
                last_error = e
                continue
                
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                # 针对超时和连接错误
                retry_count += 1
                wait_time = min(30, 2 ** retry_count + random.uniform(0, 1))
                logger.warning(f"第 {retry_count} 次API请求失败: {e}，等待 {wait_time:.2f} 秒")
                time.sleep(wait_time)
                last_error = e
                continue
                
            except Exception as e:
                # 其他错误
                retry_count += 1
                wait_time = min(30, 2 ** retry_count + random.uniform(0, 1))
                logger.warning(f"第 {retry_count} 次API请求失败: {e}，等待 {wait_time:.2f} 秒")
                time.sleep(wait_time)
                last_error = e
                continue
        
        # 所有重试都失败
        if not success and last_error:
            logger.error(f"经过 {max_retries} 次重试后仍然失败: {last_error}")
            raise last_error
        
        # 不应该走到这里，但为安全起见
        return None

    def _select_best_api_endpoint(self):
        """测试并选择响应最快的API端点"""
        best_url = self.backup_urls[0]  # 使用第一个URL作为默认值
        best_latency = float('inf')
        
        # 确保代理设置存在
        proxies = getattr(self, 'proxies', None)
        
        for url in self.backup_urls:
            try:
                start_time = time.time()
                response = requests.get(
                    f"{url}/api/v5/public/time", 
                    proxies=proxies,
                    timeout=5,
                    verify=False
                )
                latency = time.time() - start_time
                
                if response.status_code == 200 and latency < best_latency:
                    best_url = url
                    best_latency = latency
                    logger.info(f"测试API端点 {url}: 延迟 {latency:.3f}秒")
                    
            except Exception as e:
                logger.warning(f"测试API端点 {url} 失败: {e}")
        
        return best_url

    def _call_api_with_retry(self, api_func, *args, **kwargs):
        """改进的API调用重试机制，专注于SSL错误处理"""
        max_retries = 5
        retry_count = 0
        last_error = None
        
        # 移除不兼容参数
        api_kwargs = kwargs.copy()
        if 'verify' in api_kwargs:
            del api_kwargs['verify']
        
        while retry_count < max_retries:
            try:
                # 调用API函数
                result = api_func(*args, **api_kwargs)
                
                # 检查是否成功
                if isinstance(result, dict) and result.get('code') == '0':
                    return result
                    
                # 如果不成功，记录错误并重试
                error_msg = f"API调用返回错误: {result}"
                logger.warning(error_msg)
                last_error = Exception(error_msg)
                
            except ssl.SSLError as e:
                # SSL错误特殊处理
                logger.warning(f"SSL错误，第{retry_count+1}次重试: {e}")
                last_error = e
                time.sleep(min(30, 2 ** retry_count))  # 指数退避但最大30秒
                retry_count += 1
                continue
                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                # 连接超时错误特殊处理
                logger.warning(f"连接错误，第{retry_count+1}次重试: {e}")
                last_error = e
                time.sleep(min(30, 2 ** retry_count))
                retry_count += 1
                continue
                
            except Exception as e:
                logger.warning(f"API调用异常: {e}")
                last_error = e
            
            # 增加重试次数
            retry_count += 1
            
            # 在重试之前等待
            if retry_count < max_retries:
                time.sleep(min(30, 2 ** retry_count))
        
        # 如果所有重试都失败，抛出最后一个错误
        raise last_error
    
    def verify_api_credentials(self):
        """验证API密钥的有效性"""
        try:
            logger.info("验证API密钥...")
            
            # 尝试获取账户配置，这是一个轻量级API调用，可用于验证密钥
            result = self.account_api.get_account_config()
            
            # 打印返回结果
            logger.info(f"API密钥验证结果: {result}")
            
            if result.get('code') == '0':
                logger.info("API密钥验证成功")
                return True
            else:
                error_msg = f"API密钥验证失败: {result}"
                logger.error(error_msg)
                return False
        except Exception as e:
            logger.error(f"验证API密钥时发生异常: {e}", exc_info=True)
            return False