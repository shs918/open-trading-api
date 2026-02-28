# KIS 국내 주식 자동 매매 솔루션 — 구현 계획

## 1. 솔루션 개요

한국투자증권(KIS) Open Trading API를 활용한 국내 주식 자동 매매 시스템.
마켓 레짐(상승/횡보/하락)을 실시간으로 판단하고, 국면별 최적 전략을 자동 실행한다.

### 핵심 목표
- 모든 시장 국면에서 수익 창출 지향
- 정규장(KRX) + 프리마켓(NXT) 커버
- 실전/모의/백테스트 3가지 모드 지원
- 안전성 우선 설계

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoTrader (메인 오케스트레이터)             │
│  - 스케줄러 (장 시작/종료, 주기적 실행)                         │
│  - 모드 관리 (실전/모의/백테스트)                               │
│  - 로깅 & 알림                                               │
├──────────┬──────────┬──────────┬─────────────────────────────┤
│          │          │          │                             │
│  ┌───────▼──────┐   │  ┌───────▼──────┐  ┌──────────────┐   │
│  │ MarketRegime │   │  │  Strategy    │  │  Execution   │   │
│  │  Analyzer    │   │  │  Engine      │  │  Engine      │   │
│  │              │   │  │              │  │              │   │
│  │ - 거시 지표  │──▶│  │ - 상승 전략  │─▶│ - 주문 실행  │   │
│  │ - 미시 지표  │   │  │ - 횡보 전략  │  │ - 리스크관리 │   │
│  │ - 복합 판단  │   │  │ - 하락 전략  │  │ - 포지션관리 │   │
│  └───────▲──────┘   │  └───────▲──────┘  └──────▲───────┘   │
│          │          │          │                │            │
├──────────┼──────────┼──────────┼────────────────┼────────────┤
│  ┌───────┴──────────┴──────────┴────────────────┴───────┐   │
│  │              DataProvider (데이터 계층)                │   │
│  │  - KIS API 래퍼 (REST + WebSocket)                    │   │
│  │  - 데이터 캐싱 & 정규화                                │   │
│  │  - 백테스트용 히스토리컬 데이터 관리                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 디렉토리 구조

```
auto_trader/
├── __init__.py
├── main.py                      # 진입점, CLI 인터페이스
├── config.py                    # 설정 관리 (모드, 파라미터)
│
├── data/                        # 데이터 계층
│   ├── __init__.py
│   ├── provider.py              # KIS API 래퍼 (통합 인터페이스)
│   ├── market_data.py           # 시세/지수/차트 데이터 수집
│   ├── account_data.py          # 계좌/잔고/손익 조회
│   └── cache.py                 # 데이터 캐싱 (API 호출 최소화)
│
├── regime/                      # 마켓 레짐 분석
│   ├── __init__.py
│   ├── analyzer.py              # 레짐 판단 오케스트레이터
│   ├── macro_indicators.py      # 거시 지표 (지수, 외국인, 환율 등)
│   ├── micro_indicators.py      # 미시 지표 (거래량, 변동성, 매매동향 등)
│   └── regime_model.py          # 레짐 분류 모델 (규칙 기반 + 통계)
│
├── strategy/                    # 매매 전략
│   ├── __init__.py
│   ├── base.py                  # 전략 베이스 클래스
│   ├── bull_strategy.py         # 상승장 전략 (모멘텀/추세추종)
│   ├── sideways_strategy.py     # 횡보장 전략 (평균회귀/박스권)
│   ├── bear_strategy.py         # 하락장 전략 (방어/인버스/현금비중)
│   └── stock_selector.py        # 종목 선정 로직
│
├── execution/                   # 주문 실행
│   ├── __init__.py
│   ├── order_manager.py         # 주문 생성/실행/취소
│   ├── position_manager.py      # 포지션 관리 (보유/비중)
│   └── risk_manager.py          # 리스크 관리 (손절/익절/한도)
│
├── backtest/                    # 백테스트
│   ├── __init__.py
│   ├── engine.py                # 백테스트 엔진
│   ├── data_loader.py           # 과거 데이터 로딩/저장
│   └── performance.py           # 성과 분석 (수익률, MDD, 샤프 등)
│
└── utils/                       # 유틸리티
    ├── __init__.py
    ├── logger.py                # 로깅 설정
    ├── scheduler.py             # 스케줄링 (장 시작/종료 연동)
    └── notifier.py              # 알림 (콘솔 로그)
```

---

## 4. 핵심 컴포넌트 상세 설계

### 4.1 DataProvider — 데이터 계층

KIS API를 래핑하여 통일된 인터페이스를 제공한다.

**활용 KIS API:**

| 용도 | KIS API | 설명 |
|------|---------|------|
| 현재가 | `inquire_price` | 종목 실시간 가격 |
| 일봉 | `inquire_daily_itemchartprice` | 일/주/월 캔들 데이터 |
| 분봉 | `inquire_time_itemchartprice` | 분 단위 캔들 (당일) |
| KOSPI 지수 | `inquire_index_price` | KOSPI(0001), KOSDAQ(1001), KOSPI200(2001) |
| 지수 일봉 | `inquire_daily_indexchartprice` | 지수 히스토리컬 |
| 거래량 | `volume_rank`, `volume_power` | 거래량 순위/체결강도 |
| 투자자 동향 | `inquire_investor` | 외국인/기관/개인 매매 동향 |
| 프로그램매매 | `comp_program_trade_today` | 프로그램 매매 현황 |
| 공매도 | `daily_short_sale` | 공매도 추이 |
| 시장 상태 | `market_status_krx`, `market_status_nxt` | KRX/NXT 장 상태 |
| 해외지수 | overseas `inquire_time_indexchartprice` | S&P500, 나스닥 등 |
| ETF NAV | `etf_nav_trend` | ETF 순자산가치 추이 |
| 호가 (NXT) | `asking_price_nxt` | NXT 프리마켓 호가 |
| 재무비율 | `finance_ratio` | PER, PBR, ROE 등 |

**실시간 WebSocket API:**

| 용도 | WS API | 설명 |
|------|--------|------|
| KRX 체결 | `ccnl_krx` | KRX 실시간 체결 |
| NXT 체결 | `ccnl_nxt` | NXT 실시간 체결 |
| KRX 호가 | `asking_price_krx` | KRX 실시간 호가 |
| 지수 체결 | `index_ccnl` | 지수 실시간 데이터 |

**핵심 메서드:**

```python
class DataProvider:
    def get_current_price(self, ticker: str) -> pd.DataFrame: ...
    def get_daily_candles(self, ticker: str, period: str, start: str, end: str) -> pd.DataFrame: ...
    def get_minute_candles(self, ticker: str) -> pd.DataFrame: ...
    def get_index_price(self, index_code: str) -> pd.DataFrame: ...
    def get_index_history(self, index_code: str, start: str, end: str) -> pd.DataFrame: ...
    def get_investor_trends(self, ticker: str) -> pd.DataFrame: ...
    def get_volume_data(self, ticker: str) -> pd.DataFrame: ...
    def get_market_status(self, market: str) -> dict: ...  # "krx" | "nxt"
    def get_account_balance(self) -> pd.DataFrame: ...
    def get_overseas_index(self, index_code: str) -> pd.DataFrame: ...
```

### 4.2 MarketRegimeAnalyzer — 마켓 레짐 분석

다중 지표를 종합하여 현재 시장 국면을 판단한다.

**레짐 분류:**

```python
class MarketRegime(Enum):
    STRONG_BULL = "strong_bull"    # 강한 상승 (공격적 매수)
    BULL = "bull"                  # 상승 (매수 우위)
    SIDEWAYS = "sideways"         # 횡보 (중립/선별 매매)
    BEAR = "bear"                 # 하락 (방어/현금 확대)
    STRONG_BEAR = "strong_bear"   # 강한 하락 (최대 방어)
```

**거시 지표 (MacroIndicators):**

| 지표 | 산출 방식 | KIS API |
|------|----------|---------|
| KOSPI 추세 | 이동평균 (20/60/120일) 배열 | `inquire_daily_indexchartprice` |
| KOSPI 모멘텀 | ROC (Rate of Change) | `inquire_daily_indexchartprice` |
| 외국인 순매수 추이 | 5/20일 누적 순매수 | `inquire_investor` |
| 기관 순매수 추이 | 5/20일 누적 순매수 | `inquire_investor` |
| 프로그램 매매 | 차익/비차익 순매수 | `comp_program_trade_today` |
| 해외 지수 동향 | S&P500/NASDAQ 일간 등락 | overseas `dailyprice` |
| 시장 거래대금 | 20일 평균 대비 비율 | `inquire_index_price` |

**미시 지표 (MicroIndicators):**

| 지표 | 산출 방식 | KIS API |
|------|----------|---------|
| 시장 등락 비율 | 상승/하락 종목 비율 (ADR) | `market_status_krx` |
| 거래량 체결강도 | 매수/매도 체결강도 | `volume_power` |
| 신고가/신저가 비율 | 52주 신고가 vs 신저가 | `near_new_highlow` |
| 공매도 비율 추이 | 공매도 거래대금/전체 비율 | `daily_short_sale` |
| 변동성 | KOSPI200 변동성 (ELW 기반) | ELW `volatility_trend_daily` |
| 이격도 | 주가 vs 이동평균 괴리 | `disparity` |

**복합 판단 로직:**

```python
class RegimeAnalyzer:
    def analyze(self) -> RegimeResult:
        """
        각 지표에 점수(-2 ~ +2)를 부여하고 가중 합산하여 레짐 판단.

        가중치 예시:
        - KOSPI 추세 방향: 25%
        - 외국인/기관 수급: 20%
        - 해외 지수 동향: 15%
        - 시장 거래대금: 10%
        - 등락 비율 (ADR): 10%
        - 변동성: 10%
        - 공매도/신고가/신저가: 10%

        Returns:
            RegimeResult(regime, confidence, scores, timestamp)
        """
```

### 4.3 StrategyEngine — 전략 엔진

레짐별 서로 다른 매매 전략을 실행한다.

**공통 전략 인터페이스:**

```python
class BaseStrategy(ABC):
    @abstractmethod
    def select_stocks(self, regime: MarketRegime) -> list[StockSignal]: ...

    @abstractmethod
    def calculate_position_size(self, signal: StockSignal, account: AccountInfo) -> float: ...

    @abstractmethod
    def get_exit_conditions(self, position: Position) -> ExitCondition: ...
```

**레짐별 전략:**

| 레짐 | 전략 | 포지션 비중 | 핵심 로직 |
|------|------|-----------|----------|
| **강한 상승** | 모멘텀 추세추종 | 주식 80~90% | 상승 모멘텀 강한 종목 매수, 이동평균 돌파, 거래량 동반 상승 |
| **상승** | 모멘텀 + 선별 | 주식 60~80% | 업종 순환 고려, 외국인/기관 매수 종목 선호 |
| **횡보** | 평균회귀 + 박스권 | 주식 40~60% | 지지/저항선 활용, RSI 과매도 매수 / 과매수 매도 |
| **하락** | 방어 + 현금확대 | 주식 20~40% | 배당주/방어주 위주, 손절 타이트, 현금비중 확대 |
| **강한 하락** | 최대방어 + 인버스ETF | 주식 0~20% | 대부분 현금, 인버스 ETF 헤지 검토 |

**종목 선정 기준 (stock_selector.py):**

```python
class StockSelector:
    def select(self, regime: MarketRegime, universe: list[str]) -> list[StockSignal]:
        """
        레짐별 종목 선정 로직:

        공통 필터:
        - 시가총액 상위 (유동성 확보)
        - 거래대금 일정 수준 이상

        상승장 필터:
        - 20일 이동평균 위, 거래량 증가
        - 외국인/기관 순매수 종목
        - 모멘텀 점수 상위

        횡보장 필터:
        - RSI 30 이하 (과매도) 매수 신호
        - 볼린저밴드 하단 근접
        - PER/PBR 저평가

        하락장 필터:
        - 배당수익률 상위
        - 재무안정성 (부채비율 낮은) 종목
        - 방어적 업종 (필수소비재, 통신, 유틸리티)
        """
```

### 4.4 ExecutionEngine — 실행 엔진

**OrderManager:**

```python
class OrderManager:
    def place_buy(self, ticker: str, qty: int, price: int, order_type: str) -> OrderResult: ...
    def place_sell(self, ticker: str, qty: int, price: int, order_type: str) -> OrderResult: ...
    def cancel_order(self, order_no: str) -> OrderResult: ...
    def get_pending_orders(self) -> pd.DataFrame: ...
```

활용 KIS API: `order_cash`, `order_rvsecncl`, `inquire_psbl_order`, `inquire_psbl_sell`

**RiskManager:**

```python
class RiskManager:
    # 설정 파라미터
    max_loss_per_trade: float = 0.02       # 건당 최대 손실 2%
    max_portfolio_loss: float = 0.05       # 포트폴리오 최대 손실 5%
    max_single_stock_weight: float = 0.10  # 단일 종목 최대 비중 10%
    trailing_stop_pct: float = 0.05        # 트레일링 스탑 5%

    def check_order(self, order: Order, portfolio: Portfolio) -> RiskCheckResult: ...
    def check_stop_loss(self, position: Position) -> bool: ...
    def check_take_profit(self, position: Position) -> bool: ...
    def get_max_position_size(self, ticker: str, portfolio: Portfolio) -> int: ...
```

**PositionManager:**

```python
class PositionManager:
    def get_positions(self) -> list[Position]: ...
    def get_portfolio_value(self) -> float: ...
    def get_cash_ratio(self) -> float: ...
    def rebalance(self, target_weights: dict[str, float]) -> list[Order]: ...
```

활용 KIS API: `inquire_balance`, `inquire_account_balance`, `inquire_balance_rlz_pl`

### 4.5 BacktestEngine — 백테스트 엔진

```python
class BacktestEngine:
    def __init__(self, start_date: str, end_date: str, initial_capital: float): ...

    def run(self, strategy: BaseStrategy) -> BacktestResult: ...

    def load_historical_data(self, tickers: list[str], start: str, end: str) -> dict: ...
```

**데이터 수집 & 저장:**
- KIS API `inquire_daily_itemchartprice`로 일봉 데이터 수집
- `inquire_daily_indexchartprice`로 지수 히스토리컬 수집
- CSV/SQLite로 로컬 캐싱 (API 재호출 방지)

**성과 분석 (performance.py):**
- 누적 수익률 / 연환산 수익률 (CAGR)
- 최대 낙폭 (MDD)
- 샤프 비율
- 승률 / 손익비
- 벤치마크(KOSPI) 대비 초과수익

### 4.6 모드 관리

```python
class TradingMode(Enum):
    LIVE = "live"           # 실전투자 (prod 엔드포인트)
    PAPER = "paper"         # 모의투자 (vps 엔드포인트)
    BACKTEST = "backtest"   # 백테스트 (과거 데이터)

class Config:
    mode: TradingMode
    # LIVE 모드 진입 조건
    paper_min_days: int = 30          # 모의투자 최소 운영 기간
    paper_min_profit_rate: float = 0  # 모의투자 최소 수익률
    paper_max_mdd: float = 0.15       # 모의투자 최대 MDD 허용
```

### 4.7 NXT 프리마켓 지원

```python
class MarketSession(Enum):
    PRE_MARKET_NXT = "pre_market_nxt"   # NXT 프리마켓 (08:00~08:50)
    REGULAR_KRX = "regular_krx"         # 정규장 KRX (09:00~15:30)
    AFTER_HOURS = "after_hours"         # 시간외 (15:40~16:00)
```

NXT 전용 API 활용: `asking_price_nxt`, `ccnl_nxt`, `market_status_nxt`, `exp_ccnl_nxt`

---

## 5. 구현 순서 (Phase별)

### Phase 1: 기반 구축 (데이터 + 인프라)
1. `auto_trader/config.py` — 설정 관리, 모드 전환
2. `auto_trader/utils/logger.py` — 구조화된 로깅
3. `auto_trader/data/provider.py` — KIS API 통합 래퍼
4. `auto_trader/data/market_data.py` — 시세/지수/차트 수집
5. `auto_trader/data/account_data.py` — 계좌 조회
6. `auto_trader/data/cache.py` — 데이터 캐싱

### Phase 2: 마켓 레짐 분석
7. `auto_trader/regime/macro_indicators.py` — 거시 지표 계산
8. `auto_trader/regime/micro_indicators.py` — 미시 지표 계산
9. `auto_trader/regime/regime_model.py` — 레짐 분류 로직
10. `auto_trader/regime/analyzer.py` — 레짐 분석 오케스트레이터

### Phase 3: 전략 엔진
11. `auto_trader/strategy/base.py` — 전략 베이스 클래스
12. `auto_trader/strategy/stock_selector.py` — 종목 선정
13. `auto_trader/strategy/bull_strategy.py` — 상승장 전략
14. `auto_trader/strategy/sideways_strategy.py` — 횡보장 전략
15. `auto_trader/strategy/bear_strategy.py` — 하락장 전략

### Phase 4: 실행 엔진
16. `auto_trader/execution/order_manager.py` — 주문 관리
17. `auto_trader/execution/position_manager.py` — 포지션 관리
18. `auto_trader/execution/risk_manager.py` — 리스크 관리

### Phase 5: 백테스트
19. `auto_trader/backtest/data_loader.py` — 히스토리컬 데이터 수집/저장
20. `auto_trader/backtest/engine.py` — 백테스트 시뮬레이션
21. `auto_trader/backtest/performance.py` — 성과 분석

### Phase 6: 통합 & 오케스트레이션
22. `auto_trader/utils/scheduler.py` — 장 시간 스케줄링
23. `auto_trader/utils/notifier.py` — 알림
24. `auto_trader/main.py` — 메인 진입점, CLI

---

## 6. 주요 설계 원칙

1. **안전성 우선**: 모의투자에서 충분히 검증 후 실전 전환. 리스크 관리 파라미터 보수적 기본값.
2. **모듈성**: 각 컴포넌트 독립적 테스트/교체 가능. 전략 추가 시 `BaseStrategy` 상속만으로 확장.
3. **데이터 일관성**: 모든 API 결과를 `pd.DataFrame`으로 통일. 캐싱으로 API 호출 최소화.
4. **기존 코드 활용**: `examples_llm/`의 개별 API 함수를 직접 import하여 사용. 인증은 기존 `kis_auth.py` 활용.
5. **점진적 구현**: Phase별로 동작 가능한 단위로 구현. Phase 1~2만으로도 레짐 분석 단독 실행 가능.

---

## 7. 의존성

기존 `pyproject.toml` 의존성으로 충분:
- `pandas` — 데이터 처리
- `requests` — REST API 호출
- `websockets` — 실시간 데이터
- `pyyaml` — 설정 파일
- `pycryptodome` — WebSocket 암호화

추가 필요 시:
- `schedule` — 스케줄링 (또는 표준 라이브러리 `sched`/`threading.Timer` 활용)
- `sqlite3` (표준 라이브러리) — 백테스트 데이터 캐싱
