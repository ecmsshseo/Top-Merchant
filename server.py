from flask import Flask, jsonify, render_template, request
import threading, time, json, os, csv
from datetime import datetime, date
import config

app = Flask(__name__)

cache = {
    "rows": [], "total": 0,
    "updated_at": None, "is_sample": False, "error": None,
    "nodeny_mall_ids": set(),
}
cache_lock = threading.Lock()

# ── weekgubun CSV 로드 ──────────────────────────────────
_weekgubun = {}   # { "2026-05-29": "5월5주", ... }

def load_weekgubun():
    global _weekgubun
    path = os.path.join(os.path.dirname(__file__), "weekgubun.csv")
    if not os.path.exists(path):
        print(f"[weekgubun] 파일 없음: {path}")
        return
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                # 탭 구분이 아닐 경우 콤마로 재시도
                break
        # 컬럼 확인 후 재로드
        with open(path, "r", encoding="utf-8-sig") as f:
            first = f.read(200)
        delim = "\t" if "\t" in first else ","
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delim)
            count = 0
            for row in reader:
                # 컬럼명 strip
                row = {k.strip(): v.strip() for k, v in row.items() if k}
                d = row.get("일자", "")
                w = row.get("주차", "")
                if d and w:
                    _weekgubun[d] = w
                    count += 1
        print(f"[weekgubun] 로드 완료: {count}개")
    except Exception as e:
        print(f"[weekgubun] 로드 실패: {e}")

def date_to_week(date_str):
    """날짜 문자열 → 주차 라벨 (예: '5월5주')"""
    return _weekgubun.get(date_str, date_str)


# ── gspread 인증 ──────────────────────────────────────────
def get_gspread_client():
    import gspread
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    base = os.path.dirname(__file__)
    token_path = os.path.join(base, "token.json")
    cred_path  = os.path.join(base, "credentials.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return gspread.authorize(creds)


# ── 시트 fetch ──────────────────────────────────────────
def fetch_data():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 데이터 갱신 중...")
    try:
        gc = get_gspread_client()
        ss = gc.open_by_key(config.SPREADSHEET_ID)

        ws   = ss.worksheet(config.SHEET_NAME)
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            raise Exception("메인 시트 데이터 없음")

        header = [h.strip() for h in vals[0]]
        idx    = {n: i for i, n in enumerate(header)}

        def get(row, col):
            i = idx.get(col)
            return str(row[i]).strip() if i is not None and i < len(row) else ""

        rows = []
        for row in vals[1:]:
            no = get(row, "NO")
            if not no:
                continue
            try:
                float(no.replace(".00", ""))
            except:
                continue
            rows.append({
                "no": no, "history": get(row, "기존 top머천트 이력"),
                "company": get(row, "company_name"), "mall_id": get(row, "mall_id"),
                "shop_no": get(row, "shop_no"), "yt_url": get(row, "유튜브 채널 URL"),
                "integration": get(row, "integration_status"),
                "changed_at": get(row, "integration_status_changed_at"),
                "billing": get(row, "billing_status"), "linking": get(row, "linking_status"),
                "token": get(row, "linking_token"), "affiliate": get(row, "affiliate_status"),
                "consent": get(row, "약관 동의 여부"), "service_origin": get(row, "service_origin"),
                "outcall": get(row, "아웃콜 이력"), "manager": get(row, "Y쇼핑 담당자"),
                "grade": get(row, "TOP100/vip"),
            })

        nodeny_ids = set()
        try:
            ws2   = ss.worksheet(config.SHEET_NAME_ORIG)
            vals2 = ws2.get_all_values()
            if vals2 and len(vals2) > 1:
                h2  = [h.strip() for h in vals2[0]]
                i2  = {n: i for i, n in enumerate(h2)}
                mid = i2.get("mall_id")
                nod = i2.get("샵스_약관미동의")
                if mid is not None and nod is not None:
                    for row in vals2[1:]:
                        if len(row) > max(mid, nod):
                            if str(row[nod]).strip() == "미동의":
                                nodeny_ids.add(str(row[mid]).strip())
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 샵스_약관미동의 미동의: {len(nodeny_ids)}개")
        except Exception as e2:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  원본시트 읽기 실패: {e2}")

        with cache_lock:
            cache["rows"]            = rows
            cache["total"]           = len(rows)
            cache["updated_at"]      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cache["is_sample"]       = False
            cache["error"]           = None
            cache["nodeny_mall_ids"] = nodeny_ids

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 데이터 갱신 완료 — {len(rows)}건")
        save_snapshot()

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  데이터 갱신 실패: {e}")
        with cache_lock:
            cache["error"] = str(e)
            if not cache["rows"]:
                cache["rows"]       = _sample_rows()
                cache["total"]      = len(cache["rows"])
                cache["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cache["is_sample"]  = True


# ── 세그먼트 집계 ──────────────────────────────────────────
def compute_segments(rows, nodeny_ids=None, scope="all", exclude_nodeny=False):
    if nodeny_ids is None:
        nodeny_ids = set()

    def is_honsa(r):  return r.get("manager", "") != ""
    def is_center(r): return r.get("manager", "") == ""
    evo = lambda r: r.get("integration", "")
    aff = lambda r: r.get("affiliate", "")
    is_nodeny = lambda r: r.get("mall_id", "") in nodeny_ids

    nodeny_count = len([r for r in rows if is_nodeny(r)])

    if scope == "honsa":
        scoped = [r for r in rows if is_honsa(r)]
    elif scope == "center":
        scoped = [r for r in rows if is_center(r)]
    else:
        scoped = rows

    work = [r for r in scoped if not is_nodeny(r)] if exclude_nodeny else scoped
    honsa_work  = [r for r in work if is_honsa(r)]
    center_work = [r for r in work if is_center(r)]

    def cnt(lst, ev=None, af=None):
        r = lst
        if ev:             r = [x for x in r if evo(x)==ev]
        if af is not None: r = [x for x in r if aff(x)==af]
        return len(r)

    done = cnt(center_work, "ACTIVE", "ACTIVE")
    p2   = cnt(center_work, "ACTIVE", "ELIGIBLE")
    p3a  = cnt(center_work, "ACTIVE", "UNSPECIFIED")
    p3b  = cnt(center_work, "ACTIVE", "PAUSED")
    padd = cnt(center_work, "ACTIVE", "")
    p4   = len([r for r in center_work if evo(r)=="UNSTABLE"])
    p4_t = len([r for r in center_work if evo(r)=="UNSTABLE" and aff(r)=="ACTIVE"])

    return {
        "total":        len(work),
        "honsa_total":  len(honsa_work),
        "honsa_done":   cnt(honsa_work, "ACTIVE", "ACTIVE"),
        "honsa_need":   len([r for r in honsa_work if not (evo(r)=="ACTIVE" and aff(r)=="ACTIVE")]),
        "done":  done, "p2": p2, "p3a": p3a, "p3b": p3b, "padd": padd,
        "p4":    p4,   "p4_target": p4_t,
        "plan_a": p2 + p3a + p3b + padd,
        "nodeny_count": nodeny_count,
        "separate": 14,
        "exclude_nodeny": exclude_nodeny,
    }


# ── 스냅샷 ──────────────────────────────────────────────
def save_snapshot():
    try:
        with cache_lock:
            rows       = cache["rows"]
            nodeny_ids = cache["nodeny_mall_ids"]
        seg   = compute_segments(rows, nodeny_ids)
        today = date.today().isoformat()
        snap  = {
            "date": today, "total": seg["total"],
            "done": seg["done"], "honsa_done": seg["honsa_done"],
            "honsa_need": seg["honsa_need"], "honsa_total": seg["honsa_total"],
            "p2": seg["p2"], "p3a": seg["p3a"], "p3b": seg["p3b"],
            "padd": seg["padd"], "p4": seg["p4"], "p4_target": seg["p4_target"],
            "plan_a": seg["plan_a"], "nodeny_count": seg["nodeny_count"],
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "week_label": date_to_week(today),
        }
        d = os.path.join(os.path.dirname(__file__), "snapshots")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{today}.json"), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 스냅샷 저장 완료 → snapshots/{today}.json")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  스냅샷 저장 실패: {e}")

def load_snapshots():
    d = os.path.join(os.path.dirname(__file__), "snapshots")
    if not os.path.exists(d): return []
    result = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"): continue
        try:
            with open(os.path.join(d, f), "r", encoding="utf-8") as fp:
                snap = json.load(fp)
                # week_label 없는 구 스냅샷에 추가
                if "week_label" not in snap:
                    snap["week_label"] = date_to_week(snap.get("date",""))
                result.append(snap)
        except: continue
    return result

def auto_refresh():
    while True:
        time.sleep(config.REFRESH_INTERVAL)
        fetch_data()

def _sample_rows():
    ia = ["ACTIVE","ACTIVE","ACTIVE","ACTIVE","UNSTABLE"]
    aa = ["ACTIVE","ELIGIBLE","UNSPECIFIED","PAUSED",""]
    co = ["주식회사 한창인터내셔날","삼신","주식회사 에이치케이","(주)순녹","Globient Corp."]
    rows = []
    for i in range(2688):
        si = i % 5
        rows.append({
            "no": str(i+1), "company": co[i%len(co)],
            "mall_id": f"mall{str(i+1).zfill(4)}", "shop_no": str((i%15)+1),
            "integration": ia[si], "affiliate": aa[si],
            "consent": "동의" if si<3 else "미동의",
            "service_origin": "YTSHOPS" if si<4 else "LEGACY_YTSHOPPING",
            "grade": "VIP" if i%5==0 else "TOP100" if i%7==0 else "",
            "manager": "구본주" if i%9==0 else "백영범" if i%13==0 else "최재완" if i%17==0 else "",
            "outcall": "아웃콜 대상" if i%7==0 else "",
            "billing": "ACTIVE", "linking": "LINKED" if si<4 else "PENDING",
            "token": f"merchant_id:{5000000000+i}" if si<4 else "",
            "changed_at": "2026-05-21", "history": "top 머천트" if i%3==0 else "추가",
            "yt_url": f"UCsample{i:04d}",
        })
    return rows


# ── Flask 라우트 ──────────────────────────────────────────
@app.route("/")
def index(): return render_template("index.html")
@app.route("/overview")
def overview(): return render_template("overview.html")
@app.route("/explorer")
def explorer(): return render_template("explorer.html")
@app.route("/status-guide")
def status_guide(): return render_template("status-guide.html")
@app.route("/scenario")
def scenario(): return render_template("scenario.html")

@app.route("/api/segments")
def api_segments():
    scope          = request.args.get("scope", "all")
    exclude_nodeny = request.args.get("exclude_nodeny", "false").lower() == "true"
    with cache_lock:
        seg = compute_segments(cache["rows"], cache["nodeny_mall_ids"], scope, exclude_nodeny)
        return jsonify({
            "segments": seg, "updated_at": cache["updated_at"],
            "is_sample": cache["is_sample"], "kpi_target": config.KPI_TARGET,
        })

@app.route("/api/history")
def api_history():
    return jsonify({"snapshots": load_snapshots()})

@app.route("/api/refresh")
def api_refresh():
    threading.Thread(target=fetch_data, daemon=True).start()
    return jsonify({"message": "갱신 시작"})

@app.route("/api/filter")
def api_filter():
    conditions_raw = request.args.get("conditions", "[]")
    logic          = request.args.get("logic", "AND")
    page           = int(request.args.get("page", 1))
    page_size      = int(request.args.get("page_size", 50))
    try:    conditions = json.loads(conditions_raw)
    except: conditions = []
    with cache_lock:
        rows = cache["rows"]
    if not conditions:
        filtered = rows
    else:
        def match(row):
            results = []
            for cond in conditions:
                vals = cond.get("values", [])
                if not vals: continue
                results.append(row.get(cond.get("field",""), "") in vals)
            if not results: return True
            return all(results) if logic=="AND" else any(results)
        filtered = [r for r in rows if match(r)]
    total     = len(filtered)
    page_rows = filtered[(page-1)*page_size : page*page_size]
    return jsonify({
        "total": total, "page": page, "page_size": page_size,
        "rows": [{
            "no": r.get("no",""), "company": r.get("company",""),
            "mall_id": r.get("mall_id",""), "integration": r.get("integration",""),
            "affiliate": r.get("affiliate",""), "consent": r.get("consent",""),
            "grade": r.get("grade",""), "service_origin": r.get("service_origin",""),
        } for r in page_rows],
    })


if __name__ == "__main__":
    print("=" * 55)
    print("  Top Merchant 현황 대시보드")
    print("=" * 55)
    print(f"  접속 주소 : http://localhost:{config.PORT}")
    print(f"  갱신 주기 : {config.REFRESH_INTERVAL // 60}분")
    print("  종료      : Ctrl+C")
    print("=" * 55)
    load_weekgubun()
    fetch_data()
    threading.Thread(target=auto_refresh, daemon=True).start()
    app.run(host=config.HOST, port=config.PORT, debug=False)
