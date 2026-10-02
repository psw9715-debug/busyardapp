// 특이사항 어휘 — PC 프로그램의 words.json + word_counts.json 에서 뽑았다.
//
// 18일치 일지에 실제로 적힌 특이사항은 스무 가지가 채 안 된다. 그래서 말로
// 부르는 것 말고 버튼으로 집는 길도 함께 둔다 — 손이 비면 버튼이 더 빠르고 정확하다.
// 순서는 PC 프로그램의 버튼 배열과 같은 규칙(사용횟수 내림차순, 동점이면 기존 순서)이다.
//
// `python tools/build_daywork_words.py` 로 다시 뽑는다.
export const WORDS = [
  { text: "대차", count: 37 },
  { text: "세차", count: 11 },
  { text: "에어컨 고장", count: 3 },
  { text: "브레이크 소음", count: 3 },
  { text: "안내방송고장", count: 2 },
  { text: "출력저하", count: 2 },
  { text: "측면", count: 2 },
  { text: "후면", count: 2 },
  { text: "전광판고장", count: 2 },
  { text: "전면LED고장", count: 2 },
  { text: "요소수 보충", count: 1 },
  { text: "상황실보고", count: 1 },
  { text: "벨 저절로 켜짐", count: 1 },
  { text: "단말기 교체", count: 1 },
  { text: "부동액보충", count: 1 },
  { text: "기어고장", count: 1 },
  { text: "냉각수 누수", count: 1 },
  { text: "워셔액 보충", count: 1 },
  { text: "장애인 리프트 고장", count: 1 },
  { text: "수소부족", count: 0 },
  { text: "고장", count: 0 },
  { text: "단말기", count: 0 },
  { text: "경고등", count: 0 },
  { text: "교환", count: 0 },
  { text: "하차벨고장", count: 0 },
  { text: "차량고장", count: 0 },
  { text: "전면", count: 0 },
];
