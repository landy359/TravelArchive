import aiohttp
import urllib.parse
from typing import Any, Optional

# 실제 프로젝트 경로에 맞게 BaseProcessor 임포트 경로를 수정하세요.
from module.node.base.base import BaseProcessor

class APIQueryProcessor(BaseProcessor):
    """
    공공데이터포털 등의 외부 API를 비동기적으로 호출하고 데이터를 반환하는 프로세서.
    
    특징:
    - aiohttp의 자동 URL 인코딩으로 인한 공공데이터포털 serviceKey 인증 에러(401) 방지 로직 포함.
    - 입력받은 payload를 쿼리 파라미터로 변환하여 GET 요청 수행.
    """
    def __init__(self, base_url: str, service_key: str = None):
        """
        Args:
            base_url (str): 호출할 API의 엔드포인트 URL (예: http://apis.data.go.kr/...)
            service_key (str, optional): API 인증키. 공공데이터포털의 경우 반드시 Decoding 키를 입력.
        """
        super().__init__()
        self.base_url = base_url
        self.service_key = service_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def on_start(self) -> None:
        """노드 시작 시 aiohttp 세션을 초기화합니다."""
        self.session = aiohttp.ClientSession()

    async def on_stop(self) -> None:
        """노드 종료 시 aiohttp 세션을 안전하게 닫습니다."""
        if self.session:
            await self.session.close()

    async def process(self, data: Any) -> Optional[Any]:
        """
        입력된 데이터를 파라미터로 삼아 API를 호출합니다.

        Args:
            data (dict): API 호출 시 사용할 쿼리 파라미터 딕셔너리.
                         (예: {"numOfRows": "100", "pageNo": "1", ...})

        Returns:
            dict or str: API 호출 결과 (JSON 파싱 성공 시 dict, 실패 시 날것의 str 반환)
            None: 호출 실패 또는 에러 발생 시
        """
        if not self.session:
            self.signal("error", "HTTP session is not initialized.")
            return None

        try:
            # 1. 전달받은 데이터를 복사하여 원본 훼손 방지
            params = data.copy() if isinstance(data, dict) else {}
            
            # 2. 인증키가 객체 생성 시 주입되었다면 파라미터에 병합
            if self.service_key:
                params['serviceKey'] = self.service_key
            
            # 3. urllib.parse.urlencode를 사용하여 안전하게 쿼리 스트링 조합 
            # (aiohttp의 자동 인코딩 충돌 우회)
            query_string = urllib.parse.urlencode(params)
            request_url = f"{self.base_url}?{query_string}" if query_string else self.base_url
            
            # 4. API 호출 (공공데이터포털 SSL 이슈 우회를 위해 ssl=False 적용)
            async with self.session.get(request_url, ssl=False) as response:
                if response.status == 200:
                    try:
                        return await response.json()
                    except aiohttp.ContentTypeError:
                        # JSON이 아닌 XML이나 평문으로 올 경우 텍스트로 반환
                        return await response.text()
                else:
                    error_msg = await response.text()
                    self.signal("error", f"HTTP {response.status}: {error_msg}")
                    return None
                    
        except Exception as e:
            self.signal("error", f"API Connection Error: {str(e)}")
            return None