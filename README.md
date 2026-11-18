# English для магистратуры — Android (APK)

Android-приложение: тренажёр по английскому для подготовки к КТ в магистратуру РК.
Внутри — WebView с офлайн-приложением (теория простым языком, видео по темам,
тренировка, пробный экзамен на 50 вопросов, словарь, прогресс).

APK нельзя собрать «вручную кликом» — Android-приложения компилируются. Ниже два
простых способа получить готовый `.apk`.

## Способ 1 — GitHub (без установки программ) ⭐

1. Залей этот проект в свой репозиторий на GitHub (например, через `git push`
   или кнопкой **Add file → Upload files** на github.com).
2. Открой вкладку **Actions** в репозитории — сборка `Build APK` запустится сама
   (workflow уже лежит в `.github/workflows/build.yml`).
3. Когда сборка позеленеет (≈3–5 минут), зайди в неё и скачай артефакт
   **english-magistratura-apk** — внутри файл `app-debug.apk`.
4. Перекинь `app-debug.apk` на телефон и установи (разреши «Установку из
   неизвестных источников»).

## Способ 2 — Android Studio

1. Установи [Android Studio](https://developer.android.com/studio).
2. **Open** → выбери папку этого проекта. Дождись, пока Gradle всё подтянет.
3. Меню **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
4. Готовый файл появится в `app/build/outputs/apk/debug/app-debug.apk`
   (ссылка «locate» покажет его). Перекинь на телефон и установи.

## Способ 3 — командная строка (если есть Android SDK)

```bash
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

---

### Что внутри

| Путь | Что это |
|------|---------|
| `app/src/main/assets/index.html` | само приложение-тренажёр (офлайн) |
| `app/src/main/java/.../MainActivity.java` | обёртка WebView, открывает видео в браузере |
| `.github/workflows/build.yml` | авто-сборка APK на GitHub |

Это **debug**-сборка — ставится на любой телефон с разрешением «неизвестные
источники». Для публикации в Google Play нужна подписанная release-сборка.

Обновить контент приложения: замени `app/src/main/assets/index.html`.
