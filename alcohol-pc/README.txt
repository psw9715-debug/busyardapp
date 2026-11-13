음주측정 PC 지킴이
==================
무엇: 측정 서버의 기록을 '보기만' 하고, 불기 단계에서 끊기면(찰칵 뒤 13초 측정완료 없음, 또는 '미측정')
      이 PC 화면 한가운데에 큰 빨간 창 + 경보음 + (한국어 음성이 있으면) 말로 "다시 측정해 주세요" 를 띄운다.
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
