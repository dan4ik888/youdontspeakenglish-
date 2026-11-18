package kz.magistratura.english;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {

    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

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

        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
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

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
