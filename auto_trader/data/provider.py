# -*- coding: utf-8 -*-
"""KIS API 통합 래퍼.

기존 examples_llm/kis_auth.py의 인증/호출 기능을 활용하여,
자동 매매 시스템에 필요한 통일된 데이터 접근 인터페이스를 제공한다.
"""

import os
import sys
from pathlib import Path

import pandas as pd

from auto_trader.config import Config, TradingMode
from auto_trader.utils.logger import get_logger

logger = get_logger("data.provider")

# examples_llm 경로를 sys.path에 추가하여 kis_auth import 가능하게 함
_EXAMPLES_LLM_DIR = str(Path(__file__).parent.parent.parent / "examples_llm")
if _EXAMPLES_LLM_DIR not in sys.path:
    sys.path.insert(0, _EXAMPLES_LLM_DIR)


class DataProvider:
    """KIS Open API 통합 데이터 제공자.

    인증을 관리하고, 시세/주문/계좌 관련 API를 통일된 인터페이스로 호출한다.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._authenticated = False
        self._ka = None  # kis_auth 모듈 참조

    def authenticate(self) -> None:
        """KIS API 인증을 수행한다."""
        import kis_auth as ka

        self._ka = ka
        svr = self._config.kis_server  # "prod" or "vps"
        ka.auth(svr=svr, product="01")
        self._authenticated = True
        logger.info("KIS API 인증 완료 (server=%s)", svr)

    def _ensure_auth(self) -> None:
        """인증 상태를 확인하고 필요시 인증한다."""
        if not self._authenticated:
            self.authenticate()

    @property
    def _env_dv(self) -> str:
        """API 호출용 환경 구분값."""
        return "real" if self._config.mode == TradingMode.LIVE else "demo"

    @property
    def _trenv(self):
        """KIS 환경 정보 (계좌번호 등)."""
        self._ensure_auth()
        return self._ka.getTREnv()

    # ─── 시세 조회 ───────────────────────────────────────────────

    def get_current_price(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """종목 현재가를 조회한다.

        Args:
            ticker: 종목코드 (예: "005930").
            market: 시장 구분 (J:KRX, NX:NXT, UN:통합).

        Returns:
            현재가 데이터 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_price.inquire_price import inquire_price

        return inquire_price(self._env_dv, market, ticker)

    def get_daily_chart(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        period: str = "D",
        market: str = "J",
        adj_price: str = "0",
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """종목 일/주/월/년 차트 데이터를 조회한다.

        Args:
            ticker: 종목코드.
            start_date: 조회 시작일 (YYYYMMDD).
            end_date: 조회 종료일 (YYYYMMDD).
            period: 기간분류 (D:일봉, W:주봉, M:월봉, Y:년봉).
            market: 시장 구분 (J:KRX, NX:NXT, UN:통합).
            adj_price: 수정주가 여부 (0:수정주가, 1:원주가).

        Returns:
            (요약 DataFrame, OHLCV DataFrame).
        """
        self._ensure_auth()
        from domestic_stock.inquire_daily_itemchartprice.inquire_daily_itemchartprice import (
            inquire_daily_itemchartprice,
        )

        return inquire_daily_itemchartprice(
            self._env_dv, market, ticker, start_date, end_date, period, adj_price
        )

    def get_minute_chart(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """종목 분봉 데이터를 조회한다.

        Args:
            ticker: 종목코드.
            market: 시장 구분.

        Returns:
            분봉 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_time_itemchartprice.inquire_time_itemchartprice import (
            inquire_time_itemchartprice,
        )

        return inquire_time_itemchartprice(self._env_dv, market, ticker)

    # ─── 지수 조회 ───────────────────────────────────────────────

    def get_index_price(self, index_code: str = "0001") -> pd.DataFrame:
        """국내 업종 현재 지수를 조회한다.

        Args:
            index_code: 지수코드 (0001:KOSPI, 1001:KOSDAQ, 2001:KOSPI200).

        Returns:
            지수 데이터 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_index_price.inquire_index_price import (
            inquire_index_price,
        )

        return inquire_index_price("U", index_code)

    def get_index_daily_chart(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
        period: str = "D",
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """지수 일/주/월 차트 데이터를 조회한다.

        Args:
            index_code: 지수코드.
            start_date: 조회 시작일 (YYYYMMDD).
            end_date: 조회 종료일 (YYYYMMDD).
            period: 기간분류 (D/W/M/Y).

        Returns:
            (요약 DataFrame, OHLCV DataFrame).
        """
        self._ensure_auth()
        from domestic_stock.inquire_daily_indexchartprice.inquire_daily_indexchartprice import (
            inquire_daily_indexchartprice,
        )

        return inquire_daily_indexchartprice(
            fid_cond_mrkt_div_code="U",
            fid_input_iscd=index_code,
            fid_input_date_1=start_date,
            fid_input_date_2=end_date,
            fid_period_div_code=period,
            env_dv=self._env_dv,
        )

    # ─── 투자자/수급 동향 ─────────────────────────────────────────

    def get_investor_trends(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """종목별 투자자 매매 동향을 조회한다.

        Args:
            ticker: 종목코드.
            market: 시장 구분.

        Returns:
            투자자별 매매 동향 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_investor.inquire_investor import inquire_investor

        return inquire_investor(self._env_dv, market, ticker)

    # ─── 거래량/체결강도 ──────────────────────────────────────────

    def get_volume_power(self, market: str = "J") -> pd.DataFrame:
        """체결강도 상위 종목을 조회한다.

        Args:
            market: 시장 구분 (J:KRX).

        Returns:
            체결강도 상위 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.volume_power.volume_power import volume_power

        return volume_power(
            fid_trgt_exls_cls_code="0",
            fid_cond_mrkt_div_code="J",
            fid_cond_scr_div_code="20168",
            fid_input_iscd="0000",
            fid_div_cls_code="0",
            fid_input_price_1="",
            fid_input_price_2="",
            fid_vol_cnt="",
            fid_trgt_cls_code="0",
        )

    # ─── 시장 상태 ───────────────────────────────────────────────

    def get_market_time(self) -> pd.DataFrame:
        """장 운영 시간 정보를 조회한다.

        Returns:
            장 운영 시간 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.market_time.market_time import market_time

        return market_time(self._env_dv)

    # ─── 계좌/잔고 ───────────────────────────────────────────────

    def get_balance(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """계좌 잔고를 조회한다.

        Returns:
            (보유종목 DataFrame, 계좌요약 DataFrame).
        """
        self._ensure_auth()
        from domestic_stock.inquire_balance.inquire_balance import inquire_balance

        trenv = self._trenv
        return inquire_balance(
            env_dv=self._env_dv,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
            afhr_flpr_yn="N",
            inqr_dvsn="02",
            unpr_dvsn="01",
            fund_sttl_icld_yn="N",
            fncg_amt_auto_rdpt_yn="N",
            prcs_dvsn="00",
        )

    def get_account_balance(self) -> pd.DataFrame:
        """계좌 전체 잔고(예수금 등)를 조회한다.

        Returns:
            계좌 잔고 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_account_balance.inquire_account_balance import (
            inquire_account_balance,
        )

        trenv = self._trenv
        return inquire_account_balance(
            env_dv=self._env_dv,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
            inqr_dvsn_1="",
            bspr_bf_dt_aply_yn="",
        )

    # ─── 주문 ────────────────────────────────────────────────────

    def place_order(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: int = 0,
        order_type: str = "00",
        market: str = "KRX",
    ) -> pd.DataFrame:
        """매수/매도 주문을 실행한다.

        Args:
            ticker: 종목코드.
            side: "buy" 또는 "sell".
            quantity: 주문 수량.
            price: 주문 가격 (0이면 시장가).
            order_type: 주문구분 (00:지정가, 01:시장가 등).
            market: 거래소 (KRX, NXT).

        Returns:
            주문 결과 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.order_cash.order_cash import order_cash

        trenv = self._trenv

        if price == 0:
            order_type = "01"  # 시장가

        return order_cash(
            env_dv=self._env_dv,
            ord_dv=side,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
            pdno=ticker,
            ord_dvsn=order_type,
            ord_qty=str(quantity),
            ord_unpr=str(price),
            excg_id_dvsn_cd=market,
        )

    def cancel_order(
        self,
        order_no: str,
        order_org_no: str = "",
        quantity: str = "0",
        market: str = "KRX",
    ) -> pd.DataFrame:
        """주문을 취소한다.

        Args:
            order_no: 원주문번호.
            order_org_no: 한국거래소전송주문조직번호.
            quantity: 취소 수량 (0이면 전량).
            market: 거래소 구분.

        Returns:
            취소 결과 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.order_rvsecncl.order_rvsecncl import order_rvsecncl

        trenv = self._trenv
        qty_all = "Y" if quantity == "0" else "N"

        return order_rvsecncl(
            env_dv=self._env_dv,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
            krx_fwdg_ord_orgno=order_org_no,
            orgn_odno=order_no,
            ord_dvsn="00",
            rvse_cncl_dvsn_cd="02",  # 취소
            ord_qty=quantity,
            ord_unpr="0",
            qty_all_ord_yn=qty_all,
            excg_id_dvsn_cd=market,
        )

    # ─── 재무/펀더멘탈 ────────────────────────────────────────────

    def get_finance_ratio(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """종목 재무비율(PER, PBR, ROE 등)을 조회한다.

        Args:
            ticker: 종목코드.
            market: 시장 구분.

        Returns:
            재무비율 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.finance_ratio.finance_ratio import finance_ratio

        return finance_ratio(self._env_dv, market, ticker)

    # ─── 기타 시장 데이터 ─────────────────────────────────────────

    def get_short_sale(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """공매도 데이터를 조회한다.

        Args:
            ticker: 종목코드.
            market: 시장 구분.

        Returns:
            공매도 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.daily_short_sale.daily_short_sale import daily_short_sale

        return daily_short_sale(self._env_dv, market, ticker)

    def get_near_new_highlow(self, market: str = "J") -> pd.DataFrame:
        """신고가/신저가 근접 종목을 조회한다.

        Args:
            market: 시장 구분.

        Returns:
            신고가/신저가 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.near_new_highlow.near_new_highlow import near_new_highlow

        return near_new_highlow(self._env_dv, market)

    def get_market_cap(self, market: str = "J") -> pd.DataFrame:
        """시가총액 순위를 조회한다.

        Args:
            market: 시장 구분.

        Returns:
            시가총액 순위 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.market_cap.market_cap import market_cap

        return market_cap(self._env_dv, market)

    def get_disparity(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """이격도를 조회한다.

        Args:
            ticker: 종목코드.
            market: 시장 구분.

        Returns:
            이격도 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.disparity.disparity import disparity

        return disparity(self._env_dv, market, ticker)

    def get_program_trade(self) -> pd.DataFrame:
        """당일 프로그램 매매 현황을 조회한다.

        Returns:
            프로그램 매매 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.comp_program_trade_today.comp_program_trade_today import (
            comp_program_trade_today,
        )

        return comp_program_trade_today(self._env_dv)

    def get_inquire_ccnl(self) -> pd.DataFrame:
        """당일 체결 내역을 조회한다.

        Returns:
            체결 내역 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_ccnl.inquire_ccnl import inquire_ccnl

        trenv = self._trenv
        return inquire_ccnl(
            env_dv=self._env_dv,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
        )

    def get_psbl_order(self, ticker: str) -> pd.DataFrame:
        """매수 가능 수량/금액을 조회한다.

        Args:
            ticker: 종목코드.

        Returns:
            매수가능 조회 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_psbl_order.inquire_psbl_order import inquire_psbl_order

        trenv = self._trenv
        return inquire_psbl_order(
            env_dv=self._env_dv,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
            pdno=ticker,
            ord_unpr="0",
            ord_dvsn="01",
        )

    def get_psbl_sell(self, ticker: str) -> pd.DataFrame:
        """매도 가능 수량을 조회한다.

        Args:
            ticker: 종목코드.

        Returns:
            매도가능 조회 DataFrame.
        """
        self._ensure_auth()
        from domestic_stock.inquire_psbl_sell.inquire_psbl_sell import inquire_psbl_sell

        trenv = self._trenv
        return inquire_psbl_sell(
            env_dv=self._env_dv,
            cano=trenv.my_acct,
            acnt_prdt_cd=trenv.my_prod,
            pdno=ticker,
        )
