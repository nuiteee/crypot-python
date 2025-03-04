# Crypto AI Trading Bot 🤖

一个基于 Python 的加密货币自动交易机器人，支持多种交易策略，通过 Telegram 进行交互控制。

## 功能特点 ✨

- 🔄 支持多种交易策略：
  - 三重信号验证策略
  - 波动率突破策略
  - 趋势跟踪策略
  - 均值回归策略
  - 原始震荡下跌策略

- 📱 Telegram 机器人控制：
  - 实时查看交易状态
  - 切换不同交易策略
  - 查看账户余额
  - 查看交易历史
  - 设置交易参数

- 💹 交易功能：
  - 自动开平仓
  - 动态止盈止损
  - 仓位管理
  - 风险控制

## 环境要求 🔧

- Python 3.8+
- OKX API 账户
- Telegram Bot Token

## 安装步骤 📥

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/crypto-ai-trading-bot.git
cd crypto-ai-trading-bot
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
   - 复制 `.env.example` 为 `.env`
   - 填写以下配置：
     - OKX API 密钥
     - Telegram Bot Token
     - 代理设置（如需）

## 使用方法 🚀

1. 启动机器人：
```bash
python main.py
```

2. 在 Telegram 中与机器人交互：
   - `/start` - 显示主菜单
   - `/status` - 查看当前状态
   - `/balance` - 查看账户余额
   - 选择交易策略
   - 设置交易参数

## 配置说明 ⚙️

### 基础配置

- `SYMBOL`: 交易对（默认：BTC/USDT）
- `LEVERAGE`: 杠杆倍数（1-75倍）
- `POSITION_SIZE`: 开仓数量
- `MAX_POSITIONS`: 最大持仓数

### 策略参数

- `RSI_PERIOD`: RSI周期
- `MA_FAST`: 快速均线周期
- `MA_SLOW`: 慢速均线周期
- `STOP_LOSS_PERCENT`: 止损百分比
- `TAKE_PROFIT_PERCENT`: 止盈百分比

## 安全提示 ⚠️

- 请勿在生产环境中使用默认参数
- 建议先在模拟盘测试
- 确保 API 密钥的安全性
- 定期检查日志和交易记录

## 贡献指南 🤝

欢迎提交 Pull Request 或创建 Issue！

## 免责声明 📢

本项目仅供学习和研究使用，作者不对使用本项目导致的任何损失负责。交易加密货币具有高风险，请谨慎使用。

## 许可证 📄

MIT License

## 联系方式 📧

- Telegram：[你的Telegram用户名]
- Email：[你的邮箱]

## 致谢 🙏

感谢以下开源项目：
- python-telegram-bot
- ccxt
- pandas
- numpy