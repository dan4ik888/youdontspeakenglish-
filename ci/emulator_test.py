# -*- coding: utf-8 -*-
"""Проверка APK на настоящем Android-эмуляторе (запускается в GitHub Actions).
Ставит APK, запускает, управляет WebView через DevTools (debug-сборка),
делает скриншоты, проверяет кнопку «Назад», внешние ссылки, сохранение
прогресса после перезапуска и падения в logcat. Результаты — в test-out/."""
import json, os, re, subprocess, time, urllib.request
import websocket  # pip install websocket-client

PKG = "kz.magistratura.english"
ACT = PKG + "/.MainActivity"
APK = os.environ.get("APK", "apk/app-debug.apk")
OUT = "test-out"
os.makedirs(OUT, exist_ok=True)
R = []


def log(name, ok, detail=""):
    R.append({"name": name, "ok": bool(ok), "detail": str(detail)[:600]})
    print(("OK   " if ok else "FAIL ") + name + ("  — " + str(detail)[:300] if detail else ""), flush=True)


def adb(*a, timeout=120):
    try:
        p = subprocess.run(["adb", *a], capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"ADB-ERROR {e}"


def shot(name):
    try:
        data = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=60).stdout
        open(os.path.join(OUT, name), "wb").write(data)
    except Exception as e:
        print("screenshot error", e)


def alive():
    return bool(adb("shell", "pidof", PKG).strip())


class CDP:
    def __init__(self):
        self.ws, self.n = None, 0

    def connect(self, timeout=60):
        t0 = time.time()
        while time.time() - t0 < timeout:
            pid = adb("shell", "pidof", PKG).strip().split()
            names = re.findall(r"@(webview_devtools_remote_\d+)", adb("shell", "cat", "/proc/net/unix"))
            name = next((x for x in names if pid and x.endswith("_" + pid[0])), names[-1] if names else None)
            if name:
                adb("forward", "--remove-all")
                adb("forward", "tcp:9222", "localabstract:" + name)
                try:
                    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
                    pages = [p for p in pages if p.get("type") == "page"]
                    if pages:
                        self.ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=30)
                        return True
                except Exception:
                    pass
            time.sleep(2)
        return False

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                return m

    def ev(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        res = r.get("result", {})
        if "exceptionDetails" in res:
            return {"__error__": json.dumps(res["exceptionDetails"])[:300]}
        return res.get("result", {}).get("value")

    def tap(self, x, y):
        # настоящий (trusted) клик с жестом пользователя
        for t in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


FIND_A = r"""(()=>{const t=document.querySelector('.qtext').innerText.trim();
const q=Q.find(x=>x.q.replace(/___/g,'?').trim()===t);return q?q.a:-1})()"""

ORIGIN = None   # (left, top) WebView на экране, в физических пикселях
TAPS = {"adb": 0, "cdp": 0}


def webview_origin():
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml", timeout=60)
    xml = adb("shell", "cat", "/sdcard/ui.xml")
    m = re.search(r'class="android\.webkit\.WebView"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    return (int(m.group(1)), int(m.group(2))) if m else None


def center(sel):
    js = "(()=>{const e=document.querySelector(%s);if(!e)return null;e.scrollIntoView({block:'center'});" \
         "const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()" % json.dumps(sel)
    xy = CD.ev(js)
    time.sleep(0.4)
    return CD.ev(js) or xy


def tap(xy):
    """Настоящий тап по экрану (системный тачскрин); запасной вариант — клик через DevTools."""
    if not xy:
        return
    if ORIGIN:
        dpr = CD.ev("devicePixelRatio") or 1
        adb("shell", "input", "tap", str(int(ORIGIN[0] + xy[0] * dpr)), str(int(ORIGIN[1] + xy[1] * dpr)))
        TAPS["adb"] += 1
    else:
        CD.tap(*xy)
        TAPS["cdp"] += 1


try:
    # ---------- установка и запуск ----------
    log("Версия Android эмулятора", True, "Android " + adb("shell", "getprop", "ro.build.version.release").strip()
        + " / API " + adb("shell", "getprop", "ro.build.version.sdk").strip())
    out = adb("install", "-r", APK, timeout=240)
    log("APK устанавливается", "Success" in out, out.strip()[-200:])
    adb("logcat", "-c")
    out = adb("shell", "am", "start", "-W", "-n", ACT)
    log("Приложение запускается", "Status: ok" in out or "Complete" in out, out.strip()[-200:])
    time.sleep(8)
    log("Процесс жив после запуска", alive())
    shot("1_launch.png")

    CD = CDP()
    log("Подключение к WebView", CD.connect())
    ORIGIN = webview_origin()
    log("WebView найден на экране (для настоящих тапов)", ORIGIN is not None, ORIGIN)

    info = CD.ev("""JSON.stringify({q:typeof Q!=='undefined'?Q.length:-1,topics:TOPICS.length,
      tabs:document.querySelectorAll('#tabs .tab').length,hero:(document.querySelector('.hero h2')||{}).innerText,
      ls:(()=>{try{localStorage.setItem('_t','1');return localStorage.getItem('_t')==='1'}catch(e){return 'ERR '+e}})(),
      w:innerWidth,h:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent})""")
    d = json.loads(info) if isinstance(info, str) else {}
    log("Приложение загрузилось в WebView (201 задание, 16 тем, 6 вкладок)",
        d.get("q") == 201 and d.get("topics") == 16 and d.get("tabs") == 6, info)
    log("localStorage работает (прогресс сохраняется)", d.get("ls") is True, d.get("ls"))
    log("Нет горизонтальной прокрутки на телефоне",
        CD.ev("document.documentElement.scrollWidth<=document.documentElement.clientWidth") is True)

    # ---------- темы: настоящими тапами ----------
    xy = center("#tabs .tab[data-v='topics']")
    tap(xy); time.sleep(1.2)
    log("Тап по вкладке «Темы»", CD.ev("location.hash") == "#topics", CD.ev("location.hash"))
    shot("2_topics.png")
    xy = center(".topic[data-id='cond']")
    tap(xy); time.sleep(1.5)
    CD.ev("window.scrollTo(0,0)"); time.sleep(0.5)
    log("Тап по теме «Conditionals»: теория открылась",
        CD.ev("location.hash") == "#topics/cond" and (CD.ev("document.querySelector('.theory').innerText.length") or 0) > 300)
    shot("3_topic_theory.png")
    log("Тема: 2 видео-кнопки",
        CD.ev("document.querySelectorAll('a.act[href*=\"youtube.com/results\"]').length") == 2)

    xy = center("[data-practice]")
    tap(xy); time.sleep(1.2)
    a = CD.ev(FIND_A)
    wrong = (a + 1) % 4
    CD.ev("window.scrollTo(0,0)"); time.sleep(0.3)
    xy = center(".opt[data-k='%d']" % wrong)
    tap(xy); time.sleep(1.2)
    st = CD.ev("""JSON.stringify({show:document.querySelector('.explain').classList.contains('show'),
      correct:document.querySelectorAll('.opt.correct').length,wrong:document.querySelectorAll('.opt.wrong').length,
      verdict:document.querySelector('.explain .et').innerText,streak:document.getElementById('streakN').innerText})""")
    s = json.loads(st)
    log("Тап по неверному варианту: красный/зелёный + объяснение",
        s["show"] and s["correct"] == 1 and s["wrong"] == 1, st)
    log("Серия дней в шапке обновилась сразу", s["streak"] == "1", s["streak"])
    shot("4_practice_feedback.png")
    xy = center("[data-back]")
    tap(xy); time.sleep(1.2)
    log("Тап «‹ Conditionals» из тренировки возвращает к теме",
        bool(CD.ev("!!document.querySelector('.theory')")))

    # ---------- системная кнопка «Назад» ----------
    CD.ev("go('home')"); time.sleep(0.6)
    CD.ev("go('topics')"); time.sleep(0.6)
    CD.ev("go('topics/present')"); time.sleep(0.8)
    adb("shell", "input", "keyevent", "4"); time.sleep(1.5)
    h = CD.ev("location.hash")
    log("Кнопка «Назад» Android возвращает на прошлый экран (а не закрывает приложение)",
        h == "#topics" and alive(), f"hash={h}")

    # ---------- экзамен ----------
    CD.ev("go('home')"); time.sleep(0.4)
    CD.ev("go('exam')"); time.sleep(0.8)
    xy = center("[data-start]")
    tap(xy); time.sleep(1.5)
    CD.ev("window.scrollTo(0,0)"); time.sleep(0.3)
    shot("5_exam_question.png")
    res = CD.ev("""(async()=>{for(let k=0;k<50;k++){const t=document.querySelector('.qtext').innerText.trim();
      const q=Q.find(x=>x.q.replace(/___/g,'?').trim()===t);
      document.querySelector('.opt[data-k="'+q.a+'"]').click();
      (document.querySelector('[data-nx]')||document.querySelector('[data-submit]')).click();
      await new Promise(r=>setTimeout(r,25));}
      return document.querySelector('.result-score .big').innerText.replace(/\\s/g,'')+' | '+document.querySelector('.verdict').innerText})()""")
    log("Экзамен 50 вопросов: 50/50, «порог пройден»", str(res).startswith("50/50") and "пройден" in str(res), res)
    time.sleep(0.8)
    shot("6_exam_result.png")
    xy = center("[data-done]")
    tap(xy); time.sleep(1)
    log("«Готово» после экзамена работает", bool(CD.ev("!!document.querySelector('[data-start]')")))

    # ---------- словарь ----------
    CD.ev("go('vocab')"); time.sleep(0.8)
    xy = center("#flash")
    tap(xy); time.sleep(1)
    log("Словарь: карточка переворачивается по тапу",
        CD.ev("document.getElementById('flash').classList.contains('flipped')") is True)
    shot("7_vocab.png")

    # ---------- перезапуск: прогресс сохраняется ----------
    before = CD.ev("overall().answered")
    CD.close()
    adb("shell", "am", "force-stop", PKG); time.sleep(1.5)
    adb("shell", "am", "start", "-W", "-n", ACT); time.sleep(6)
    CD = CDP(); CD.connect()
    after = CD.ev("overall().answered")
    exams = CD.ev("S.exams.length")
    log("После закрытия и запуска приложения прогресс на месте",
        isinstance(before, int) and before > 0 and after == before and exams >= 1,
        f"ответов {before} → {after}, экзаменов {exams}")

    # ---------- тёмная тема ----------
    CD.ev("document.getElementById('themeBtn').click()"); time.sleep(0.8)
    shot("8_dark.png")
    log("Тёмная тема", CD.ev("document.documentElement.getAttribute('data-theme')") == "dark")
    CD.ev("document.getElementById('themeBtn').click()"); time.sleep(0.4)

    # ---------- видео-ссылка открывается снаружи ----------
    CD.ev("go('topics')"); time.sleep(0.5)
    CD.ev("go('topics/present')"); time.sleep(1)
    pk = adb("shell", "pm", "list", "packages").lower()
    browsers = [b for b in ["com.android.chrome", "org.chromium.webview_shell", "com.google.android.youtube",
                            "com.android.browser"] if b in pk]
    xy = center("a.act[href*='youtube.com/results']")
    tap(xy); time.sleep(5)
    href = CD.ev("location.href")
    acts = adb("shell", "dumpsys", "activity", "activities")
    resumed = (re.findall(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)[^\n]*", acts) or [""])[0].strip()
    shot("9_after_video_tap.png")
    log("Тап по видео: приложение не падает и не уходит со своего экрана",
        alive() and str(href).startswith("file:///android_asset/"), f"href={str(href)[:60]}")
    if browsers:
        log("Видео открывается во внешнем приложении", PKG not in resumed, f"{resumed} | браузеры: {browsers}")
    else:
        log("Видео: на эмуляторе нет браузера — проверили, что приложение не падает", alive(), resumed)
    adb("shell", "am", "start", "-W", "-n", ACT); time.sleep(2)

except Exception as e:
    log("Тест прерван исключением", False, repr(e))

log("Тапы выполнены", True, f"системный тачскрин: {TAPS['adb']}, через DevTools: {TAPS['cdp']}")

# ---------- logcat ----------
lc = adb("logcat", "-d", timeout=90)
open(os.path.join(OUT, "logcat.txt"), "w", encoding="utf-8").write(lc)
L = lc.splitlines()
fatal = [L[i] + " / " + " ".join(L[i+1:i+3]) for i, l in enumerate(L)
         if "FATAL EXCEPTION" in l and any(PKG in x for x in L[i+1:i+4])]
console = [l for l in lc.splitlines() if "CONSOLE" in l and ("Uncaught" in l or "TypeError" in l or "ReferenceError" in l)]
log("Нет падений (FATAL EXCEPTION) в системном логе", not fatal, fatal[:3])
log("Нет JavaScript-ошибок в консоли WebView", not console, console[:3])

json.dump(R, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
fails = [r for r in R if not r["ok"]]
print(f"\nИТОГО: {len(R) - len(fails)} OK, {len(fails)} FAIL")
