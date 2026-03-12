"""
SourceFlowX – 상품 설명 생성 모듈
AI(OpenAI), 리치 HTML, 원본 텍스트 3가지 방식으로
상품 설명을 생성한다.
"""

import os
import json
import re
import time

from utils import setup_logger, clean_html_body, sanitize_text

logger = setup_logger("description")


# ================================================================
# CSS 스타일 (Shopify 테마 충돌 방지용 sfx- 접두사)
# ================================================================

_RICH_HTML_STYLE = """<style>
.sfx-product-description { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
.sfx-product-description h2 { font-size: 1.5em; margin-bottom: 15px; }
.sfx-product-description h3 { font-size: 1.2em; margin-top: 20px; margin-bottom: 10px; color: #222; }
.sfx-image-section { margin: 20px 0; text-align: center; }
.sfx-image-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 20px 0; }
.sfx-specs table { width: 100%; border-collapse: collapse; margin-top: 10px; }
.sfx-specs td { padding: 8px 12px; border-bottom: 1px solid #eee; }
.sfx-specs td:first-child { font-weight: bold; width: 30%; background: #f9f9f9; }
</style>"""


def generate_original_text(product):
    # type: (dict) -> str
    """
    아마존 원본 설명 텍스트를 그대로 반환한다.

    Args:
        product: 상품 데이터 딕셔너리.

    Returns:
        str: 원본 설명 문자열. 없으면 빈 문자열.
    """
    return product.get("description", "")


def generate_rich_html(product):
    # type: (dict) -> str
    """
    상품 이미지와 설명을 결합하여 보기 좋은 리치 HTML을 생성한다.

    A+ Content가 있으면 우선 사용하고, 없으면 이미지를 텍스트 사이에
    삽입하는 리치 HTML을 생성한다. CSS 클래스는 sfx- 접두사로
    Shopify 테마 충돌을 방지한다.

    Args:
        product: 상품 데이터 딕셔너리.

    Returns:
        str: 리치 HTML 문자열.
    """
    # 1. aplus_html이 이미 있으면 사용 (불릿 포인트 + A+ Content 결합)
    aplus = product.get("aplus_html", "")
    desc = product.get("description", "")

    if aplus and len(aplus) > 100:
        combined = ""
        if desc and len(desc) > 50:
            combined += '<div class="sfx-product-description">'
            combined += '<div class="sfx-features">'
            combined += desc  # 기존 불릿 포인트 (이미 <ul><li> 형식)
            combined += "</div>"
            combined += (
                '<hr style="margin:30px 0;border:none;border-top:1px solid #eee;">'
            )
            combined += "</div>"
        combined += aplus
        return combined

    # 2. description에서 A+ Content 흔적 확인
    if "aplus-v2" in desc or ("aplus" in desc and len(desc) > 500):
        return desc

    # 3. 없으면 기존 리치 HTML 생성
    title = product.get("detail_title", product.get("title", ""))
    description = product.get("description", "")
    images = product.get("all_images", [])
    brand = product.get("detail_brand", product.get("brand", ""))
    rating = product.get("detail_rating", product.get("rating", ""))
    asin = product.get("asin", "")

    # 설명 텍스트를 특징(불릿)과 본문으로 분리
    features, detail_text = _split_description(description)

    img_style = 'style="max-width:100%;height:auto;"'
    alt_text = sanitize_text(title) if title else "Product Image"

    parts = [_RICH_HTML_STYLE]
    parts.append('<div class="sfx-product-description">')

    # 제목
    if title:
        parts.append("  <h2>{}</h2>".format(sanitize_text(title)))

    # 메인 이미지
    if images:
        parts.append('  <div class="sfx-image-section">')
        parts.append(
            '    <img src="{}" alt="{}" {}>'.format(images[0], alt_text, img_style)
        )
        parts.append("  </div>")

    # 특징 리스트
    if features:
        parts.append('  <div class="sfx-features">')
        parts.append("    <h3>Key Features</h3>")
        parts.append("    <ul>")
        for feat in features:
            parts.append("      <li>{}</li>".format(feat))
        parts.append("    </ul>")
        parts.append("  </div>")

    # 이미지 (특징 뒤에 2번째 이미지)
    if len(images) >= 3:
        parts.append('  <div class="sfx-image-section">')
        parts.append(
            '    <img src="{}" alt="{}" {}>'.format(images[1], alt_text, img_style)
        )
        parts.append("  </div>")

    # 상세 설명
    if detail_text:
        parts.append('  <div class="sfx-detail">')
        parts.append("    <h3>Description</h3>")
        parts.append("    <p>{}</p>".format(detail_text))
        parts.append("  </div>")

    # 이미지 (상세 설명 뒤에 3번째 이미지)
    if len(images) >= 4:
        parts.append('  <div class="sfx-image-section">')
        parts.append(
            '    <img src="{}" alt="{}" {}>'.format(images[2], alt_text, img_style)
        )
        parts.append("  </div>")

    # 나머지 이미지 → 2열 그리드
    remaining_start = 3 if len(images) >= 4 else (2 if len(images) >= 3 else 1)
    remaining_imgs = images[remaining_start:]
    if remaining_imgs:
        parts.append('  <div class="sfx-image-grid">')
        for img in remaining_imgs:
            parts.append(
                '    <div><img src="{}" alt="{}" {}></div>'.format(
                    img, alt_text, img_style
                )
            )
        parts.append("  </div>")

    # 이미지 1~2장인 경우: 상단에만 배치 (이미 처리됨)
    if 1 < len(images) < 3:
        parts.append('  <div class="sfx-image-section">')
        parts.append(
            '    <img src="{}" alt="{}" {}>'.format(images[1], alt_text, img_style)
        )
        parts.append("  </div>")

    # 제품 정보 테이블
    specs = []
    if brand:
        specs.append(("Brand", brand))
    if rating:
        specs.append(("Rating", "{} / 5.0".format(rating)))
    if asin:
        specs.append(("ASIN", asin))

    if specs:
        parts.append('  <div class="sfx-specs">')
        parts.append("    <h3>Product Information</h3>")
        parts.append("    <table>")
        for label, value in specs:
            parts.append("      <tr><td>{}</td><td>{}</td></tr>".format(label, value))
        parts.append("    </table>")
        parts.append("  </div>")

    parts.append("</div>")

    return "\n".join(parts)


def _split_description(description):
    # type: (str) -> tuple
    """
    설명 텍스트를 특징 리스트와 본문으로 분리한다.

    <li> 태그 내용은 특징으로, <p> 태그 내용은 본문으로 분류한다.
    HTML이 아닌 일반 텍스트도 처리한다.

    Args:
        description: 원본 설명 문자열.

    Returns:
        tuple: (features: list[str], detail_text: str)
    """
    features = []
    detail_parts = []

    if not description:
        return features, ""

    # <li> 태그에서 특징 추출
    li_matches = re.findall(r"<li[^>]*>(.*?)</li>", description, re.DOTALL)
    for match in li_matches:
        text = re.sub(r"<[^>]+>", "", match).strip()
        if text:
            features.append(text)

    # <p> 태그에서 본문 추출
    p_matches = re.findall(r"<p[^>]*>(.*?)</p>", description, re.DOTALL)
    for match in p_matches:
        text = re.sub(r"<[^>]+>", "", match).strip()
        if text:
            detail_parts.append(text)

    # HTML이 아닌 경우 일반 텍스트 처리
    if not features and not detail_parts:
        plain = re.sub(r"<[^>]+>", "", description).strip()
        lines = [l.strip() for l in plain.split("\n") if l.strip()]

        for line in lines:
            if line.startswith(("•", "-", "·", "*", "–")):
                features.append(line.lstrip("•-·*– "))
            elif len(line) < 100 and not line.endswith("."):
                features.append(line)
            else:
                detail_parts.append(line)

    detail_text = " ".join(detail_parts)
    return features, detail_text


def generate_ai_description(product, api_key, model="gpt-4o-mini", custom_prompt=None):
    # type: (dict, str, str, str) -> str
    """
    OpenAI API로 SEO 최적화된 상품 설명을 생성한다.

    openai 0.x와 1.x+ 모두 호환한다.
    API 호출 실패 시 원본 설명을 반환한다.

    Args:
        product: 상품 데이터 딕셔너리.
        api_key: OpenAI API 키.
        model: 사용할 모델 (기본 gpt-4o-mini).
        custom_prompt: 커스텀 시스템 프롬프트 (None이면 기본 사용).

    Returns:
        str: 생성된 HTML 설명 문자열.
    """
    try:
        import openai
    except ImportError:
        logger.error("openai 패키지가 설치되지 않았습니다: pip install openai")
        return product.get("description", "")

    title = product.get("detail_title", product.get("title", ""))
    brand = product.get("detail_brand", product.get("brand", ""))
    price = product.get("price", "")
    rating = product.get("detail_rating", product.get("rating", ""))
    reviews = product.get("reviews_count", "")
    description = product.get("description", "")

    system_prompt = custom_prompt or (
        "You are an expert Shopify product copywriter. "
        "Write a compelling, SEO-optimized product description in HTML format. "
        "Include: engaging headline, key features as bullet points, "
        "detailed description, and a call-to-action. "
        "Use clean HTML with proper headings (h2, h3), paragraphs, and lists. "
        "Make the tone professional yet friendly. "
        "Optimize for search engines naturally. "
        "Write in English."
    )

    user_prompt = (
        "Write a product description for:\n\n"
        "Title: {title}\n"
        "Brand: {brand}\n"
        "Price: ${price}\n"
        "Rating: {rating}/5.0 ({reviews} reviews)\n\n"
        "Existing description:\n{description}\n\n"
        "Generate a compelling HTML product description."
    ).format(
        title=title,
        brand=brand,
        price=price,
        rating=rating,
        reviews=reviews,
        description=description[:1000] if description else "(no description)",
    )

    try:
        # OpenAI 1.x+ API
        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1500,
                temperature=0.7,
            )
            result = response.choices[0].message.content

        except (AttributeError, TypeError):
            # OpenAI 0.x API 폴백
            openai.api_key = api_key
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1500,
                temperature=0.7,
            )
            result = response["choices"][0]["message"]["content"]

        # rate limit 방지
        time.sleep(1)

        if result:
            # 마크다운 코드블록 및 AI 부가 설명 제거
            result = result.strip()
            # ```html ... ``` 블록 안의 내용만 추출
            import re

            match = re.search(r"```html\s*(.*?)\s*```", result, re.DOTALL)
            if match:
                result = match.group(1).strip()
            else:
                # ``` 없이 온 경우에도 정리
                if result.startswith("```html"):
                    result = result[7:]
                if result.startswith("```"):
                    result = result[3:]
                if result.endswith("```"):
                    result = result[:-3]
                result = result.strip()

            logger.info(
                "[AI 설명] %s: 생성 완료 (%d자)", product.get("asin", ""), len(result)
            )
            return result
        else:
            return product.get("description", "")

    except Exception as e:
        logger.error("[AI 설명] %s: 오류 - %s", product.get("asin", "?"), e)
        return product.get("description", "")


def generate_descriptions(
    products, style="original", api_key=None, model="gpt-4o-mini", custom_prompt=None
):
    # type: (list, str, str, str, str) -> list
    """
    상품 리스트 전체에 대해 선택된 스타일로 설명을 생성한다.

    각 상품의 description과 body_html 필드를 업데이트한다.

    Args:
        products: 상품 딕셔너리 리스트.
        style: 생성 방식 ("original", "rich_html", "ai_seo").
        api_key: OpenAI API 키 (ai_seo 스타일 시 필수).
        model: AI 모델 이름.
        custom_prompt: 커스텀 시스템 프롬프트.

    Returns:
        list: 설명이 업데이트된 상품 리스트.
    """
    total = len(products)
    logger.info("[설명 생성] 스타일: %s, 상품 수: %d", style, total)

    if style in ("ai_seo", "clean_ai_polish", "decluttly") and not api_key:
        logger.warning(
            "[설명 생성] AI 스타일인데 API 키 없음, 가용 방식으로 대체합니다."
        )

    for i, product in enumerate(products):
        try:
            # A+ Content 보완 추출 기능은 사용자 요청에 의해 폐기되었습니다.

            if style == "original":
                body = generate_original_text(product)

            elif style == "rich_html":
                body = generate_rich_html(product)

            elif style == "ai_seo":
                body = generate_ai_description(
                    product, api_key, model=model, custom_prompt=custom_prompt
                )

            elif style == "clean_shopify":
                body = generate_clean_description(product)

            elif style == "clean_ai_polish":
                # 1단계: Clean 파이프라인
                clean_html = generate_clean_description(product)

                # 2단계: AI Polish
                if api_key:
                    try:
                        # store_name은 product에 저장된 값 또는 빈 문자열 사용
                        store_name = product.get("_store_name", "")
                        seo_separator = product.get("_seo_separator", "|")
                        result = ai_polish_description(
                            product,
                            clean_html,
                            api_key,
                            model,
                            store_name,
                            seo_separator,
                        )
                        body = result.get("body_html", clean_html)
                        if result.get("seo_title"):
                            product["_ai_seo_title"] = result["seo_title"]
                        if result.get("seo_description"):
                            product["_ai_seo_description"] = result["seo_description"]
                    except Exception as e:
                        logger.error(
                            "[AI Polish] %s 처리 오류: %s",
                            product.get("asin", ""),
                            str(e),
                        )
                        body = clean_html
                else:
                    logger.warning("[AI Polish] API 키 없음, Clean 결과만 사용")
                    body = clean_html

            elif style == "decluttly":
                # Decluttly 스타일: AI가 Title, Subtitle, Body, SEO 모두 생성
                store_name = product.get("_store_name", "Decluttly")
                seo_separator = product.get("_seo_separator", "|")
                result = generate_decluttly_description(
                    product, api_key, model, store_name, seo_separator
                )
                body = result.get("body_html", "")
                if not body:
                    body = generate_clean_description(product)
                # AI 결과를 product에 저장 (shopify_exporter에서 활용)
                if result.get("ai_title"):
                    product["_ai_title"] = result["ai_title"]
                if result.get("ai_subtitle"):
                    product["_ai_subtitle"] = result["ai_subtitle"]
                if result.get("seo_title"):
                    product["_ai_seo_title"] = result["seo_title"]
                if result.get("seo_description"):
                    product["_ai_seo_description"] = result["seo_description"]

            else:
                body = generate_original_text(product)

            product["body_html"] = body

            # 진행 상황 로깅 (매 10개마다)
            if (i + 1) % 10 == 0 or (i + 1) == total:
                logger.info(
                    "[설명 생성] %d/%d 완료 (%.0f%%)",
                    i + 1,
                    total,
                    ((i + 1) / total) * 100,
                )

        except Exception as e:
            logger.error("[설명 생성] %s: 오류 - %s", product.get("asin", "?"), e)

    logger.info("[설명 생성] 완료: %d개 상품 처리", total)
    return products


# ================================================================
# Clean Description (Shopify Optimized)
# ================================================================


def generate_clean_description(product):
    # type: (dict) -> str
    """
    Shopify 최적화된 클린 HTML 상품 설명을 생성한다.

    아마존 원본 HTML에서 불필요한 요소를 제거하고,
    Features / Specifications / Summary 구조로 재구성한다.

    10단계 클리닝 파이프라인:
    1. style/script/img 태그 제거
    2. SFX/specs 섹션 제거
    3. <li> 기반 Feature 추출
    4. 괄호 안 코드/모델번호 제거
    5. 브랜드명/상표 문구 제거
    6. 특허/보증 문구 제거
    7. 아마존 전용 용어 제거
    8. 비영어 문자 정리
    9. Specifications 추출 (material, color, dimensions)
    10. 최종 HTML 조립 및 검증

    Args:
        product: 상품 데이터 딕셔너리.

    Returns:
        str: 클리닝된 HTML 설명 문자열.
    """
    title = product.get("detail_title") or product.get("title", "")
    brand = product.get("detail_brand") or product.get("brand", "")
    raw_html = product.get("body_html") or product.get("description", "")

    # 원본이 없으면 빈 문자열 반환
    if not raw_html or len(raw_html.strip()) < 30:
        return _build_fallback_description(product)

    # === 1단계: style/script/img/noscript 태그 제거 ===
    cleaned = re.sub(
        r"<style[^>]*>.*?</style>", "", raw_html, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(
        r"<script[^>]*>.*?</script>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(
        r"<noscript[^>]*>.*?</noscript>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(r"<img[^>]*/?>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<link[^>]*/?>", "", cleaned, flags=re.IGNORECASE)

    # === 2단계: SFX/specs 전용 섹션 제거 ===
    cleaned = re.sub(
        r'<div[^>]*class="[^"]*sfx[^"]*"[^>]*>.*?</div>',
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(
        r'<div[^>]*id="[^"]*productDescription_feature[^"]*"[^>]*>.*?</div>',
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # === 3단계: <li> 기반 Feature 추출 ===
    features = []
    li_matches = re.findall(
        r"<li[^>]*>(.*?)</li>", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    for li_text in li_matches:
        # 1. HTML 태그 제거
        text = re.sub(r"<[^>]+>", "", li_text).strip()
        text = re.sub(r"\s+", " ", text)

        # 2. 각종 괄호 제거
        text = re.sub(r"【[^】]*】\s*", "", text)
        text = re.sub(r"\[[^\]]*\]\s*", "", text)
        text = re.sub(r"『[^』]*』\s*", "", text)
        text = re.sub(r"「[^」]*」\s*", "", text)
        text = re.sub(r"〖[^〗]*〗\s*", "", text)
        text = re.sub(r"《[^》]*》\s*", "", text)
        text = text.strip(" -:")

        # 3. 특수 기호/이모지 제거 (기존 코드)
        text = re.sub(
            r"^[\u2714\u2705\u2713\u2611\u2022\u25CF\u25CB\u25AA\u25AB\u2B50\u2605\u2606\u27A4\u25B6\u25BA\u2023\u2043\u2219\u203A\u00BB\u279C\u2192\u27A1\u2794\u25C6\u25C7\u2756\u2766\u2767\u2740\u273F\u2731\u2732\u2733\u2734\u2735\u00B7]+\s*",
            "",
            text,
        )
        text = re.sub(r"^[\-–—·•►▶→➤★☆✦✧◆◇♦]+\s*", "", text)
        text = text.strip()

        # 4. 대문자 라벨 제거 (ALL CAPS + 구분자)
        label_match = re.match(
            r"^([A-Z][A-Z\s&/,]{3,40})\s*(?:[:;\-–—]|-{2,})\s*", text
        )
        if label_match:
            text = text[label_match.end() :]
            if text and text[0].islower():
                text = text[0].upper() + text[1:]

        # 5. Title Case 라벨 + -- 구분자 제거
        label_match2 = re.match(r"^([A-Z][A-Za-z\s&/,\-]{3,40}?)\s*-{2,}\s*", text)
        if label_match2:
            text = text[label_match2.end() :]
            if text and text[0].islower():
                text = text[0].upper() + text[1:]

        # 6. Feature 길이 제한 (기존 코드)
        if len(text) > 150:
            sentence_end = re.search(r"[.!?]\s", text[:200])
            if sentence_end and sentence_end.end() > 30:
                text = text[: sentence_end.end()].strip()
            else:
                words = text[:150].rsplit(" ", 1)
                text = words[0] if len(words) > 1 else text[:150]
                text = text.rstrip(".,!?;: ") + "."

        # 7. 최종 필터
        if len(text) > 15:
            features.append(text)

    # 최대 5개 feature만 유지
    features = features[:5]

    # === 4단계: 괄호 안 코드/모델번호 제거 ===
    cleaned = re.sub(r"\([^)]*[A-Z]{2,}[0-9]+[^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[[^\]]*[A-Z]{2,}[0-9]+[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"\u3010[^\u3011]*\u3011", "", cleaned)

    # === 5단계: 브랜드명/상표 문구 제거 ===
    brand_patterns = [
        r"(?i)\bby\s+" + re.escape(brand) + r"\b" if brand else None,
        (
            r"(?i)\b" + re.escape(brand) + r"\s*(?:\u00ae|\u2122|\u00a9)\s*"
            if brand
            else None
        ),
        (
            r"(?i)(?:visit|from)\s+the\s+" + re.escape(brand) + r"\s+store"
            if brand
            else None
        ),
        r"(?i)brand:\s*" + re.escape(brand) if brand else None,
    ]
    for pat in brand_patterns:
        if pat:
            cleaned = re.sub(pat, "", cleaned)

    # === 6단계: 특허/보증/법적 문구 제거 ===
    legal_patterns = [
        r"(?i)patent\s*(pending|#|number|no\.?)[\s\S]{0,50}",
        r"(?i)(?:we|our)\s+(?:offer|provide|include)\s+(?:a\s+)?(?:\d+[-\s]*(?:year|month|day))?\s*(?:warranty|guarantee|money[- ]?back)",
        r"(?i)satisfaction\s+(?:guaranteed|100%)",
        r"(?i)(?:if\s+you\s+(?:are\s+)?not\s+(?:satisfied|happy)|(?:full|100%?)\s+refund)",
        r"(?i)(?:authorized|official)\s+(?:dealer|seller|retailer)",
        r"(?i)\u00a9\s*\d{4}[^.]*\.",
    ]
    for pat in legal_patterns:
        cleaned = re.sub(pat, "", cleaned)

    # === 7단계: 아마존 전용 용어 제거 ===
    amazon_patterns = [
        r"(?i)(?:add\s+to\s+cart|buy\s+now|subscribe\s+(?:&|and)\s+save)",
        r"(?i)(?:frequently\s+bought\s+together|customers\s+(?:who|also)\s+(?:bought|viewed))",
        r"(?i)(?:sponsored|advertisement)",
        r"(?i)(?:amazon|amzn|prime)\s*(?:\'?s?\s+)?(?:choice|best\s*seller)",
        r"(?i)fulfilled\s+by\s+amazon",
        r"(?i)(?:asin|isbn)[\s:]*[A-Z0-9]{10}",
        r"(?i)click\s+here",
        r"(?i)see\s+more\s+product\s+details",
    ]
    for pat in amazon_patterns:
        cleaned = re.sub(pat, "", cleaned)

    # === 8단계: 비영어 문자 정리 ===
    cleaned = re.sub(
        r'[^\x00-\x7F<>/="\'\s.,:;!?@#$%&*()\-+\[\]{}|\\~`\u00b0\u00d7\u00b1\u00b2\u00b3\u00b5\u00bc\u00bd\u00be]',
        "",
        cleaned,
    )

    # === 추가: 인치/피트 기호 변환 (8단계 직후) ===
    # "" (이스케이프된 큰따옴표) → in.
    cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*""', r"\1 in.", cleaned)
    # " (단일 큰따옴표, 숫자 뒤) → in.
    cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*"(?!\w)', r"\1 in.", cleaned)
    # '' (이스케이프된 작은따옴표, 피트) → ft.
    cleaned = re.sub(r"(\d+(?:\.\d+)?)\s*''", r"\1 ft.", cleaned)

    # === 9단계: Specifications 추출 ===
    specs = {}
    spec_fields = {
        "Material": [
            r"(?i)material\s*:?\s*([A-Za-z][A-Za-z\s]{2,30}?)(?:\.|,|\s{2}|$)",
            r"(?i)made\s+(?:of|from|with)\s+([A-Za-z][A-Za-z\s]{2,30}?)(?:\.|,|\s{2}|$)",
        ],
        "Color": [
            r"(?i)colou?r\s*:\s*([A-Za-z][A-Za-z\s]{2,20}?)(?:\.|,|\s{2}|$)",
        ],
        "Dimensions": [
            r'(?i)(?:dimensions?|size|measures?)\s*:?\s*([\d]+[\d\s.xX\u00d7"\']+\s*(?:inches?|in|cm|mm|feet|ft)?)',
        ],
    }
    source_text = re.sub(r"<[^>]+>", " ", raw_html)
    source_text = re.sub(r"\s+", " ", source_text)

    for field, patterns in spec_fields.items():
        for pat in patterns:
            match = re.search(pat, source_text)
            if match:
                value = match.group(1).strip()
                # === 추가: 스펙 값 검증 ===
                # 일반적인 단어(of, the, a, in 등)로만 구성되면 무효
                filler_words = {
                    "of",
                    "the",
                    "a",
                    "an",
                    "in",
                    "on",
                    "for",
                    "to",
                    "and",
                    "or",
                    "most",
                    "all",
                    "some",
                    "this",
                    "that",
                    "it",
                    "is",
                }
                value_words = set(value.lower().split())
                if value_words.issubset(filler_words):
                    continue  # 무효한 값, 건너뛰기

                if 3 < len(value) < 100:
                    specs[field] = value
                break

    # 아마존 상세 정보 필드 추가 제거됨 (이슈 2)
    # === 10단계: 최종 HTML 조립 ===
    text_only = re.sub(r"<[^>]+>", " ", cleaned)
    text_only = re.sub(r"\s+", " ", text_only).strip()

    # 첫 번째 의미있는 문장을 summary로 사용
    sentences = re.split(r"(?<=[.!?])\s+", text_only)
    summary_sentences = []
    for s in sentences:
        s = s.strip()
        if 30 < len(s) < 300:
            summary_sentences.append(s)
            if len(summary_sentences) >= 2:
                break

    # === 추가: Summary 문장 정리 ===
    cleaned_summary_sentences = []

    # 제거할 접두어 패턴들
    prefix_patterns = [
        r"^(?:No\s+\w+\s*:\s*)",  # "No Fabric :" 등
        r"^(?:Note\s*:\s*)",  # "Note:" 등
        r"^(?:Please\s+note\s*:\s*)",  # "Please note:" 등
        r"^(?:Important\s*:\s*)",  # "Important:" 등
        r"^(?:Attention\s*:\s*)",  # "Attention:" 등
        r"^(?:Disclaimer\s*:\s*)",  # "Disclaimer:" 등
        r"^(?:Warning\s*:\s*)",  # "Warning:" 등
    ]

    for s in summary_sentences:
        for pat in prefix_patterns:
            s = re.sub(pat, "", s, flags=re.IGNORECASE).strip()
        # 첫 글자 대문자 보장
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        if len(s) > 30:
            cleaned_summary_sentences.append(s)

    summary = " ".join(cleaned_summary_sentences) if cleaned_summary_sentences else ""

    # === 추가: summary와 features 첫 항목 중복 제거 ===
    if summary and features:
        import difflib

        summary_clean = re.sub(r"[^a-zA-Z0-9\s]", "", summary.lower()).strip()
        first_feat_clean = re.sub(r"[^a-zA-Z0-9\s]", "", features[0].lower()).strip()

        # 유사도 80% 이상이면 첫 번째 feature 제거
        similarity = difflib.SequenceMatcher(
            None, summary_clean, first_feat_clean
        ).ratio()
        if similarity > 0.8:
            features = features[1:]

    # HTML 조립
    html_parts = []

    # Summary 섹션
    if summary:
        html_parts.append("<p>{}</p>".format(summary))

    # Features 섹션
    if features:
        html_parts.append("<h3>Features</h3>")
        html_parts.append("<ul>")
        for feat in features:
            html_parts.append("  <li>{}</li>".format(feat))
        html_parts.append("</ul>")

    # Specifications 섹션
    if specs:
        html_parts.append("<h3>Specifications</h3>")
        html_parts.append("<ul>")
        for key, value in specs.items():
            html_parts.append("  <li><strong>{}:</strong> {}</li>".format(key, value))
        html_parts.append("</ul>")

    final_html = "\n".join(html_parts)

    # === 최종 검증 ===
    if len(final_html.strip()) < 50:
        return _build_fallback_description(product)

    # 연속 빈 줄 정리
    final_html = re.sub(r"\n{3,}", "\n\n", final_html)

    logger.info(
        "[Clean 설명] %s: 생성 완료 (%d자, features=%d, specs=%d)",
        product.get("asin", ""),
        len(final_html),
        len(features),
        len(specs),
    )

    return final_html


def _build_fallback_description(product):
    # type: (dict) -> str
    """
    클린 설명 생성 실패 시 기본 설명을 생성한다.

    타이틀과 가용 정보로 최소한의 HTML을 만든다.

    Args:
        product: 상품 데이터 딕셔너리.

    Returns:
        str: 기본 HTML 설명 문자열.
    """
    title = product.get("detail_title") or product.get("title", "")
    brand = product.get("detail_brand") or product.get("brand", "")
    price = product.get("price", "")

    parts = []
    if title:
        parts.append("<p>{}</p>".format(title))
    if brand:
        parts.append("<p><strong>Brand:</strong> {}</p>".format(brand))
    if price:
        parts.append("<p><strong>Original Price:</strong> {}</p>".format(price))

    return "\n".join(parts) if parts else "<p>Product description not available.</p>"


def fetch_openrouter_models(api_key):
    # type: (str) -> list
    """
    OpenRouter에서 사용 가능한 모델 목록을 가져옵니다.

    Args:
        api_key: OpenRouter API 키 (sk-or-...)

    Returns:
        모델 목록 [{'id': 'google/gemini-2.5-flash-lite', 'name': 'Gemini 2.5 Flash Lite',
                    'pricing_prompt': '0.0000003', 'pricing_completion': '0.0000025',
                    'context_length': 1000000}, ...]
        실패 시 빈 리스트 반환
    """
    import requests

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if response.status_code != 200:
            logger.error(
                "[OpenRouter] 모델 목록 조회 실패: HTTP %d", response.status_code
            )
            return []

        data = response.json().get("data", [])

        # 텍스트 입출력이 가능한 모델만 필터링
        models = []
        for m in data:
            # output_modalities에 'text'가 포함된 모델만
            output_mods = m.get("architecture", {}).get("output_modalities", [])
            if "text" not in output_mods:
                continue

            model_id = m.get("id", "")
            model_name = m.get("name", model_id)
            pricing = m.get("pricing", {})
            prompt_price = pricing.get("prompt", "0")
            completion_price = pricing.get("completion", "0")
            context_length = m.get("context_length", 0)

            # 가격 표시 문자열 생성
            try:
                p_cost = float(prompt_price) * 1_000_000
                c_cost = float(completion_price) * 1_000_000
                if p_cost == 0 and c_cost == 0:
                    price_label = "FREE"
                else:
                    price_label = f"${p_cost:.2f}/${c_cost:.2f} per 1M"
            except (ValueError, TypeError):
                price_label = "N/A"

            models.append(
                {
                    "id": model_id,
                    "name": model_name,
                    "price_label": price_label,
                    "context_length": context_length,
                    "display": f"{model_name} ({price_label})",
                }
            )

        # 정렬: 무료 모델 먼저, 그 다음 이름순
        models.sort(key=lambda x: (0 if x["price_label"] == "FREE" else 1, x["name"]))

        logger.info("[OpenRouter] %d개 텍스트 모델 로드 완료", len(models))
        return models

    except Exception as e:
        logger.error("[OpenRouter] 모델 목록 조회 오류: %s", str(e))
        return []


def ai_polish_description(
    product: dict,
    clean_html: str,
    api_key: str,
    model: str = "google/gemini-2.5-flash-lite",
    store_name: str = "",
    seo_separator: str = "|",
) -> dict:
    """
    OpenRouter API를 사용하여 상품 설명을 더욱 다듬고 SEO를 추가한다.

    1. Body HTML: 아마존 특유의 표기 제거, 브랜드명 대체, 문법 수정
    2. SEO Description: 완전한 1-2문장으로 재생성

    Args:
        product: 상품 딕셔너리 (title, brand 등)
        clean_html: generate_clean_description()으로 생성된 HTML
        api_key: OpenRouter API 키
        model: 사용할 모델 ID (기본: google/gemini-2.5-flash)
        store_name: 스토어 이름

    Returns:
        {'body_html': '...', 'seo_title': '...', 'seo_description': '...'}
        실패 시 {'body_html': clean_html, 'seo_title': '', 'seo_description': ''}
    """
    import time

    title = product.get("detail_title") or product.get("title", "")
    brand = product.get("detail_brand") or product.get("brand", "")

    system_prompt = """You are a Shopify product description editor. Your job is to polish product descriptions for an e-commerce store.

Rules for Body HTML:
1. Replace any brand name mentions with "This" (singular product) or "These" (plural/set) or "The" (general). NEVER use "Our" - this is a curated store, not the manufacturer.
   Examples: "Cisily sponge holder is great" → "This sponge holder is great", "Vtopmart containers are durable" → "These containers are durable", "The WOWBOX organizer set" → "The organizer set"
2. Fix grammar errors, typos, and awkward phrasing
3. Remove any "--" separators and fix the resulting sentence flow
4. Keep the HTML structure exactly as provided (<p>, <h3>, <ul>, <li>, etc.)
5. Do NOT add new information, features, or claims that aren't in the original
6. Do NOT change the HTML tags or add new sections
7. Keep each <li> concise (1-2 sentences max)
8. Remove any remaining Amazon-specific language
9. Write naturally as if this is your own store's product
10. NEVER change any numbers, measurements, dimensions, weights, capacities, quantities, or specifications from the original
11. ALL performance claims, features, and functionality descriptions must come directly from the original text - only rephrase the sentence structure, never invent or exaggerate
12. If the original says "holds up to 36 cans", you must keep "36 cans" exactly - do not round, estimate, or change
13. Do NOT add superlatives or marketing claims not present in the original (e.g., do not add "best", "amazing", "revolutionary" unless the original uses them)
14. Material names, color names, and technical specifications must remain exactly as stated in the original
15. If the summary paragraph (<p>) and the first feature (<li>) have the same or very similar content, remove the first <li> to avoid repetition

Rules for SEO Title:
1. Create a concise, keyword-rich product title
2. Maximum {max_seo_title_len} characters - this is a hard limit, do NOT exceed it
3. Do NOT include the store name or separator
4. Must be a complete, meaningful phrase (no trailing prepositions, conjunctions, or cut-off words)
5. Focus on the main product name and key feature
6. Use only information from the original product title

Rules for SEO Description:
1. Write exactly 1 complete sentence summarizing the product
2. Maximum 110 characters (store name suffix will be added separately to reach 160 total)
3. Do NOT include the store name
4. The sentence MUST end with a period
5. Do NOT write a sentence you cannot finish within 110 characters
6. No "..." or truncation - the sentence must be grammatically complete
7. Focus on the main benefit/feature
8. Use only facts and features from the original description - do not invent benefits"""

    # Store Name suffix 길이 계산
    if store_name:
        suffix_len = len(f" {seo_separator} {store_name}")
    else:
        suffix_len = 0
    max_seo_title_len = 60 - suffix_len

    # system_prompt에서 {max_seo_title_len}을 실제 값으로 대체
    system_prompt = system_prompt.replace("{max_seo_title_len}", str(max_seo_title_len))

    user_prompt = f"""Product Title: {title}
Brand to remove: {brand}
Store Name (for reference only, do NOT include in outputs): {store_name}

Polish this HTML description and generate SEO title and description:

{clean_html}

Respond in this exact JSON format (no markdown, no code blocks):
{{"body_html": "<p>...polished HTML here...</p>", "seo_title": "Concise Product Title Here", "seo_description": "One or two complete sentences about the product."}}"""

    try:
        # OpenAI 호환 API 호출
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
                extra_headers={
                    "HTTP-Referer": "https://sourceflowx.app",
                    "X-Title": "SourceFlowX",
                },
            )
            result_text = response.choices[0].message.content.strip()
        except ImportError:
            # openai 패키지가 없으면 requests로 직접 호출
            import requests as req

            resp = req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://sourceflowx.app",
                    "X-Title": "SourceFlowX",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error(
                    "[AI Polish] API 오류: HTTP %d - %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return {"body_html": clean_html, "seo_title": "", "seo_description": ""}
            result_text = resp.json()["choices"][0]["message"]["content"].strip()

        # 응답 파싱
        import json

        # 마크다운 코드블록 제거
        result_text = result_text.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()

        parsed = json.loads(result_text)
        body_html = parsed.get("body_html", clean_html)
        seo_title = parsed.get("seo_title", "")
        seo_desc = parsed.get("seo_description", "")

        # body_html 검증
        if not body_html or len(body_html) < 50:
            body_html = clean_html

        # seo_title 검증: max_seo_title_len 초과 시 단어 단위 자르기
        max_title_len = 60 - (
            len(f" {seo_separator} {store_name}") if store_name else 0
        )
        if seo_title and len(seo_title) > max_title_len:
            words = seo_title[:max_title_len].rsplit(" ", 1)
            seo_title = words[0] if len(words) > 1 else seo_title[:max_title_len]
            seo_title = seo_title.rstrip(",-&|").strip()

        # seo_description 검증: 130자 초과 시 마지막 마침표까지만 사용
        if seo_desc and len(seo_desc) > 130:
            # 마지막 마침표 위치 찾기
            last_period = seo_desc[:130].rfind(".")
            if last_period > 30:
                seo_desc = seo_desc[: last_period + 1]
            else:
                # 마침표를 못 찾으면 단어 단위로 자르고 마침표 추가
                words = seo_desc[:130].rsplit(" ", 1)
                seo_desc = words[0] if len(words) > 1 else seo_desc[:130]
                seo_desc = seo_desc.rstrip(".,!?;: ") + "."

        logger.info(
            "[AI Polish] %s: 완료 (body=%d자, seo_title=%d자, seo_desc=%d자, model=%s)",
            product.get("asin", ""),
            len(body_html),
            len(seo_title),
            len(seo_desc),
            model,
        )

        time.sleep(1)  # rate limit 방지

        return {
            "body_html": body_html,
            "seo_title": seo_title,
            "seo_description": seo_desc,
        }

    except json.JSONDecodeError as e:
        logger.error("[AI Polish] JSON 파싱 오류: %s", str(e))
        return {"body_html": clean_html, "seo_title": "", "seo_description": ""}
    except Exception as e:
        logger.error("[AI Polish] 오류: %s", str(e))
        return {"body_html": clean_html, "seo_title": "", "seo_description": ""}


def generate_decluttly_description(
    product,
    api_key,
    model="google/gemini-2.5-flash-lite",
    store_name="Decluttly",
    seo_separator="|",
):
    # type: (dict, str, str, str, str) -> dict
    """
    Decluttly 스타일: AI가 Title, Subtitle, Body HTML, SEO를 한 번에 생성.

    깔끔한 홈&오가나이징 전문 스토어에 맞는 톤으로 작성.
    Body는 3~5개 benefit 섹션 + 간단 스펙 구조.

    Returns:
        dict: {'ai_title', 'ai_subtitle', 'body_html', 'seo_title', 'seo_description'}
    """
    import time as _time
    import json as _json

    title = product.get("detail_title") or product.get("title", "")
    brand = product.get("detail_brand") or product.get("brand", "")
    description = product.get("description", "")
    aplus = product.get("aplus_html", "")
    rating = product.get("detail_rating") or product.get("rating", "")
    reviews = product.get("reviews_count", "")

    # Store Name suffix 길이 계산
    suffix_len = len(" {} {}".format(seo_separator, store_name)) if store_name else 0
    max_seo_title_chars = 70 - suffix_len

    system_prompt = (
        """You are a product copywriter for Decluttly, a premium home & organization online store.
Your writing style is clean, benefit-focused, and inviting. Write as a curated store, NOT as the manufacturer.
NEVER use "Our" — use "This", "The", or "These" instead.

You will generate 5 outputs in a single JSON response.

=== 1. ai_title (Product Title) ===
- Format: "{Product Name} \u2014 {Key Benefit Phrase}"
- Example: "Bamboo Drawer Dividers \u2014 Custom-Fit Kitchen Organization"
- Max 70 characters total. Remove brand names. Capitalize major words.
- The benefit should highlight WHY a customer would want this.
- Do NOT repeat words from the product name in the benefit phrase.

=== 2. ai_subtitle (Product Subtitle) ===
- One sentence (max 80 characters) summarizing the main value proposition.
- Example: "Keep every drawer neat and clutter-free, no tools required."
- Conversational, benefit-driven tone. Must end with a period.

=== 3. body_html (Product Description) ===
- Do NOT use any emojis.
- Follow this exact structure:
  <h3>[Emotional Headline without emojis]</h3>
  <p>[2-3 sentences of problem-to-solution story]</p>
  <h3>What Makes It Great</h3>
  <ul>
    <li><strong>[Benefit 1]:</strong> [Description]</li>
    <li><strong>[Benefit 2]:</strong> [Description]</li>
    <li><strong>[Benefit 3]:</strong> [Description]</li>
    <li>...</li>
  </ul>
  <h3>Details & Specs</h3>
  <ul>
    <li><strong>Material:</strong> ...</li>
    <li><strong>Dimensions:</strong> ...</li>
    <li>...</li>
  </ul>
- Remove ALL brand names from the body. Replace with "This" / "The" / "These".
- NEVER invent specs, dimensions, or claims not in the source.
- Do NOT include full technical specification tables. The system will automatically append the detailed Amazon technical specs and A+ Content image galeries below your output.
- Keep total body between 200-500 words.

=== 4. seo_title ===
- Concise, keyword-rich title for search engines.
- Max """
        + str(max_seo_title_chars)
        + """ characters (store name added separately).
- Do NOT include the store name.

=== 5. seo_description ===
- One complete sentence, max 110 characters.
- Summarize the product for search results.
- Must end with the exact phrase: "Shop now at Decluttly." """
    )

    user_prompt = """Product Title: {title}
Brand (remove from all outputs): {brand}
Rating: {rating} ({reviews} reviews)

Original Description:
{description}

A+ Content:
{aplus_excerpt}

Respond in this exact JSON format (no markdown, no code blocks):
{{"ai_title": "...", "ai_subtitle": "...", "body_html": "<p>...</p><h3>...</h3>...", "seo_title": "...", "seo_description": "..."}}""".format(
        title=title,
        brand=brand,
        rating=rating,
        reviews=reviews,
        description=description[:2000] if description else "(no description)",
        aplus_excerpt=aplus[:1500] if aplus else "(no A+ content)",
    )

    fallback = {
        "ai_title": "",
        "ai_subtitle": "",
        "body_html": "",
        "seo_title": "",
        "seo_description": "",
    }

    try:
        result_text = ""
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=3000,
                temperature=0.5,
                extra_headers={
                    "HTTP-Referer": "https://sourceflowx.app",
                    "X-Title": "SourceFlowX",
                },
            )
            result_text = response.choices[0].message.content.strip()
        except ImportError:
            import requests as req

            resp = req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://sourceflowx.app",
                    "X-Title": "SourceFlowX",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 3000,
                    "temperature": 0.5,
                },
                timeout=60,
            )
            if resp.status_code != 200:
                logger.error(
                    "[Decluttly] API 오류: HTTP %d - %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return fallback
            result_text = resp.json()["choices"][0]["message"]["content"].strip()

        # 마크다운 코드블록 제거
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()

        parsed = _json.loads(result_text)

        ai_title = parsed.get("ai_title", "")
        ai_subtitle = parsed.get("ai_subtitle", "")
        body_html = parsed.get("body_html", "")
        seo_title = parsed.get("seo_title", "")
        seo_desc = parsed.get("seo_description", "")

        # ai_title 검증: 70자 제한
        if ai_title and len(ai_title) > 70:
            if "\u2014" in ai_title:
                parts = ai_title.split("\u2014", 1)
                short_name = parts[0].strip()
                short_benefit = parts[1].strip()
                while (
                    len(short_name) + 3 + len(short_benefit) > 70
                    and " " in short_benefit
                ):
                    short_benefit = short_benefit.rsplit(" ", 1)[0].rstrip(",-").strip()
                ai_title = "{} \u2014 {}".format(short_name, short_benefit)
            else:
                ai_title = ai_title[:70].rsplit(" ", 1)[0].strip()

        # ai_subtitle 검증: 80자 제한
        if ai_subtitle and len(ai_subtitle) > 80:
            last_period = ai_subtitle[:80].rfind(".")
            if last_period > 20:
                ai_subtitle = ai_subtitle[: last_period + 1]
            else:
                ai_subtitle = ai_subtitle[:80].rsplit(" ", 1)[0].rstrip(".,!?") + "."

        # seo_title 검증
        if seo_title and len(seo_title) > max_seo_title_chars:
            seo_title = seo_title[:max_seo_title_chars].rsplit(" ", 1)[0]
            seo_title = seo_title.rstrip(",-&|").strip()

        # seo_description 검증: 110자 제한 유지하면서 끝 구문 확보
        if seo_desc:
            shop_now = "Shop now at Decluttly."
            if not seo_desc.endswith(shop_now):
                seo_desc = seo_desc.rstrip(" ") + (" " + shop_now)

            if (
                len(seo_desc) > 130
            ):  # Shop now 추가로 110자를 약간 초과할 수 있으므로 상한선 조금 여유있게
                # 앞 부분만 자르기
                target_len = 130 - len(shop_now) - 1
                last_period = seo_desc[:target_len].rfind(".")
                if last_period > 20:
                    seo_desc = seo_desc[: last_period + 1] + " " + shop_now
                else:
                    seo_desc = (
                        seo_desc[:target_len].rsplit(" ", 1)[0].rstrip(".,!?")
                        + ". "
                        + shop_now
                    )

        # body_html 검증
        if not body_html or len(body_html) < 50:
            body_html = ""

        # Specs 추가 (A+ Content는 사용자 요청으로 제외함)
        specs_html = product.get("specs_html", "")
        if specs_html:
            body_html += "<br><h3>Full Specifications</h3><br>{}".format(specs_html)

        logger.info(
            "[Decluttly] %s: 완료 (title=%d, subtitle=%d, body=%d, seo_t=%d, seo_d=%d)",
            product.get("asin", ""),
            len(ai_title),
            len(ai_subtitle),
            len(body_html),
            len(seo_title),
            len(seo_desc),
        )

        _time.sleep(1)  # rate limit 방지

        return {
            "ai_title": ai_title,
            "ai_subtitle": ai_subtitle,
            "body_html": body_html,
            "seo_title": seo_title,
            "seo_description": seo_desc,
        }

    except _json.JSONDecodeError as e:
        logger.error(
            "[Decluttly] JSON 파싱 오류: %s | 원문: %s", str(e), result_text[:300]
        )
        return fallback
    except Exception as e:
        logger.error("[Decluttly] %s: 오류 - %s", product.get("asin", "?"), str(e))
        return fallback
