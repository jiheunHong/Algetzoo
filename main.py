# -*- coding: utf-8 -*-
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("algetzoo")

sessions: Dict[str, Dict[str, Any]] = {}


def get_default_session() -> Dict[str, Any]:
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


@mcp.tool()
def set_drinking_plan(
    goal_count: int = 3,
    condition: str = "좋음",
    eta_time: str = "23:00",
    emergency_contact: str = ""
) -> str:
    """Saves today's drinking plan including goal count, condition, estimated return time, and emergency contact."""
    session = get_default_session()
    session["plan"] = {
        "goal_count": goal_count,
        "condition": condition,
        "eta_time": eta_time,
        "emergency_contact": emergency_contact
    }

    advices = []
    if condition == "공복":
        advices.append("현재 빈속이므로 음주 전에 가벼운 식사를 하시거나 안주를 든든하게 드세요.")
    elif condition == "조금 피곤함":
        advices.append("피로가 있는 상태에서는 평소보다 취기가 급격히 올라올 수 있으니 속도를 조절하세요.")
    elif condition == "숙취가 남아있음":
        advices.append("숙취가 아직 해소되지 않았습니다! 오늘은 절대 과음하지 마시고 가급적 물을 많이 드세요.")

    advice_text = "\n💡 " + "\n💡 ".join(advices) if advices else "\n💡 오늘 컨디션은 아주 좋습니다! 즐겁고 건강하게 절주해 봅시다."

    return (
        f"📝 오늘의 음주 계획 저장 완료\n"
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
    """Checks user's physical status before starting and recommends goal adjustments."""
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
    session["plan"]["goal_count"] = adjusted_goal

    warning_text = "\n⚠️ " + "\n⚠️ ".join(warnings) if warnings else "\n✨ 현재 신체 컨디션은 양호합니다."

    return (
        f"📊 신체 컨디션 진단 결과\n"
        f"- 수면 시간: {sleep_hours}시간\n"
        f"- 식사 여부: {'식사 완료' if had_meal else '공복 (식사 필요)'}\n"
        f"- 피로 상태: {fatigue_level}\n"
        f"{warning_text}\n\n"
        f"🛡️ 안전 권장 주량: 기존 {current_goal}잔 → {adjusted_goal}잔"
    )


@mcp.tool()
def log_drink(
    drink_type: str,
    count: int = 1,
    time: Optional[str] = None
) -> str:
    """Logs a drink entry with alcohol type, count, and time."""
    session = get_default_session()

    if not time:
        time = datetime.now().strftime("%H:%M")
    if not session["session_start"]:
        session["session_start"] = time

    session["records"].append({"type": drink_type, "count": count, "time": time})
    session["total_count"] += count

    total = session["total_count"]
    goal = session["plan"]["goal_count"]

    if total > goal:
        status_msg = f"🚨 목표량({goal}잔) 초과, 현재 {total}잔입니다."
    elif total == goal:
        status_msg = f"⚠️ 목표 주량({goal}잔)에 도달했습니다."
    else:
        status_msg = f"📈 현재 {total}/{goal}잔, 남은 잔 수: {goal - total}잔"

    return f"🍻 음주 기록 완료\n- 마신 술: {drink_type} {count}잔 ({time})\n{status_msg}"


@mcp.tool()
def monitor_pace() -> str:
    """Calculates drinking pace and returns warnings if the pace is too fast."""
    session = get_default_session()

    if not session["session_start"] or not session["records"]:
        return "ℹ️ 아직 기록된 음주 로그가 없습니다."

    start_str = session["session_start"]
    now = datetime.now()

    try:
        start_time = datetime.strptime(start_str, "%H:%M")
        current_time = datetime.strptime(now.strftime("%H:%M"), "%H:%M")
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

    if pace > 3.0 or total > goal:
        risk = "DANGER"
        advice = "음주를 중단하고 휴식을 취하세요."
    elif pace > 1.5 or (goal - total <= 1):
        risk = "CAUTION"
        advice = "속도를 늦추고 물을 마시세요."
    else:
        risk = "SAFE"
        advice = "안정적인 페이스입니다."

    return (
        f"⏱️ 실시간 음주 페이스 분석\n"
        f"- 시작 시각: {start_str}\n"
        f"- 누적 음주: {total}잔\n"
        f"- 현재 속도: 시간당 {pace}잔\n"
        f"- 위험도: {risk}\n"
        f"- 안내: {advice}"
    )


@mcp.tool()
def drunk_self_check(
    feel_level: str = "멀쩡함",
    typing_text_input: str = ""
) -> str:
    """Assesses sobriety level using self-reported symptoms and key input accuracy tests."""
    session = get_default_session()
    session["safety_state"]["drunk_level"] = feel_level

    typing_score = 100
    if typing_text_input:
        broken_pattern = len(re.findall(r"[ㄱ-ㅎㅏ-ㅣ]", typing_text_input))
        if broken_pattern > 0:
            typing_score -= broken_pattern * 15
        if len(typing_text_input) < 5:
            typing_score -= 25
        typing_score = max(0, typing_score)

    if feel_level in ["어지러움", "기억이 흐림", "만취"] or typing_score < 70:
        session["safety_state"]["protection_mode"] = True
        return f"🚨 위험 수준입니다. 현재 상태: {feel_level}, 타자 점수: {typing_score}"
    elif feel_level == "약간 취함" or typing_score < 90:
        return f"⚠️ 취기 경보입니다. 현재 상태: {feel_level}, 타자 점수: {typing_score}"

    return f"👍 비교적 안정 상태입니다. 현재 상태: {feel_level}, 타자 점수: {typing_score}"


@mcp.tool()
def trigger_escape_call(
    caller_name: str = "엄마",
    scenario_type: str = "급한 일"
) -> str:
    """Generates a fake call scenario script and provides action guides to exit uncomfortable drinking spots."""
    return f"📞 {caller_name}에게서 '{scenario_type}' 상황의 가짜 전화 시나리오를 시작합니다. 자연스럽게 자리를 정리하고 나와 주세요."


@mcp.tool()
def start_safe_return(
    current_location: str,
    eta_minutes: int = 40
) -> str:
    """Initiates safe return home procedure. Prepares checklists and taxi call links."""
    session = get_default_session()
    session["safety_state"]["safe_return_started"] = True
    session["safety_state"]["location_checkpoint"] = current_location

    return (
        f"🚖 안전 귀가 절차 시작\n"
        f"- 현재 위치: {current_location}\n"
        f"- 예상 소요: {eta_minutes}분\n"
        f"- 확인 항목: 휴대폰, 지갑, 가방, 겉옷"
    )


@mcp.tool()
def generate_recap(
    next_day_condition: str = "숙취 있음",
    estimated_expense: int = 0
) -> str:
    """Generates the morning-after drinking recap summary comparing goals and actual consumption."""
    session = get_default_session()
    total = session["total_count"]
    goal = session["plan"]["goal_count"]
    achievement = "목표 절주 성공" if total <= goal else "목표량 초과"

    return (
        f"☀️ 음주 회고 리포트\n"
        f"- 총 음주량: {total}잔\n"
        f"- 목표 주량: {goal}잔\n"
        f"- 결과: {achievement}\n"
        f"- 다음 날 상태: {next_day_condition}\n"
        f"- 추정 지출: {estimated_expense:,}원"
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")