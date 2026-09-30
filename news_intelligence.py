import os
import sys
import re
import json
import html
from typing import List, Dict, Any, Optional

# Windows UTF-8 encoding safeguard
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    MODEL_NAME,
    MODEL_LIGHT_NAME,
    GEMINI_API_KEY,
    NEWS_RANKING_TOP_K,
    MAX_SNIPPET_LENGTH
)


def _sanitize_news_text(text: str, max_len: Optional[int] = None) -> str:
    """HTML 엔티티, 태그, 언론사 광고성 상투 문구를 제거하고 길이를 축소(Token Diet)"""
    if not text:
        return ""
    # 1. HTML 엔티티 복원 (&quot;, &lt;, &gt;, &middot;, &amp; 등)
    clean = html.unescape(text)
    # 2. HTML 태그 제거
    clean = re.sub(r"<[^>]+>", "", clean)
    # 3. 언론사 보도자료/광고성 상투 문구 제거
    boilerplates = [
        r"무단\s*전재\s*및\s*재배포\s*금지.*",
        r"저작권자\s*ⓒ.*",
        r"\[.*?기자\]",
        r"\(.*?기자\)",
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        r"▶.*",
        r"네이버에서.*구독.*",
        r"실시간\s*속보.*",
        r"모바일\s*한경.*",
    ]
    for bp in boilerplates:
        clean = re.sub(bp, "", clean)
    # 4. 공백 압축
    clean = re.sub(r"\s+", " ", clean).strip()
    # 5. 최대 길이 제한 (토큰 절감)
    if max_len and len(clean) > max_len:
        clean = clean[:max_len].rstrip() + "..."
    return clean



# ============================================================
# 1. 뉴스 인텔리전스 LLM 프롬프트
# ============================================================

NEWS_INTELLIGENCE_PROMPT_TEMPLATE = """# 역할
당신은 헤지펀드 투자심의위원회(Bull-Gom)의 시니어 뉴스 인텔리전스(News Intelligence) 분석가입니다.
당신의 임무는 무의미한 시황 중계성 기사(Noise)를 철저히 걸러내고, 기업의 주가와 펀더멘털(실적, 밸류에이션, 자회사 가치, 리스크)에 지대한 파급력을 가진 핵심 뉴스(Signal)만을 엄선하여 정량 평가하는 것입니다.

# 분석 대상 기업
- 대상 기업명: [{corp_name}]

# 수집된 원천 뉴스 후보군 ({article_count}건)
{articles_text}

# 평가 및 필터링 가이드라인
1. **주가 및 펀더멘털 영향도 채점 (1~10점)**:
   - **배제 대상 (1~3점 또는 제외)**: 단순 지수 시황("코스피 보합 출발", "기관/외인 순매수 상위", "오늘의 증시", "특징주", 단순 테마 중계 등)
   - **중립/통상적 뉴스 (4~6점)**: 통상적인 임원 인사, 단순 사회공헌, 정례 행사, 시장 평균 수준의 일상적 코멘트
   - **핵심 가점 대상 (7~10점 - 적극 선별)**:
     * **대규모 수주 및 공급 계약** (예: 글로벌 빅테크/엔비디아향 HBM/eSSD 공급, 대형 파운드리/배터리 계약 등)
     * **핵심 자회사 모멘텀 및 지배구조** (예: 자회사 실적 턴어라운드, IPO/미국 상장 검토, 중복상장 논란, 지분 매각/인수 등)
     * **주력 제품 및 기술 경쟁 우위** (차세대 수율/양산 일정, 판가(ASP) 급등락, 시장 점유율 독점/잠식)
     * **치명적 하방 리스크 및 지정학적 변수** (대미 반도체 수출 통제, 제재, 특허 소송, 대규모 설비투자 부담, 주가 급락 촉발 요인)

2. **유형 분류 (Category)**:
   - **Catalyst**: 기업가치 상승, 실적 턴어라운드, 목표주가 상향, 밸류에이션 리레이팅 촉매
   - **Risk**: 주가 하방 압력, 자회사 중복상장/지분 희석 우려, 수급 이탈, 실적 둔화, 규제 리스크

3. **핵심 영향 사유 (core_reason)**:
   - 기사가 해당 기업의 주가/실적/자회사에 미치는 구체적 인과관계를 1~2줄로 명확하게 요약하세요. (단순 제목 반복 금지)

# 출력 형식 (반드시 준수)
마크다운 코드블록이나 다른 설명 없이, 아래 JSON 포맷의 순수 배열(Array)만 출력하세요:
[
  {{
    "title": "수집된 기사 원문 제목",
    "impact_score": 9,
    "category": "Catalyst" 또는 "Risk",
    "core_reason": "핵심 영향 사유 1~2줄 요약 (예: 자회사 흑자 전환 및 미국 상장 추진으로 NAND 사업부 적자 해소 및 밸류에이션 재평가 기대)",
    "provider": "언론사명",
    "pubDate": "보도 일자",
    "link": "기사 링크"
  }}
]
"""


# ============================================================
# 2. 휴리스틱 Fallback 채점기
# ============================================================

def _heuristic_rank_news(corp_name: str, articles: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """LLM 호출 불가 또는 파싱 실패 시 키워드 펀더멘털 영향도 기반 휴리스틱 랭킹"""
    catalyst_keywords = [
        "수주", "공급", "계약", "흑자", "턴어라운드", "상장", "IPO", "인수", "특허", "독점",
        "양산", "사상최대", "호실적", "목표가 상향", "엔비디아", "빅테크", "HBM", "솔리다임", "자회사"
    ]
    risk_keywords = [
        "급락", "폭락", "하락", "적자", "규제", "제재", "소송", "중복상장", "물적분할",
        "희석", "피크아웃", "검찰", "해킹", "압수수색", "우려", "쇼크", "목표가 하향"
    ]
    noise_keywords = [
        "코스피", "코스닥", "보합", "이 시각", "증시", "순매수", "오전 시황", "마감 시황", "장초반"
    ]

    scored_items = []
    for a in articles:
        title = _sanitize_news_text(a.get("title", ""))
        snippet = _sanitize_news_text(a.get("snippet", ""))
        combined = f"{title} {snippet}"

        score = 5
        cat = "Catalyst"

        # 노이즈 감점
        for kw in noise_keywords:
            if kw in combined:
                score -= 2

        # 촉매 가점
        for kw in catalyst_keywords:
            if kw in combined:
                score += 2
                cat = "Catalyst"

        # 리스크 가점
        for kw in risk_keywords:
            if kw in combined:
                score += 2
                cat = "Risk"

        score = max(1, min(10, score))

        # 핵심 사유 추출
        core_reason = f"[{cat}] {corp_name} 기업 가치 및 주가 변동성 핵심 요인"
        if "솔리다임" in combined:
            core_reason = "자회사 솔리다임 상장 추진 및 실적 턴어라운드 모멘텀"
        elif "HBM" in combined:
            core_reason = "주력 HBM 공급 및 차세대 메모리 시장 점유율 경쟁력"
        elif "급락" in combined or "하락" in combined:
            core_reason = "최근 시장 변동성 및 수급/대외 리스크에 따른 주가 영향"

        scored_items.append({
            "title": title,
            "impact_score": score,
            "category": cat,
            "core_reason": core_reason,
            "provider": a.get("provider", "언론사"),
            "pubDate": a.get("pubDate", "-"),
            "link": a.get("link", "")
        })

    scored_items.sort(key=lambda x: x["impact_score"], reverse=True)
    return scored_items[:top_k]


# ============================================================
# 3. 뉴스 인텔리전스 평가 및 순위 결정 함수
# ============================================================

def evaluate_and_rank_news(
    corp_name: str,
    raw_articles: List[Dict[str, Any]],
    llm: Optional[Any] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    수집된 20~30건 이상의 원천 뉴스를 분석하여 주가/펀더멘털 파급력 Top 3~5개를 선별합니다.
    - 지수 시황 노이즈 필터링
    - 1~10점 척도 impact_score 정량 채점
    - Catalyst / Risk 분류 및 핵심 영향 사유(core_reason) 요약
    """
    if not raw_articles:
        return []

    # 중복 및 공백 제거
    valid_articles = []
    seen_titles = set()
    for a in raw_articles:
        t = (a.get("title") or "").strip()
        norm_t = re.sub(r"[^가-힣a-zA-Z0-9]", "", t)[:20]
        if norm_t and norm_t not in seen_titles:
            seen_titles.add(norm_t)
            valid_articles.append(a)

    if not valid_articles:
        return []

    # LLM이 없는 경우 경량/고속 모델 인스턴스 생성 (Model Tiering)
    if llm is None:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            light_model = MODEL_LIGHT_NAME or MODEL_NAME
            llm = ChatGoogleGenerativeAI(
                model=light_model,
                google_api_key=GEMINI_API_KEY,
                temperature=0.1
            )
        except Exception as e:
            sys.stderr.write(f"[NewsIntelligence] LLM 초기화 실패, Fallback 적용: {e}\n")
            return _heuristic_rank_news(corp_name, valid_articles, top_k)

    # 텍스트 포맷 구성 (최대 25건 전달, 불필요한 링크 제거 및 스니펫/태그 정제 토큰 다이어트)
    eval_pool = valid_articles[:25]
    articles_text_lines = []
    for idx, a in enumerate(eval_pool, 1):
        p = a.get("provider", "언론사")
        d = a.get("pubDate", "-")
        t = _sanitize_news_text(a.get("title", ""))
        s = _sanitize_news_text(a.get("snippet", ""), max_len=MAX_SNIPPET_LENGTH)
        articles_text_lines.append(f"{idx}. [{p} | {d}] {t}\n   - 요약: {s}")

    articles_text = "\n".join(articles_text_lines)

    prompt = NEWS_INTELLIGENCE_PROMPT_TEMPLATE.format(
        corp_name=corp_name,
        article_count=len(eval_pool),
        articles_text=articles_text
    )

    try:
        resp = llm.invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and "text" in p:
                    parts.append(str(p["text"]))
                elif hasattr(p, "text"):
                    parts.append(str(p.text))
                else:
                    parts.append(str(p))
            raw_text = "\n".join(parts).strip()
        else:
            raw_text = str(content).strip()

        # JSON 파싱 (마크다운 코드블록 제거)
        clean_json_str = raw_text
        if "```json" in clean_json_str:
            clean_json_str = clean_json_str.split("```json")[-1].split("```")[0].strip()
        elif "```" in clean_json_str:
            clean_json_str = clean_json_str.split("```")[-1].split("```")[0].strip()

        # 브래킷 매칭
        match = re.search(r"\[\s*\{.*\}\s*\]", clean_json_str, re.DOTALL)
        if match:
            clean_json_str = match.group(0)

        parsed_list = None
        try:
            parsed_list = json.loads(clean_json_str)
        except Exception:
            # Fallback 1: 개별 JSON 객체 분리 추출
            obj_matches = re.findall(r'\{[^{}]*"title"[^{}]*\}', clean_json_str, re.DOTALL)
            if obj_matches:
                items = []
                for obj_str in obj_matches:
                    try:
                        items.append(json.loads(obj_str))
                    except Exception:
                        pass
                if items:
                    parsed_list = items

        if not parsed_list or not isinstance(parsed_list, list):
            raise ValueError("유효한 JSON 배열 형식을 찾을 수 없습니다.")

        # 원천 기사 메타데이터(링크, 언론사, 날짜) 보강
        title_meta_map = {
            re.sub(r"[^가-힣a-zA-Z0-9]", "", a.get("title", ""))[:15]: a
            for a in eval_pool
        }

        ranked_results = []
        for item in parsed_list:
            t = item.get("title", "").strip()
            score = item.get("impact_score", 5)
            try:
                score = int(score)
            except Exception:
                score = 5
            score = max(1, min(10, score))

            cat = str(item.get("category", "Catalyst")).strip()
            if cat not in ["Catalyst", "Risk"]:
                cat = "Catalyst" if "촉매" in cat or "상승" in cat else "Risk"

            reason = str(item.get("core_reason", "")).strip()

            # 메타데이터 복원
            norm_key = re.sub(r"[^가-힣a-zA-Z0-9]", "", t)[:15]
            matched_meta = title_meta_map.get(norm_key, {})

            provider = item.get("provider") or matched_meta.get("provider", "언론사")
            pub_date = item.get("pubDate") or matched_meta.get("pubDate", "-")
            link = item.get("link") or matched_meta.get("link", "")

            ranked_results.append({
                "title": t,
                "impact_score": score,
                "category": cat,
                "core_reason": reason,
                "provider": provider,
                "pubDate": pub_date,
                "link": link
            })

        # 점수 기준 내림차순 정렬
        ranked_results.sort(key=lambda x: x["impact_score"], reverse=True)
        final_top = ranked_results[:top_k]

        if final_top:
            return final_top

    except Exception as e:
        sys.stderr.write(f"[NewsIntelligence] LLM 분석 파싱 중 예외 발생, Fallback 적용: {e}\n")

    return _heuristic_rank_news(corp_name, valid_articles, top_k)


# ============================================================
# 4. Context Data 및 최종 보고서용 포맷팅 함수
# ============================================================

def format_ranked_news_for_context(ranked_news: List[Dict[str, Any]], total_count: Optional[int] = None) -> str:
    """선별된 핵심 뉴스를 Context Data에 주입할 표준 마크다운으로 포맷팅"""
    if not ranked_news:
        return "- 최근 주요 특이 뉴스 및 파급 요인 없음"

    count_desc = f"총 {total_count}건의 기사" if total_count else "수집된 전체 기사"
    lines = [
        "### 🏆 [뉴스 인텔리전스 선별 핵심 촉매 및 리스크 (News Intelligence Top-Ranked)]",
        f"※ 실시간 수집된 {count_desc} 중 주가 및 펀더멘털 파급력(1점에서 10점 척도)이 가장 높은 핵심 뉴스 {len(ranked_news)}건을 엄밀히 선별한 결과입니다.",
        ""
    ]

    for idx, n in enumerate(ranked_news, 1):
        icon = "🔥" if n["category"] == "Catalyst" else "⚠️"
        lines.append(
            f"{idx}. {icon} **[영향도: {n['impact_score']}/10 | {n['category']} | {n['provider']}]** {n['title']}"
        )
        lines.append(f"   - **핵심 영향 요약**: {n['core_reason']}")
        if n.get("pubDate") and n["pubDate"] != "-":
            lines.append(f"   - **보도 일자**: {n['pubDate']}")
        if n.get("link"):
            lines.append(f"   - **기사 원문 링크**: [원문 바로가기]({n['link']})")
        lines.append("")

    return "\n".join(lines).strip()


def format_ranked_news_for_report(ranked_news: List[Dict[str, Any]]) -> str:
    """최종 투자심의 보고서 본문에 수록할 정돈된 뉴스 섹션 포맷팅"""
    if not ranked_news:
        return "최근 수집된 특이 뉴스 없음"

    lines = [
        "| 순위 | 영향도 | 분류 | 언론사 | 핵심 뉴스 제목 및 파급 요약 | 원문 링크 |",
        "| :---: | :---: | :---: | :---: | :--- | :---: |"
    ]

    for idx, n in enumerate(ranked_news, 1):
        cat_badge = f"🟢 {n['category']}" if n["category"] == "Catalyst" else f"🔴 {n['category']}"
        link_str = f"[바로가기]({n['link']})" if n.get("link") else "-"
        detail = f"**{n['title']}**<br><span style='color: #4b5563; font-size: 0.9em;'>👉 {n['core_reason']}</span>"
        lines.append(
            f"| {idx} | **{n['impact_score']}점** | {cat_badge} | {n['provider']} | {detail} | {link_str} |"
        )

    return "\n".join(lines)

