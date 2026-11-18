# -*- coding: utf-8 -*-
"""Проверка APK на настоящем Android-эмуляторе (запускается в GitHub Actions).
Ставит APK, запускает, управляет WebView через DevTools (debug-сборка),
тапает по экрану системным тачскрином, делает скриншоты, проверяет кнопку
«Назад», внешние ссылки, сохранение прогресса после перезапуска, JS-ошибки
и падения в logcat. Результаты — в test-out/."""
import json, os, re, subprocess, time, urllib.request
import websocket  # pip install websocket-client

PKG = "kz.magistratura.english"
ACT = PKG + "/.MainActivity"
APK = os.environ.get("APK", "apk/app-debug.apk")
OUT = "test-out"
os.makedirs(OUT, exist_ok=True)
R = []
CD = None
ORIGIN = None          # (left, top) WebView на экране в физических пикселях
TAPS = {"touchscreen": 0, "devtools": 0}


def log(name, ok, detail=""):
    R.append({"name": name, "ok": bool(ok), "detail": str(detail)[:600]})
    print(("OK   " if ok else "FAIL ") + name + ("  — " + str(detail)[:300] if detail else ""), flush=True)


def adb(*a, timeout=120):
    try:
        p = subprocess.run(["adb", *a], capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"ADB-ERROR {e}"


def launch():
    """Запуск ровно как тап по иконке на рабочем столе (MAIN/LAUNCHER + флаги лаунчера):
    если приложение уже открыто — Android просто возвращает его задачу на экран."""
    return adb("shell", "am", "start", "-W", "-a", "android.intent.action.MAIN",
               "-c", "android.intent.category.LAUNCHER", "-f", "0x10200000", "-n", ACT)


def alive():
    return bool(adb("shell", "pidof", PKG).strip())


class CDP:
    def __init__(self):
        self.ws, self.n, self.events = None, 0, []

    def connect(self, timeout=90):
        t0 = time.time()
        while time.time() - t0 < timeout:
            pid = adb("shell", "pidof", PKG).strip().split()
            names = re.findall(r"@(webview_devtools_remote_\d+)", adb("shell", "cat", "/proc/net/unix"))
            name = next((x for x in names if pid and x.endswith("_" + pid[0])), None)
            if name:
                adb("forward", "--remove-all")
                adb("forward", "tcp:9222", "localabstract:" + name)
                try:
                    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
                    pages = [p for p in pages if p.get("type") == "page"]
                    if pages:
                        # без заголовка Origin — иначе новый WebView отклоняет подключение
                        self.ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"],
                                                              timeout=60, suppress_origin=True)
                        return True
                except Exception as e:
                    print("connect retry:", e, flush=True)
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
            self.events.append(m)

    def drain(self, secs=1.5):
        self.ws.settimeout(0.3)
        t0 = time.time()
        while time.time() - t0 < secs:
            try:
                self.events.append(json.loads(self.ws.recv()))
            except Exception:
                pass
        self.ws.settimeout(60)

    def ev(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        res = r.get("result", {})
        if "exceptionDetails" in res:
            return {"__error__": json.dumps(res["exceptionDetails"])[:300]}
        return res.get("result", {}).get("value")

    def click(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def settle(extra=2.0):
    """Ждём, пока страница реально нарисует кадр (эмулятор рисует медленно, без GPU)."""
    try:
        CD.ev("Promise.race([new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(1)))),"
              "new Promise(r=>setTimeout(()=>r(0),4000))])")
    except Exception:
        pass
    time.sleep(extra)


def shot(name):
    settle(2.5)
    try:
        data = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=60).stdout
        open(os.path.join(OUT, name), "wb").write(data)
    except Exception as e:
        print("screenshot error", e)


def center(sel):
    js = ("(()=>{const e=document.querySelector(%s);if(!e)return null;e.scrollIntoView({block:'center'});"
          "const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()") % json.dumps(sel)
    CD.ev(js)
    settle(0.8)
    return CD.ev(js)


def tap(xy):
    """Настоящий тап системным тачскрином; если калибровка не удалась — клик через DevTools."""
    if not xy:
        return
    if ORIGIN:
        dpr = CD.ev("devicePixelRatio") or 1
        adb("shell", "input", "tap", str(int(ORIGIN[0] + xy[0] * dpr)), str(int(ORIGIN[1] + xy[1] * dpr)))
        TAPS["touchscreen"] += 1
    else:
        CD.click(*xy)
        TAPS["devtools"] += 1


def calibrate():
    """Тапаем в известную точку экрана прозрачным слоем и смотрим, куда попало в странице."""
    CD.ev("""(()=>{const d=document.createElement('div');d.id='__cal';
      d.style.cssText='position:fixed;inset:0;z-index:2147483647;background:transparent';
      window.__cal=null;d.addEventListener('click',e=>{window.__cal=[e.clientX,e.clientY];d.remove();},{once:true});
      document.body.appendChild(d);return 1})()""")
    settle(1.0)
    size = re.findall(r"(\d+)x(\d+)", adb("shell", "wm", "size"))
    W, H = (int(size[-1][0]), int(size[-1][1])) if size else (1080, 2400)
    sx, sy = W // 2, H // 2
    adb("shell", "input", "tap", str(sx), str(sy))
    for _ in range(20):
        time.sleep(0.5)
        c = CD.ev("window.__cal")
        if c:
            dpr = CD.ev("devicePixelRatio") or 1
            return (round(sx - c[0] * dpr), round(sy - c[1] * dpr)), c
    CD.ev("(()=>{const d=document.getElementById('__cal');if(d)d.remove();return 1})()")
    return None, None


FIND_A = r"""(()=>{const t=document.querySelector('.qtext').innerText.trim();
const q=Q.find(x=>x.q.replace(/___/g,'?').trim()===t);return q?q.a:-1})()"""

try:
    # ---------- установка и запуск ----------
    log("Версия Android эмулятора", True, "Android " + adb("shell", "getprop", "ro.build.version.release").strip()
        + " / API " + adb("shell", "getprop", "ro.build.version.sdk").strip())
    out = adb("install", "-r", APK, timeout=240)
    log("APK устанавливается", "Success" in out, out.strip()[-120:])
    adb("logcat", "-c")
    t_launch = time.time()
    out = launch()
    log("Приложение запускается", "Status: ok" in out, re.sub(r"\s+", " ", out.strip())[-160:])

    CD = CDP()
    log("Подключение к WebView", CD.connect())
    # ждём, пока приложение отрисует главный экран
    ready = False
    for _ in range(60):
        if CD.ev("!!document.querySelector('.hero h2')") is True:
            ready = True
            break
        time.sleep(1)
    log("Главный экран загрузился", ready, f"через {time.time() - t_launch:.1f} c (эмулятор без GPU)")
    CD.call("Runtime.enable")   # покажет и ошибки, случившиеся до подключения
    CD.drain(2)
    log("Процесс жив", alive())
    shot("1_home.png")

    info = CD.ev("""JSON.stringify({q:Q.length,topics:TOPICS.length,tabs:document.querySelectorAll('#tabs .tab').length,
      hero:document.querySelector('.hero h2').innerText,
      ls:(()=>{try{localStorage.setItem('_t','1');return localStorage.getItem('_t')==='1'}catch(e){return 'ERR '+e}})(),
      w:innerWidth,h:innerHeight,dpr:devicePixelRatio,
      overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
      bridge:typeof AndroidBridge,
      ua:navigator.userAgent.replace(/.*Chrome\\//,'Chrome/').split(' ')[0]})""")
    d = json.loads(info) if isinstance(info, str) else {}
    log("Приложение в WebView: 201 задание, 16 тем, 6 вкладок",
        d.get("q") == 201 and d.get("topics") == 16 and d.get("tabs") == 6, info)
    log("localStorage работает (прогресс будет сохраняться)", d.get("ls") is True, d.get("ls"))
    log("Мост приложения для цвета системных полос подключён", d.get("bridge") == "object", d.get("bridge"))
    log("Нет горизонтальной прокрутки на экране телефона", d.get("overflow", 1) <= 0, f"экран {d.get('w')}x{d.get('h')} css px")

    # ---------- калибровка настоящих тапов ----------
    ORIGIN, hit = calibrate()
    log("Тап по экрану доходит до приложения (калибровка тачскрина)", ORIGIN is not None,
        f"WebView начинается с {ORIGIN} px, тап попал в {hit}")

    # ---------- темы ----------
    tap(center("#tabs .tab[data-v='topics']")); settle(1.5)
    log("Тап по вкладке «Темы»", CD.ev("location.hash") == "#topics", CD.ev("location.hash"))
    shot("2_topics.png")
    tap(center(".topic[data-id='cond']")); settle(1.5)
    CD.ev("window.scrollTo(0,0)")
    log("Тап по теме: теория открылась",
        CD.ev("location.hash") == "#topics/cond" and (CD.ev("document.querySelector('.theory').innerText.length") or 0) > 300)
    shot("3_topic_theory.png")
    log("У темы 2 кнопки видео",
        CD.ev("document.querySelectorAll('a.act[href*=\"youtube.com/results\"]').length") == 2)

    tap(center("[data-practice]")); settle(1.5)
    a = CD.ev(FIND_A)
    wrong = (a + 1) % 4 if isinstance(a, int) and a >= 0 else 0
    CD.ev("window.scrollTo(0,0)")
    tap(center(".opt[data-k='%d']" % wrong)); settle(1.5)
    st = CD.ev("""JSON.stringify({show:document.querySelector('.explain').classList.contains('show'),
      correct:document.querySelectorAll('.opt.correct').length,wrong:document.querySelectorAll('.opt.wrong').length,
      streak:document.getElementById('streakN').innerText})""")
    s = json.loads(st) if isinstance(st, str) else {}
    log("Тап по неверному варианту: красный + зелёный + объяснение",
        s.get("show") and s.get("correct") == 1 and s.get("wrong") == 1, st)
    log("Серия дней в шапке обновилась сразу", s.get("streak") == "1", s.get("streak"))
    CD.ev("window.scrollTo(0,0)")
    shot("4_practice_feedback.png")
    tap(center("[data-back]")); settle(1.5)
    log("Тап «‹ назад» из тренировки возвращает к теме", CD.ev("!!document.querySelector('.theory')") is True)

    # ---------- системная кнопка «Назад» ----------
    CD.ev("go('home')"); settle(0.8)
    CD.ev("go('topics')"); settle(0.8)
    CD.ev("go('topics/present')"); settle(1.0)
    adb("shell", "input", "keyevent", "4"); settle(1.5)
    h = CD.ev("location.hash")
    log("Кнопка «Назад» Android: прошлый экран, а не выход", h == "#topics" and alive(), f"hash={h}")

    # ---------- экзамен ----------
    CD.ev("go('home')"); settle(0.5)
    CD.ev("go('exam')"); settle(1.0)
    tap(center("[data-start]")); settle(1.5)
    log("Тап «Начать экзамен»", CD.ev("!!document.getElementById('tmr')") is True)
    CD.ev("window.scrollTo(0,0)")
    shot("5_exam_question.png")
    res = CD.ev("""(async()=>{for(let k=0;k<50;k++){const t=document.querySelector('.qtext').innerText.trim();
      const q=Q.find(x=>x.q.replace(/___/g,'?').trim()===t);
      document.querySelector('.opt[data-k="'+q.a+'"]').click();
      (document.querySelector('[data-nx]')||document.querySelector('[data-submit]')).click();
      await new Promise(r=>setTimeout(r,20));}
      return document.querySelector('.result-score .big').innerText.replace(/\\s/g,'')+' | '+document.querySelector('.verdict').innerText})()""")
    log("Экзамен 50 вопросов: 50/50 и «порог пройден»", str(res).startswith("50/50") and "пройден" in str(res), res)
    shot("6_exam_result.png")
    tap(center("[data-done]")); settle(1.2)
    log("Тап «Готово» после экзамена", CD.ev("!!document.querySelector('[data-start]')") is True)

    # ---------- словарь ----------
    CD.ev("go('vocab')"); settle(1.0)
    tap(center("#flash")); settle(1.5)
    log("Словарь: карточка переворачивается по тапу",
        CD.ev("document.getElementById('flash').classList.contains('flipped')") is True)
    shot("7_vocab.png")

    # ---------- перезапуск: прогресс сохраняется ----------
    before = CD.ev("overall().answered")
    CD.close()
    adb("shell", "am", "force-stop", PKG); time.sleep(1.5)
    launch()
    CD = CDP(); CD.connect()
    for _ in range(60):
        if CD.ev("!!document.querySelector('.hero h2')") is True:
            break
        time.sleep(1)
    after = CD.ev("overall().answered")
    exams = CD.ev("S.exams.length")
    log("После закрытия и запуска приложения прогресс на месте",
        isinstance(before, int) and before > 0 and after == before and (exams or 0) >= 1,
        f"ответов {before} → {after}, экзаменов {exams}")
    CD.call("Runtime.enable"); CD.drain(1.5)

    # ---------- тёмная тема ----------
    tap(center("#themeBtn")); settle(1.2)
    log("Тёмная тема по тапу", CD.ev("document.documentElement.getAttribute('data-theme')") == "dark")
    CD.ev("window.scrollTo(0,0)")
    shot("8_dark.png")
    CD.ev("document.getElementById('themeBtn').click()"); settle(0.5)

    # ---------- Android выгрузил приложение из памяти -> возврат на тот же экран ----------
    CD.ev("go('topics')"); settle(0.6)
    CD.ev("go('topics/cond')"); settle(1.0)
    adb("shell", "input", "keyevent", "3"); time.sleep(2.5)          # на домашний экран
    adb("shell", "am", "kill", PKG); time.sleep(2.5)                   # как это делает система в фоне
    was_killed = not alive()
    CD.close()
    launch()            # как тап по иконке
    CD = CDP(); CD.connect()
    for _ in range(60):
        if CD.ev("!!(document.querySelector('.theory')||document.querySelector('.hero'))") is True:
            break
        time.sleep(1)
    h3 = CD.ev("location.hash")
    log("После выгрузки из памяти приложение открывается на том же экране",
        was_killed and h3 == "#topics/cond" and CD.ev("!!document.querySelector('.theory')") is True,
        f"процесс был выгружен: {was_killed}, экран: {h3}")
    CD.ev("window.scrollTo(0,0)")
    shot("9_restored_after_kill.png")

    # ---------- видео открывается снаружи ----------
    CD.ev("go('topics')"); settle(0.6)
    CD.ev("go('topics/present')"); settle(1.0)
    pk = adb("shell", "pm", "list", "packages").lower()
    handlers = [b for b in ["com.android.chrome", "com.google.android.youtube", "com.android.browser"] if b in pk]
    tap(center("a.act[href*='youtube.com/results']")); time.sleep(6)
    href = CD.ev("location.href")
    acts = adb("shell", "dumpsys", "activity", "activities")
    resumed = (re.findall(r"(?:topResumedActivity|mResumedActivity)[^\n]*", acts) or [""])[0].strip()
    shot("10_after_video_tap.png")
    log("Тап по видео: приложение не открывает YouTube внутри себя",
        str(href).startswith("file:///android_asset/"), f"href={str(href)[:50]}")
    log("Видео открылось во внешнем приложении (YouTube/браузер)",
        bool(handlers) and PKG not in resumed, f"{resumed[:150]} | есть: {handlers}")
    in_bg_killed = not alive()
    CD.close()
    launch()
    CD = CDP(); CD.connect()
    for _ in range(60):
        if CD.ev("!!(document.querySelector('.theory')||document.querySelector('.hero'))") is True:
            break
        time.sleep(1)
    h4 = CD.ev("location.hash")
    log("Вернулся из видео — та же тема на экране",
        h4 == "#topics/present" and CD.ev("!!document.querySelector('.theory')") is True,
        f"экран: {h4}, Android выгружал приложение: {in_bg_killed}")
    shot("11_back_from_video.png")

except Exception as e:
    import traceback
    log("Тест прерван исключением", False, traceback.format_exc()[-500:])

log("Тапы выполнены", True, f"системный тачскрин: {TAPS['touchscreen']}, через DevTools: {TAPS['devtools']}")

# ---------- JS-ошибки из консоли WebView ----------
try:
    if CD:
        CD.drain(1.0)
        evs = CD.events
        exc = [e["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:150]
               for e in evs if e.get("method") == "Runtime.exceptionThrown"]
        cerr = [" ".join(str(a.get("value", a.get("description", ""))) for a in e["params"].get("args", []))[:150]
                for e in evs if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") == "error"]
        log("Нет JavaScript-ошибок в консоли WebView", not exc and not cerr, (exc + cerr)[:3])
except Exception as e:
    log("Проверка консоли WebView", False, repr(e))

# ---------- logcat ----------
lc = adb("logcat", "-d", timeout=90)
open(os.path.join(OUT, "logcat.txt"), "w", encoding="utf-8").write(lc)
L = lc.splitlines()
fatal = [L[i] + " / " + " ".join(L[i + 1:i + 3]) for i, l in enumerate(L)
         if "FATAL EXCEPTION" in l and any(PKG in x for x in L[i + 1:i + 4])]
anr = [l for l in L if "ANR in " + PKG in l]
log("Нет падений приложения (FATAL EXCEPTION)", not fatal, fatal[:2])
log("Нет зависаний «Приложение не отвечает» (ANR)", not anr, anr[:2])

json.dump(R, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
fails = [r for r in R if not r["ok"]]
print(f"\nИТОГО: {len(R) - len(fails)} OK, {len(fails)} FAIL")
