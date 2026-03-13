"""
SourceFlowX Collector (Phase 1)
아마존 제품 페이지의 모든 원본 데이터를 가공 없이 수집하여 JSON으로 저장합니다.
트래픽 절감: 제품당 1회 HTML 요청 (~0.7MB), 기존 대비 약 50% 절감.
"""

__version__ = "1.0.0"