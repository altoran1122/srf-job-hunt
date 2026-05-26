# SRF Job Hunt

SRF 친구들과 공유하기 위한 금융권 신입/인턴 채용 큐레이션 보드입니다.

## 실행

```powershell
& "C:\Users\User\AppData\Local\Programs\Python\Python314\python.exe" server.py
```

브라우저에서 `http://127.0.0.1:8787`을 엽니다.

초기 공유 비밀번호는 `srf2026`입니다. 앱 우상단 설정에서 새 공유 비밀번호로 바꿀 수 있습니다.

## Render 배포

이 저장소에는 Render Blueprint 파일인 `render.yaml`이 포함되어 있습니다.

1. 이 폴더를 GitHub 저장소로 올립니다.
2. Render에서 `New` > `Blueprint`를 선택합니다.
3. GitHub 저장소를 연결합니다.
4. 환경변수 입력 화면에서 `SRF_PASSWORD`를 원하는 공유 비밀번호로 설정합니다.
5. 사람인 API 키는 첫 배포 때 필요하지 않습니다. 배포 후 앱 우상단 설정에서 나중에 넣으면 됩니다.
6. 배포가 끝나면 `https://...onrender.com` 주소가 생깁니다.

Render의 무료 Web Service는 파일 변경사항이 재시작/재배포 때 유지되지 않을 수 있고, 유휴 상태에서 잠들 수 있습니다. SRF 멤버들이 실제로 계속 쓰려면 유료 Web Service에 persistent disk를 붙이거나, 별도 데이터베이스로 옮기는 것을 권장합니다.

## 현재 기능

- 공유 비밀번호 로그인
- 이름별 개인 상태 저장
- 공고 카드 내부에서 바로 열리는 상세 보기
- 주요업무, 지원자격, 우대사항, 확인 항목 bullet 표시
- 회사, 직무, 출처, 상태, 보기, 마감 임박, 추천 필터
- 태그 다중 선택 필터
- 내 관심, 내 코멘트, 지원완료 보기
- 관심/지원완료 토글
- 개인별 코멘트 저장
- 원문 링크와 지원 링크 연결
- 직접 공고 추가
- KOFIA 공개 채용안내 1시간마다 자동 수집
- 공유 사람인 access-key가 설정되어 있으면 사람인 공식 Job Search API도 1시간마다 자동 수집
- 슈퍼루키 공개 채용공고도 1시간마다 자동 수집

## 사람인 API 설정

사람인 access-key는 사용자마다 따로 받는 구조가 아닙니다. 운영자가 한 번 발급받아 SRF Jobs 우상단 설정에 저장하면, 같은 서버를 쓰는 친구들이 모두 그 공유 키로 수집 결과를 봅니다.

1. 운영자가 사람인 API 사이트에서 access-key를 발급받습니다.
2. SRF Jobs 우상단 설정에서 `공유 사람인 access-key`를 저장합니다.
3. 저장 직후 한 번 수집하고, 이후 서버가 켜져 있는 동안 1시간마다 자동 수집합니다.

참고: 사람인 공식 문서에 따르면 Job Search API는 `https://oapi.saramin.co.kr/job-search` GET 엔드포인트와 `access-key`를 사용합니다.

## 데이터 원칙

이 앱은 원문 JD를 통째로 복제하지 않고, 짧은 큐레이션 요약과 원문 링크를 저장하는 방식으로 설계했습니다.
민간 채용 플랫폼은 약관과 로그인 범위를 침범하지 않는 선에서 공개 정보 또는 공식 API를 우선 사용하세요.

## 파일 구조

```text
server.py               로컬 API 서버, 로그인, 사용자 상태 저장
web/index.html          웹앱 화면
web/styles.css          UI 스타일
web/app.js              필터, 상태 저장, 수집 동작
data/jobs.json          공고 데이터
data/users.json         개인별 관심/상태/코멘트 데이터
data/config.json        공유 비밀번호 해시와 API 키
collectors/kofia.py     KOFIA 공개 채용안내 수집기
collectors/saramin.py   사람인 공식 API 수집기
collectors/superookie.py 슈퍼루키 공개 채용공고 수집기
collectors/curation.py  요약, 태그, 구분 판별 규칙
```
