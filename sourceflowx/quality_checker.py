"""
SourceFlowX - 품질 검증 모듈
스크래핑 결과물을 자동으로 검증하고
문제 있는 상품을 걸러내는 품질 검사기.
"""

import os
import json
from datetime import datetime

import config
from utils import parse_price, setup_logger


class QualityChecker:
    """
    스크래핑된 상품 데이터를 8가지 기준으로 자동 검증하는 품질 검사기.

    가격, 평점, 리뷰 수, 이미지, 제목, 브랜드, ASIN 형식, 중복 여부를
    검사하여 통과/탈락/경고로 분류한다.
    """

    def __init__(self, products):
        # type: (list) -> None
        """
        QualityChecker를 초기화한다.

        Args:
            products: 검사할 상품 딕셔너리 리스트.
        """
        self.products = products
        self.passed = []  # 통과한 상품
        self.rejected = []  # 탈락한 상품
        self.warnings = []  # 경고 있는 상품 (통과했지만 확인 권장)
        self._seen_titles = set()  # 제목 중복 검사용 (O(1) 조회)
        self._seen_asins = set()  # ASIN 중복 검사용 (O(1) 조회)
        self.logger = setup_logger("quality")

    def run_all_checks(
        self,
        min_price=None,
        max_price=None,
        min_rating=None,
        min_reviews=None,
        min_images=None,
        min_title_length=None,
    ):
        # type: (float, float, float, int, int, int) -> list
        """
        전체 자동 검증을 실행하고 통과한 상품 리스트를 반환한다.

        8가지 검사(제목, 가격, 평점, 리뷰, 이미지, 브랜드, ASIN, 중복)를 수행하여
        issues가 있으면 탈락, warns만 있으면 경고(통과), 둘 다 없으면 통과로 분류.

        Args:
            min_price: 최소 가격. None이면 config.MIN_PRICE.
            max_price: 최대 가격. None이면 config.MAX_PRICE.
            min_rating: 최소 평점. None이면 config.MIN_RATING.
            min_reviews: 최소 리뷰 수. None이면 config.MIN_REVIEWS.
            min_images: 최소 이미지 수. None이면 config.MIN_IMAGES.
            min_title_length: 최소 제목 길이. None이면 config.MIN_TITLE_LENGTH.

        Returns:
            list: 통과한 상품 딕셔너리 리스트.
        """
        # 기본값 적용
        if min_price is None:
            min_price = config.MIN_PRICE
        if max_price is None:
            max_price = config.MAX_PRICE
        if min_rating is None:
            min_rating = config.MIN_RATING
        if min_reviews is None:
            min_reviews = config.MIN_REVIEWS
        if min_images is None:
            min_images = config.MIN_IMAGES
        if min_title_length is None:
            min_title_length = config.MIN_TITLE_LENGTH

        # 검사 시작 로그
        self.logger.info("============================================================")
        self.logger.info("  자동 품질 검사 시작 (%d개 상품)", len(self.products))
        self.logger.info("============================================================")
        self.logger.info("  기준: 가격 $%s~$%s", min_price, max_price)
        self.logger.info("        평점 %s+ / 리뷰 %s+", min_rating, min_reviews)
        self.logger.info(
            "        이미지 %s장+ / 제목 %s자+", min_images, min_title_length
        )
        self.logger.info("============================================================")

        for p in self.products:
            issues = []  # 탈락 사유
            warns = []  # 경고 사유

            # ── 검사 1: 제목 ──
            title = p.get("detail_title") or p.get("title", "")
            if not title or len(title) < min_title_length:
                issues.append("제목 없음/너무 짧음")

            # ── 검사 2: 가격 ──
            price = parse_price(p.get("price", "0"))
            if price <= 0:
                issues.append("가격 0 또는 누락")
            elif price < min_price:
                issues.append("가격 너무 낮음 (${})".format(price))
            elif price > max_price:
                issues.append("가격 너무 높음 (${})".format(price))

            # ── 검사 3: 평점 ──
            try:
                rating = float(str(p.get("rating", "0")).strip())
                if rating == 0:
                    warns.append("평점 정보 없음")
                elif rating < min_rating:
                    issues.append("평점 낮음 ({})".format(rating))
            except (ValueError, TypeError):
                warns.append("평점 파싱 실패")

            # ── 검사 4: 리뷰 수 ──
            try:
                reviews_raw = str(p.get("reviews_count", "0"))
                reviews_raw = reviews_raw.replace(",", "").replace("+", "")
                reviews = int(float(reviews_raw)) if reviews_raw.strip() else 0
                if reviews < min_reviews:
                    issues.append("리뷰 부족 ({}개)".format(reviews))
            except (ValueError, TypeError):
                warns.append("리뷰수 파싱 실패")

            # ── 검사 5: 이미지 ──
            images = p.get("all_images", [])
            if len(images) < min_images:
                issues.append("이미지 없음 ({}장)".format(len(images)))
            elif len(images) < 3:
                warns.append("이미지 적음 ({}장)".format(len(images)))

            # 이미지 URL 유효성
            for img_url in images:
                if not str(img_url).startswith("http"):
                    issues.append("잘못된 이미지 URL 포함")
                    break

            # ── 검사 6: 브랜드 ──
            brand = p.get("detail_brand") or p.get("brand", "")
            if not brand:
                warns.append("브랜드 정보 없음")

            # ── 검사 7: ASIN 형식 ──
            asin = p.get("asin", "")
            if not asin or len(asin) != 10:
                issues.append("ASIN 형식 이상 ({})".format(asin))

            # ── 검사 8: 중복 (set 사용, O(1)) ──
            if asin and asin in self._seen_asins:
                issues.append("ASIN 중복")
            if title and title in self._seen_titles:
                issues.append("제목 중복")

            # ── 판정 ──
            if issues:
                p["_reject_reasons"] = issues
                self.rejected.append(p)
            else:
                if warns:
                    p["_warnings"] = warns
                    self.warnings.append(p)
                self.passed.append(p)
                # 중복 검사용 set에 추가 (통과한 것만)
                if asin:
                    self._seen_asins.add(asin)
                if title:
                    self._seen_titles.add(title)

        self._print_report()
        return self.passed

    def _print_report(self):
        # type: () -> None
        """
        검사 결과 리포트를 로그로 출력한다.

        통과/탈락/경고 수와 비율, 탈락 사유 빈도순 TOP 10을 출력.
        """
        total = len(self.products)
        passed = len(self.passed)
        rejected = len(self.rejected)
        warned = len(self.warnings)

        self.logger.info("============================================================")
        self.logger.info("  품질 검사 결과")
        self.logger.info("============================================================")
        self.logger.info("  전체: %d개", total)

        if total > 0:
            self.logger.info("  ✓ 통과: %d개 (%.1f%%)", passed, (passed / total) * 100)
            self.logger.info(
                "  ✗ 탈락: %d개 (%.1f%%)", rejected, (rejected / total) * 100
            )
        else:
            self.logger.info("  ✓ 통과: %d개", passed)
            self.logger.info("  ✗ 탈락: %d개", rejected)

        self.logger.info("  ⚠ 경고: %d개 (통과했지만 확인 권장)", warned)
        self.logger.info("============================================================")

        # 탈락 사유 통계 (빈도순 TOP 10)
        if self.rejected:
            reason_count = {}
            for p in self.rejected:
                for reason in p.get("_reject_reasons", []):
                    reason_count[reason] = reason_count.get(reason, 0) + 1

            sorted_reasons = sorted(
                reason_count.items(), key=lambda x: x[1], reverse=True
            )

            self.logger.info("  탈락 사유 TOP:")
            for reason, count in sorted_reasons[:10]:
                self.logger.info("    - %s: %d건", reason, count)

    def export_report(self, filename=None):
        # type: (str) -> None
        """
        상세 리포트를 JSON 파일로 저장한다.

        Args:
            filename: 저장 파일 경로.
                      None이면 config.OUTPUT_DIR/config.REPORT_FILENAME.
        """
        if filename is None:
            filename = os.path.join(config.OUTPUT_DIR, config.REPORT_FILENAME)

        report = {
            "checked_at": datetime.now().isoformat(),
            "total": len(self.products),
            "passed": len(self.passed),
            "rejected": len(self.rejected),
            "warnings": len(self.warnings),
            "rejected_items": [
                {
                    "asin": p.get("asin"),
                    "title": (p.get("detail_title") or p.get("title", ""))[:50],
                    "reasons": p.get("_reject_reasons", []),
                }
                for p in self.rejected
            ],
            "warning_items": [
                {
                    "asin": p.get("asin"),
                    "title": (p.get("detail_title") or p.get("title", ""))[:50],
                    "warnings": p.get("_warnings", []),
                }
                for p in self.warnings
            ],
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.logger.info("  리포트 저장: %s", filename)
