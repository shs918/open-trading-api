# -*- coding: utf-8 -*-
"""백테스트 성과 분석 모듈.

수익률, MDD, 샤프 비율, 승률, 손익비 등 핵심 성과 지표를 산출한다.
"""

from dataclasses import dataclass, field
from math import sqrt

import pandas as pd

from auto_trader.backtest.engine import BacktestResult, DailySnapshot
from auto_trader.utils.logger import get_logger

logger = get_logger("backtest.performance")

# 연간 거래일수 (KRX 기준)
TRADING_DAYS_PER_YEAR = 245
# 무위험 수익률 (연간, 한국 국고채 기준 근사)
RISK_FREE_RATE = 0.035


@dataclass
class TradeStats:
    """거래 통계."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # 승률 (%)
    avg_profit: float = 0.0  # 평균 수익 (%)
    avg_loss: float = 0.0  # 평균 손실 (%)
    profit_loss_ratio: float = 0.0  # 손익비
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


@dataclass
class PerformanceReport:
    """성과 분석 리포트."""

    strategy_name: str
    period: str  # "YYYYMMDD ~ YYYYMMDD"
    initial_capital: float
    final_value: float

    # 수익률 지표
    total_return: float = 0.0  # 누적 수익률 (%)
    cagr: float = 0.0  # 연환산 수익률 (%)
    benchmark_return: float = 0.0  # 벤치마크 수익률 (%)
    excess_return: float = 0.0  # 초과수익 (%)

    # 위험 지표
    mdd: float = 0.0  # 최대 낙폭 (%)
    mdd_start: str = ""  # MDD 시작일
    mdd_end: str = ""  # MDD 최저점일
    volatility: float = 0.0  # 연환산 변동성 (%)
    sharpe_ratio: float = 0.0  # 샤프 비율
    sortino_ratio: float = 0.0  # 소르티노 비율
    calmar_ratio: float = 0.0  # 칼마 비율 (CAGR / MDD)

    # 거래 통계
    trade_stats: TradeStats = field(default_factory=TradeStats)

    # 일별 데이터
    daily_returns: list[float] = field(default_factory=list)
    cumulative_values: list[float] = field(default_factory=list)


class PerformanceAnalyzer:
    """성과 분석기."""

    def analyze(
        self,
        result: BacktestResult,
        benchmark_data: pd.DataFrame | None = None,
    ) -> PerformanceReport:
        """백테스트 결과를 분석한다.

        Args:
            result: 백테스트 결과.
            benchmark_data: 벤치마크 지수 DataFrame (date, close).

        Returns:
            PerformanceReport.
        """
        report = PerformanceReport(
            strategy_name=result.strategy_name,
            period=f"{result.start_date} ~ {result.end_date}",
            initial_capital=result.initial_capital,
            final_value=result.final_value,
            total_return=result.total_return,
        )

        snapshots = result.daily_snapshots
        if not snapshots:
            return report

        # 일별 수익률 리스트
        daily_returns = [s.daily_return for s in snapshots]
        report.daily_returns = daily_returns
        report.cumulative_values = [s.total_value for s in snapshots]

        # CAGR (연환산 수익률)
        report.cagr = self._calc_cagr(
            result.initial_capital, result.final_value, len(snapshots),
        )

        # MDD
        mdd, mdd_start, mdd_end = self._calc_mdd(snapshots)
        report.mdd = mdd
        report.mdd_start = mdd_start
        report.mdd_end = mdd_end

        # 변동성
        report.volatility = self._calc_volatility(daily_returns)

        # 샤프 비율
        report.sharpe_ratio = self._calc_sharpe(daily_returns)

        # 소르티노 비율
        report.sortino_ratio = self._calc_sortino(daily_returns)

        # 칼마 비율
        if report.mdd != 0:
            report.calmar_ratio = report.cagr / abs(report.mdd)

        # 벤치마크 수익률
        if benchmark_data is not None and not benchmark_data.empty:
            report.benchmark_return = self._calc_benchmark_return(benchmark_data)
            report.excess_return = report.total_return - report.benchmark_return

        # 거래 통계
        report.trade_stats = self._calc_trade_stats(result)

        logger.info(
            "성과 분석 완료: 수익률=%.2f%%, CAGR=%.2f%%, MDD=%.2f%%, 샤프=%.2f, 승률=%.1f%%",
            report.total_return,
            report.cagr,
            report.mdd,
            report.sharpe_ratio,
            report.trade_stats.win_rate,
        )

        return report

    # ─── 수익률 지표 ────────────────────────────────────────────

    @staticmethod
    def _calc_cagr(initial: float, final: float, trading_days: int) -> float:
        """CAGR(연환산 수익률)을 계산한다."""
        if initial <= 0 or trading_days <= 0:
            return 0.0
        years = trading_days / TRADING_DAYS_PER_YEAR
        if years <= 0:
            return 0.0
        return ((final / initial) ** (1 / years) - 1) * 100

    @staticmethod
    def _calc_benchmark_return(benchmark_data: pd.DataFrame) -> float:
        """벤치마크 수익률을 계산한다."""
        if len(benchmark_data) < 2:
            return 0.0
        closes = pd.to_numeric(benchmark_data["close"], errors="coerce")
        first = closes.iloc[0]
        last = closes.iloc[-1]
        if first <= 0:
            return 0.0
        return ((last - first) / first) * 100

    # ─── 위험 지표 ──────────────────────────────────────────────

    @staticmethod
    def _calc_mdd(snapshots: list[DailySnapshot]) -> tuple[float, str, str]:
        """MDD(최대 낙폭)를 계산한다.

        Returns:
            (MDD %, 시작일, 최저점일).
        """
        if not snapshots:
            return 0.0, "", ""

        peak = snapshots[0].total_value
        peak_date = snapshots[0].date
        max_dd = 0.0
        mdd_start = ""
        mdd_end = ""

        for snap in snapshots:
            if snap.total_value > peak:
                peak = snap.total_value
                peak_date = snap.date
            dd = (snap.total_value - peak) / peak
            if dd < max_dd:
                max_dd = dd
                mdd_start = peak_date
                mdd_end = snap.date

        return max_dd * 100, mdd_start, mdd_end

    @staticmethod
    def _calc_volatility(daily_returns: list[float]) -> float:
        """연환산 변동성을 계산한다."""
        if len(daily_returns) < 2:
            return 0.0
        series = pd.Series(daily_returns)
        daily_std = series.std()
        return daily_std * sqrt(TRADING_DAYS_PER_YEAR) * 100

    @staticmethod
    def _calc_sharpe(daily_returns: list[float]) -> float:
        """샤프 비율을 계산한다."""
        if len(daily_returns) < 2:
            return 0.0
        series = pd.Series(daily_returns)
        daily_rf = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
        excess = series - daily_rf
        if excess.std() == 0:
            return 0.0
        return (excess.mean() / excess.std()) * sqrt(TRADING_DAYS_PER_YEAR)

    @staticmethod
    def _calc_sortino(daily_returns: list[float]) -> float:
        """소르티노 비율을 계산한다 (하방 변동성만 사용)."""
        if len(daily_returns) < 2:
            return 0.0
        series = pd.Series(daily_returns)
        daily_rf = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
        excess = series - daily_rf
        downside = excess[excess < 0]
        if downside.empty or downside.std() == 0:
            return 0.0
        return (excess.mean() / downside.std()) * sqrt(TRADING_DAYS_PER_YEAR)

    # ─── 거래 통계 ──────────────────────────────────────────────

    @staticmethod
    def _calc_trade_stats(result: BacktestResult) -> TradeStats:
        """거래 통계를 계산한다."""
        trades = result.trades
        if not trades:
            return TradeStats()

        # 매수-매도 쌍 매칭
        buy_map: dict[str, list] = {}
        profits: list[float] = []

        for trade in trades:
            if trade.side == "buy":
                buy_map.setdefault(trade.ticker, []).append(trade)
            elif trade.side == "sell":
                buys = buy_map.get(trade.ticker, [])
                if buys:
                    buy_trade = buys.pop(0)
                    pnl_pct = (trade.price - buy_trade.price) / buy_trade.price * 100
                    profits.append(pnl_pct)

        if not profits:
            return TradeStats(total_trades=len(trades))

        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]

        # 최대 연속 승/패
        max_cons_wins = 0
        max_cons_losses = 0
        cons_wins = 0
        cons_losses = 0
        for p in profits:
            if p > 0:
                cons_wins += 1
                cons_losses = 0
                max_cons_wins = max(max_cons_wins, cons_wins)
            else:
                cons_losses += 1
                cons_wins = 0
                max_cons_losses = max(max_cons_losses, cons_losses)

        avg_profit = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0

        return TradeStats(
            total_trades=len(profits),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=(len(wins) / len(profits)) * 100 if profits else 0,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            profit_loss_ratio=profit_loss_ratio,
            max_consecutive_wins=max_cons_wins,
            max_consecutive_losses=max_cons_losses,
        )

    # ─── 리포트 출력 ────────────────────────────────────────────

    @staticmethod
    def format_report(report: PerformanceReport) -> str:
        """성과 리포트를 텍스트로 포맷한다."""
        ts = report.trade_stats
        lines = [
            "=" * 60,
            f"  백테스트 성과 리포트: {report.strategy_name}",
            "=" * 60,
            f"  기간:       {report.period}",
            f"  초기 자본:   {report.initial_capital:>15,.0f} 원",
            f"  최종 자산:   {report.final_value:>15,.0f} 원",
            "",
            "─── 수익률 ───",
            f"  누적 수익률:  {report.total_return:>8.2f}%",
            f"  CAGR:        {report.cagr:>8.2f}%",
            f"  벤치마크:     {report.benchmark_return:>8.2f}%",
            f"  초과수익:     {report.excess_return:>8.2f}%",
            "",
            "─── 위험 지표 ───",
            f"  MDD:         {report.mdd:>8.2f}%  ({report.mdd_start} ~ {report.mdd_end})",
            f"  변동성:       {report.volatility:>8.2f}%",
            f"  샤프 비율:    {report.sharpe_ratio:>8.2f}",
            f"  소르티노:     {report.sortino_ratio:>8.2f}",
            f"  칼마 비율:    {report.calmar_ratio:>8.2f}",
            "",
            "─── 거래 통계 ───",
            f"  총 거래:      {ts.total_trades:>6d} 건",
            f"  승리:         {ts.winning_trades:>6d} 건",
            f"  패배:         {ts.losing_trades:>6d} 건",
            f"  승률:         {ts.win_rate:>8.1f}%",
            f"  평균 수익:    {ts.avg_profit:>8.2f}%",
            f"  평균 손실:    {ts.avg_loss:>8.2f}%",
            f"  손익비:       {ts.profit_loss_ratio:>8.2f}",
            f"  최대연속승:   {ts.max_consecutive_wins:>6d} 건",
            f"  최대연속패:   {ts.max_consecutive_losses:>6d} 건",
            "=" * 60,
        ]
        return "\n".join(lines)

    @staticmethod
    def to_dataframe(report: PerformanceReport) -> pd.DataFrame:
        """일별 수익률을 DataFrame으로 반환한다."""
        if not report.daily_returns:
            return pd.DataFrame()
        return pd.DataFrame({
            "daily_return": report.daily_returns,
            "cumulative_value": report.cumulative_values,
        })
