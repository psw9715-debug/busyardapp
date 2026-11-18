음주측정 PC 지킴이
==================
무엇: 측정 서버의 기록을 '보기만' 하고, 불기 단계에서 끊기면(찰칵 뒤 13초 측정완료 없음, 또는 '미측정')
      이 PC 화면이 3초쯤 빨갛게 번쩍이며 "삐뽀삐뽀" 소리 뒤 "음주측정 다시 해주세요" 라고 말한다(이름은 말하지 않는다 — 줄 선 사람들이 있어 짧고 조용하게).
      음악만 나오고 멈추는 경우(측정대기중 5초)는 직원이 앞에서 기다리고 있으니 번쩍·사이렌 없이 노란 띠와 "카드나 지문을 다시 찍어 주세요" 말만(15초마다 최대 3번).
      같은 때 B 컴퓨터가 읽을 수 있게 alerts.log 에도 적는다. 화면 경보 켜기/끄기: 저장소 alcohol-pc/onsite.txt 에 on / off (5분 안에 반영).
      측정 프로그램은 건드리지 않는다 (로그인과 조회만).

설치 (이 PC 에서 한 번만)
  방법 1) 탐색기 주소창에  \192.168.35.22\sctc17\유틸리티\음주PC에이전트  → install.bat 두 번 누르기
  방법 2) PowerShell 에 한 줄 붙여넣기 (인터넷 되는 PC):
     powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/psw9715-debug/busyardapp/main/alcohol-pc/install.ps1 | iex"
  설치 중 측정 웹 admin 비밀번호를 한 번 묻는다. 끝나면 결과 창이 한 번 뜬다
  (인터넷·NAS·측정 서버 로그인·한국어 음성이 되는지). 그 뒤로는 창 없이 돌고, 켤 때 저절로 시작한다.

그 뒤로는: 새 판을 GitHub(안 되면 NAS)에 올리면 5분 안에 스스로 받아 바꾸고 다시 뜬다. 자리에 갈 일 없음.
끄기: NAS 폴더에 STOP 이라는 빈 파일을 만들면 5분 안에 스스로 시작프로그램을 지우고 끝낸다.
기록: C:\ProgramData\AlcoholWatch\watch.log, inventory.txt (NAS 가 되면 '보고' 폴더에도 5분마다 올라온다)
