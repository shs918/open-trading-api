# CLAUDE.md

## Project Overview

KIS(한국투자증권) Open Trading API 기반 국내 주식 자동매매 솔루션.
마켓 레짐(상승/횡보/하락)을 실시간 분석하고, 국면별 최적 전략을 자동 실행한다.

## Setup

```bash
# Install dependencies (requires Python 3.11+)
uv sync

# With optional features (Web UI + Telegram)
uv sync --extra all

# Configure credentials
cp auto_trader_config.example.yaml auto_trader_config.yaml
# Edit auto_trader_config.yaml with your KIS API keys and account info
```

## Running

```bash
# 모의투자 모드 (기본)
uv run kis-trader trade --mode paper

# 실전투자 모드
uv run kis-trader trade --mode live

# 백테스트
uv run kis-trader backtest --start 20240101 --end 20241231 --strategy bull

# 시스템 상태 조회
uv run kis-trader status
```

## Project Structure

```
auto_trader/           # 메인 패키지
├── main.py            # CLI 진입점, 오케스트레이터
├── config.py          # 설정 관리 (모드, 리스크, 텔레그램 등)
├── data/              # 데이터 계층 (KIS API 래퍼, 캐시)
├── regime/            # 마켓 레짐 분석 (거시/미시 지표, 복합 판단)
├── strategy/          # 매매 전략 (상승/횡보/하락장 전략)
├── execution/         # 주문 실행 (주문/포지션/리스크 관리)
├── backtest/          # 백테스트 엔진 (시뮬레이션, 성과 분석)
├── ui/                # Web UI 대시보드 (FastAPI + HTML/CSS/JS)
└── telegram/          # 텔레그램 봇 (원격 모니터링/제어)

kis_api/               # KIS Open API 래퍼 (원본: open-trading-api/examples_llm)
├── kis_auth.py        # 인증/토큰 관리
└── domestic_stock/    # 국내 주식 API 함수 (23개)
```

## Code Conventions

- **Language:** Python
- **Package manager:** `uv`
- **Naming:** `snake_case` for modules/variables/functions; `PascalCase` for classes
- **Type hints:** Required on all function signatures
- **Data return type:** `pandas.DataFrame` for API results
- **Security:** No hardcoded credentials; use YAML config files

## Key Files

- `auto_trader_config.yaml` — 솔루션 설정 (모드, 리스크, 텔레그램 등)
- `kis_api/kis_auth.py` — KIS API 인증/토큰 관리
- `auto_trader/data/provider.py` — KIS API 통합 인터페이스
- `auto_trader/main.py` — CLI 진입점, AutoTrader 오케스트레이터
- `PLAN.md` — 상세 아키텍처 및 구현 계획

## Important Notes

- `kis_api/` 디렉토리는 `open-trading-api/examples_llm/`에서 추출한 KIS API 래퍼
- 인증 토큰은 `~/.KIS/config/KIS[YYYYMMDD]`에 캐싱됨
- `prod` 엔드포인트 = 실전투자, `vps` 엔드포인트 = 모의투자
