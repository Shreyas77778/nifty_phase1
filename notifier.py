import telebot
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.bot = telebot.TeleBot(self.token)

    def send_alert(self, trade_data):
        """Standard Trade Entry/Exit Alerts"""
        header_emoji = "🚀" if "BUY" in trade_data.get('action', 'BUY') else "⚠️"
        msg = (
            f"{header_emoji} *SECTOR-SENSE AI: {trade_data.get('action', 'SIGNAL')}* {header_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *SYMBOL:* `{trade_data.get('symbol')}`\n"
            f"📂 *SECTOR:* {trade_data.get('sector', 'NIFTY-50')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *ENTRY:* `{trade_data.get('entry')}` | *SL:* `{trade_data.get('sl')}`\n"
            f"🧠 *LOGIC:* _{trade_data.get('logic', 'Trend alignment')}_\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ *Time:* {trade_data.get('timestamp', 'Just Now')}"
        )
        self._send(msg)

    def send_m2m_report(self, m2m_data):
        """
        💰 Hourly Mark-to-Market (M2M) Institutional Report
        """
        pnl = m2m_data.get('total_pnl', 0.0)
        pnl_emoji = "🤑" if pnl >= 0 else "📉"
        pnl_color = "🟢 Profit" if pnl >= 0 else "🔴 Loss"
        
        # Build Active Positions string
        positions_str = ""
        for p in m2m_data.get('positions', []):
            side = "🟢" if p['Action'] == "BUY" else "🔴"
            positions_str += f"{side} `{p['Symbol']}` | PnL: `{round(p['PnL'], 2)}` \n"

        if not positions_str: positions_str = "_No active positions._"

        msg = (
            f"{pnl_emoji} *HOURLY FUND REPORT* {pnl_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *TOTAL M2M:* `{pnl_color}: ₹{round(pnl, 2)}` \n"
            f"🛡️ *ACTIVE TRANCHES:* `{m2m_data.get('active_count', 0)}` \n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 *OPEN POSITIONS:* \n{positions_str}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ *Update Time:* {datetime.now().strftime('%H:%M IST')}"
        )
        self._send(msg)

    def _send(self, message):
        try:
            self.bot.send_message(self.chat_id, message, parse_mode='Markdown')
        except Exception as e:
            print(f"❌ Telegram Error: {e}")

# Test
if __name__ == "__main__":
    notifier = TelegramNotifier()
    # notifier.send_m2m_report({'total_pnl': 2500.50, 'active_count': 2, 'positions': [{'Symbol': 'NIFTY (22500 CE)', 'Action': 'BUY', 'PnL': 1200.0}]})