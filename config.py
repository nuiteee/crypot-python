import os
from dotenv import load_dotenv
from loguru import logger

# 加载环境变量
load_dotenv()

# 代理设置
PROXY = os.environ.get('HTTP_PROXY')  # 代理设置
PROXY_URL = os.environ.get('PROXY_URL', PROXY)  # 如果PROXY_URL未设置，使用HTTP_PROXY

# 确保代理URL格式正确
if PROXY_URL and not PROXY_URL.startswith(('http://', 'https://', 'socks5://')):
    PROXY_URL = f"http://{PROXY_URL}"

# OKX API配置
OKX_API_KEY = os.environ.get('OKX_API_KEY')
OKX_API_SECRET_KEY = os.environ.get('OKX_API_SECRET_KEY')
OKX_PASSPHRASE = os.environ.get('OKX_PASSPHRASE')
OKX_FLAG = '1'  # 0: 模拟交易, 1: 实盘交易

# Telegram配置
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# 安全地转换TELEGRAM_CHAT_ID为整数
try:
    TELEGRAM_CHAT_ID_INT = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else 0
except ValueError:
    logger.warning(f"无效的TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}，使用默认值0")
    TELEGRAM_CHAT_ID_INT = 0

# 授权用户列表
AUTHORIZED_USERS = {
    TELEGRAM_CHAT_ID_INT,  # 从环境变量读取的ID
    5245966324,  # 添加额外的授权用户ID
}

# 移除可能的0值（如果TELEGRAM_CHAT_ID无效）
if 0 in AUTHORIZED_USERS:
    AUTHORIZED_USERS.remove(0)

# 交易参数
SYMBOL = 'BTC/USDT'  # BTC永续合约
LEVERAGE = 10  # 20倍杠杆
POSITION_SIZE = 0.01  # 开仓数量(BTC)
MAX_POSITIONS = 3  # 最大持仓数

# 策略参数
RSI_PERIOD = 14  # RSI周期
RSI_OVERBOUGHT = 60  # RSI超买阈值
RSI_OVERSOLD = 40  # RSI超卖阈值
MA_FAST = 9  # 快速均线周期
MA_SLOW = 21  # 慢速均线周期
STOP_LOSS_PERCENT = 3  # 止损百分比
TAKE_PROFIT_PERCENT = 6  # 止盈百分比

# 运行参数
CHECK_INTERVAL = 60  # 策略检查间隔（秒）

# 将原来的OKX_API_KEY等变量复制给新的变量名
API_KEY = OKX_API_KEY
API_SECRET_KEY = OKX_API_SECRET_KEY
PASSPHRASE = OKX_PASSPHRASE 