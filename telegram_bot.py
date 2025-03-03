from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import asyncio
import httpx
from loguru import logger
import config
import datetime
import matplotlib.pyplot as plt
import io
import backoff  # 如果没有安装，请先 pip install backoff
import time

class TelegramBot:
    def __init__(self, token: str, strategy=None):
        """初始化Telegram机器人"""
        self.token = token
        self.strategy = strategy
        self.application = None
        self.is_offline = False
        self.history_cache = {}
        self.page_size = 5
        self.max_retries = 3
        self.retry_delay = 2
        self._running = False
        self.last_retry_time = 0
        self.min_retry_interval = 60
        self.offline_messages = []
        self.authorized_users = self._load_authorized_users()

    def _register_handlers(self):
        """注册所有命令和回调处理器"""
        try:
            # 注册命令处理器
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("balance", self.balance_command))
            self.application.add_handler(CommandHandler("select_strategy", self.select_strategy_command))
            self.application.add_handler(CommandHandler("history", self.history_command))
            self.application.add_handler(CommandHandler("run", self.run_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            
            # 注册回调查询处理器
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            # 注册消息处理器
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            logger.info("命令处理器注册成功")
            
        except Exception as e:
            logger.error(f"注册命令处理器时出错: {e}")
            raise

    async def _init_bot(self):
        """异步初始化机器人"""
        try:
            # 设置代理
            proxy_url = config.PROXY_URL
            if proxy_url and not proxy_url.startswith(('http://', 'https://', 'socks5://')):
                proxy_url = f"http://{proxy_url}"
            
            # 初始化应用
            builder = (ApplicationBuilder()
                .token(self.token)
                .get_updates_proxy_url(proxy_url)
                .proxy_url(proxy_url)
                .connect_timeout(60.0)
                .read_timeout(60.0)
                .write_timeout(60.0)
                .connection_pool_size(8)
                .pool_timeout(60.0))
            
            # 创建应用实例
            self.application = builder.build()
            
            # 注册所有处理器
            self._register_handlers()
            
            self.is_offline = False
            logger.info("Telegram机器人初始化成功")
            
        except Exception as e:
            logger.error(f"初始化Telegram机器人失败: {e}")
            self.is_offline = True
            raise

    async def run(self):
        """运行Telegram机器人"""
        if self.is_offline or not self.application:
            logger.warning("Telegram机器人未正确初始化或处于离线模式")
            return

        max_retries = 4  # 最大重试次数
        retry_count = 0
        retry_delay = 2  # 重试间隔（秒）

        while retry_count < max_retries:
            try:
                logger.info("正在启动Telegram机器人...")
                self._running = True
                
                # 使用上下文管理器确保正确的启动和关闭
                async with self.application:
                    await self.application.initialize()
                    await self.application.start()
                    await self.application.updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True,
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60
                    )
                    
                    # 保持运行直到收到停止信号
                    while self._running:
                        try:
                            await asyncio.sleep(1)
                        except asyncio.CancelledError:
                            logger.info("收到取消信号，准备关闭...")
                            break
                    
                    # 如果正常退出循环，跳出重试
                    break
                    
            except httpx.ConnectError as e:
                retry_count += 1
                logger.warning(f"连接错误 (尝试 {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error("达到最大重试次数，设置为离线模式")
                    self.is_offline = True
                    break
                
            except Exception as e:
                logger.error(f"运行Telegram机器人时出错: {e}")
                self.is_offline = True
                break

        if self.is_offline:
            logger.warning("Telegram机器人已切换到离线模式")

    def _create_ssl_context(self):
        """创建SSL上下文"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/start命令"""
        if not self._check_authorized(update):
            return
        
        try:
            user_name = update.effective_user.first_name
            
            # 添加表情图标的欢迎消息
            message = (
                f"🚀 {user_name}，已接入Crypto Al 1.0量子交易系统 \n\n  "
                f"🤖 AI 量化核心已就绪 \n\n"
               f"选择核心作战单元⚛️ \n\n"
            )
            
            # 修改按钮布局，将查看持仓改为选择策略
            keyboard = [
                [InlineKeyboardButton("📊 查看状态", callback_data="status"),
                 InlineKeyboardButton("💰 查看余额", callback_data="balance")],
                [InlineKeyboardButton("🎯 选择策略", callback_data="select_strategy"),
                 InlineKeyboardButton("📜 交易历史", callback_data="history")],
                [InlineKeyboardButton("📊 生成图表", callback_data="chart"),
                 InlineKeyboardButton("▶️ 运行策略", callback_data="run")],
                [InlineKeyboardButton("⏹️ 停止策略", callback_data="stop"),
                 InlineKeyboardButton("⚙️ 高级设置", callback_data="help")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.message:
                await update.message.reply_text(text=message, reply_markup=reply_markup)
            else:
                await self.send_message(text=message, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"处理start命令时出错: {e}")
            await self.send_message(text=f"❌ 处理命令出错: {str(e)}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/help命令，改为高级设置"""
        if not self._check_authorized(update):
            return
        
        try:
            message = (
                "⚙️ *高级设置*\n\n"
                "请选择要设置的项目："
            )
            
            # 创建设置按钮
            keyboard = [
                [InlineKeyboardButton("🪙 选择交易币种", callback_data="select_coins"),
                 InlineKeyboardButton("⚔️ 设置杠杆倍数", callback_data="set_leverage")],
                [InlineKeyboardButton("📊 调整策略参数", callback_data="strategy_params"),
                 InlineKeyboardButton("⏱️ 设置交易间隔", callback_data="set_interval")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"显示高级设置时出错: {e}")
            await self.send_message(text=f"❌ 显示高级设置时出错: {str(e)}")

    async def select_coins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理选择交易币种"""
        try:
            # 获取市值前10的币种
            top_coins = [
                ('BTC', 'Bitcoin'),
                ('ETH', 'Ethereum'),
                ('SOL', 'Solana'),
                ('XRP', 'Ripple'),
                ('BNB', 'Binance Coin'),
                ('ADA', 'Cardano'),
                ('AVAX', 'Avalanche'),
                ('DOGE', 'Dogecoin'),
                ('DOT', 'Polkadot'),
                ('LINK', 'Chainlink')
            ]
            
            message = "🪙 *选择交易币种*\n\n选择要交易的币种（可多选）："
            
            # 创建币种选择按钮，每行两个
            keyboard = []
            for i in range(0, len(top_coins), 2):
                row = []
                for symbol, name in top_coins[i:i+2]:
                    # 检查是否已选择
                    is_selected = symbol in self.strategy.selected_coins
                    status = "✅" if is_selected else "⭕"
                    row.append(InlineKeyboardButton(
                        f"{status} {symbol}",
                        callback_data=f"coin_{symbol}"
                    ))
                keyboard.append(row)
            
            # 添加确认和返回按钮
            keyboard.append([
                InlineKeyboardButton("✅ 确认", callback_data="confirm_coins"),
                InlineKeyboardButton("🔙 返回设置", callback_data="help")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"选择币种时出错: {e}")
            await self.send_message(text=f"❌ 选择币种时出错: {str(e)}")

    async def set_leverage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理设置杠杆倍数"""
        try:
            message = (
                "⚔️ *设置杠杆倍数*\n\n"
                f"当前杠杆倍数: {config.LEVERAGE}倍\n\n"
                "选择新的杠杆倍数："
            )
            
            # 创建杠杆选择按钮，每行四个
            leverage_options = [1, 3, 5, 10, 20, 30, 50, 75]
            keyboard = []
            row = []
            for lev in leverage_options:
                row.append(InlineKeyboardButton(f"{lev}倍", callback_data=f"leverage_{lev}"))
                if len(row) == 4:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            
            # 添加自定义输入和返回按钮
            keyboard.append([
                InlineKeyboardButton("⌨️ 自定义输入", callback_data="custom_leverage"),
                InlineKeyboardButton("🔙 返回设置", callback_data="help")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"设置杠杆倍数时出错: {e}")
            await self.send_message(text=f"❌ 设置杠杆倍数时出错: {str(e)}")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/status命令"""
        if not self._check_authorized(update):
            return
        
        try:
            # 获取各种状态信息
            current_price = self.strategy.okx.get_current_price()
            balance = self.strategy.okx.get_account_balance()
            positions = self.strategy.okx.get_positions()
            strategy_status = "✅ 运行中" if self.strategy.running else "⏹️ 已停止"
            
            # 构建状态消息
            message = (
                "�� *Crypto AI 系统状态*\n\n"
                f"🪙 交易对: {config.SYMBOL}\n"
                f"💹 当前价格: {current_price:.1f}\n\n"
                f"⚙️ 策略类型: 三重信号验证\n"
                f"▶️ 运行状态: {strategy_status}\n\n"
                f"💰 账户余额: {balance.get('total', {}).get('USDT', 0):.2f} USDT\n"
                f"📈 当前持仓: {self._format_positions(positions)}\n"
                f"📊 今日收益: 暂无数据\n\n"
                f"⚔️ 交易杠杆: {config.LEVERAGE}倍\n"
                f"🌐 网络状态: ✅ 正常\n"
                f"🕒 更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # 添加返回主菜单按钮
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await self.send_message(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"获取状态信息时出错: {e}")
            await self.send_message(text=f"❌ 获取状态信息时出错: {str(e)}")

    def _format_positions(self, positions):
        """格式化持仓信息"""
        if not positions or not positions.get('data'):
            return "无持仓"
        
        pos_list = positions['data']
        if not pos_list:
            return "无持仓"
        
        position_info = []
        for pos in pos_list:
            if float(pos.get('pos', 0)) != 0:
                side = "多头" if pos.get('posSide') == 'long' else "空头"
                size = abs(float(pos.get('pos', 0)))
                entry_price = float(pos.get('avgPx', 0))
                pnl = float(pos.get('upl', 0))
                position_info.append(f"{side} {size} @ {entry_price:.2f} (收益: {pnl:+.2f})")
        
        return " | ".join(position_info) if position_info else "无持仓"

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/balance命令"""
        if not self._check_authorized(update):
            return
        
        try:
            # 获取账户余额
            balance = self.strategy.okx.get_account_balance()
            
            if not balance:
                message = "❌ 无法获取账户余额信息"
            else:
                # 格式化余额信息
                message = "💰 *账户余额信息*\n\n"
                
                if 'total' in balance:
                    usdt_balance = balance.get('total', {}).get('USDT', 0)
                    message += f"💵 USDT总额: `{usdt_balance:.2f}`\n"
                
                if 'used' in balance:
                    used_margin = balance.get('used', {}).get('USDT', 0)
                    message += f"🔒 已用保证金: `{used_margin:.2f}`\n"
                
                if 'free' in balance:
                    available = balance.get('free', {}).get('USDT', 0)
                    message += f"💳 可用余额: `{available:.2f}`\n"
                
                # 添加时间戳
                message += f"\n🕒 更新时间: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            
            # 添加返回主菜单按钮
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            # 检查是否是普通消息
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    parse_mode='Markdown'
                )
            # 如果都不是，使用默认发送方式
            else:
                await self.send_message(
                    text=message,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            error_msg = f"❌ 获取余额信息时出错: {str(e)}"
            logger.error(error_msg)
            await self.send_message(text=error_msg)

    async def position_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/position命令"""
        if not self._check_authorized(update):
            return
        
        try:
            positions = self.strategy.okx.get_positions()
            message = "📈 *当前持仓*\n\n"
            
            if positions:
                for pos in positions:
                    if pos['symbol'] == self.strategy.okx.symbol:
                        side = "多" if pos['side'] == 'long' else "空"
                        size = pos['contracts']
                        price = pos['entryPrice']
                        pnl = pos['unrealizedPnl']
                        message += f"{side}仓 {size} @ {price:.2f}\n"
                        message += f"盈亏: {pnl:.2f} USDT\n"
            else:
                message += "当前无持仓"
            
            # 添加返回主菜单按钮
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await self.send_message(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"获取持仓信息时出错: {e}")
            await self.send_message(text=f"获取持仓信息时出错: {e}")

    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/history命令"""
        if not self._check_authorized(update):
            return
        
        try:
            # 获取交易历史
            trades = self.strategy.okx.get_trade_history()
            
            if not trades:
                message = "📜 *交易历史*\n\n❌ 无交易记录"
            else:
                message = "📜 *交易历史记录*\n\n"
                
                # 最多显示最近10笔交易
                for trade in trades[:10]:
                    side = "🟢 买入" if trade.get('side') == 'buy' else "🔴 卖出"
                    amount = trade.get('amount', 0)
                    price = trade.get('price', 0)
                    time_str = datetime.datetime.fromtimestamp(
                        trade.get('timestamp', 0) / 1000
                    ).strftime('%Y-%m-%d %H:%M:%S')
                    
                    message += (
                        f"{side} {trade.get('symbol')}\n"
                        f"💰 价格: `{price:.2f}`\n"
                        f"📊 数量: `{amount:.4f}`\n"
                        f"时间: `{time_str}`\n\n"
                    )
            
            # 添加返回主菜单按钮
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            # 检查是否是普通消息
            elif update.message:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            # 如果都不是，使用默认发送方式
            else:
                await self.send_message(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            error_msg = f"❌ 获取交易历史时出错: {str(e)}"
            logger.error(error_msg)
            await self.send_message(text=error_msg)

    async def run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/run命令"""
        if not self._check_authorized(update):
            return
        
        try:
            # 启动策略
            self.strategy.start()
            await update.message.reply_text("策略已启动")
            
        except Exception as e:
            logger.error(f"启动策略时出错: {e}")
            await self.send_message(text=f"启动策略时出错: {e}")

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/stop命令"""
        if not self._check_authorized(update):
            return
        
        try:
            # 停止策略
            self.strategy.stop()
            await update.message.reply_text("策略已停止")
            
        except Exception as e:
            logger.error(f"停止策略时出错: {e}")
            await self.send_message(text=f"停止策略时出错: {e}")

    async def send_message(self, text, chat_id=None, parse_mode=None, reply_markup=None):
        """发送消息"""
        if not chat_id:
            chat_id = config.TELEGRAM_CHAT_ID
        
        # 如果是离线状态
        if self.is_offline:
            # 存储消息
            self.offline_messages.append({
                'text': text,
                'chat_id': chat_id,
                'parse_mode': parse_mode,
                'reply_markup': reply_markup
            })
            
            # 尝试重新连接（但不要太频繁）
            current_time = time.time()
            if current_time - self.last_retry_time >= self.min_retry_interval:
                if await self.reconnect():
                    logger.info("重新连接成功")
                else:
                    logger.warning(f"离线模式，消息已缓存: {text}")
                    self._save_message_to_file(text)
            else:
                logger.debug(f"跳过重连尝试，距离上次重试仅过去 {current_time - self.last_retry_time:.1f} 秒")
                self._save_message_to_file(text)
            return
        
        try:
            # 确保application.bot已经初始化
            if not hasattr(self.application, 'bot'):
                logger.error("Telegram bot 未正确初始化")
                self._save_message_to_file(text)
                return False
                
            # 发送消息给所有授权用户
            for user_id in self.authorized_users:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            self.is_offline = True
            # 存储消息并保存到文件
            self.offline_messages.append({
                'text': text,
                'chat_id': chat_id,
                'parse_mode': parse_mode,
                'reply_markup': reply_markup
            })
            self._save_message_to_file(text)
            return False

    def _save_message_to_file(self, text):
        """将消息保存到文件"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("telegram_messages.log", "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")
            logger.info(f"消息已保存到telegram_messages.log文件")
        except Exception as e:
            logger.error(f"保存消息到文件失败: {e}")

    async def shutdown(self):
        """关闭Telegram机器人"""
        try:
            if self.application and self.application.running:
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram机器人已关闭")
        except Exception as e:
            logger.error(f"关闭Telegram机器人时出错: {e}")

    def _check_authorized(self, update: Update) -> bool:
        """检查用户是否有权限"""
        user_id = update.effective_user.id
        
        # 如果用户ID与配置的TELEGRAM_CHAT_ID匹配，自动授权
        if str(user_id) == str(config.TELEGRAM_CHAT_ID):
            # 动态添加到授权用户列表
            self.authorized_users.add(user_id)
            return True
        
        if user_id not in self.authorized_users:
            logger.warning(f"未授权的用户尝试访问: {user_id}")
            # 可以给用户发送未授权消息
            try:
                update.message.reply_text("抱歉，您没有使用此机器人的权限。")
            except:
                pass
            return False
        return True

    def _load_authorized_users(self) -> set:
        """加载授权用户列表"""
        authorized_users = set()
        
        # 从配置文件加载授权用户
        if hasattr(config, 'AUTHORIZED_USERS'):
            if isinstance(config.AUTHORIZED_USERS, (list, set, tuple)):
                authorized_users.update(config.AUTHORIZED_USERS)
            else:
                authorized_users.add(config.AUTHORIZED_USERS)
            
        # 添加配置的TELEGRAM_CHAT_ID
        if hasattr(config, 'TELEGRAM_CHAT_ID'):
            try:
                # 确保TELEGRAM_CHAT_ID被转换为整数
                chat_id = int(str(config.TELEGRAM_CHAT_ID).strip())
                authorized_users.add(chat_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的TELEGRAM_CHAT_ID: {config.TELEGRAM_CHAT_ID}")
        
        return authorized_users

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮回调"""
        if not update.callback_query:
            return
        
        query = update.callback_query
        
        try:
            # 先处理回调，如果失败则静默处理
            try:
                await query.answer()
            except Exception as e:
                logger.warning(f"回调应答失败: {e}")
            
            callback_data = query.data
            
            if callback_data == "select_strategy":
                await self.select_strategy_command(update, context)
            elif callback_data.startswith("strategy_"):
                strategy_id = callback_data.split("_")[1]
                # 设置新策略
                if strategy_id in self.strategy.available_strategies:
                    self.strategy.current_strategy = strategy_id
                    await self.send_message(
                        text=f"✅ 已切换到策略: {self.strategy.available_strategies[strategy_id]}"
                    )
                    # 返回主菜单
                    await self.start_command(update, context)
            elif callback_data == "status":
                await self.status_command(update, context)
            elif callback_data == "balance":
                await self.balance_command(update, context)
            elif callback_data == "position":
                await self.position_command(update, context)
            elif callback_data == "history":
                await self.history_command(update, context)
            elif callback_data == "run":
                await self.run_command(update, context)
            elif callback_data == "stop":
                await self.stop_command(update, context)
            elif callback_data == "help":
                await self.help_command(update, context)
            elif callback_data == "main_menu":
                await self.start_command(update, context)
            elif callback_data.startswith("coin_"):
                await self.handle_coin_selection(update, context)
            elif callback_data.startswith("leverage_"):
                await self.handle_leverage_setting(update, context)
            elif callback_data == "custom_leverage":
                await self.handle_custom_leverage(update, context)
            elif callback_data == "confirm_coins":
                await self.handle_coins_confirmation(update, context)
            
        except Exception as e:
            logger.error(f"处理回调时出错: {e}")
            try:
                # 尝试发送错误消息
                error_message = f"❌ 处理命令出错: {str(e)}"
                if query.message:
                    await query.message.reply_text(error_message)
                else:
                    await self.send_message(text=error_message)
            except Exception as send_error:
                logger.error(f"发送错误消息失败: {send_error}")
                self._save_message_to_file(f"错误: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理普通消息"""
        if not self._check_authorized(update):
            return
            
        try:
            message_text = update.message.text
            # 处理消息逻辑...
            
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            await self.send_message(text=f"消息处理出错: {e}")

    async def send_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """生成并发送交易数据图表"""
        if not self._check_authorized(update):
            return
        
        try:
            # 获取K线数据
            df = self.strategy.okx.get_kline_data()
            if df is None or df.empty:
                await update.message.reply_text("无法获取K线数据")
                return
            
            # 创建图表
            plt.figure(figsize=(10, 6))
            plt.plot(df['timestamp'], df['close'], label='Close Price')
            plt.fill_between(df['timestamp'], df['lower_band'], df['upper_band'], color='gray', alpha=0.3, label='Bollinger Bands')
            plt.title('BTC/USDT Price Chart')
            plt.xlabel('Time')
            plt.ylabel('Price (USDT)')
            plt.legend()
            plt.grid(True)
            
            # 将图表保存到字节流
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()
            
            # 发送图表
            await update.message.reply_photo(photo=buf)
        
        except Exception as e:
            logger.error(f"生成图表时出错: {e}")
            await self.send_message(text=f"生成图表时出错: {e}")

    async def reconnect(self):
        """尝试重新连接"""
        current_time = time.time()
        
        # 检查是否达到最小重试间隔
        if current_time - self.last_retry_time < self.min_retry_interval:
            return False
        
        logger.info("尝试重新连接Telegram...")
        self.last_retry_time = current_time
        
        try:
            self._init_bot()
            if not self.is_offline:
                # 发送所有离线消息
                for msg in self.offline_messages:
                    await self.send_message(**msg)
                self.offline_messages.clear()
                return True
        except Exception as e:
            logger.error(f"重新连接失败: {e}")
        
        return False

    async def select_strategy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理策略选择"""
        if not self._check_authorized(update):
            return
        
        try:
            # 确保strategy是AdvancedTradingStrategy实例
            if not hasattr(self.strategy, 'available_strategies'):
                raise AttributeError("策略对象不支持策略选择功能")
            
            message = (
                "🎯 *选择交易策略*\n\n"
                "请选择要使用的策略："
            )
            
            # 创建策略选择按钮
            keyboard = []
            for strategy_id, strategy_name in self.strategy.available_strategies.items():
                # 检查是否是当前选中的策略
                status = "✅" if strategy_id == self.strategy.current_strategy else "⭕"
                keyboard.append([InlineKeyboardButton(
                    f"{status} {strategy_name}",
                    callback_data=f"strategy_{strategy_id}"
                )])
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"显示策略选择时出错: {e}")
            await self.send_message(text=f"❌ 显示策略选择时出错: {str(e)}")
