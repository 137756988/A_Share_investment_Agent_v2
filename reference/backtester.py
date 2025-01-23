from datetime import datetime, timedelta
import json
import time
import logging
import matplotlib.pyplot as plt
import pandas as pd
import os
import sys
import matplotlib

from main import run_hedge_fund
from tools.api import get_price_data

# Configure Chinese font based on OS
if sys.platform.startswith('win'):
    matplotlib.rc('font', family='Microsoft YaHei')
elif sys.platform.startswith('linux'):
    matplotlib.rc('font', family='WenQuanYi Micro Hei')
else:
    matplotlib.rc('font', family='PingFang SC')

# Enable minus sign display
matplotlib.rcParams['axes.unicode_minus'] = False


class Backtester:
    def __init__(self, agent, ticker, start_date, end_date, initial_capital, num_of_news=5):
        self.agent = agent
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.portfolio = {"cash": initial_capital, "stock": 0}
        self.portfolio_values = []
        self.num_of_news = num_of_news

        # Setup logging
        self.setup_backtest_logging()
        self.logger = self.setup_logging()

        # Initialize API call management
        self._api_call_count = 0
        self._api_window_start = time.time()
        self._last_api_call = 0

        # Validate inputs
        self.validate_inputs()

    def setup_logging(self):
        """Setup logging system"""
        logger = logging.getLogger('backtester')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def validate_inputs(self):
        """Validate input parameters"""
        try:
            start = datetime.strptime(self.start_date, "%Y-%m-%d")
            end = datetime.strptime(self.end_date, "%Y-%m-%d")
            if start >= end:
                raise ValueError("Start date must be earlier than end date")
            if self.initial_capital <= 0:
                raise ValueError("Initial capital must be greater than 0")
            if not isinstance(self.ticker, str) or len(self.ticker) != 6:
                raise ValueError("Invalid stock code format")
            self.logger.info("Input parameters validated")
        except Exception as e:
            self.logger.error(f"Input parameter validation failed: {str(e)}")
            raise

    def setup_backtest_logging(self):
        """Setup backtest logging"""
        log_dir = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        self.backtest_logger = logging.getLogger('backtest')
        self.backtest_logger.setLevel(logging.INFO)

        if self.backtest_logger.handlers:
            self.backtest_logger.handlers.clear()

        current_date = datetime.now().strftime('%Y%m%d')
        backtest_period = f"{self.start_date.replace('-', '')}_{self.end_date.replace('-', '')}"
        log_file = os.path.join(
            log_dir, f"backtest_{self.ticker}_{current_date}_{backtest_period}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)
        self.backtest_logger.addHandler(file_handler)

        self.backtest_logger.info(
            f"Backtest Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.backtest_logger.info(f"Stock Code: {self.ticker}")
        self.backtest_logger.info(
            f"Backtest Period: {self.start_date} to {self.end_date}")
        self.backtest_logger.info(
            f"Initial Capital: {self.initial_capital:,.2f}\n")
        self.backtest_logger.info("-" * 100)

    def get_agent_decision(self, current_date, lookback_start, portfolio):
        """Get agent decision with API rate limiting"""
        max_retries = 3
        current_time = time.time()

        if current_time - self._api_window_start >= 60:
            self._api_call_count = 0
            self._api_window_start = current_time

        if self._api_call_count >= 8:
            wait_time = 60 - (current_time - self._api_window_start)
            if wait_time > 0:
                self.logger.info(
                    f"API limit reached, waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                self._api_call_count = 0
                self._api_window_start = time.time()

        for attempt in range(max_retries):
            try:
                if self._last_api_call:
                    time_since_last_call = time.time() - self._last_api_call
                    if time_since_last_call < 6:
                        time.sleep(6 - time_since_last_call)

                self._last_api_call = time.time()
                self._api_call_count += 1

                result = self.agent(
                    ticker=self.ticker,
                    start_date=lookback_start,
                    end_date=current_date,
                    portfolio=portfolio,
                    num_of_news=self.num_of_news
                )

                try:
                    if isinstance(result, str):
                        result = result.replace(
                            '```json\n', '').replace('\n```', '').strip()
                        parsed_result = json.loads(result)

                        formatted_result = {
                            "decision": parsed_result,
                            "analyst_signals": {}
                        }

                        if "agent_signals" in parsed_result:
                            formatted_result["analyst_signals"] = {
                                signal["agent"]: {
                                    "signal": signal.get("signal", "unknown"),
                                    "confidence": signal.get("confidence", 0)
                                }
                                for signal in parsed_result["agent_signals"]
                            }

                        return formatted_result
                    return result
                except json.JSONDecodeError as e:
                    self.logger.warning(f"JSON parsing error: {str(e)}")
                    self.logger.warning(f"Raw result: {result}")
                    return {"decision": {"action": "hold", "quantity": 0}, "analyst_signals": {}}

            except Exception as e:
                if "AFC is enabled" in str(e):
                    self.logger.warning(
                        f"AFC limit triggered, waiting 60 seconds...")
                    time.sleep(60)
                    self._api_call_count = 0
                    self._api_window_start = time.time()
                    continue

                self.logger.warning(
                    f"Failed to get agent decision (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    return {"decision": {"action": "hold", "quantity": 0}, "analyst_signals": {}}
                time.sleep(2 ** attempt)

    def execute_trade(self, action, quantity, current_price):
        """Execute trade with portfolio constraints"""
        if action == "buy" and quantity > 0:
            cost = quantity * current_price
            if cost <= self.portfolio["cash"]:
                self.portfolio["stock"] += quantity
                self.portfolio["cash"] -= cost
                return quantity
            else:
                max_quantity = int(self.portfolio["cash"] // current_price)
                if max_quantity > 0:
                    self.portfolio["stock"] += max_quantity
                    self.portfolio["cash"] -= max_quantity * current_price
                    return max_quantity
                return 0
        elif action == "sell" and quantity > 0:
            quantity = min(quantity, self.portfolio["stock"])
            if quantity > 0:
                self.portfolio["cash"] += quantity * current_price
                self.portfolio["stock"] -= quantity
                return quantity
            return 0
        return 0

    def run_backtest(self):
        """Run backtest simulation"""
        dates = pd.date_range(self.start_date, self.end_date, freq="B")

        self.logger.info("\nStarting backtest...")
        print(f"{'Date':<12} {'Code':<6} {'Action':<6} {'Quantity':>8} {'Price':>8} {'Cash':>12} {'Stock':>8} {'Total':>12} {'Bull':>8} {'Bear':>8} {'Neutral':>8}")
        print("-" * 110)

        for current_date in dates:
            lookback_start = (current_date - timedelta(days=30)
                              ).strftime("%Y-%m-%d")
            current_date_str = current_date.strftime("%Y-%m-%d")

            output = self.get_agent_decision(
                current_date_str, lookback_start, self.portfolio)

            self.backtest_logger.info(f"\nTrade Date: {current_date_str}")
            if "analyst_signals" in output:
                self.backtest_logger.info("\nAgent Analysis Results:")
                for agent_name, signal in output["analyst_signals"].items():
                    self.backtest_logger.info(f"\n{agent_name}:")

                    signal_str = f"- Signal: {signal.get('signal', 'unknown')}"
                    if 'confidence' in signal:
                        signal_str += f", Confidence: {signal.get('confidence', 0)*100:.0f}%"
                    self.backtest_logger.info(signal_str)

                    if 'analysis' in signal:
                        self.backtest_logger.info("- Analysis:")
                        analysis = signal['analysis']
                        if isinstance(analysis, dict):
                            for key, value in analysis.items():
                                self.backtest_logger.info(f"  {key}: {value}")
                        elif isinstance(analysis, list):
                            for item in analysis:
                                self.backtest_logger.info(f"  • {item}")
                        else:
                            self.backtest_logger.info(f"  {analysis}")

                    if 'reason' in signal:
                        self.backtest_logger.info("- Decision Rationale:")
                        reason = signal['reason']
                        if isinstance(reason, list):
                            for item in reason:
                                self.backtest_logger.info(f"  • {item}")
                        else:
                            self.backtest_logger.info(f"  • {reason}")

            agent_decision = output.get(
                "decision", {"action": "hold", "quantity": 0})
            action, quantity = agent_decision.get(
                "action", "hold"), agent_decision.get("quantity", 0)

            self.backtest_logger.info("\nFinal Decision:")
            self.backtest_logger.info(f"Action: {action.upper()}")
            self.backtest_logger.info(f"Quantity: {quantity}")
            if "reason" in agent_decision:
                self.backtest_logger.info(
                    f"Reason: {agent_decision['reason']}")

            df = get_price_data(self.ticker, lookback_start, current_date_str)
            if df is None or df.empty:
                continue

            current_price = df.iloc[-1]['close']
            executed_quantity = self.execute_trade(
                action, quantity, current_price)

            total_value = self.portfolio["cash"] + \
                self.portfolio["stock"] * current_price
            self.portfolio["portfolio_value"] = total_value

            if len(self.portfolio_values) > 0:
                daily_return = (
                    total_value / self.portfolio_values[-1]["Portfolio Value"] - 1) * 100
            else:
                daily_return = 0

            self.portfolio_values.append({
                "Date": current_date,
                "Portfolio Value": total_value,
                "Daily Return": daily_return
            })

            # Count signals
            bull_count = sum(1 for signal in output.get("analyst_signals", {}).values()
                             if signal.get("signal") == "buy")
            bear_count = sum(1 for signal in output.get("analyst_signals", {}).values()
                             if signal.get("signal") == "sell")
            neutral_count = sum(1 for signal in output.get("analyst_signals", {}).values()
                                if signal.get("signal") == "hold")

            print(
                f"{current_date_str:<12} {self.ticker:<6} {action:<6} {executed_quantity:>8} "
                f"{current_price:>8.2f} {self.portfolio['cash']:>12.2f} {self.portfolio['stock']:>8} "
                f"{total_value:>12.2f} {bull_count:>8} {bear_count:>8} {neutral_count:>8}"
            )

    def analyze_performance(self):
        """Analyze backtest performance"""
        performance_df = pd.DataFrame(self.portfolio_values).set_index("Date")

        performance_df["Cumulative Return"] = (
            performance_df["Portfolio Value"] / self.initial_capital - 1) * 100

        performance_df["Portfolio Value (K)"] = performance_df["Portfolio Value"] / 1000

        # Create subplots
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(12, 10), height_ratios=[1, 1])
        fig.suptitle("Backtest Analysis", fontsize=12)

        # Portfolio value plot
        line1 = ax1.plot(performance_df.index,
                         performance_df["Portfolio Value (K)"],
                         label="Portfolio Value",
                         marker='o')
        ax1.set_ylabel("Portfolio Value (K)")
        ax1.set_title("Portfolio Value Change")
        ax1.grid(True)

        for x, y in zip(performance_df.index, performance_df["Portfolio Value (K)"]):
            ax1.annotate(f'{y:.1f}K',
                         (x, y),
                         textcoords="offset points",
                         xytext=(0, 10),
                         ha='center',
                         fontsize=8)

        # Cumulative return plot
        line2 = ax2.plot(performance_df.index,
                         performance_df["Cumulative Return"],
                         label="Cumulative Return",
                         color='green',
                         marker='o')
        ax2.set_ylabel("Cumulative Return (%)")
        ax2.set_title("Cumulative Return Change")
        ax2.grid(True)

        for x, y in zip(performance_df.index, performance_df["Cumulative Return"]):
            ax2.annotate(f'{y:.2f}%',
                         (x, y),
                         textcoords="offset points",
                         xytext=(0, 10),
                         ha='center',
                         fontsize=8)

        plt.xlabel("Date")
        plt.tight_layout()
        plt.show()

        # Calculate performance metrics
        total_return = (
            self.portfolio["portfolio_value"] - self.initial_capital) / self.initial_capital
        print(f"\nTotal Return: {total_return * 100:.2f}%")

        self.backtest_logger.info("\n" + "=" * 50)
        self.backtest_logger.info("Backtest Summary")
        self.backtest_logger.info("=" * 50)
        self.backtest_logger.info(
            f"Initial Capital: {self.initial_capital:,.2f}")
        self.backtest_logger.info(
            f"Final Value: {self.portfolio['portfolio_value']:,.2f}")
        self.backtest_logger.info(f"Total Return: {total_return * 100:.2f}%")

        # Calculate Sharpe Ratio
        daily_returns = performance_df["Daily Return"] / 100
        mean_daily_return = daily_returns.mean()
        std_daily_return = daily_returns.std()
        sharpe_ratio = (mean_daily_return / std_daily_return) * \
            (252 ** 0.5) if std_daily_return != 0 else 0
        self.backtest_logger.info(f"Sharpe Ratio: {sharpe_ratio:.2f}")

        # Calculate Maximum Drawdown
        rolling_max = performance_df["Portfolio Value"].cummax()
        drawdown = (performance_df["Portfolio Value"] / rolling_max - 1) * 100
        max_drawdown = drawdown.min()
        self.backtest_logger.info(f"Maximum Drawdown: {max_drawdown:.2f}%")

        return performance_df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run backtest simulation')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock code (e.g., 600519)')
    parser.add_argument('--end-date', type=str,
                        default=datetime.now().strftime('%Y-%m-%d'),
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--start-date', type=str,
                        default=(datetime.now() - timedelta(days=90)
                                 ).strftime('%Y-%m-%d'),
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--initial-capital', type=float,
                        default=100000,
                        help='Initial capital (default: 100000)')
    parser.add_argument('--num-of-news', type=int,
                        default=5,
                        help='Number of news articles to analyze (default: 5)')

    args = parser.parse_args()

    backtester = Backtester(
        agent=run_hedge_fund,
        ticker=args.ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        num_of_news=args.num_of_news
    )

    backtester.run_backtest()
    performance_df = backtester.analyze_performance()
