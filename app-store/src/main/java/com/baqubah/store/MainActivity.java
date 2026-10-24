
package com.baqubah.store;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.webkit.WebChromeClient;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Button;
import android.graphics.Color;
import android.view.Gravity;

public class MainActivity extends Activity {

    private WebView webView;
    private TextView status;

    private final String PAGE_URL =
        "https://emada0360-del.github.io/delivery-manager/store.html";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(Color.WHITE);

        status = new TextView(this);
        status.setText("جاري فتح توصيل السريع...");
        status.setGravity(Gravity.CENTER);
        status.setPadding(12, 16, 12, 16);
        status.setTextColor(Color.WHITE);
        status.setBackgroundColor(Color.rgb(242, 140, 40));
        layout.addView(status);

        webView = new WebView(this);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);

        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url,
                                      android.graphics.Bitmap favicon) {
                status.setVisibility(View.VISIBLE);
                status.setText("جاري التحميل...");
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                status.setVisibility(View.GONE);
            }
        });

        layout.addView(webView,
            new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        Button reload = new Button(this);
        reload.setText("إعادة تحميل");
        reload.setOnClickListener(v -> webView.reload());
        layout.addView(reload);

        setContentView(layout);
        webView.loadUrl(PAGE_URL);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
