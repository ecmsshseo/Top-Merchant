// ============================================================
// Top Merchant Dashboard - Google Apps Script
// 시트: "top merchant 리스트_확정의 사본"
// 배포: 웹 앱으로 배포 → URL을 dashboard/config.js에 붙여넣기
// ============================================================

const SHEET_NAME = "top merchant 리스트_확정의 사본";

// 컬럼 인덱스 (0-based)
const COL = {
  NO: 0,
  HISTORY: 1,
  COMPANY: 2,
  MALL_ID: 3,
  SHOP_NO: 4,
  YT_URL: 5,
  INTEGRATION: 6,
  CHANGED_AT: 7,
  BILLING: 8,
  LINKING: 9,
  TOKEN: 10,
  AFFILIATE: 11,
  CONSENT: 12,
  SERVICE_ORIGIN: 13,
  OUTCALL: 14,
  MANAGER: 15,
  GRADE: 16,
};

function doGet(e) {
  const output = ContentService.createTextOutput();
  output.setMimeType(ContentService.MimeType.JSON);

  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_NAME);

    if (!sheet) {
      output.setContent(JSON.stringify({ error: "시트를 찾을 수 없습니다: " + SHEET_NAME }));
      return output;
    }

    const lastRow = sheet.getLastRow();
    const lastCol = sheet.getLastColumn();

    // 헤더 제외, 2행부터
    const range = sheet.getRange(2, 1, lastRow - 1, Math.max(lastCol, 17));
    const values = range.getValues();

    const rows = [];
    for (const row of values) {
      const no = String(row[COL.NO]).trim();
      if (!no || no === "") continue;

      // NO가 숫자인지 확인
      const noNum = parseFloat(no);
      if (isNaN(noNum)) continue;

      rows.push({
        no: no,
        history: String(row[COL.HISTORY] || "").trim(),
        company: String(row[COL.COMPANY] || "").trim(),
        mall_id: String(row[COL.MALL_ID] || "").trim(),
        shop_no: String(row[COL.SHOP_NO] || "").trim(),
        yt_url: String(row[COL.YT_URL] || "").trim(),
        integration: String(row[COL.INTEGRATION] || "").trim(),
        changed_at: String(row[COL.CHANGED_AT] || "").trim(),
        billing: String(row[COL.BILLING] || "").trim(),
        linking: String(row[COL.LINKING] || "").trim(),
        token: String(row[COL.TOKEN] || "").trim(),
        affiliate: String(row[COL.AFFILIATE] || "").trim(),
        consent: String(row[COL.CONSENT] || "").trim(),
        service_origin: String(row[COL.SERVICE_ORIGIN] || "").trim(),
        outcall: String(row[COL.OUTCALL] || "").trim(),
        manager: String(row[COL.MANAGER] || "").trim(),
        grade: String(row[COL.GRADE] || "").trim(),
      });
    }

    const result = {
      updated_at: new Date().toISOString(),
      total: rows.length,
      rows: rows,
    };

    output.setContent(JSON.stringify(result));
  } catch (err) {
    output.setContent(JSON.stringify({ error: err.toString() }));
  }

  return output;
}

// ============================================================
// Apps Script 배포 방법:
// 1. 구글시트 열기
// 2. 확장 프로그램 > Apps Script
// 3. 이 코드 전체 붙여넣기
// 4. 저장 (Ctrl+S)
// 5. 배포 > 새 배포 클릭
// 6. 유형: 웹 앱
// 7. 다음 사용자로 실행: 나(본인)
// 8. 액세스 권한: 조직 내 모든 사용자 (회사 도메인)
// 9. 배포 클릭 → URL 복사
// 10. dashboard/config.js의 APPS_SCRIPT_URL에 붙여넣기
// ============================================================
