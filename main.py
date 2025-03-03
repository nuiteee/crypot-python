import asyncio
import time
import schedule
from loguru import logger
import config
from okx_handler import OkxHandler
from strategy import TradingStrategy
from telegram_bot import TelegramBot
import traceback
import sys
import threading
import argparse
import urllib3
import os
from advanced_strategy import AdvancedTradingStrategy
import signal
from dotenv import load_dotenv

# 抑制SSL验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置日志
logger.add("trading_bot.log", rotation="10 MB", level="INFO")

# 在setuplogger之后添加
logger.info(f"启动机器人，环境配置：")
logger.info(f"Telegram Bot Token: {config.TELEGRAM_BOT_TOKEN[:5]}...{config.TELEGRAM_BOT_TOKEN[-5:] if config.TELEGRAM_BOT_TOKEN else None}")
logger.info(f"Telegram Chat ID: {config.TELEGRAM_CHAT_ID}")
logger.info(f"代理设置: {config.PROXY}")
logger.info(f"代理URL: {config.PROXY_URL}")

def signal_handler(sig, frame):
    """处理退出信号"""
    logger.info("接收到退出信号，正在关闭程序...")
    sys.exit(0)

async def run_strategy(strategy, telegram_bot):
    """运行交易策略"""
    while True:
        try:
            # 执行策略逻辑
            result = strategy.run_strategy()
            if result:
                await telegram_bot.send_message(text=result)
        except Exception as e:
            logger.error(f"策略执行错误: {e}")
        await asyncio.sleep(config.CHECK_INTERVAL)

async def send_daily_report(telegram_bot, strategy):
    """发送每日报告"""
    try:
        # 获取账户余额
        balance = strategy.okx.get_account_balance()
        balance_text = "获取余额失败"
        if balance and 'data' in balance and balance['data']:
            usdt_balance = None
            for item in balance['data'][0]['details']:
                if item['ccy'] == 'USDT':
                    usdt_balance = item
                    break
            
            if usdt_balance:
                avail = float(usdt_balance.get('availEq', usdt_balance.get('availBal', '0')))
                balance_text = f"USDT余额: {avail:.2f}"
        
        # 获取持仓信息
        positions = strategy.okx.get_positions()
        position_text = "无持仓"
        if positions and 'data' in positions and positions['data']:
            position_text = "当前持仓:\n"
            for pos in positions['data']:
                if float(pos['pos']) != 0:
                    side = pos['posSide']
                    size = abs(float(pos['pos']))
                    avg_price = float(pos['avgPx'])
                    unrealized_pnl = float(pos['upl'])
                    position_text += f"- {side}: {size} @ {avg_price:.2f}, 浮动盈亏: {unrealized_pnl:.2f} USDT\n"
        
        # 获取当前价格
        current_price = strategy.okx.get_current_price()
        price_text = f"BTC当前价格: {current_price}"
        
        # 发送每日报告
        message = (
            f"📊 每日账户报告 📊\n\n"
            f"{balance_text}\n\n"
            f"{position_text}\n\n"
            f"{price_text}\n\n"
            f"策略: BTC震荡下跌策略, {config.LEVERAGE}倍杠杆"
        )
        
        await telegram_bot.send_message(message)
    except Exception as e:
        error_msg = f"发送每日报告出错: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await telegram_bot.send_message(f"❌ 每日报告生成错误: {str(e)}")

async def scheduled_task(telegram_bot, strategy):
    """定时任务"""
    try:
        while True:
            await run_strategy(strategy, telegram_bot)
            await asyncio.sleep(config.CHECK_INTERVAL)
    except Exception as e:
        logger.error(f"定时任务出错: {e}")
        await telegram_bot.send_message(text=f"❌ 定时任务错误: {str(e)}")

# 修改运行Telegram机器人的函数
def run_telegram_bot(bot):
    """在单独线程中运行Telegram机器人"""
    try:
        bot.run()
    except Exception as e:
        logger.error(f"Telegram机器人运行出错: {e}")

def setup_signal_handlers():
    """设置信号处理器以优雅退出"""
    # 注册SIGINT信号处理器（Ctrl+C）
    signal.signal(signal.SIGINT, signal_handler)
    
    # 在Windows上，SIGTERM可能不可用
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except AttributeError:
        pass
        
    logger.info("信号处理器已设置")

def load_config():
    """从.env文件加载配置"""
    try:
        # 加载.env文件
        load_dotenv()
        
        # 从环境变量获取配置
        return {
            'telegram_token': os.getenv('TELEGRAM_BOT_TOKEN'),
            'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID'),
            'proxy': os.getenv('PROXY'),
            'proxy_url': os.getenv('PROXY_URL'),
            'okx_api_key': os.getenv('OKX_API_KEY'),
            'okx_secret_key': os.getenv('OKX_API_SECRET_KEY'),
            'okx_passphrase': os.getenv('OKX_PASSPHRASE'),
            'okx_flag': os.getenv('OKX_FLAG', '0'),  # 默认使用测试网
            'symbol': os.getenv('SYMBOL', 'BTC-USDT-SWAP'),  # 默认交易对
            'leverage': int(os.getenv('LEVERAGE', '10')),  # 默认10倍杠杆
            'check_interval': int(os.getenv('CHECK_INTERVAL', '60')),  # 默认60秒检查间隔
            'authorized_users': [int(os.getenv('TELEGRAM_CHAT_ID'))]  # 默认只授权配置的chat_id
        }
    except Exception as e:
        logger.error(f"加载.env配置失败: {e}")
        raise

async def main():
    """主函数"""
    try:
        # 初始化OKX API处理器
        okx_handler = OkxHandler()
        
        # 使用高级策略类
        strategy = AdvancedTradingStrategy(okx_handler)
        
        # 使用token初始化Telegram机器人
        telegram_bot = TelegramBot(
            token=os.getenv('TELEGRAM_BOT_TOKEN'),
            strategy=strategy  # 传入高级策略实例
        )
        
        # 等待机器人初始化
        await telegram_bot._init_bot()
        
        # 创建任务
        strategy_task = asyncio.create_task(strategy.run_strategy())
        telegram_task = asyncio.create_task(telegram_bot.run())
        
        # 等待任务完成
        await asyncio.gather(strategy_task, telegram_task)
            
    except asyncio.CancelledError:
        logger.info("任务被取消")
    except Exception as e:
        logger.error(f"主程序运行出错: {e}")
    finally:
        if 'telegram_bot' in locals():
            await telegram_bot.shutdown()

if __name__ == "__main__":
    try:
        # 设置信号处理
        setup_signal_handlers()
        
        # 获取或创建事件循环
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 运行主函数
        loop.run_until_complete(main())
        
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
    finally:
        try:
            # 清理事件循环中的所有任务
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            # 等待所有任务完成
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            # 关闭事件循环
            loop.close()
        except Exception as e:
            logger.error(f"清理事件循环时出错: {e}")