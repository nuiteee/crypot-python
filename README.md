项目名称：crypot bot


<img width="416" alt="image" src="https://github.com/user-attachments/assets/c348e223-ed78-4b0f-a1f0-f386bcec378f" />



项目简介

本项目是一个高级交易策略框架，整合了 OKX 交易所 API，并通过 Telegram 机器人进行消息通知。它能够处理市场数据、执行交易策略并发送交易提醒。

文件结构:

.
├── advanced_strategy.py       # 主要的高级交易策略实现
├── config.py                  # 配置文件，包含 API 密钥等信息
├── main.py                    # 入口文件，启动整个项目
├── okx_handler.py             # OKX 交易所 API 处理模块
├── send_message_sync.py       # 同步发送消息的工具
├── strategy.py                # 交易策略逻辑
├── telegram_bot.py            # Telegram 机器人，发送和接收消息
├── telegram_messages.log      # 记录 Telegram 相关日志
└── README.md                  # 说明文档

安装依赖

在使用本项目之前，请确保你已经安装了所有必要的依赖。你可以使用以下命令安装：
pip install -r requirements.txt
如果没有 requirements.txt，请手动安装相关依赖，例如：
pip install requests python-telegram-bot okx

配置

在 config.py 文件中设置你的 API 密钥和其他相关信息，例如：
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
TELEGRAM_TOKEN = "your_telegram_token"
CHAT_ID = "your_chat_id"

运行项目

你可以通过以下命令运行项目：
python main.py

主要功能

交易策略执行：

通过 strategy.py 处理交易信号

结合 okx_handler.py 与 OKX 交易所交互

消息通知：

通过 telegram_bot.py 发送交易提醒

记录在 telegram_messages.log

同步消息发送：

send_message_sync.py 允许同步发送 Telegram 消息

日志

日志存储在 telegram_messages.log，可用于调试和监控。

贡献

如果你希望贡献代码，请 fork 本项目并提交 Pull Request。

许可证

本项目遵循 MIT 许可证。






