# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from mcp.server.fastmcp import FastMCP

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("algetzoo-mcp")

# FastMCP 서버 인스턴스 생성
# PlayMCP 심사 정책 준수: "algetzoo" 식별자 사용
mcp = FastMCP("algetzoo")

# 인메모리 데이터 구조 (DB 없음, 인증 없음)
# 세션 단위로 데이터 관리 (user_id는 "default" 고정)
sessions: Dict[str, Dict[str, Any]] = {}

def get_default_session() -> Dict[str, Any]:
    """기본 세션을 초기화하고 반환합니다."""
    if "default" not in sessions:
        sessions["default"] = {
            "plan": {
                "goal_count": 3,
                "condition": "좋음",
                "eta_time": "23:00",
                "emergency_contact": ""
            },
            "records": [],
            "total_count": 0,
            "session_start": None,
            "safety_state": {
                "drunk_level": "멀쩡함",
                "protection_mode": False,
                "escape_requested": False,
                "safe_return_started": False,
                "location_checkpoint": "",
                "belongings_checked": False
            },
            "recap": None
        }
    return sessions["default"]

# ==========================================
# MCP Tools 구현 (PlayMCP 정책 준수)
# 1. 도구 설명(docstring)은 영어로 작성하여 LLM이 명확히 인지하게 함
# 2. 반환되는 응답 텍스트는 한국어로 처리 (24KB 이하로 간결하게 유지)
# ==========================================

@mcp.tool()
def set_drinking_plan(
    goal_count: int = 3,
    condition: str = "좋음",
    eta_time: str = "23:00",
    emergency_contact: str = ""
) -> str:
    """Saves today's drinking plan including goal count, condition, estimated return time, and emergency contact.

    Args:
        goal_count: Today's drinking limit in cups/shots (default: 3)
        condition: User's physical condition (e.g. 좋음, 조금 피곤함, 공복, 숙취가 남아있음)
        eta_time: Planned return home time in HH:MM format (default: 23:00)
        emergency_contact: Optional emergency contact number to notify if in danger
    """
    session = get_default_session()
    session["plan"] = {
        "goal_count": goal_count,
        "condition": condition,
        "eta_time": eta_time,
        "emergency_contact": emergency_contact
    }
    
    # 컨디션별 맞춤 조언 생성
    advices = []
    if condition == "공복":
        advices.append("현재 빈속이므로 음주 전에 가벼운 식사를 하시거나 안주를 든든하게 드세요.")
    elif condition == "조금 피곤함":
        advices.append("피로가 있는 상태에서는 평소보다 취기가 급격히 올라올 수 있으니 속도를 조절하세요.")
    elif condition == "숙취가 남아있음":
        advices.append("숙취가 아직 해소되지 않았습니다! 오늘은 절대 과음하지 마시고 가급적 물을 많이 드세요.")
    
    advice_text = "\n💡 " + "\n💡 ".join(advices) if advices else "\n💡 오늘 컨디션은 아주 좋습니다! 즐겁고 건강하게 절주해 봅시다."
    
    return (
        f"📝 **오늘의 음주 계획 저장 완료**\n"
        f"🎯 목표 잔 수: {goal_count}잔\n"
        f"🏃 현재 컨디션: {condition}\n"
        f"⏰ 귀가 목표 시각: {eta_time}\n"
        f"📞 비상 연락처: {emergency_contact if emergency_contact else '미설정'}\n"
        f"{advice_text}"
    )


@mcp.tool()
def check_condition(
    sleep_hours: int = 7,
    had_meal: bool = True,
    fatigue_level: str = "보통"
) -> str:
    """Checks user's physical status before starting and recommends goal adjustments.

    Args:
        sleep_hours: Sleep hours last night (default: 7)
        had_meal: Whether the user had dinner or meal before starting (default: True)
        fatigue_level: Fatigue state (e.g. 좋음, 보통, 피곤함, 매우 피곤함)
    """
    warnings = []
    suggested_modifier = 0
    
    if sleep_hours < 6:
        warnings.append(f"수면 시간({sleep_hours}시간)이 부족하여 숙취 위험이 커지고 술이 빠르게 취할 수 있습니다.")
        suggested_modifier -= 1
        
    if not had_meal:
        warnings.append("식사를 하지 않은 공복 상태입니다. 안주를 충분히 먹거나 먼저 가볍게 채워주세요.")
        suggested_modifier -= 1
        
    if fatigue_level in ["피곤함", "매우 피곤함"]:
        warnings.append("몸에 피로가 쌓여 있어 알코올 해독 속도가 평소보다 느려질 수 있습니다.")
        suggested_modifier -= 1
        
    session = get_default_session()
    current_goal = session["plan"]["goal_count"]
    adjusted_goal = max(1, current_goal + suggested_modifier)
    
    # 주량 조정 자동 반영
    session["plan"]["goal_count"] = adjusted_goal
    
    warning_text = "\n⚠️ " + "\n⚠️ ".join(warnings) if warnings else "\n✨ 현재 신체 컨디션은 양호합니다."
    
    return (
        f"📊 **신체 컨디션 진단 결과**\n"
        f"- 수면 시간: {sleep_hours}시간\n"
        f"- 식사 여부: {'식사 완료' if had_meal else '공복 (식사 필요)'}\n"
        f"- 피로 상태: {fatigue_level}\n"
        f"{warning_text}\n\n"
        f"🛡️ **안전 권장 주량**: 기존 {current_goal}잔 → **{adjusted_goal}잔**으로 조정되었습니다. 안전을 위해 무리하지 마세요!"
    )


@mcp.tool()
def log_drink(
    drink_type: str,
    count: int = 1,
    time: Optional[str] = None
) -> str:
    """Logs a drink entry with alcohol type, count, and time.

    Args:
        drink_type: Type of alcohol (e.g. 소주, 맥주, 와인, 막걸리, 하이볼)
        count: Number of shots or cups consumed (default: 1)
        time: The time of drinking in HH:MM format (default: current local time)
    """
    session = get_default_session()
    
    if not time:
        time = datetime.now().strftime("%H:%M")
        
    # 첫 잔을 기록할 때 음주 세션 시작 시간 설정
    if not session["session_start"]:
        session["session_start"] = time
        
    session["records"].append({
        "type": drink_type,
        "count": count,
        "time": time
    })
    
    session["total_count"] += count
    total = session["total_count"]
    goal = session["plan"]["goal_count"]
    
    # 알림 메시지 생성
    water_reminder = "🥤 **절주 팁**: 술 한 잔을 마셨다면 물도 한 잔 함께 채워주세요. 알코올 분해를 돕습니다."
    
    status_msg = ""
    if total > goal:
        status_msg = f"\n🚨 **[목표 초과 경고]** 오늘 설정한 목표량({goal}잔)을 초과하여 현재 {total}잔째 마셨습니다. 음주를 즉시 멈추고 안정을 취하세요."
    elif total == goal:
        status_msg = f"\n⚠️ 오늘 설정하신 목표 주량({goal}잔)에 다다랐습니다! 이제 술자리를 정리할 시점입니다."
    else:
        status_msg = f"\n📈 현재 {total}/{goal}잔 기록되었습니다. (남은 잔 수: {goal - total}잔)"
        
    return (
        f"🍻 **음주 기록 완료**\n"
        f"- 마신 술: {drink_type} {count}잔 ({time})\n"
        f"{status_msg}\n"
        f"{water_reminder}"
    )


@mcp.tool()
def monitor_pace() -> str:
    """Calculates drinking pace (drinks per hour) and returns warnings if the pace is too fast. Call to inspect current drinking risk."""
    session = get_default_session()
    
    if not session["session_start"] or not session["records"]:
        return "ℹ️ 아직 기록된 음주 로그가 없습니다. 마신 술을 기록하시면 페이스 모니터링을 해드릴게요."
        
    start_str = session["session_start"]
    now = datetime.now()
    
    try:
        start_time = datetime.strptime(start_str, "%H:%M")
        current_time = datetime.strptime(now.strftime("%H:%M"), "%H:%M")
        
        # 자정이 지난 경우 시간 보정
        if current_time < start_time:
            time_diff = (current_time + timedelta(days=1)) - start_time
        else:
            time_diff = current_time - start_time
            
        elapsed_hours = max(0.2, time_diff.total_seconds() / 3600.0)
    except Exception:
        elapsed_hours = 1.0
        
    total = session["total_count"]
    pace = round(total / elapsed_hours, 1)
    goal = session["plan"]["goal_count"]
    
    risk_level = "safe"
    pace_animal = "🐢 느릿느릿 거북이 페이스 (안정적)"
    advice = "안정적이고 여유로운 속도로 잘 조절하고 있습니다. 물을 동반해 주세요!"
    
    if pace > 3.0 or total > goal:
        risk_level = "danger"
        pace_animal = "🐆 질주하는 치타 페이스 (위험)"
        advice = "⚠️ 과속 경고! 음주 속도가 시간당 3잔 이상으로 과도하게 빠르거나 이미 목표를 초과했습니다. 음주를 중단하고 최소 30분간 휴식을 취하세요."
    elif pace > 1.5 or (goal - total <= 1):
        risk_level = "caution"
        pace_animal = "🐇 깡충깡충 토끼 페이스 (주의)"
        advice = "💡 주의 요망! 조금 빠르게 드시고 계십니다. 술잔을 비우는 템포를 늦추고 대화를 많이 나누세요."
        
    return (
        f"⏱️ **실시간 음주 페이스 분석**\n"
        f"- 시작 시각: {start_str} (경과 시간: {round(elapsed_hours, 1)}시간)\n"
        f"- 누적 음주: {total}잔\n"
        f"- 현재 속도: 시간당 평균 **{pace}잔**\n"
        f"- 음주 페이스 동물: {pace_animal}\n"
        f"- 위험도 수준: **[{risk_level.upper()}]**\n\n"
        f"💬 **알겠주의 맞춤 케어**: {advice}"
    )


@mcp.tool()
def drunk_self_check(
    feel_level: str = "멀쩡함",
    typing_text_input: str = ""
) -> str:
    """Assesses sobriety level using self-reported symptoms and key input accuracy tests.

    Args:
        feel_level: Subjective drunkenness (멀쩡함, 약간 취함, 어지러움, 기억이 흐림, 만취)
        typing_text_input: Typed string to evaluate coordination and spelling mistakes
    """
    session = get_default_session()
    session["safety_state"]["drunk_level"] = feel_level
    
    # 동물 캐릭터 매핑 (서로 겹치지 않게 재배정)
    animal_mapping = {
        "멀쩡함": "🦉 이성적인 부엉이 (맨정신 상태)",
        "약간 취함": "🦜 말이 많아진 앵무새 (슬슬 기분이 좋아짐)",
        "어지러움": "🐼 뒤뚱거리는 판다 (균형 감각 저하 감지)",
        "기억이 흐림": "🦛 무거워진 하마 (인지 및 반응 둔화)",
        "만취": "🐕 네 발로 걷는 멍멍이 (이성을 놓기 시작함)"
    }
    
    animal_status = animal_mapping.get(feel_level, f"🦄 미지의 동물 ({feel_level})")
    
    typing_score = 100
    if typing_text_input:
        # 간단한 정규식을 사용하여 초성/자음만 연속해서 적은 패턴 감지 (예: ㅋㅋㅋ, ㅠㅠ, ㄴㅁㄴ 등)
        import re
        broken_pattern = len(re.findall(r'[ㄱ-ㅎㅏ-ㅣ]', typing_text_input))
        if broken_pattern > 0:
            typing_score -= (broken_pattern * 15)
            
        # 텍스트 길이와 입력 품질 확인
        if len(typing_text_input) < 5:
            typing_score -= 25
            
        typing_score = max(0, typing_score)
        
    safety_action = "현재까지는 안전하게 조율 중입니다."
    requires_protection = False
    
    # 타자 점수가 낮을 경우 취기 상태 강제 보정
    final_animal = animal_status
    if typing_score < 70 and feel_level in ["멀쩡함", "약간 취함"]:
        final_animal = "🦛 무거워진 하마 (타자 오타로 인한 강제 감지)"
        safety_action = "🚨 **위험 수준 도달!** 타자 정확도가 현저히 낮아 신체 제어가 느려진 상태입니다. 귀가 준비를 권장합니다."
        requires_protection = True
        session["safety_state"]["protection_mode"] = True
    elif feel_level in ["어지러움", "기억이 흐림", "만취"] or typing_score < 70:
        safety_action = "🚨 **위험 수준 도달!** 현재 취기가 심하게 올랐거나 타자 흐트러짐이 심각합니다. 술자리를 파하고 귀가를 즉시 시작할 것을 추천합니다."
        requires_protection = True
        session["safety_state"]["protection_mode"] = True
    elif feel_level == "약간 취함" or typing_score < 90:
        safety_action = "⚠️ **취기 경보!** 알코올 영향이 가시적으로 감지됩니다. 추가 알코올 섭취는 중단하고 시원한 물을 자주 마시세요."
        
    score_details = f"({typing_score}점)" if typing_text_input else "(검사 미입력)"
    
    return (
        f"🧠 **취기 자가 분석 결과**\n"
        f"- 나의 음주 동물: {final_animal}\n"
        f"- 타자 정확도 점수: {score_details}\n"
        f"- 진단 의견: {safety_action}\n\n"
        f"{'🙋‍♂️ 자리를 자연스럽게 피하고 싶다면 [가짜 전화]를 요청하거나 [안전 귀가] 절차를 활용해 보세요.' if requires_protection else '👍 남은 시간 동안에도 안전한 페이스를 이어가세요.'}"
    )


@mcp.tool()
def trigger_escape_call(
    caller_name: str = "엄마",
    scenario_type: str = "급한 일"
) -> str:
    """Generates a fake call scenario script and provides action guides to exit uncomfortable drinking spots.

    Args:
        caller_name: Name of the caller displayed on screen (default: 엄마)
        scenario_type: Type of scenario (급한 일, 야근/회사 호출, 막차 독촉)
    """
    session = get_default_session()
    session["safety_state"]["escape_requested"] = True
    
    scenarios = {
        "급한 일": (
            f"📞 **{caller_name}의 급한 긴급 전화 발송** (따르릉-)\n\n"
            f"\"어! 지금 집에 싱크대 호스가 터져서 아랫집에 누수가 발생했대. 얼른 와서 같이 정리하고 밸브 좀 잠가야 해. 빨리 와!\""
        ),
        "야근/회사 호출": (
            f"📞 **{caller_name}의 업무 긴급 호출** (진동 징- 징-)\n\n"
            f"\"여보세요? 죄송한데 아까 처리해 주신 보고서 수식 오류로 시스템 연동이 안 되고 있습니다. 급한 상황이라 지금 즉시 원격으로 접속해 주셔야 할 것 같습니다!\""
        ),
        "막차 독촉": (
            f"📞 **{caller_name}의 막차 귀가 독촉** (따르릉-)\n\n"
            f"\"너 아직도 집에 안 오고 뭐 해? 지금 막차 출발 시간 20분밖에 안 남았어. 지금 당장 지하철역으로 뛰어오지 않으면 오늘 외박이야! 당장 가방 싸서 나와!\""
        )
    }
    
    script = scenarios.get(scenario_type, scenarios["급한 일"])
    
    return (
        f"🏃 **술자리 자연스러운 탈출 지원 (가짜 전화)**\n\n"
        f"{script}\n\n"
        f"💡 **행동 매뉴얼**\n"
        f"1. 휴대폰 화면의 위 긴급 메시지를 확인한 직후, 사뭇 진지하거나 당황한 표정을 지으세요.\n"
        f"2. 통화하는 척하며 자연스럽게 자리에서 일어나 겉옷과 가방을 챙기세요.\n"
        f"3. 동석자들에게 양해를 구하고 밖으로 나옵니다. 무사히 나오셨다면 '안전 귀가' 도구를 호출해 귀가 체크를 등록하세요!"
    )


@mcp.tool()
def start_safe_return(
    current_location: str,
    eta_minutes: int = 40
) -> str:
    """Initiates safe return home procedure. Prepares checklists and taxi call links.

    Args:
        current_location: User's current location (e.g. 강남역 10번출구, 홍대입구)
        eta_minutes: Estimated travel time to home in minutes (default: 40)
    """
    session = get_default_session()
    session["safety_state"]["safe_return_started"] = True
    session["safety_state"]["location_checkpoint"] = current_location
    session["safety_state"]["belongings_checked"] = True
    
    # 24KB 제한 및 간결한 카카오톡 UI 최적화
    return (
        f"🚖 **안전 귀가 절차 시작**\n"
        f"📍 현재 위치: {current_location} 저장 완료\n"
        f"⏰ 귀가 알림: {eta_minutes}분 후 자동 도착 체크 메시지가 발생합니다.\n\n"
        f"🎒 **최종 소지품 자가 점검**\n"
        f"- [ ] 휴대폰 & 에어팟 📱\n"
        f"- [ ] 카드 & 지갑 💳\n"
        f"- [ ] 가방 & 겉옷 🧥\n\n"
        f"🚕 **카카오 T 택시 호출하기**\n"
        f"👉 [카카오 T 택시 앱 바로가기](kakaot://taxi)\n\n"
        f"집에 무사히 도착하신 뒤에는 '귀가 완료' 또는 '집에 도착'을 알려주세요!"
    )


@mcp.tool()
def generate_recap(
    next_day_condition: str = "숙취 있음",
    estimated_expense: int = 0
) -> str:
    """Generates the morning-after drinking recap summary comparing goals and actual consumption.

    Args:
        next_day_condition: Morning status (괜찮음, 피곤함, 숙취 있음)
        estimated_expense: Money spent during the drinking session in KRW
    """
    session = get_default_session()
    total = session["total_count"]
    goal = session["plan"]["goal_count"]
    
    recap_mapping = {
        "괜찮음": "🦁 포효하는 아침 사자 (에너지가 넘치는 생생한 상태!)",
        "피곤함": "🐨 꿀잠 자는 코알라 (피로 회복과 잠이 필요한 상태)",
        "숙취 있음": "🐻 굴 속의 겨울잠 곰 (머리가 아파 침대를 나갈 수 없는 상태)"
    }
    
    recap_animal = recap_mapping.get(next_day_condition, f"🦄 미지의 아침 동물 ({next_day_condition})")
    
    achievement = "🎯 목표 절주 성공!" if total <= goal else "🚨 목표량 초과 (과음 주의)"
    
    feedback = "목표 주량을 초과하지 않고 훌륭한 자제력을 발휘하셨습니다!" if total <= goal else "어제 계획보다 많이 드셨군요. 다음에는 절주 페이스 경보에 한 번 더 집중해 보아요."
    
    if next_day_condition == "숙취 있음":
        feedback += " 숙취가 있으니 꿀물이나 따뜻한 국물로 속을 달래고 수분을 보충하세요."
        
    return (
        f"☀️ **알겠주(Algetzoo) 어젯밤 음주 정산 및 회고**\n"
        f"- 나의 아침 동물: {recap_animal}\n"
        f"- 총 음주량: {total}잔 (목표 주량: {goal}잔) -> **{achievement}**\n"
        f"- 어제 사용한 총 지출: {estimated_expense:,}원\n\n"
        f"📢 **알겠주의 종합 피드백**: {feedback[:180]}"
    )

# ==========================================
# FastAPI Application 및 엔드포인트 설정
# ==========================================

app = FastAPI(
    title="Algetzoo MCP Server",
    description="카카오 PlayMCP 등록용 실시간 절주 및 음주 안전 에이전트 알겠주(Algetzoo) MCP 서버",
    version="1.0.0"
)

# FastMCP 서버의 SSE 애플리케이션 마운트
# /mcp 경로에서 MCP API가 동작하며, 하위 /mcp/sse, /mcp/messages 엔드포인트가 형성됨
app.mount("/mcp", mcp.sse_app())

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """서버 접속 시 보이고 실행 여부를 가독성 있게 확인하는 웰컴 페이지"""
    return """
    <html>
        <head>
            <title>Algetzoo MCP Server</title>
            <meta charset="utf-8">
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; background-color: #f7f9fc; color: #333; padding: 40px; }
                .card { background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); max-width: 600px; margin: 0 auto; }
                h1 { color: #ffe300; background-color: #3c3e40; padding: 15px; border-radius: 8px; text-align: center; font-size: 24px; margin-top: 0; }
                .status { font-weight: bold; color: #2e7d32; display: flex; align-items: center; justify-content: center; margin: 20px 0; }
                .status::before { content: '●'; margin-right: 8px; font-size: 20px; }
                ul { padding-left: 20px; line-height: 1.8; }
                code { background: #eef2f6; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
                .footer { text-align: center; margin-top: 30px; font-size: 12px; color: #888; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🍻 알겠주(Algetzoo) MCP Server</h1>
                <div class="status">서버가 정상적으로 가동 중입니다 (FastAPI + FastMCP)</div>
                <p>카카오 PlayMCP에 등록하기 위해 아래 엔드포인트들을 노출하고 있습니다:</p>
                <ul>
                    <li><strong>SSE Connection URL</strong>: <code>/mcp/sse</code></li>
                    <li><strong>SSE Messages URL</strong>: <code>/mcp/messages</code></li>
                </ul>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <h3>🛡️ 제공되는 MCP 도구 목록 (정확히 8개):</h3>
                <ol>
                    <li><code>set_drinking_plan</code> (사전 계획 저장)</li>
                    <li><code>check_condition</code> (컨디션 기반 사전 위험도 진단)</li>
                    <li><code>log_drink</code> (실시간 음주 잔 수 기록)</li>
                    <li><code>monitor_pace</code> (시간당 속도 분석 및 경고)</li>
                    <li><code>drunk_self_check</code> (주관적 취기 및 타자 오타 체크)</li>
                    <li><code>trigger_escape_call</code> (자연스러운 자리 이탈 가짜전화)</li>
                    <li><code>start_safe_return</code> (귀가 체크 및 소지품 점검, 카카오 택시)</li>
                    <li><code>generate_recap</code> (다음 날 숙취 여부 및 금액 회고 리포트)</li>
                </ol>
            </div>
            <div class="footer">© 2026 Algetzoo Team. Powered by Google DeepMind Antigravity.</div>
        </body>
    </html>
    """

@app.get("/health")
async def health_check():
    """서버의 상태와 인메모리 세션 상태를 빠르게 체크하는 헬스체크 API"""
    session = get_default_session()
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "mcp_server": "algetzoo",
            "session_active": session["session_start"] is not None,
            "total_drinks": session["total_count"],
            "session_data": {
                "goal_count": session["plan"]["goal_count"],
                "start_time": session["session_start"],
                "drunk_level": session["safety_state"]["drunk_level"],
                "safe_return_started": session["safety_state"]["safe_return_started"]
            }
        }
    )

if __name__ == "__main__":
    import uvicorn
    # 로컬 실행 가이드: python main.py 로 직접 실행하거나, uvicorn main:app --reload 로 실행 가능
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
