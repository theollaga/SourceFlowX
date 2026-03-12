"""
SourceFlowX – Shopify Admin API 연동 모듈
상품 등록, 업데이트, 중복 확인, 이미지 업로드를 지원한다.
"""

import os
import json
import time
import requests

from utils import setup_logger, parse_price, sanitize_text, clean_html_body

logger = setup_logger("shopify_api")


class ShopifyClient:
    """
    Shopify Admin REST API 클라이언트.

    상품 CRUD, 중복 확인, 이미지 업로드, 전체 삭제를 제공한다.
    API 버전: 2024-01 (안정 버전).
    rate limit: 매 요청 후 0.5초 대기 (2 req/sec 준수).
    """

    def __init__(self, store_url, api_key):
        # type: (str, str) -> None
        """
        Shopify 클라이언트를 초기화한다.

        Args:
            store_url: Shopify 스토어 URL (예: your-store.myshopify.com).
            api_key: Admin API Access Token.
        """
        # URL 정리
        url = store_url.strip().rstrip("/")
        url = url.replace("https://", "").replace("http://", "")

        if not url.endswith(".myshopify.com"):
            # 도메인이 없으면 .myshopify.com 추가 시도
            if "." not in url:
                url = url + ".myshopify.com"

        self.store_url = url
        self.api_key = api_key.strip()
        self.base_url = "https://{}/admin/api/2024-01".format(self.store_url)
        self.headers = {
            "X-Shopify-Access-Token": self.api_key,
            "Content-Type": "application/json",
        }
        self.logger = logger
        self.existing_products = {}  # handle -> {id, title, variant_id}

    def test_connection(self):
        # type: () -> tuple
        """
        Shopify 스토어 연결을 테스트한다.

        Returns:
            tuple: (성공 여부: bool, 메시지: str).
        """
        url = "{}/shop.json".format(self.base_url)

        try:
            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                data = response.json()
                shop_name = data.get("shop", {}).get("name", "Unknown")
                self.logger.info("[연결 테스트] 성공: %s", shop_name)
                return (True, "연결 성공: {}".format(shop_name))

            elif response.status_code == 401:
                return (False, "API 키가 올바르지 않습니다")

            elif response.status_code == 404:
                return (False, "스토어 URL이 올바르지 않습니다")

            else:
                return (
                    False,
                    "연결 실패: HTTP {} – {}".format(
                        response.status_code, response.text[:200]
                    ),
                )

        except requests.exceptions.ConnectionError:
            return (False, "연결 실패: 서버에 연결할 수 없습니다")
        except requests.exceptions.Timeout:
            return (False, "연결 실패: 요청 시간 초과")
        except Exception as e:
            return (False, "연결 실패: {}".format(e))

    def get_existing_products(self):
        # type: () -> dict
        """
        스토어의 기존 상품을 조회하여 handle 매핑을 구성한다.

        Link 헤더의 next URL로 페이지네이션을 처리한다.

        Returns:
            dict: handle → {id, title, variant_id} 매핑.
        """
        self.existing_products = {}
        url = "{}/products.json?limit=250&fields=id,handle,title,variants".format(
            self.base_url
        )

        page = 1
        while url:
            try:
                response = requests.get(url, headers=self.headers, timeout=30)

                if response.status_code != 200:
                    self.logger.error("[기존 상품 조회] HTTP %d", response.status_code)
                    break

                data = response.json()
                products = data.get("products", [])

                for p in products:
                    handle = p.get("handle", "")
                    variants = p.get("variants", [])
                    variant_id = variants[0]["id"] if variants else None

                    self.existing_products[handle] = {
                        "id": p.get("id"),
                        "title": p.get("title", ""),
                        "variant_id": variant_id,
                    }

                # 페이지네이션: Link 헤더에서 next URL 추출
                url = self._get_next_page_url(response)
                page += 1
                time.sleep(0.5)

            except Exception as e:
                self.logger.error("[기존 상품 조회] 오류: %s", e)
                break

        self.logger.info(
            "[기존 상품 조회] 총 %d개 상품 확인", len(self.existing_products)
        )
        return self.existing_products

    def _get_next_page_url(self, response):
        # type: (requests.Response) -> str or None
        """
        Link 헤더에서 다음 페이지 URL을 추출한다.

        Args:
            response: HTTP 응답 객체.

        Returns:
            str or None: 다음 페이지 URL. 없으면 None.
        """
        link_header = response.headers.get("Link", "")
        if 'rel="next"' in link_header:
            parts = link_header.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    return url
        return None

    def create_product(self, product):
        # type: (dict) -> tuple
        """
        상품을 Shopify 스토어에 등록한다.

        Args:
            product: 상품 데이터 딕셔너리.

        Returns:
            tuple: (성공 여부: bool, 메시지: str).
        """
        title = sanitize_text(product.get("detail_title") or product.get("title", ""))
        asin = product.get("asin", "")
        body_html = product.get("body_html") or product.get("description", "")
        vendor = product.get("detail_brand") or product.get("brand", "")
        price = str(product.get("price", ""))
        compare_price = str(product.get("original_price", ""))

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": "",
                "tags": "amazon-import",
                "status": "draft",
                "variants": [
                    {
                        "price": price,
                        "compare_at_price": compare_price if compare_price else None,
                        "sku": asin,
                        "inventory_management": "shopify",
                        "inventory_quantity": 999,
                        "inventory_policy": "deny",
                        "requires_shipping": True,
                        "taxable": True,
                    }
                ],
                "images": [],
            }
        }

        # 이미지 추가
        all_images = product.get("all_images", [])
        if not all_images and product.get("main_image"):
            all_images = [product.get("main_image")]

        for img_url in all_images:
            if img_url:
                payload["product"]["images"].append({"src": img_url})

        url = "{}/products.json".format(self.base_url)

        try:
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=30
            )

            if response.status_code == 201:
                data = response.json()
                product_id = data.get("product", {}).get("id")
                handle = data.get("product", {}).get("handle", "")

                # 캐시 업데이트
                if handle:
                    variants = data.get("product", {}).get("variants", [])
                    self.existing_products[handle] = {
                        "id": product_id,
                        "title": title,
                        "variant_id": variants[0]["id"] if variants else None,
                    }

                self.logger.info("[등록] %s: %s (ID: %s)", asin, title[:40], product_id)
                return (True, "등록 완료: {}".format(title[:50]))

            else:
                error_detail = response.text[:300]
                self.logger.error(
                    "[등록 실패] %s: HTTP %d – %s",
                    asin,
                    response.status_code,
                    error_detail,
                )
                return (
                    False,
                    "등록 실패 (HTTP {}): {}".format(
                        response.status_code, error_detail
                    ),
                )

        except Exception as e:
            self.logger.error("[등록 오류] %s: %s", asin, e)
            return (False, "등록 오류: {}".format(e))

    def update_product(self, product_id, product):
        # type: (int, dict) -> tuple
        """
        기존 상품의 가격, 재고, 설명을 업데이트한다.

        Args:
            product_id: Shopify 상품 ID.
            product: 상품 데이터 딕셔너리.

        Returns:
            tuple: (성공 여부: bool, 메시지: str).
        """
        body_html = product.get("body_html") or product.get("description", "")

        payload = {
            "product": {
                "id": product_id,
                "body_html": body_html,
                "variants": [
                    {
                        "price": str(product.get("price", "")),
                        "compare_at_price": str(product.get("original_price", ""))
                        or None,
                        "inventory_quantity": 999,
                    }
                ],
            }
        }

        url = "{}/products/{}.json".format(self.base_url, product_id)

        try:
            response = requests.put(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code == 200:
                self.logger.info("[업데이트] 상품 ID %s 완료", product_id)
                return (True, "업데이트 완료")
            else:
                self.logger.error(
                    "[업데이트 실패] ID %s: HTTP %d", product_id, response.status_code
                )
                return (False, "업데이트 실패 (HTTP {})".format(response.status_code))

        except Exception as e:
            self.logger.error("[업데이트 오류] ID %s: %s", product_id, e)
            return (False, "업데이트 오류: {}".format(e))

    def upload_products(self, products, on_duplicate="skip", progress_callback=None):
        # type: (list, str, callable) -> dict
        """
        상품 리스트를 Shopify 스토어에 업로드한다.

        중복 상품은 skip 또는 update 처리한다.
        rate limit 준수를 위해 매 요청 후 0.5초 대기한다.

        Args:
            products: 상품 딕셔너리 리스트.
            on_duplicate: 중복 처리 ("skip" 또는 "update").
            progress_callback: 진행 콜백 (current, total, title, status).

        Returns:
            dict: 결과 통계 (total, created, updated, skipped, failed, errors).
        """
        result = {
            "total": len(products),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }

        try:
            # 기존 상품 조회
            self.get_existing_products()

            for i, product in enumerate(products):
                asin = product.get("asin", "").lower()
                title = product.get("detail_title") or product.get("title", "")

                # 중복 확인 (handle = ASIN 소문자)
                existing = self.existing_products.get(asin)

                if existing:
                    if on_duplicate == "skip":
                        result["skipped"] += 1
                        status = "건너뜀"
                        self.logger.info("[건너뜀] %s: 이미 존재", asin)
                    else:
                        # 업데이트
                        success, msg = self.update_product(existing["id"], product)
                        if success:
                            result["updated"] += 1
                            status = "업데이트"
                        else:
                            result["failed"] += 1
                            result["errors"].append("{}: {}".format(asin, msg))
                            status = "실패"
                else:
                    # 신규 등록
                    success, msg = self.create_product(product)
                    if success:
                        result["created"] += 1
                        status = "등록"
                    else:
                        result["failed"] += 1
                        result["errors"].append("{}: {}".format(asin, msg))
                        status = "실패"

                # 진행 콜백
                if progress_callback:
                    progress_callback(i + 1, len(products), title, status)

                # rate limit (0.5초 대기)
                time.sleep(0.5)

        except Exception as e:
            self.logger.error("[업로드 중단] 오류: %s", e)
            result["errors"].append("중단: {}".format(e))

        self.logger.info(
            "[업로드 완료] 등록: %d, 업데이트: %d, 건너뜀: %d, 실패: %d",
            result["created"],
            result["updated"],
            result["skipped"],
            result["failed"],
        )
        return result

    def delete_all_products(self, progress_callback=None):
        # type: (callable) -> tuple
        """
        스토어의 모든 상품을 삭제한다.

        Args:
            progress_callback: 진행 콜백 (current, total).

        Returns:
            tuple: (삭제 성공 수, 실패 수).
        """
        self.get_existing_products()

        all_ids = [info["id"] for info in self.existing_products.values()]
        total = len(all_ids)
        deleted = 0
        failed = 0

        self.logger.info("[전체 삭제] 대상: %d개", total)

        for i, product_id in enumerate(all_ids):
            url = "{}/products/{}.json".format(self.base_url, product_id)

            try:
                response = requests.delete(url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    deleted += 1
                else:
                    failed += 1
                    self.logger.error(
                        "[삭제 실패] ID %s: HTTP %d", product_id, response.status_code
                    )

            except Exception as e:
                failed += 1
                self.logger.error("[삭제 오류] ID %s: %s", product_id, e)

            if progress_callback:
                progress_callback(i + 1, total)

            time.sleep(0.5)

        self.logger.info("[전체 삭제 완료] 삭제: %d, 실패: %d", deleted, failed)
        self.existing_products.clear()
        return (deleted, failed)
