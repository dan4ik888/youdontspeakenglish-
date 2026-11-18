package kz.magistratura.english;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {

    private static final String START_URL = "file:///android_asset/index.html";
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        applySystemBars(false);

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true); // localStorage -> прогресс сохраняется

        web.setWebViewClient(new WebViewClient() {
            // Внешние ссылки (YouTube и т.п.) открываем в браузере/приложении
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return openExternally(request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return openExternally(Uri.parse(url));
            }
        });

        // Мост для страницы: она сообщает, светлая или тёмная тема включена
        web.addJavascriptInterface(new Bridge(), "AndroidBridge");

        // Если Android выгрузил приложение (например, пока смотрели видео),
        // возвращаемся на тот же экран, а не на главную.
        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) {
            web.loadUrl(START_URL);
        }
        setContentView(web);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) {
            web.saveState(outState);
        }
    }

    private boolean openExternally(Uri url) {
        String scheme = url.getScheme();
        if ("http".equals(scheme) || "https".equals(scheme)) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, url));
            } catch (Exception ignored) {
            }
            return true;
        }
        return false;
    }

    /** Цвет строки состояния и навигации под тему приложения. */
    @SuppressWarnings("deprecation")
    private void applySystemBars(boolean dark) {
        if (Build.VERSION.SDK_INT < 21) {
            return;
        }
        Window w = getWindow();
        View decor = w.getDecorView();
        int flags = 0;
        if (dark) {
            w.setStatusBarColor(Color.parseColor("#121D30"));
            w.setNavigationBarColor(Color.parseColor("#0A1220"));
        } else if (Build.VERSION.SDK_INT >= 23) {
            // светлая полоса с тёмными значками
            w.setStatusBarColor(Color.WHITE);
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 27) {
                w.setNavigationBarColor(Color.parseColor("#EEF2F7"));
                flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
        } else {
            // Android 5–5.1: значки строки состояния только белые — берём фирменный синий
            w.setStatusBarColor(Color.parseColor("#0B6FB4"));
        }
        decor.setSystemUiVisibility(flags);
    }

    private class Bridge {
        @JavascriptInterface
        public void setDark(final boolean dark) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    applySystemBars(dark);
                }
            });
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
