import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# 0. 환경 변수 로드 (절대 경로 탐색 보장)
# ==========================================
CURRENT_DIR = Path(__file__).resolve().parent
ENV_PATH = CURRENT_DIR / ".env"
load_dotenv(ENV_PATH)

# 공통 기본 API 키
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ==========================================
# 1. 대화 생성 에이전트 세트 (Generation)
# ==========================================
GENERATION_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL_GENERATION = os.getenv("LLM_MODEL_GENERATION", "gpt-4o-mini")

# {p_topic}, {s_topic}, {s_context}, {past_chat_history}, {current_msg_content} 자리표시자 사용
GENERATION_PROMPT = (
    "너는 여행 일정을 도와주는 AI 어시스턴트야. 인사·정체성·잡담 같은 일반 질문에는 "
    "간결하고 자연스럽게 답하고, 사용자가 여행 계획을 원하면 도와줘. "
    "없는 일정·장소를 지어내지 말고, 묻지 않은 여행 얘기로 화제를 돌리지 마.\n"
    "[개인화 정보]: {p_topic}\n"
    "[현재 대화 주제]: {s_topic}\n"
    "[이전 대화 요약]: {s_context}\n"
    "[최근 대화 기록 (버퍼)]:\n{past_chat_history}\n"
    "[현재 사용자 메시지]: {current_msg_content}"
)

# ==========================================
# 라우터 전용 프롬프트 (Port3 → LLM)
# {usr_anal}, {ssn_tpc}, {ssn_pcl}, {cc} 자리표시자 사용
# 출력: LLM_Response JSON (protocol.py 스펙 그대로)
# ==========================================
ROUTER_PROMPT = (
    "너는 여행 계획 도우미 AI야.\n"
    "반드시 아래 JSON 형식으로만 출력해. 다른 말은 절대 쓰지 마.\n"
    "\n"
    "【핵심 규칙】\n"
    "▶ 먼저 사용자 메시지가 '여행 일정 생성/수정 요청'인지 판단하라.\n"
    "   - 여행 계획과 무관한 일반 질문·인사·잡담·정체성 질문(예: '너는 누구야', '안녕', '고마워')이면:\n"
    "     T_PN·T_CD·T_MP·T_MK·T_SL을 모두 생략(변경 없음)하고, CC에만 여행 도우미로서\n"
    "     자연스럽고 짧게 답하라. 저장된 일정을 굳이 설명하거나 여행 얘기로 화제를 돌리지 마라.\n"
    "     없는 일정·장소를 지어내지 마라. (예: '저는 여행 일정을 도와드리는 AI예요. 어디로 떠나고 싶으세요?')\n"
    "   - 명확한 여행 계획 요청일 때만 아래 T_PN 규칙을 적용한다.\n"
    "▶ T_PN 장소는 반드시 [방문 가능한 장소 DB] 목록에서만 선택한다. DB에 없는 장소는 절대 사용 금지.\n"
    "▶ T_PN 전체에서 같은 장소를 두 번 이상 사용 금지.\n"
    "▶ [여행 날짜] 섹션이 있으면 T_PN을 반드시 채워야 한다. T_PN 없이 CC만 쓰는 것은 오답이다.\n"
    "▶ T_PN을 먼저 확정하고, CC는 T_PN에 있는 장소 이름만 자연스럽게 언급한다.\n"
    "▶ CC에 T_PN에 없는 장소를 쓰거나, 일정을 장황하게 나열하는 것은 오답이다.\n"
    "▶ CC는 반드시 순한국어로만 작성한다. 영어 단어·문구 절대 사용 금지 (breathtaking, amazing 등 불가).\n"
    "\n"
    "출력 형식:\n"
    "{{\n"
    '  "USR_ANAL": "<그대로 유지>",\n'
    '  "SSN_TPC":  "<그대로 유지>",\n'
    '  "SSN_PCL":  "<그대로 유지>",\n'
    '  "T_CD": ["YYMMDD", ...],\n'
    '  "T_PN": [[{{"date":"YYMMDD","order":0,"place":"실제장소명"}}]],\n'
    '  "T_PN_B": [[{{"date":"YYMMDD","order":0,"place":"실제장소명"}}]],\n'
    '  "CC": "<T_PN 장소만 언급하는 2~3문장 요약. 장소 나열 금지. 자연스러운 소개. 반드시 200자 이내>",\n'
    '  "T_SL": "<B안 전체 여행 소개 2~3문장. CC와 동일한 형식·분량. 선택지 없으면 빈 문자열>",\n'
    '  "T_MP": [],\n'
    '  "T_MK": []\n'
    "}}\n"
    "\n"
    "변경 없는 필드는 생략하면 이전 값 유지.\n"
    "T_CD/T_MP/T_MK에 빈 배열([])을 넣으면 해당 위젯 초기화. T_PN은 빈 배열 금지 — 반드시 실제 장소로 채울 것.\n"
    "T_PN 외부 배열 수 = 날짜 수와 반드시 일치.\n"
    "T_SL 있을 때: T_PN=A안 일정, T_PN_B=B안 일정, CC=A안 요약, T_SL=B안 요약.\n"
    "\n"
    "[개인화 정보]: {usr_anal}\n"
    "[현재 대화 주제]: {ssn_tpc}\n"
    "[과거 대화 기록]:\n{ssn_pcl}\n"
    "[현재 사용자 메시지]: {cc}"
)

# ==========================================
# 2. 맥락 흡수 에이전트 세트 (Absorb) — 버퍼 풀 때 topic+summary 통합
# ==========================================
ABSORB_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL_ABSORB = os.getenv("LLM_MODEL_ABSORB", "gpt-4o-mini")

# {current_context}, {history_text} 자리표시자 사용
# 출력 형식: 첫 줄 "title: <15자 이내>", 둘째 줄 "context: <한 문단 100자 이내>"
ABSORB_PROMPT = (
    "너는 여행 대화 세션을 관리하는 AI야.\n"
    "기존 세션 주제와 요약, 새 대화를 통합하여 아래 형식으로만 응답해. 다른 말은 절대 쓰지 마.\n"
    "title: <갱신된 세션 주제 이름, 20자 이내>\n"
    "context: <봇이 앞으로 참고할 핵심 정보를 한 문단으로 100자 이내>\n"
    "[현재 세션 주제]: {current_title}\n"
    "[기존 대화 요약]: {current_context}\n"
    "[새로 추가된 대화 내역]:\n{history_text}"
)

# ==========================================
# 4. 개인화 정보 처리 에이전트 세트 (Personal)
# ==========================================
PERSONAL_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL_PERSONAL = os.getenv("LLM_MODEL_PERSONAL", "gpt-4o-mini")
# {prev_summary}, {delta_type}, {delta_description}, {session_topics},
# {travel_settings} 자리표시자 사용
PERSONAL_PROMPT = (
    "너는 여행 사용자 성향 분석 AI야.\n"
    "아래 정보를 종합하여 정확히 두 문단으로만 출력해. 다른 말은 쓰지 마.\n"
    "첫 번째 문단: 'AI 스타일 : '로 시작하여 AI가 이 사용자에게 어떤 말투·스타일로 응답해야 하는지 서술(200자 이내).\n"
    "두 번째 문단: '사용자 스타일 : '로 시작하여 사용자의 여행 성향·관심사·목적을 서술(300자 이내).\n"
    "[현재 분석 요약]: {prev_summary}\n"
    "[변화 유형]: {delta_type}\n"
    "[새로운 정보]: {delta_description}\n"
    "[보유 세션 주제 목록]: {session_topics}\n"
    "[AI 스타일 설정]: {style_settings}\n"
    "[여행 취향 설정]: {travel_settings}"
)

# ==========================================
# 5. 인증 설정 (JWT)
# ==========================================
ACCESS_TOKEN_SECRET_KEY = os.getenv("ACCESS_TOKEN_SECRET_KEY", "")
REFRESH_TOKEN_SECRET_KEY = os.getenv("REFRESH_TOKEN_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
REFRESH_TOKEN_EXPIRE_DAYS = os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")





#docker compose -f docker-compose-db.yml up -d && docker compose -f docker-compose-system.yml up -d --build && docker compose -f docker-compose-nginx.yml up -d
#docker rm -f travelarchive_nginx && docker rm -f travelarchive_backend && docker rm -f travelarchive_db